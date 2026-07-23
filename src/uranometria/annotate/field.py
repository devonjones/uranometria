"""Field cross-match: what's actually in the solved frame.

Deep-sky objects come from the bundled offline catalog (OpenNGC + Sharpless).
Field stars come from VizieR's Gaia DR3 mirror (magnitudes + parallax
distances) with Tycho-2 supplying friendlier designations, and SIMBAD names
the bright stars — all gated behind allow_online, and all via CDS services
(the Gaia archive itself is never contacted, since it is blocked in some
sandboxes).
"""

import math

from ..catalog import Catalog

ARCSEC = 1.0 / 3600.0


def sep_deg(ra1, dec1, ra2, dec2):
    r1, d1, r2, d2 = map(math.radians, (ra1, dec1, ra2, dec2))
    s = math.sin(d1) * math.sin(d2) + math.cos(d1) * math.cos(d2) * math.cos(r1 - r2)
    return math.degrees(math.acos(max(-1.0, min(1.0, s))))


def _designation_rank(disp):
    """Preference when one object carries several designations: M < NGC < IC < rest."""
    if disp.startswith("M") and disp[1:].isdigit():
        return (0, len(disp))
    for i, prefix in enumerate(("NGC", "IC", "Sh2")):
        if disp.startswith(prefix):
            return (i + 1, len(disp))
    return (9, len(disp))


def dsos_in_field(center_ra, center_dec, radius_deg, catalog=None):
    """Bundled-catalog objects within radius of the field center (offline).
    Aliases of the same object (M51 / NGC 5194) collapse to one entry, keeping
    the best-known designation."""
    catalog = catalog or Catalog()
    best = {}
    for rec in catalog.by_key.values():
        d = sep_deg(center_ra, center_dec, rec["ra"], rec["dec"])
        if d > radius_deg:
            continue
        key = (round(rec["ra"], 4), round(rec["dec"], 4))
        cur = best.get(key)
        if cur is None or _designation_rank(rec["disp"]) < _designation_rank(cur["disp"]):
            best[key] = dict(rec, sep_deg=d)
    hits = sorted(best.values(), key=lambda r: r["sep_deg"])
    return hits


def stars_in_field(center_ra, center_dec, radius_deg, *, mag_limit=12.5, max_stars=100):
    """Gaia DR3 (via VizieR) stars in the search circle, brightest first, with
    Tycho-2 designations where available. Online only. Callers apply their own
    in-frame filtering before trimming to a display count — the search circle
    is bigger than the frame, so trimming here would starve the frame."""
    from astropy import units as u
    from astropy.coordinates import SkyCoord
    from astroquery.vizier import Vizier

    center = SkyCoord(center_ra * u.deg, center_dec * u.deg)
    radius = radius_deg * u.deg

    gaia = Vizier(
        catalog="I/355/gaiadr3",
        columns=["Source", "RA_ICRS", "DE_ICRS", "Gmag", "Plx", "e_Plx"],
        column_filters={"Gmag": f"<{mag_limit}"},
        row_limit=500,
    ).query_region(center, radius=radius)
    stars = []
    if gaia:
        for row in gaia[0]:
            plx = float(row["Plx"]) if row["Plx"] else None
            dist = 1000.0 / plx if plx and plx > 0.5 else None
            stars.append(
                {
                    "designation": f"Gaia DR3 {row['Source']}",
                    "ra": float(row["RA_ICRS"]),
                    "dec": float(row["DE_ICRS"]),
                    "mag": round(float(row["Gmag"]), 1),
                    "band": "G",
                    "dist_pc": round(dist) if dist else None,
                }
            )
    stars.sort(key=lambda s: s["mag"])
    stars = stars[:max_stars]

    tycho = Vizier(
        catalog="I/259/tyc2",
        columns=["TYC1", "TYC2", "TYC3", "RA(ICRS)", "DE(ICRS)", "VTmag"],
        row_limit=200,
    ).query_region(center, radius=radius)
    if tycho:
        for row in tycho[0]:
            tyc = f"TYC {row['TYC1']}-{row['TYC2']}-{row['TYC3']}"
            tra, tdec = float(row["RA(ICRS)"]), float(row["DE(ICRS)"])
            for s in stars:
                if sep_deg(s["ra"], s["dec"], tra, tdec) < 2 * ARCSEC:
                    s["designation"] = tyc
                    break
    return stars


def named_bright_stars(center_ra, center_dec, radius_deg, *, mag_limit=8.5):
    """SIMBAD-named bright stars in the field (HD/proper names, spectral type).
    Online only; returns [] when SIMBAD has nothing bright here."""
    from astropy import units as u
    from astropy.coordinates import SkyCoord
    from astroquery.simbad import Simbad

    sim = Simbad()
    sim.add_votable_fields("V", "sp_type", "plx_value", "otype")
    try:
        table = sim.query_region(
            SkyCoord(center_ra * u.deg, center_dec * u.deg),
            radius=radius_deg * u.deg,
            # allfluxes.V is the TAP flux column; 'G..' excludes the whole
            # galaxy otype hierarchy so bright Seyferts don't masquerade as stars
            criteria=f"allfluxes.V < {mag_limit} AND otype != 'G..'",
        )
    except TypeError:
        # older astroquery without criteria support: filter client-side
        table = sim.query_region(
            SkyCoord(center_ra * u.deg, center_dec * u.deg), radius=radius_deg * u.deg
        )
    out = []
    if table is None:
        return out
    cols = {c.lower(): c for c in table.colnames}

    def col(row, *names):
        for n in names:
            if n in cols and row[cols[n]] is not None:
                v = row[cols[n]]
                try:
                    if hasattr(v, "mask") and v.mask:
                        continue
                except Exception:
                    pass
                return v
        return None

    for row in table:
        v = col(row, "v", "flux_v", "flux(v)")
        try:
            v = float(v) if v is not None else None
        except (TypeError, ValueError):
            v = None
        if v is None or v >= mag_limit:
            continue
        ra = float(col(row, "ra"))
        dec = float(col(row, "dec"))
        plx = col(row, "plx_value")
        try:
            plx = float(plx) if plx is not None else None
        except (TypeError, ValueError):
            plx = None
        out.append(
            {
                "designation": str(col(row, "main_id")),
                "ra": ra,
                "dec": dec,
                "mag": round(v, 2),
                "band": "V",
                "sp_type": (str(col(row, "sp_type")) or None),
                "dist_pc": round(1000.0 / plx) if plx and plx > 0.5 else None,
            }
        )
    out.sort(key=lambda s: s["mag"])
    return out
