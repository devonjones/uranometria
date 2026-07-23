"""ASTAP plate-solver wrapper.

Runs the astap_cli binary against an image and returns the solved WCS. ASTAP
is fully offline (bundled star database), which keeps solving independent of
any network allowlist. The binary and database locations come from arguments
or the ASTAP_CLI / ASTAP_DB environment variables.
"""

import os
import shutil
import subprocess
import tempfile


class AstapError(Exception):
    """The solver could not run or could not solve the image."""


def _astap_binary(astap=None):
    exe = astap or os.environ.get("ASTAP_CLI") or "astap_cli"
    found = shutil.which(exe) or (exe if os.path.isfile(exe) else None)
    if not found:
        raise AstapError(
            "astap_cli not found. Install the ASTAP command-line solver and a star "
            "database from https://www.hnsky.org/astap.htm, then pass --astap/--astap-db "
            "or set the ASTAP_CLI and ASTAP_DB environment variables."
        )
    return found


def _parse_ini(path):
    out = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if "=" in line:
                k, _, v = line.partition("=")
                out[k.strip()] = v.strip()
    return out


def solve(
    image,
    *,
    astap=None,
    db_dir=None,
    db=None,
    ra_hours=None,
    dec=None,
    radius=30.0,
    fov=0.0,
    timeout=120,
):
    """Plate-solve `image` and return a dict of WCS keywords.

    ra_hours/dec are optional pointing hints (RA in hours, dec in degrees);
    radius is the search radius around the hint in degrees; fov is the image
    height in degrees (0 = auto). Returns keys: crval1, crval2 (deg), crpix1,
    crpix2, cd1_1..cd2_2, scale_arcsec_px, fov_deg, rotation_deg, solver.
    """
    exe = _astap_binary(astap)
    db_dir = db_dir or os.environ.get("ASTAP_DB")
    with tempfile.TemporaryDirectory(prefix="uranometria-solve-") as tmp:
        base = os.path.join(tmp, "solve")
        cmd = [
            exe,
            "-f",
            os.fspath(image),
            "-o",
            base,
            "-r",
            str(radius),
            "-fov",
            str(fov),
            "-z",
            "0",
        ]
        if db_dir:
            cmd += ["-d", db_dir]
        if db:
            cmd += ["-D", db]
        if ra_hours is not None and dec is not None:
            cmd += ["-ra", str(ra_hours), "-spd", str(90.0 + dec)]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise AstapError(f"astap_cli timed out after {timeout}s on {image}") from None
        ini_path = base + ".ini"
        if not os.path.isfile(ini_path):
            raise AstapError(
                f"astap_cli produced no result for {image}: {proc.stdout or proc.stderr}"
            )
        ini = _parse_ini(ini_path)
        if ini.get("PLTSOLVD") != "T":
            raise AstapError(
                f"plate solve failed for {image}: {ini.get('ERROR', proc.stdout.strip())}"
            )
        try:
            result = {
                "crval1": float(ini["CRVAL1"]),
                "crval2": float(ini["CRVAL2"]),
                "crpix1": float(ini["CRPIX1"]),
                "crpix2": float(ini["CRPIX2"]),
                "cd1_1": float(ini["CD1_1"]),
                "cd1_2": float(ini["CD1_2"]),
                "cd2_1": float(ini["CD2_1"]),
                "cd2_2": float(ini["CD2_2"]),
            }
        except (KeyError, ValueError) as err:
            raise AstapError(f"unexpected solver output in {ini_path}: {err}") from None
        result["scale_arcsec_px"] = abs(float(ini.get("CDELT2", 0))) * 3600.0 or None
        result["rotation_deg"] = float(ini.get("CROTA2", 0.0))
        result["solver"] = "ASTAP"
        if ini.get("CMDLINE"):
            result["solver_cmdline"] = ini["CMDLINE"]
        return result


def wcs_from_solution(solution, width, height):
    """Build an astropy WCS from a solve() result (TAN projection)."""
    from astropy.wcs import WCS

    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [solution["crval1"], solution["crval2"]]
    w.wcs.crpix = [solution["crpix1"], solution["crpix2"]]
    w.wcs.cd = [
        [solution["cd1_1"], solution["cd1_2"]],
        [solution["cd2_1"], solution["cd2_2"]],
    ]
    w.pixel_shape = (width, height)
    return w
