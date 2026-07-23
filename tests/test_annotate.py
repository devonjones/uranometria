import json

import pytest

pytest.importorskip("astropy")

from uranometria.annotate.field import dsos_in_field, sep_deg
from uranometria.annotate.solver import wcs_from_solution

# ASTAP's real solution for the M51 1411-sub drizzled stack (2026-07-14)
M51_SOLUTION = {
    "crval1": 202.51666,
    "crval2": 47.20639,
    "crpix1": 1936.0,
    "crpix2": 1096.0,
    "cd1_1": -0.00032993,
    "cd1_2": 0.00001020,
    "cd2_1": 0.00001023,
    "cd2_2": 0.00032992,
    "scale_arcsec_px": 1.188,
    "rotation_deg": 178.2,
    "solver": "ASTAP",
}


def test_dsos_in_field_m51():
    hits = dsos_in_field(202.5167, 47.2064, 0.7)
    names = {h["disp"] for h in hits}
    assert "M51" in names
    assert "NGC 5195" in names  # the companion
    assert all(h["sep_deg"] <= 0.7 for h in hits)
    assert hits[0]["disp"] in ("M51", "NGC 5194")  # sorted by separation


def test_dsos_in_field_dedupes_aliases():
    hits = dsos_in_field(202.5167, 47.2064, 0.5)
    # M51 and NGC 5194 are the same record under two keys; only one entry
    m51ish = [h for h in hits if abs(h["ra"] - 202.4696) < 0.01 and abs(h["dec"] - 47.1952) < 0.01]
    assert len(m51ish) == 1


def test_wcs_projection_roundtrip():
    wcs = wcs_from_solution(M51_SOLUTION, 3872, 2192)
    # the field center must project to the reference pixel
    x, y = wcs.wcs_world2pix([[M51_SOLUTION["crval1"], M51_SOLUTION["crval2"]]], 0)[0]
    assert x == pytest.approx(M51_SOLUTION["crpix1"] - 1, abs=0.01)
    assert y == pytest.approx(M51_SOLUTION["crpix2"] - 1, abs=0.01)
    # a point one arcminute away lands ~50px away at 1.188"/px
    x2, y2 = wcs.wcs_world2pix([[M51_SOLUTION["crval1"], M51_SOLUTION["crval2"] + 1 / 60]], 0)[0]
    d = ((x2 - x) ** 2 + (y2 - y) ** 2) ** 0.5
    assert d == pytest.approx(60 / 1.188, rel=0.01)


def test_sep_deg_wraps():
    assert sep_deg(359.9, 0, 0.1, 0) == pytest.approx(0.2, abs=1e-6)


def test_model_offline_and_links(monkeypatch, tmp_path):
    import uranometria.annotate.model as model

    monkeypatch.setattr(model, "solve", lambda image, **kw: dict(M51_SOLUTION))
    monkeypatch.setattr(model, "_image_size", lambda image: (3872, 2192))
    m = model.build_model(tmp_path / "fake.fit", allow_online=False)
    assert m["schema"] == 1
    kinds = {o["kind"] for o in m["objects"]}
    assert kinds == {"dso"}  # offline: no star queries
    m51 = next(o for o in m["objects"] if o["designation"] == "M51")
    assert 0 <= m51["x"] <= 3872 and 0 <= m51["y"] <= 2192
    assert m51["links"]["wikipedia"].endswith("Messier_51")
    assert "sim-id" in m51["links"]["simbad"]
    assert any("offline" in w for w in m["warnings"])
    out = model.write_model(m, tmp_path / "m.json")
    assert json.load(open(out))["image"] == "fake.fit"


def test_solver_missing_binary(monkeypatch):
    from uranometria.annotate.solver import AstapError, solve

    monkeypatch.setenv("ASTAP_CLI", "/nonexistent/astap_cli")
    monkeypatch.setattr("shutil.which", lambda x: None)
    with pytest.raises(AstapError, match="astap_cli not found"):
        solve("whatever.fit")


