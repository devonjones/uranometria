"""Assemble and persist the annotation model.

The model is the contract between the solve/cross-match pipeline and the
renderers (annotated PNG, interactive HTML, sky-map lightbox overlay): plain
JSON, one file per image, with everything positioned in both sky and pixel
coordinates.

Pixel convention (`solved.pixel_frame`): x grows rightward, 0-indexed.
"fits0" (FITS sources): y follows FITS row order — draw directly onto the
array as loaded by astropy. "raster0" (JPEG/PNG sources): y is top-down in
the raster's own frame — draw directly onto the raster. The conversion from
ASTAP's solver frame (always FITS row order; it converts rasters internally)
happens at model build time, including the CD matrix's y-column, so the
compass stays honest. Renderers compositing a fits0 model onto an exported
top-down raster of the same data must flip: y_display = height - 1 - y.
"""

import json
import math
import os
from datetime import datetime, timezone

from .field import dso_distances, dsos_in_field, named_bright_stars, stars_in_field
from .solver import solve, wcs_from_solution

SCHEMA = 1


def _is_fits(image):
    return os.fspath(image).lower().endswith((".fit", ".fits", ".fts"))


def _image_size(image):
    path = os.fspath(image)
    if path.lower().endswith((".fit", ".fits", ".fts")):
        from astropy.io import fits

        with fits.open(path) as hdul:
            for hdu in hdul:
                if hdu.data is not None and getattr(hdu.data, "ndim", 0) >= 2:
                    h, w = hdu.data.shape[-2:]
                    return w, h
        raise ValueError(f"no image data in {path}")
    from PIL import Image

    with Image.open(path) as im:
        return im.size


def _links(designation, common=None):
    import urllib.parse

    links = {
        "simbad": "https://simbad.cds.unistra.fr/simbad/sim-id?Ident="
        + urllib.parse.quote_plus(designation)
    }
    if designation.startswith("M") and designation[1:].isdigit():
        links["wikipedia"] = f"https://en.wikipedia.org/wiki/Messier_{designation[1:]}"
    elif common:
        links["wikipedia"] = "https://en.wikipedia.org/wiki/" + urllib.parse.quote(
            common.replace(" ", "_"), safe="_()'-,."
        )
    return links


def _harmonize_pair_distances(objects):
    """A nebula and the cluster that lights it (Sh2-142 / NGC 7380) are one
    physical complex; cluster distances are the better-measured of the two
    (Gaia member parallaxes), so a co-located nebula inherits the cluster's
    distance instead of showing a contradictory literature value."""
    from .field import sep_deg

    clusters = [
        o
        for o in objects
        if o["kind"] == "dso" and o.get("dist_ly") and "cluster" in (o.get("type") or "").lower()
    ]
    for o in objects:
        if o["kind"] != "dso":
            continue
        t = (o.get("type") or "").lower()
        if "cluster" in t or not ("nebula" in t or "h ii" in t or "emission" in t):
            continue
        for c in clusters:
            if sep_deg(o["ra"], o["dec"], c["ra"], c["dec"]) < 0.35:
                o["dist_ly"] = c["dist_ly"]
                break


