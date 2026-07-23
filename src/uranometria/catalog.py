"""Designation resolution: coordinate parsing, bundled catalogs, Sesame fallback.

Bundled (offline): Messier, NGC/IC (OpenNGC), Sharpless (Sh2), Caldwell,
Barnard 33, Melotte, and common names known to OpenNGC. Anything else can be
resolved online through the CDS Sesame service.
"""

import csv
import re
import urllib.parse
import urllib.request

from .resources import data_text, data_json


# ---------------------------------------------------------------- parsing
def parse_angle(value, is_ra):
    """Accept decimal degrees, or sexagesimal strings like '20h15m22s',
    '20:15:22', '+38 21 18', '-05d23m28s', '+41°16′09″'."""
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if re.fullmatch(r"[+-]?\d+(\.\d+)?", s):
        return float(s)
    t = re.sub(r"[hdms:°'′\"″]", " ", s.lower()).strip()
    parts = t.split()
    if not parts:
        raise ValueError(f"cannot parse angle {value!r}")
    sign = -1.0 if parts[0].startswith("-") else 1.0
    nums = [abs(float(p)) for p in parts]
    deg = (
        nums[0] + (nums[1] if len(nums) > 1 else 0) / 60 + (nums[2] if len(nums) > 2 else 0) / 3600
    )
    if is_ra and ("h" in s.lower() or ":" in s or deg <= 24 and len(nums) > 1):
        deg *= 15.0
    return sign * deg


def fmt_coord(ra, dec):
    rh = ra / 15.0
    h = int(rh)
    m = int(round((rh - h) * 60))
    if m == 60:
        h, m = h + 1, 0
    sign = "+" if dec >= 0 else "−"
    ad = abs(dec)
    d = int(ad)
    am = int(round((ad - d) * 60))
    if am == 60:
        d, am = d + 1, 0
    return f"{h:02d}h {m:02d}m  {sign}{d:02d}° {am:02d}′"


# ---------------------------------------------------------------- catalogs
TYPE_NAMES = {
    "OCl": "Open cluster",
    "GCl": "Globular cluster",
    "G": "Galaxy",
    "PN": "Planetary nebula",
    "SNR": "Supernova remnant",
    "EmN": "Emission nebula",
    "RfN": "Reflection nebula",
    "HII": "H II region",
    "Neb": "Nebula",
    "Cl+N": "Cluster + nebula",
    "DrkN": "Dark nebula",
    "*Ass": "Stellar association",
    "**": "Double star",
    "*": "Star",
    "GPair": "Galaxy pair",
    "GTrpl": "Galaxy triplet",
    "GGroup": "Galaxy group",
    "Nova": "Nova",
    "Other": "Deep-sky object",
}


def _load_constellation_names():
    out = {}
    for f in data_json("constellations.json")["features"]:
        abbr = re.sub(r"\d+$", "", f["id"])
        out.setdefault(abbr, f["properties"].get("la", f["properties"]["name"]))
    return out


CONST_NAMES = _load_constellation_names()


class Catalog:
    """Offline designation lookup over the bundled catalog files."""

    def __init__(self):
        self.by_key = {}  # normalized designation -> record
        self.by_common = {}  # lowercase common name -> record
        self._load_openngc()
        self._load_sharpless()

    @staticmethod
    def _rec(disp, ra, dec, typ, con, common):
        return dict(disp=disp, ra=ra, dec=dec, type=typ, constellation=con, common=common)

    def _load_openngc(self):
        rows = []
        for fn in ("NGC.csv", "addendum.csv"):
            rows += list(csv.DictReader(data_text(fn).splitlines(), delimiter=";"))
        raw = {r["Name"]: r for r in rows}
        for r in rows:
            if r["Type"] in ("Dup", "NonEx") or not r["RA"]:
                # duplicates resolve through their NGC/IC cross-reference
                if r["Type"] == "Dup":
                    tgt = (
                        "NGC" + r["NGC"].zfill(4)
                        if r.get("NGC")
                        else "IC" + r["IC"].zfill(4) if r.get("IC") else None
                    )
                    if tgt in raw and raw[tgt]["RA"]:
                        r = dict(raw[tgt], Name=r["Name"], M=r["M"] or raw[tgt]["M"])
                    else:
                        continue
                else:
                    continue
            ra = parse_angle(r["RA"], is_ra=True)
            dec = parse_angle(r["Dec"], is_ra=False)
            common = (r.get("Common names") or "").split(",")[0].strip()
            rec = self._rec(
                self._display(r["Name"]),
                ra,
                dec,
                TYPE_NAMES.get(r["Type"], r["Type"]),
                CONST_NAMES.get(r["Const"], r["Const"]),
                common,
            )
            self.by_key.setdefault(self._norm(r["Name"]), rec)
            if r.get("M"):
                self.by_key.setdefault(f"M{int(r['M'])}", dict(rec, disp=f"M{int(r['M'])}"))
            for ident in (r.get("Identifiers") or "").split(","):
                m = re.fullmatch(r"C (\d{3})", ident.strip())
                if m:
                    self.by_key.setdefault(f"C{int(m.group(1))}", dict(rec, disp=rec["disp"]))
            for cn in (r.get("Common names") or "").split(","):
                if cn.strip():
                    self.by_common.setdefault(cn.strip().lower(), rec)

    def _load_sharpless(self):
        seen = set()
        for line in data_text("sh2.tsv").splitlines():
            if line.startswith("#") or not re.match(r"\s*\d", line):
                continue
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            n = int(parts[0])
            if n in seen:
                continue
            seen.add(n)
            self.by_key[f"SH2{n}"] = self._rec(
                f"Sh2-{n}", float(parts[1]), float(parts[2]), "Emission nebula (H II)", "", ""
            )

    @staticmethod
    def _display(name):
        m = re.fullmatch(r"(NGC|IC|Mel|HCG|UGC|PGC)0*(\d+)(.*)", name)
        if m:
            return f"{m.group(1)} {m.group(2)}{m.group(3)}"
        m = re.fullmatch(r"([MBC])0*(\d+)", name)
        if m:
            return f"{m.group(1)}{m.group(2)}"
        return name

    @staticmethod
    def _norm(desig):
        s = re.sub(r"[\s._]", "", desig.upper())
        s = s.replace("MESSIER", "M").replace("CALDWELL", "C").replace("BARNARD", "B")
        s = s.replace("MELOTTE", "MEL")
        m = re.fullmatch(r"(SH2?|S)-?(\d+)", s)
        if m:
            return f"SH2{int(m.group(2))}"
        m = re.fullmatch(r"(NGC|IC|MEL|M|B|C)0*(\d+)([A-Z-]*)", s)
        if m:
            pref = {"MEL": "Mel"}.get(m.group(1), m.group(1))
            return f"{pref}{int(m.group(2))}{m.group(3)}"
        return s

    def lookup(self, desig):
        rec = self.by_key.get(self._norm(desig)) or self.by_common.get(desig.strip().lower())
        return dict(rec) if rec else None


def sesame(desig, timeout=15):
    """CDS Sesame name resolver — network fallback for unknown designations."""
    url = "https://cds.unistra.fr/cgi-bin/nph-sesame/-oI/A?" + urllib.parse.quote(desig)
    req = urllib.request.Request(url, headers={"User-Agent": "uranometria"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        text = resp.read().decode("utf-8", "replace")
    m = re.search(r"%J\s+([\d.+-]+)\s+([\d.+-]+)", text)
    if not m:
        return None
    return dict(
        disp=desig,
        ra=float(m.group(1)),
        dec=float(m.group(2)),
        type="Deep-sky object",
        constellation="",
        common="",
    )
