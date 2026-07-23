import pytest

import uranometria
from uranometria.catalog import Catalog, fmt_coord, parse_angle

@pytest.fixture(scope="module")
def catalog():
    return Catalog()

def test_parse_angle_formats():
    assert parse_angle(83.63, True) == pytest.approx(83.63)
    assert parse_angle("20h15m22s", True) == pytest.approx(303.8417, abs=1e-3)
    assert parse_angle("20:15:22", True) == pytest.approx(303.8417, abs=1e-3)
    assert parse_angle("+38 21 18", False) == pytest.approx(38.355, abs=1e-3)
    assert parse_angle("-05d23m28s", False) == pytest.approx(-5.3911, abs=1e-3)

def test_fmt_coord():
    assert fmt_coord(10.68, 41.27) == "00h 43m  +41° 16′"

@pytest.mark.parametrize("desig,disp,dec", [
    ("M31", "M31", 41.27),
    ("M45", "M45", 24.1),             # Messier special case via addendum
    ("ngc 7380", "NGC 7380", 58.06),
    ("Sh2-142", "Sh2-142", 58.10),
    ("C9", "C9", 62.5),               # Caldwell without an NGC number (Cave Nebula)
    ("Caldwell 14", "C14", 57.1),     # Double Cluster — Caldwell addendum entry
    ("B33", "B33", -2.46),            # Barnard 33 (Horsehead)
])
def test_catalog_lookup(catalog, desig, disp, dec):
    rec = catalog.lookup(desig)
    assert rec is not None, desig
    assert rec["disp"] == disp
    assert rec["dec"] == pytest.approx(dec, abs=0.2)

def test_common_name_lookup(catalog):
    assert catalog.lookup("Pleiades")["common"] == "Pleiades"

def test_generate_northern(tmp_path):
    out = tmp_path / "map.html"
    warnings = uranometria.generate({"objects": ["M31", "M42"]}, out, allow_online=False)
    html = out.read_text()
    assert warnings == []
    assert html.count('<svg class="sky"') == 1
    assert 'id="mk-0"' in html and 'id="mk-1"' in html

def test_generate_auto_southern(tmp_path):
    out = tmp_path / "map.html"
    uranometria.generate({"objects": ["M31", "NGC 104"]}, out, allow_online=False)
    html = out.read_text()
    assert html.count('<svg class="sky"') == 2

def test_manual_entry_and_color(tmp_path):
    cfg = {"objects": [{"label": "X-1", "name": "Test", "type": "Nebula",
                        "constellation": "Cygnus", "ra": "20h15m22s",
                        "dec": "+38 21 18", "color": "#7EC8A0"}]}
    out = tmp_path / "map.html"
    assert uranometria.generate(cfg, out) == []
    assert "--accent:#7EC8A0" in out.read_text()

def test_image_validation(tmp_path):
    (tmp_path / "pic.jpg").write_bytes(b"\xff\xd8fake")
    cfg = {"objects": [{"id": "M31", "image": "pic.jpg"},
                       {"id": "M42", "image": "missing.jpg"}]}
    out = tmp_path / "map.html"
    warnings = uranometria.generate(cfg, out, allow_online=False)
    html = out.read_text()
    assert 'data-img="pic.jpg"' in html
    assert 'data-img="missing.jpg"' not in html
    assert any("missing.jpg" in w for w in warnings)

def test_unresolvable_offline(tmp_path):
    warnings = uranometria.generate({"objects": ["M31", "vdB 141"]},
                               tmp_path / "map.html", allow_online=False)
    assert any("vdB 141" in w for w in warnings)

def test_no_objects_raises(tmp_path):
    with pytest.raises(uranometria.SkymapError):
        uranometria.generate({"objects": []}, tmp_path / "map.html")

def test_interactive_ui_hooks(tmp_path):
    out = tmp_path / "map.html"
    uranometria.generate({"objects": ["M31", "M42"]}, out, allow_online=False)
    html = out.read_text()
    assert 'id="search"' in html                  # sidebar search box
    assert '--tx:' in html                        # counter-scaled markers
    assert "SCROLL TO ZOOM" in html               # pan/zoom wiring
    assert 'class="panel legend"' in html         # independent scroll pane

def test_hemisphere_toggle(tmp_path):
    out = tmp_path / "map.html"
    uranometria.generate({"objects": ["M31", "NGC 104"]}, out, allow_online=False)
    html = out.read_text()
    assert 'id="hemitoggle"' in html
    assert 'data-hemi="north"' in html and 'data-hemi="south"' in html
    assert 'class="chart hidden" data-hemi="south"' in html   # south starts hidden
    uranometria.generate({"objects": ["M31", "M42"]}, out, allow_online=False)
    assert 'id="hemitoggle"' not in out.read_text()           # no toggle when single