def build_model(image, *, mag_limit=12.5, max_stars=15, allow_online=True, solve_kwargs=None):
    """Solve `image`, cross-match the field, and return the annotation model."""
    width, height = _image_size(image)
    solution = solve(image, **(solve_kwargs or {}))
    wcs = wcs_from_solution(solution, width, height)
    # ASTAP converts raster inputs (JPEG/PNG/TIFF) to FITS row order before
    # solving, so its pixel y is bottom-up relative to the raster file. For
    # raster sources we convert everything into the raster's own top-down
    # frame ("raster0") so renderers can draw coordinates directly.
    raster = not _is_fits(image)

    def to_frame(x, y):
        return (x, (height - 1) - y) if raster else (x, y)

    # fallback derives scale from the CD matrix column norm, rotation-proof
    scale = solution.get("scale_arcsec_px") or (
        math.hypot(solution["cd1_2"], solution["cd2_2"]) * 3600.0
    )
    fov_h = height * scale / 3600.0
    fov_w = width * scale / 3600.0
    radius = 0.5 * (fov_w**2 + fov_h**2) ** 0.5
    center_ra, center_dec = solution["crval1"], solution["crval2"]

    def in_frame(x, y, margin=8):
        return -margin <= x <= width + margin and -margin <= y <= height + margin

    objects = []

    for rec in dsos_in_field(center_ra, center_dec, radius):
        x, y = to_frame(*wcs.wcs_world2pix([[rec["ra"], rec["dec"]]], 0)[0])
        if not in_frame(x, y):
            continue
        # rough Hubble-flow distance for galaxies with a catalog redshift
        dist_ly = None
        if rec.get("z") and rec["z"] > 0 and "galaxy" in rec["type"].lower():
            dist_ly = round(rec["z"] * 299792.458 / 70.0 * 3.26156e6)
        objects.append(
            {
                "kind": "dso",
                "designation": rec["disp"],
                "aliases": rec.get("aliases") or [],
                "dist_ly": dist_ly,
                "name": rec["common"] or None,
                "type": rec["type"],
                "constellation": rec["constellation"] or None,
                "ra": rec["ra"],
                "dec": rec["dec"],
                "x": round(float(x), 1),
                "y": round(float(y), 1),
                "links": _links(rec["disp"], rec["common"]),
            }
        )

    warnings = []
    if allow_online:
        missing = [o["designation"] for o in objects if o["kind"] == "dso" and not o["dist_ly"]]
        if missing:
            try:
                found = dso_distances(missing)
                for o in objects:
                    if o["kind"] == "dso" and o["designation"] in found:
                        o["dist_ly"] = round(found[o["designation"]])
                # merged designations (IC 405 = Sh2-229): a distance SIMBAD
                # files under the alias should still reach the object
                alias_pool = [
                    a
                    for o in objects
                    if o["kind"] == "dso" and not o["dist_ly"]
                    for a in o.get("aliases") or []
                ]
                if alias_pool:
                    found = dso_distances(alias_pool)
                    for o in objects:
                        if o["kind"] != "dso" or o["dist_ly"]:
                            continue
                        for a in o.get("aliases") or []:
                            if a in found:
                                o["dist_ly"] = round(found[a])
                                break
            except Exception as err:
                warnings.append(f"SIMBAD distance lookup failed: {err}")
        _harmonize_pair_distances(objects)
        try:
            named = named_bright_stars(center_ra, center_dec, radius)
        except Exception as err:  # network/service failure degrades, never crashes
            named = []
            warnings.append(f"SIMBAD bright-star query failed: {err}")
        try:
            # over-fetch: the search circle is ~2x the frame area, so the
            # in-frame trim to max_stars happens after projection below
            stars = stars_in_field(center_ra, center_dec, radius, mag_limit=mag_limit)
        except Exception as err:
            stars = []
            warnings.append(f"VizieR field-star query failed: {err}")
    else:
        named, stars = [], []
        warnings.append("offline: field stars omitted (bundled catalogs only cover DSOs)")

    named_positions = []
    for s in named:
        x, y = to_frame(*wcs.wcs_world2pix([[s["ra"], s["dec"]]], 0)[0])
        if not in_frame(x, y):
            continue
        named_positions.append((s["ra"], s["dec"]))
        objects.append(
            {
                "kind": "star",
                "named": True,
                "designation": s["designation"],
                "type": "Star" + (f" ({s['sp_type']})" if s.get("sp_type") else ""),
                "ra": s["ra"],
                "dec": s["dec"],
                "x": round(float(x), 1),
                "y": round(float(y), 1),
                "mag": s["mag"],
                "band": s["band"],
                "dist_ly": s.get("dist_ly"),
                "links": _links(s["designation"]),
            }
        )

    from .field import sep_deg

    n = 1
    for s in stars:
        if n > max_stars:
            break
        if any(sep_deg(s["ra"], s["dec"], ra, dec) < 3 / 3600 for ra, dec in named_positions):
            continue  # already labeled as a named bright star
        x, y = to_frame(*wcs.wcs_world2pix([[s["ra"], s["dec"]]], 0)[0])
        if not in_frame(x, y):
            continue
        objects.append(
            {
                "kind": "star",
                "named": False,
                "key": n,
                "designation": s["designation"],
                "ra": s["ra"],
                "dec": s["dec"],
                "x": round(float(x), 1),
                "y": round(float(y), 1),
                "mag": s["mag"],
                "band": s["band"],
                "dist_ly": s.get("dist_ly"),
                "links": _links(s["designation"]),
            }
        )
        n += 1

    return {
        "schema": SCHEMA,
        "image": os.path.basename(os.fspath(image)),
        "image_size": [width, height],
        "solved": {
            # "fits0": 0-indexed, FITS row order (FITS sources).
            # "raster0": 0-indexed, top-left origin (JPEG/PNG sources) — the
            # solver's y and the CD y-column are converted; see module docstring.
            "pixel_frame": "raster0" if raster else "fits0",
            "cd": [
                [solution["cd1_1"], -solution["cd1_2"] if raster else solution["cd1_2"]],
                [solution["cd2_1"], -solution["cd2_2"] if raster else solution["cd2_2"]],
            ],
            "center_ra": center_ra,
            "center_dec": center_dec,
            "scale_arcsec_px": round(scale, 3),
            "fov_deg": [round(fov_w, 3), round(fov_h, 3)],
            "rotation_deg": solution.get("rotation_deg"),
            "solver": solution.get("solver", "ASTAP"),
        },
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "objects": objects,
        "warnings": warnings,
    }


def write_model(model, output):
    with open(output, "w") as f:
        json.dump(model, f, indent=1)
    return output
