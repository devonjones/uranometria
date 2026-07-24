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
            "dist_ly": 365,
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
            "dist_ly": 365,
        },
        {
            "designation": "TYC 3463-582-1",
            "ra": 202.7,
            "dec": 47.1,
            "mag": 10.9,
            "band": "G",
            "dist_ly": 3196,
        },
        {
            "designation": "Gaia DR3 2",
            "ra": 202.4,
            "dec": 47.3,
            "mag": 12.0,
            "band": "G",
            "dist_ly": None,
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


def test_cli_annotate_reports_os_errors(monkeypatch, tmp_path):
    from click.testing import CliRunner

    import uranometria.annotate as annotate_pkg
    from uranometria.cli import main

    img = tmp_path / "locked.fit"
    img.write_bytes(b"x")

    def boom(image, **kw):
        raise OSError("permission denied reading locked.fit")

    monkeypatch.setattr(annotate_pkg, "build_model", boom)
    result = CliRunner().invoke(main, ["annotate", str(img)])
    assert result.exit_code != 0
    assert "permission denied" in result.output
    assert "Traceback" not in result.output


# ---- PNG renderer (uranometria-2) ------------------------------------------


def _tiny_model(w=80, h=60):
    return {
        "schema": 1,
        "image": "tiny.jpg",
        "image_size": [w, h],
        "solved": {
            "pixel_frame": "fits0",
            "cd": [[-0.00033, 0.00001], [0.00001, 0.00033]],
            "center_ra": 202.5,
            "center_dec": 47.2,
            "scale_arcsec_px": 1.19,
            "fov_deg": [0.03, 0.02],
            "rotation_deg": 178.0,
            "solver": "ASTAP",
        },
        "generated": "2026-01-01T00:00:00+00:00",
        "objects": [
            {
                "kind": "dso",
                "designation": "M51",
                "name": "Whirlpool Galaxy",
                "type": "Galaxy",
                "ra": 202.47,
                "dec": 47.2,
                "x": 30.0,
                "y": 25.0,
                "links": {},
            },
            {
                "kind": "star",
                "named": True,
                "designation": "HD 1",
                "type": "Star (A5)",
                "ra": 202.6,
                "dec": 47.3,
                "x": 60.0,
                "y": 15.0,
                "mag": 7.0,
                "band": "V",
                "dist_ly": 326,
                "links": {},
            },
            {
                "kind": "star",
                "named": False,
                "key": 1,
                "designation": "TYC 1-2-3",
                "ra": 202.4,
                "dec": 47.1,
                "x": 20.0,
                "y": 45.0,
                "mag": 10.5,
                "band": "G",
                "dist_ly": 1631,
                "links": {},
            },
        ],
        "warnings": [],
    }


def test_compass_vectors():
    from uranometria.annotate.render_png import compass_vectors

    # identity CD: +y pixel = +north, +x pixel = +east IN ARRAY SPACE.
    # With origin='upper' display, +y renders downward, so such an image
    # correctly shows its N arrow pointing down — not a sign error.
    north, east = compass_vectors([[1e-4, 0.0], [0.0, 1e-4]])
    assert north == pytest.approx((0.0, 1.0))
    assert east == pytest.approx((1.0, 0.0))
    # mirrored x (typical sky image): east flips, north stays
    north, east = compass_vectors([[-1e-4, 0.0], [0.0, 1e-4]])
    assert north == pytest.approx((0.0, 1.0))
    assert east == pytest.approx((-1.0, 0.0))


def test_dso_color_classes():
    from uranometria.annotate.render_png import COLORS, dso_color

    assert dso_color("Galaxy") == COLORS["galaxy"]
    assert dso_color("Planetary nebula") == COLORS["planetary"]
    assert dso_color("Emission nebula (H II)") == COLORS["emission"]
    assert dso_color("Dark nebula") == COLORS["dark"]
    assert dso_color("Open cluster") == COLORS["cluster"]
    # In the annotator, Cl+N reads as the cluster: the Sharpless nebula is
    # separately labeled (NGC 7380 orange beside Sh2-142 pink)
    assert dso_color("Cluster + nebula") == COLORS["cluster"]


def test_render_png_smoke(tmp_path):
    from PIL import Image

    from uranometria.annotate.render_png import render_png

    img = tmp_path / "tiny.jpg"
    Image.new("RGB", (80, 60), (8, 10, 24)).save(img)
    out = tmp_path / "tiny_annotated.png"
    render_png(_tiny_model(), img, out)
    with Image.open(out) as rendered:
        w, h = rendered.size
    assert w > 80  # legend panel added
    assert h >= 59


def test_render_png_size_mismatch(tmp_path):
    from PIL import Image

    from uranometria.annotate.render_png import render_png

    img = tmp_path / "wrong.jpg"
    Image.new("RGB", (50, 50)).save(img)
    with pytest.raises(ValueError, match="same image"):
        render_png(_tiny_model(), img, tmp_path / "x.png")


def test_raster_model_uses_raster_frame(monkeypatch, tmp_path):
    """JPEG-solved models convert ASTAP's bottom-up y into the raster's own
    top-down frame (the NGC 7380 mirrored-circles bug)."""
    import uranometria.annotate.model as model

    H = 2192
    monkeypatch.setattr(model, "solve", lambda image, **kw: dict(M51_SOLUTION))
    monkeypatch.setattr(model, "_image_size", lambda image: (3872, H))

    fits_m = model.build_model(tmp_path / "img.fit", allow_online=False)
    jpg_m = model.build_model(tmp_path / "img.jpg", allow_online=False)
    assert fits_m["solved"]["pixel_frame"] == "fits0"
    assert jpg_m["solved"]["pixel_frame"] == "raster0"

    f = {o["designation"]: o for o in fits_m["objects"]}
    j = {o["designation"]: o for o in jpg_m["objects"]}
    for name in f:
        assert j[name]["x"] == pytest.approx(f[name]["x"])
        assert j[name]["y"] == pytest.approx((H - 1) - f[name]["y"], abs=0.11)
    # CD y-column negated so the compass renders truthfully in the new frame
    assert jpg_m["solved"]["cd"][0][1] == pytest.approx(-fits_m["solved"]["cd"][0][1])
    assert jpg_m["solved"]["cd"][1][1] == pytest.approx(-fits_m["solved"]["cd"][1][1])


def test_cli_annotate_png_import_error(monkeypatch, tmp_path):
    from click.testing import CliRunner

    import uranometria.annotate as annotate_pkg
    import uranometria.annotate.render_png as rp
    from uranometria.cli import main

    img = tmp_path / "s.fit"
    img.write_bytes(b"x")
    monkeypatch.setattr(annotate_pkg, "build_model", lambda image, **kw: _tiny_model())

    def no_mpl(*a, **k):
        raise ImportError("No module named 'matplotlib'")

    monkeypatch.setattr(rp, "render_png", no_mpl)
    result = CliRunner().invoke(main, ["annotate", str(img), "--offline", "--png"])
    assert result.exit_code != 0
    assert "[annotate] extra" in result.output
    assert "Traceback" not in result.output


# ---- PR #3 review round 1 ---------------------------------------------------


def test_hms_dms_carry():
    from uranometria.annotate.render_png import _dms, _hms

    assert _hms(0.249975) == "00h01m00s"  # carries, not 00h00m60s
    assert _hms(359.9999) == "00h00m00s"  # wraps at 24h
    assert _hms(202.51666) == "13h30m04s"
    assert _dms(10.34999) == "+10°21′00″"  # carries, not 10°20′60″
    assert _dms(-5.39) == "−5°23′24″"


def test_short_desig():
    from uranometria.annotate.render_png import _short_desig

    assert _short_desig("TYC 3463-582-1") == "TYC 3463-582-1"
    short = _short_desig("Gaia DR3 2062360626011542272")
    assert len(short) <= 20 and short.startswith("Gaia …") and short.endswith("2272")
    assert len(_short_desig("X" * 30)) == 20


def test_needs_flip():
    from uranometria.annotate.render_png import needs_flip

    assert needs_flip("fits0", "a.jpg") is True  # fits model onto raster export
    assert needs_flip("fits0", "a.fit") is False
    assert needs_flip("raster0", "a.jpg") is False
    assert needs_flip("raster0", "a.fits") is True
    assert needs_flip(None, "a.fit") is False  # pre-0.5 models default to fits0


def test_default_title_picks_nearest_dso():
    from uranometria.annotate.render_png import _default_title

    m = _tiny_model()
    m["objects"].append(
        {
            "kind": "dso",
            "designation": "IC 999",
            "name": None,
            "type": "Galaxy",
            "ra": 1,
            "dec": 1,
            "x": 41.0,
            "y": 31.0,
            "links": {},
        }
    )
    # IC 999 sits at the exact center (80x60 image): it wins over M51 at (30,25)
    assert _default_title(m) == "IC 999"
    m["objects"] = [o for o in m["objects"] if o["designation"] != "IC 999"]
    assert _default_title(m) == "M51 / Whirlpool Galaxy"


def test_render_fits_branch_and_no_cd(tmp_path):
    import numpy as np
    from astropy.io import fits
    from PIL import Image

    from uranometria.annotate.render_png import render_png

    rng = np.random.default_rng(7)
    data = (rng.random((3, 60, 80)) * 1000).astype("float32")  # RGB planes
    f = tmp_path / "t.fit"
    fits.PrimaryHDU(data).writeto(f)
    m = _tiny_model()
    m["image"] = "t.fit"
    del m["solved"]["cd"]  # pre-0.5 model: compass silently skipped
    out = tmp_path / "t_annotated.png"
    render_png(m, f, out)
    with Image.open(out) as im:
        assert im.size[0] > 80


def test_cli_render_command(tmp_path):
    import json

    from click.testing import CliRunner
    from PIL import Image

    from uranometria.cli import main

    img = tmp_path / "tiny.jpg"
    Image.new("RGB", (80, 60), (5, 5, 20)).save(img)
    model_path = tmp_path / "m.json"
    m = _tiny_model()
    m["solved"]["pixel_frame"] = "raster0"  # matches the jpg: no flip
    model_path.write_text(json.dumps(m))
    result = CliRunner().invoke(main, ["render", str(model_path), str(img)])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "tiny_annotated.png").is_file()  # default output name