# ---- pr-review-loop round 1 -------------------------------------------------


def _fake_astap(tmp_path, ini_body, exit_code=0):
    """A stand-in astap_cli that writes the given .ini next to -o base."""
    script = tmp_path / "fake_astap"
    script.write_text(
        "#!/bin/sh\n"
        'base=""\n'
        'prev=""\n'
        'for a in "$@"; do [ "$prev" = "-o" ] && base="$a"; prev="$a"; done\n'
        f'cat > "$base.ini" <<"INI"\n{ini_body}\nINI\n'
        f"exit {exit_code}\n"
    )
    script.chmod(0o755)
    return str(script)


SOLVED_INI = """PLTSOLVD=T
CRVAL1=202.51666
CRVAL2=47.20639
CRPIX1=1936.0
CRPIX2=1096.0
CD1_1=-0.00032993
CD1_2=0.00001020
CD2_1=0.00001023
CD2_2=0.00032992
CDELT2=0.00033
CROTA2=178.2"""


def test_solve_parses_fake_astap(tmp_path):
    from uranometria.annotate.solver import solve

    exe = _fake_astap(tmp_path, SOLVED_INI)
    sol = solve(tmp_path / "img.fit", astap=exe)
    assert sol["crval1"] == pytest.approx(202.51666)
    assert sol["scale_arcsec_px"] == pytest.approx(0.00033 * 3600, rel=1e-6)
    assert sol["solver"] == "ASTAP"


def test_solve_failure_paths(tmp_path):
    from uranometria.annotate.solver import AstapError, solve

    with pytest.raises(AstapError, match="plate solve failed"):
        solve(tmp_path / "i.fit", astap=_fake_astap(tmp_path, "PLTSOLVD=F\nERROR=no stars"))
    with pytest.raises(AstapError, match="unexpected solver output"):
        solve(tmp_path / "i.fit", astap=_fake_astap(tmp_path, "PLTSOLVD=T\nCRVAL1=abc"))
    noini = tmp_path / "noini"
    noini.write_text("#!/bin/sh\nexit 1\n")
    noini.chmod(0o755)
    with pytest.raises(AstapError, match="no result"):
        solve(tmp_path / "i.fit", astap=str(noini))


def test_scale_fallback_is_rotation_proof(monkeypatch, tmp_path):
    import math

    import uranometria.annotate.model as model

    rot = dict(M51_SOLUTION)
    del rot["scale_arcsec_px"]
    # 45-degree rotated CD matrix at 1.2"/px
    s = 1.2 / 3600.0
    c = math.cos(math.radians(45)) * s
    rot.update(cd1_1=c, cd1_2=c, cd2_1=-c, cd2_2=c)
    monkeypatch.setattr(model, "solve", lambda image, **kw: rot)
    monkeypatch.setattr(model, "_image_size", lambda image: (1000, 1000))
    m = model.build_model(tmp_path / "f.fit", allow_online=False)
    assert m["solved"]["scale_arcsec_px"] == pytest.approx(1.2, rel=1e-3)


