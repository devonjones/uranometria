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