def test_cli_annotate_png_success(monkeypatch, tmp_path):
    from click.testing import CliRunner
    from PIL import Image

    import uranometria.annotate as annotate_pkg
    from uranometria.cli import main

    img = tmp_path / "tiny.jpg"
    Image.new("RGB", (80, 60), (5, 5, 20)).save(img)
    m = _tiny_model()
    m["solved"]["pixel_frame"] = "raster0"
    monkeypatch.setattr(annotate_pkg, "build_model", lambda image, **kw: m)
    result = CliRunner().invoke(main, ["annotate", str(img), "--offline", "--png"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "tiny_annotated.png").is_file()


def test_dso_aliases_collected():
    from uranometria.annotate.field import dsos_in_field

    hits = dsos_in_field(202.5167, 47.2064, 0.3)
    m51 = next(h for h in hits if h["disp"] == "M51")
    assert "NGC 5194" in m51["aliases"]


def test_load_image_edge_cases(tmp_path):
    import numpy as np
    from astropy.io import fits

    from uranometria.annotate.render_png import _load_image

    # (1, H, W) singleton cube squeezes to mono
    f1 = tmp_path / "mono.fit"
    fits.PrimaryHDU(np.ones((1, 5, 8), dtype="float32")).writeto(f1)
    assert _load_image(f1).shape == (5, 8)
    # NaN borders (drizzle edges) don't poison the stretch
    data = np.ones((6, 9), dtype="float32")
    data[0, :] = np.nan
    data[2, 3] = 50.0
    f2 = tmp_path / "nan.fit"
    fits.PrimaryHDU(data).writeto(f2)
    out = _load_image(f2)
    assert np.isfinite(out).all()
    # header-only FITS reports a clear error
    f3 = tmp_path / "empty.fit"
    fits.PrimaryHDU().writeto(f3)
    with pytest.raises(ValueError, match="no image data"):
        _load_image(f3)


def test_render_applies_cross_frame_flip(tmp_path):
    """A fits0 model composited onto a JPEG must draw at flipped y — pins the
    render-time flip block itself, not just the needs_flip helper."""
    import numpy as np
    from PIL import Image

    from uranometria.annotate.render_png import render_png

    W, H = 200, 150
    img = tmp_path / "t.jpg"
    Image.new("RGB", (W, H), (0, 0, 0)).save(img)
    m = _tiny_model(W, H)
    m["image"] = "t.jpg"
    m["solved"]["pixel_frame"] = "fits0"  # jpg target => flip must apply
    m["objects"] = [
        {
            "kind": "star",
            "named": False,
            "key": 1,
            "designation": "T",
            "ra": 0.0,
            "dec": 0.0,
            "x": 40.0,
            "y": 20.0,
            "mag": 10.0,
            "band": "G",
            "dist_ly": None,
            "links": {},
        }
    ]
    out = tmp_path / "o.png"
    render_png(m, img, out)
    a = np.asarray(Image.open(out).convert("RGB"), dtype=int)

    def green_pixels(cy):
        win = a[max(0, cy - 7) : cy + 8, 30:52]
        return int(((win[:, :, 1] > 140) & (win[:, :, 0] < 140)).sum())

    assert green_pixels((H - 1) - 20) > 0  # circle drawn at the flipped row
    assert green_pixels(20) == 0  # nothing at the unflipped row


def test_dso_redshift_distance_offline(monkeypatch, tmp_path):
    import uranometria.annotate.model as model

    monkeypatch.setattr(model, "solve", lambda image, **kw: dict(M51_SOLUTION))
    monkeypatch.setattr(model, "_image_size", lambda image: (3872, 2192))
    m = model.build_model(tmp_path / "f.fit", allow_online=False)
    m51 = next(o for o in m["objects"] if o["designation"] == "M51")
    # Hubble-flow from OpenNGC redshift: ~22 Mly for M51
    assert 15e6 < m51["dist_ly"] < 32e6


def test_dso_distances_merge_and_failure(monkeypatch, tmp_path):
    import uranometria.annotate.model as model

    monkeypatch.setattr(model, "solve", lambda image, **kw: dict(M51_SOLUTION))
    monkeypatch.setattr(model, "_image_size", lambda image: (3872, 2192))
    monkeypatch.setattr(model, "named_bright_stars", lambda *a, **k: [])
    monkeypatch.setattr(model, "stars_in_field", lambda *a, **k: [])
    monkeypatch.setattr(model, "dso_distances", lambda desigs: {"IC 4277": 500_000_000})
    m = model.build_model(tmp_path / "f.fit", allow_online=True)
    ic = next(o for o in m["objects"] if o["designation"] == "IC 4277")
    assert ic["dist_ly"] == 500_000_000  # SIMBAD fill for redshift-less DSOs

    def boom(desigs):
        raise RuntimeError("simbad down")

    monkeypatch.setattr(model, "dso_distances", boom)
    m = model.build_model(tmp_path / "f.fit", allow_online=True)
    assert any("distance lookup failed" in w for w in m["warnings"])


def test_star_dist_ly_passthrough(monkeypatch, tmp_path):
    import uranometria.annotate.model as model

    monkeypatch.setattr(model, "solve", lambda image, **kw: dict(M51_SOLUTION))
    monkeypatch.setattr(model, "_image_size", lambda image: (3872, 2192))
    monkeypatch.setattr(model, "dso_distances", lambda desigs: {})
    monkeypatch.setattr(model, "named_bright_stars", lambda *a, **k: [])
    monkeypatch.setattr(
        model,
        "stars_in_field",
        lambda *a, **k: [
            {
                "designation": "TYC 1-1-1",
                "ra": 202.7,
                "dec": 47.1,
                "mag": 10.9,
                "band": "G",
                "dist_ly": 3196,
            }
        ],
    )
    m = model.build_model(tmp_path / "f.fit", allow_online=True)
    star = next(o for o in m["objects"] if o["kind"] == "star")
    assert star["dist_ly"] == 3196


def test_place_label_never_flips_anchor():
    """The strike-through invariant: anchor side always matches the leader
    direction, even for objects hard against the frame edges."""
    from uranometria.annotate.render_png import _place_label

    W, H = 1000, 800

    def no_crossings(*a):
        return 0

    for x, y in [(950, 400), (990, 100), (30, 400), (500, 30), (500, 770), (950, 770)]:
        lx, ly, ha = _place_label(x, y, W, H, W / 2, H / 2, [], no_crossings)
        assert (lx >= x) == (ha == "left"), (x, y, lx, ha)
        assert 0.02 * W <= lx <= 0.98 * W


# ---- standalone HTML page (uranometria-3) -----------------------------------


def test_render_html_standalone(tmp_path):
    from PIL import Image

    from uranometria.annotate.render_html import render_html

    img = tmp_path / "tiny.jpg"
    Image.new("RGB", (80, 60), (5, 5, 20)).save(img)
    m = _tiny_model()
    m["solved"]["pixel_frame"] = "raster0"
    m["objects"][0]["aliases"] = ["NGC 5194"]
    m["objects"][0]["dist_ly"] = 22_000_000
    m["objects"][0]["links"] = {"simbad": "https://simbad/x", "wikipedia": "https://wiki/x"}
    out = tmp_path / "page.html"
    render_html(m, img, out)
    page = out.read_text()
    assert "data:image/jpeg;base64," in page  # image embedded, self-contained
    assert "attachPanZoom" in page
    assert 'id="labels"' in page  # LABELS toggle
    assert "M51 · NGC 5194" in page  # aliases in the sidebar
    assert "~22 Mly" in page  # distance formatted
    assert 'href="https://simbad/x"' in page and "Wikipedia" in page
    assert 'id="search"' in page


def test_render_html_fits_source_flips_nothing(tmp_path):
    import numpy as np
    from astropy.io import fits

    from uranometria.annotate.render_html import render_html

    data = (np.ones((3, 60, 80)) * 500).astype("float32")
    f = tmp_path / "t.fit"
    fits.PrimaryHDU(data).writeto(f)
    m = _tiny_model()
    m["image"] = "t.fit"  # fits0 model + fits render: direct coordinates
    out = tmp_path / "page.html"
    render_html(m, f, out)
    page = out.read_text()
    assert "--ty:25.0px" in page  # M51 y unchanged
    assert "data:image/jpeg;base64," in page  # stretched render embedded


def test_cli_render_html(tmp_path):
    import json

    from click.testing import CliRunner
    from PIL import Image

    from uranometria.cli import main

    img = tmp_path / "tiny.jpg"
    Image.new("RGB", (80, 60)).save(img)
    m = _tiny_model()
    m["solved"]["pixel_frame"] = "raster0"
    mp = tmp_path / "m.json"
    mp.write_text(json.dumps(m))
    result = CliRunner().invoke(main, ["render", str(mp), str(img), "--html"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "tiny_annotated.html").is_file()


def test_cluster_nebula_distance_harmonized(monkeypatch, tmp_path):
    """Sh2-142 and NGC 7380 are one complex: the nebula inherits the
    cluster's (better-measured) distance instead of a contradictory one."""
    import uranometria.annotate.model as model

    monkeypatch.setattr(model, "solve", lambda image, **kw: dict(M51_SOLUTION))
    monkeypatch.setattr(model, "_image_size", lambda image: (3872, 2192))
    monkeypatch.setattr(model, "named_bright_stars", lambda *a, **k: [])
    monkeypatch.setattr(model, "stars_in_field", lambda *a, **k: [])

    def fake_dsos(*a, **k):
        return [
            {
                "disp": "NGC 7380",
                "common": "",
                "type": "Cluster + nebula",
                "constellation": "Cepheus",
                "ra": 202.5,
                "dec": 47.2,
                "z": None,
                "aliases": [],
                "sep_deg": 0.0,
            },
            {
                "disp": "Sh2-142",
                "common": "",
                "type": "Emission nebula (H II)",
                "constellation": "",
                "ra": 202.55,
                "dec": 47.25,
                "z": None,
                "aliases": [],
                "sep_deg": 0.05,
            },
        ]

    monkeypatch.setattr(model, "dsos_in_field", fake_dsos)
    monkeypatch.setattr(model, "dso_distances", lambda d: {"NGC 7380": 7247, "Sh2-142": 11350})
    m = model.build_model(tmp_path / "f.fit", allow_online=True)
    dso = {o["designation"]: o for o in m["objects"] if o["kind"] == "dso"}
    assert dso["NGC 7380"]["dist_ly"] == 7247
    assert dso["Sh2-142"]["dist_ly"] == 7247  # inherited from the cluster


def test_fmt_dist_ly_approx():
    from uranometria.annotate.render_png import fmt_dist_ly

    assert fmt_dist_ly(7247, approx=True) == "~7,200 ly"
    assert fmt_dist_ly(7247) == "7,247 ly"
    assert fmt_dist_ly(365) == "365 ly"
    assert fmt_dist_ly(22_000_000, approx=True) == "~22 Mly"
