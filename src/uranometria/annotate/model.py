"""Assemble and persist the annotation model.

The model is the contract between the solve/cross-match pipeline and the
renderers (annotated PNG, interactive HTML, sky-map lightbox overlay): plain
JSON, one file per image, with everything positioned in both sky and pixel
coordinates.

Pixel convention (`solved.pixel_frame` = "fits0"): object x/y are 0-indexed
in the solved image's FITS frame — x grows rightward, y follows FITS row
order, i.e. pixel (0, 0) is FITS pixel (1, 1). WCSAxes/matplotlib consume
this directly. Renderers that draw on a top-left-origin raster (SVG/HTML,
PIL) must flip: y_display = height - 1 - y — and should verify the source's
row order (Siril writes a ROWORDER card) before compositing onto exported
JPEG/PNG versions of the frame.
"""

import json
import math
import math
import os
from datetime import datetime, timezone

from .field import dsos_in_field, named_bright_stars, stars_in_field
from .solver import solve, wcs_from_solution

SCHEMA = 1


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
    links = {
        "simbad": "https://simbad.cds.unistra.fr/simbad/sim-id?Ident="
        + designation.replace(" ", "+")
    }
    if designation.startswith("M") and designation[1:].isdigit():
        links["wikipedia"] = f"https://en.wikipedia.org/wiki/Messier_{designation[1:]}"
    elif common:
        links["wikipedia"] = "https://en.wikipedia.org/wiki/" + common.replace(" ", "_")
    return links


def build_model(image, *, mag_limit=12.5, max_stars=15, allow_online=True, solve_kwargs=None):
    """Solve `image`, cross-match the field, and return the annotation model."""
    width, height = _image_size(image)
    solution = solve(image, **(solve_kwargs or {}))
    wcs = wcs_from_solution(solution, width, height)

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
        x, y = wcs.wcs_world2pix([[rec["ra"], rec["dec"]]], 0)[0]
        if not in_frame(x, y):
            continue
        objects.append(
            {
                "kind": "dso",
                "designation": rec["disp"],
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
        x, y = wcs.wcs_world2pix([[s["ra"], s["dec"]]], 0)[0]
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
                "dist_pc": s.get("dist_pc"),
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
        x, y = wcs.wcs_world2pix([[s["ra"], s["dec"]]], 0)[0]
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
                "dist_pc": s.get("dist_pc"),
                "links": _links(s["designation"]),
            }
        )
        n += 1

    return {
        "schema": SCHEMA,
        "image": os.path.basename(os.fspath(image)),
        "image_size": [width, height],
        "solved": {
            "pixel_frame": "fits0",  # see module docstring: 0-indexed, FITS row order
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