def test_model_online_star_assembly(monkeypatch, tmp_path):
    import uranometria.annotate.model as model

    named = [
        {
            "designation": "HD 117815",
            "ra": 202.86,
            "dec": 47.27,
            "mag": 7.08,
            "band": "V",
            "sp_type": "A5",
            "dist_pc": 112,
        }
    ]
    field = [
        # duplicate of the named star within 3": must be skipped
        {
            "designation": "Gaia DR3 1",
            "ra": 202.86,
            "dec": 47.27,
            "mag": 7.1,
            "band": "G",
            "dist_pc": 112,
        },
        {
            "designation": "TYC 3463-582-1",
            "ra": 202.7,
            "dec": 47.1,
            "mag": 10.9,
            "band": "G",
            "dist_pc": 980,
        },
        {
            "designation": "Gaia DR3 2",
            "ra": 202.4,
            "dec": 47.3,
            "mag": 12.0,
            "band": "G",
            "dist_pc": None,
        },
    ]
    monkeypatch.setattr(model, "solve", lambda image, **kw: dict(M51_SOLUTION))
    monkeypatch.setattr(model, "_image_size", lambda image: (3872, 2192))
    monkeypatch.setattr(model, "named_bright_stars", lambda *a, **k: named)
    monkeypatch.setattr(model, "stars_in_field", lambda *a, **k: field)
    m = model.build_model(tmp_path / "f.fit", allow_online=True, max_stars=15)
    stars = [o for o in m["objects"] if o["kind"] == "star"]
    assert [s["designation"] for s in stars] == [
        "HD 117815",
        "TYC 3463-582-1",
        "Gaia DR3 2",
    ]  # named first, Gaia-duplicate-of-named dropped
    assert stars[0]["named"] is True and stars[0]["type"] == "Star (A5)"
    assert stars[1]["key"] == 1 and stars[2]["key"] == 2
    assert m["solved"]["pixel_frame"] == "fits0"


def test_links_common_name_branch():
    from uranometria.annotate.model import _links

    links = _links("NGC 7380", "Wizard Nebula")
    assert links["wikipedia"] == "https://en.wikipedia.org/wiki/Wizard_Nebula"
    assert "NGC+7380" in links["simbad"]
    assert "wikipedia" not in _links("TYC 1-2-3")


def test_image_size_real_files(tmp_path):
    import numpy as np
    from astropy.io import fits
    from PIL import Image

    from uranometria.annotate.model import _image_size

    f = tmp_path / "t.fit"
    fits.PrimaryHDU(np.zeros((7, 9), dtype=np.uint8)).writeto(f)
    assert _image_size(f) == (9, 7)
    j = tmp_path / "t.jpg"
    Image.new("RGB", (11, 5)).save(j)
    assert _image_size(j) == (11, 5)


def test_cli_annotate_offline(monkeypatch, tmp_path):
    from click.testing import CliRunner

    import uranometria.annotate as annotate_pkg
    from uranometria.cli import main

    img = tmp_path / "stack.fit"
    img.write_bytes(b"fake")
    fake_model = {
        "schema": 1,
        "image": "stack.fit",
        "image_size": [10, 10],
        "solved": {
            "pixel_frame": "fits0",
            "center_ra": 1.0,
            "center_dec": 2.0,
            "scale_arcsec_px": 1.2,
            "fov_deg": [1.0, 0.5],
            "rotation_deg": 0.0,
            "solver": "ASTAP",
        },
        "generated": "2026-01-01T00:00:00+00:00",
        "objects": [{"kind": "dso", "designation": "M31"}],
        "warnings": ["offline: field stars omitted"],
    }
    monkeypatch.setattr(annotate_pkg, "build_model", lambda image, **kw: fake_model)
    result = CliRunner().invoke(main, ["annotate", str(img), "--offline"])
    assert result.exit_code == 0, result.output
    out = tmp_path / "stack.fit.annotations.json"  # default output name
    assert out.is_file()
    assert "1 DSOs, 0 stars" in result.output


def test_str_or_none_masks():
    import numpy as np

    from uranometria.annotate.field import _str_or_none

    assert _str_or_none("A5") == "A5"
    assert _str_or_none(None) is None
    assert _str_or_none("") is None
    assert _str_or_none("--") is None
    assert _str_or_none(np.ma.masked) is None  # stringifies to '--'


def test_cli_annotate_reports_value_errors(monkeypatch, tmp_path):
    from click.testing import CliRunner

    import uranometria.annotate as annotate_pkg
    from uranometria.cli import main

    img = tmp_path / "bad.fit"
    img.write_bytes(b"x")

    def boom(image, **kw):
        raise ValueError("no image data in bad.fit")

    monkeypatch.setattr(annotate_pkg, "build_model", boom)
    result = CliRunner().invoke(main, ["annotate", str(img)])
    assert result.exit_code != 0
    assert "no image data" in result.output
    assert "Traceback" not in result.output
