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


def _str_or_none(v):
    """Stringify a catalog cell, mapping masked/empty sentinels to None."""
    if v is None:
        return None
    text = str(v).strip()
    return text if text and text not in ("None", "--") else None


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

    The rounded-position collapse merges alias COPIES of one record (M51 /
    NGC 5194 share bit-identical coordinates). Physically distinct objects at
    distinct centroids stay separate on purpose, even overlapping pairs like
    NGC 7380 and Sh2-142 (~4' apart): on an annotated image both centroids
    are legitimate label targets, unlike the sky chart's marker-clutter
    dedupe, which works at whole-sky scale."""
    catalog = catalog or Catalog()
    best = {}
    for rec in catalog.by_key.values():
        d = sep_deg(center_ra, center_dec, rec["ra"], rec["dec"])
        if d > radius_deg:
            continue
        key = (round(rec["ra"], 4), round(rec["dec"], 4))
        cur = best.get(key)
        if cur is None:
            best[key] = dict(rec, sep_deg=d, aliases=[])
        elif _designation_rank(rec["disp"]) < _designation_rank(cur["disp"]):
            aliases = [a for a in [cur["disp"]] + cur["aliases"] if a != rec["disp"]]
            best[key] = dict(rec, sep_deg=d, aliases=aliases)
        elif rec["disp"] != cur["disp"] and rec["disp"] not in cur["aliases"]:
            cur["aliases"].append(rec["disp"])
    hits = sorted(best.values(), key=lambda r: r["sep_deg"])
    return _merge_sharpless_duplicates(hits)


# Large nebulae appear in both OpenNGC and the Sharpless catalog with centers
# that disagree by arcminutes (IC 405 vs Sh2-229: 6.8'), so the identical-
# position collapse above cannot see they are one object.
_SH_MERGE_MAX_SEP_DEG = 12.0 / 60.0

# only these OpenNGC types can be the NGC/IC face of a Sharpless object;
# dark and planetary nebulae are physically different things that merely
# sit nearby (B33 is 3.9' from Sh2-277 and is not it)
_SH_HOST_TYPES = {"Nebula", "Emission nebula", "H II region"}


def _merge_sharpless_duplicates(hits):
    """Fold a Sharpless entry into its pure-nebula NGC/IC/M counterpart:
    same object, two catalogs. Matching is one-to-one by proximity — an
    NGC/IC object carries at most one Sharpless identity, so in a crowded
    complex (Sh2-254..258 around IC 2162) only the nearest pair merges and
    the rest stay their own objects. Cluster+nebula complexes (NGC 7380 /
    Sh2-142) keep both entries: physically distinct centroids worth
    labeling."""
    merged = [h for h in hits if not h["disp"].startswith("Sh2-")]
    sharpless = [h for h in hits if h["disp"].startswith("Sh2-")]
    hosts = [m for m in merged if m["type"] in _SH_HOST_TYPES]
    pairs = []
    for h in sharpless:
        for m in hosts:
            d = sep_deg(h["ra"], h["dec"], m["ra"], m["dec"])
            if d <= _SH_MERGE_MAX_SEP_DEG:
                pairs.append((d, h, m))
    pairs.sort(key=lambda p: p[0])
    taken_sh, taken_host = set(), set()
    for d, h, m in pairs:
        if id(h) in taken_sh or id(m) in taken_host:
            continue
        taken_sh.add(id(h))
        taken_host.add(id(m))
        m["aliases"] = [a for a in m["aliases"] if a != h["disp"]] + [h["disp"]]
        if m["type"] == "Nebula":
            # generic OpenNGC "Neb" gains the Sharpless classification;
            # already-specific types (H II region) are kept
            m["type"] = h["type"]
        m["z"] = m["z"] if m["z"] is not None else h["z"]
    merged.extend(h for h in sharpless if id(h) not in taken_sh)
    return sorted(merged, key=lambda r: r["sep_deg"])


# Gaia DR3 positions are epoch J2016.0; Tycho-2 observed positions carry
# PER-STAR epochs (EpRA-1990/EpDE-1990, roughly 1990.8 to 1992.1). High-
# proper-motion stars move arcminutes across the gap (Groombridge 1830:
# ~171 arcsec), so the match must run at each Tycho row's own epochs; even
# a fixed catalog-mean epoch leaves fast movers several arcsec out.
GAIA_EPOCH = 2016.0
TYCHO_FALLBACK_EPOCH = 1991.5  # catalog mean, for rows with masked epochs


def _propagate(ra, dec, pmra_masyr, pmde_masyr, dt_years):
    """Move an ICRS position by proper motion. pmra is the projected
    mu_alpha* (mas/yr, already times cos dec), Gaia's convention. Within
    an arcminute of the pole the linear RA shift is meaningless, so RA is
    left untouched there (dec still moves; a 2 arcsec match at the exact
    pole is not a real case)."""
    dec2 = dec + pmde_masyr * dt_years / 3.6e6
    if abs(dec) > 90 - 1 / 60:
        return ra, dec2
    ra2 = ra + pmra_masyr * dt_years / 3.6e6 / math.cos(math.radians(dec))
    return ra2, dec2


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
        columns=["Source", "RA_ICRS", "DE_ICRS", "Gmag", "Plx", "e_Plx", "pmRA", "pmDE"],
        column_filters={"Gmag": f"<{mag_limit}"},
        row_limit=5000,
    ).query_region(center, radius=radius)
    stars = []
    if gaia:
        for row in gaia[0]:
            plx = float(row["Plx"]) if row["Plx"] else None
            dist_pc = 1000.0 / plx if plx and plx > 0.5 else None
            ra, dec = float(row["RA_ICRS"]), float(row["DE_ICRS"])
            pmra = float(row["pmRA"]) if row["pmRA"] else 0.0
            pmde = float(row["pmDE"]) if row["pmDE"] else 0.0
            stars.append(
                {
                    "designation": f"Gaia DR3 {row['Source']}",
                    "_pm": (pmra, pmde),
                    "ra": ra,
                    "dec": dec,
                    "mag": round(float(row["Gmag"]), 1),
                    "band": "G",
                    "dist_ly": round(dist_pc * 3.26156) if dist_pc else None,
                }
            )
    stars.sort(key=lambda s: s["mag"])
    stars = stars[:max_stars]

    tycho = Vizier(
        catalog="I/259/tyc2",
        columns=["TYC1", "TYC2", "TYC3", "RA(ICRS)", "DE(ICRS)", "VTmag", "EpRA-1990", "EpDE-1990"],
        row_limit=200,
    ).query_region(center, radius=radius)
    if tycho:
        fallback = TYCHO_FALLBACK_EPOCH - 1990.0
        for row in tycho[0]:
            tyc = f"TYC {row['TYC1']}-{row['TYC2']}-{row['TYC3']}"
            tra, tdec = float(row["RA(ICRS)"]), float(row["DE(ICRS)"])
            ep_ra = 1990.0 + (float(row["EpRA-1990"]) if row["EpRA-1990"] else fallback)
            ep_de = 1990.0 + (float(row["EpDE-1990"]) if row["EpDE-1990"] else fallback)
            for s in stars:
                pmra, pmde = s["_pm"]
                # RA and DE are observed at different epochs in Tycho-2
                era, _ = _propagate(s["ra"], s["dec"], pmra, pmde, ep_ra - GAIA_EPOCH)
                _, edec = _propagate(s["ra"], s["dec"], pmra, pmde, ep_de - GAIA_EPOCH)
                if sep_deg(era, edec, tra, tdec) < 2 * ARCSEC:
                    s["designation"] = tyc
                    break
    for s in stars:
        s.pop("_pm", None)
    return stars


def named_bright_stars(center_ra, center_dec, radius_deg, *, mag_limit=8.5):
    """SIMBAD-named bright stars in the field (HD/proper names, spectral type).
    Online only; returns [] when SIMBAD has nothing bright here."""
    from astropy import units as u
    from astropy.coordinates import SkyCoord
    from astroquery.simbad import Simbad

    sim = Simbad()
    sim.add_votable_fields("V", "sp_type", "plx_value", "otype")
    table = sim.query_region(
        SkyCoord(center_ra * u.deg, center_dec * u.deg),
        radius=radius_deg * u.deg,
        # allfluxes.V is the TAP flux column; 'G..' excludes the whole
        # galaxy otype hierarchy so bright Seyferts don't masquerade as stars.
        # criteria needs astroquery >= 0.4.8 (the TAP-based Simbad), which the
        # [annotate] extra pins.
        criteria=f"allfluxes.V < {mag_limit} AND otype != 'G..'",
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
                "sp_type": _str_or_none(col(row, "sp_type")),
                "dist_ly": round(1000.0 / plx * 3.26156) if plx and plx > 0.5 else None,
            }
        )
    out.sort(key=lambda s: s["mag"])
    return out


_DIST_LY_PER_UNIT = {"pc": 3.26156, "kpc": 3261.56, "mpc": 3.26156e6}


def dso_distances(designations):
    """SIMBAD mean distances in light-years, keyed by designation. Online only;
    designations SIMBAD doesn't know or has no distance for are simply absent."""
    from astroquery.simbad import Simbad

    sim = Simbad()
    sim.add_votable_fields("mesdistance")
    out = {}
    for desig in designations:
        try:
            t = sim.query_object(desig)
        except Exception:
            continue
        if t is None or len(t) == 0:
            continue
        cols = {c.lower(): c for c in t.colnames}
        dc, uc = cols.get("mesdistance.dist"), cols.get("mesdistance.unit")
        if not dc or not uc:
            continue
        values = []
        for row in t:
            dist, unit = row[dc], row[uc]
            try:
                if hasattr(dist, "mask") and dist.mask:
                    continue
                factor = _DIST_LY_PER_UNIT.get(str(unit).strip().lower())
                if factor and float(dist) > 0:
                    values.append(float(dist) * factor)
            except (TypeError, ValueError):
                continue
        if values:
            # the literature usually holds several measurements; the median
            # beats whichever row happens to come back first
            values.sort()
            out[desig] = values[len(values) // 2]
    return out
