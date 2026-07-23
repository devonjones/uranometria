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


@pytest.mark.parametrize(
    "desig,disp,dec",
    [
        ("M31", "M31", 41.27),
        ("M45", "M45", 24.1),  # Messier special case via addendum
        ("ngc 7380", "NGC 7380", 58.06),
        ("Sh2-142", "Sh2-142", 58.10),
        ("C9", "C9", 62.5),  # Caldwell without an NGC number (Cave Nebula)
        ("Caldwell 14", "C14", 57.1),  # Double Cluster — Caldwell addendum entry
        ("B33", "B33", -2.46),  # Barnard 33 (Horsehead)
    ],
)
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
    cfg = {
        "objects": [
            {
                "label": "X-1",
                "name": "Test",
                "type": "Nebula",
                "constellation": "Cygnus",
                "ra": "20h15m22s",
                "dec": "+38 21 18",
                "color": "#7EC8A0",
            }
        ]
    }
    out = tmp_path / "map.html"
    assert uranometria.generate(cfg, out) == []
    assert "--accent:#7EC8A0" in out.read_text()


def test_image_validation(tmp_path):
    (tmp_path / "pic.jpg").write_bytes(b"\xff\xd8fake")
    cfg = {"objects": [{"id": "M31", "image": "pic.jpg"}, {"id": "M42", "image": "missing.jpg"}]}
    out = tmp_path / "map.html"
    warnings = uranometria.generate(cfg, out, allow_online=False)
    html = out.read_text()
    assert 'data-img="pic.jpg"' in html
    assert 'data-img="missing.jpg"' not in html
    assert any("missing.jpg" in w for w in warnings)


def test_unresolvable_offline(tmp_path):
    warnings = uranometria.generate(
        {"objects": ["M31", "vdB 141"]}, tmp_path / "map.html", allow_online=False
    )
    assert any("vdB 141" in w for w in warnings)


def test_no_objects_raises(tmp_path):
    with pytest.raises(uranometria.SkymapError):
        uranometria.generate({"objects": []}, tmp_path / "map.html")


def test_interactive_ui_hooks(tmp_path):
    out = tmp_path / "map.html"
    uranometria.generate({"objects": ["M31", "M42"]}, out, allow_online=False)
    html = out.read_text()
    assert 'id="search"' in html  # sidebar search box
    assert "--tx:" in html  # counter-scaled markers
    assert "SCROLL TO ZOOM" in html  # pan/zoom wiring
    assert 'class="panel legend"' in html  # independent scroll pane


def test_hemisphere_toggle(tmp_path):
    out = tmp_path / "map.html"
    uranometria.generate({"objects": ["M31", "NGC 104"]}, out, allow_online=False)
    html = out.read_text()
    assert 'id="hemitoggle"' in html
    assert 'data-hemi="north"' in html and 'data-hemi="south"' in html
    assert 'class="chart hidden" data-hemi="south"' in html  # south starts hidden
    uranometria.generate({"objects": ["M31", "M42"]}, out, allow_online=False)
    assert 'id="hemitoggle"' not in out.read_text()  # no toggle when single


def test_sky_view_orientation():
    from uranometria.chart import CX, project

    # Sky view: RA 6h sits right of center on a northern disc (RA clockwise
    # from 0h at top), left of center on a southern disc.
    assert project(90, 0)[0] > CX
    assert project(90, 0, south=True)[0] < CX
    # Mirror (celestial-globe) view flips both.
    assert project(90, 0, mirror=True)[0] < CX
    assert project(90, 0, south=True, mirror=True)[0] > CX


def test_mirror_config(tmp_path):
    out = tmp_path / "map.html"
    uranometria.generate({"objects": ["M31"]}, out, allow_online=False)
    assert "sky view" in out.read_text()
    uranometria.generate({"objects": ["M31"], "mirror": True}, out, allow_online=False)
    assert "mirrored (globe) view" in out.read_text()


# ---- review-fixes: catalog bugs -------------------------------------------


def test_m102_resolves_offline(catalog):
    rec = catalog.lookup("M102")
    assert rec is not None
    assert rec["dec"] == pytest.approx(54.35, abs=0.2)


def test_mel_identifier_lookup(catalog):
    rec = catalog.lookup("Mel 25")
    assert rec is not None
    assert rec["common"] == "Hyades"


def test_dup_resolves_to_crossref(catalog):
    rec = catalog.lookup("IC 11")
    tgt = catalog.lookup("NGC 281")
    assert rec["disp"] == "IC 11"
    assert rec["ra"] == pytest.approx(tgt["ra"])
    assert rec["dec"] == pytest.approx(tgt["dec"])


def test_nonex_skipped(catalog):
    assert catalog.lookup("IC 67") is None


# ---- review-fixes: angle parsing and formatting ----------------------------


def test_parse_angle_edge_branches():
    assert parse_angle("83.63", True) == pytest.approx(83.63)  # string decimal RA: no *15
    assert parse_angle("-38:21:18", False) == pytest.approx(-38.355, abs=1e-3)
    assert parse_angle("20 15 22", True) == pytest.approx(303.8417, abs=1e-3)  # bare RA heuristic
    assert parse_angle("30 30", False) == pytest.approx(30.5)
    with pytest.raises(ValueError):
        parse_angle("°", True)
    with pytest.raises(ValueError):
        parse_angle("garbage", True)


def test_parse_angle_explicit_degree_cue():
    # an explicit d/° marker means degrees even for RA <= 24
    assert parse_angle("20d15m00s", True) == pytest.approx(20.25)
    assert parse_angle("20°15′00″", True) == pytest.approx(20.25)


def test_fmt_coord_rollover():
    assert fmt_coord(29.999, -29.9999) == "02h 00m  −30° 00′"
    assert fmt_coord(359.995, 0).startswith("00h 00m")  # not 24h


# ---- review-fixes: contract and error handling ----------------------------


def test_bad_manual_radec_warns_not_raises(tmp_path):
    cfg = {"objects": ["M31", {"label": "X", "ra": "garbage", "dec": "+38 21 18"}]}
    out = tmp_path / "map.html"
    warnings = uranometria.generate(cfg, out, allow_online=False)
    assert any("bad ra/dec" in w for w in warnings)
    assert 'id="mk-0"' in out.read_text()  # M31 still charted


def test_bad_mag_limit_raises_skymap_error(tmp_path):
    with pytest.raises(uranometria.SkymapError, match="mag_limit"):
        uranometria.generate({"objects": ["M31"], "mag_limit": "bright"}, tmp_path / "m.html")


def test_entry_without_id_or_coords_warns():
    from uranometria.core import resolve_objects

    objs, warns = resolve_objects([{"label": "??"}], allow_online=False)
    assert objs == [] and any("neither 'id' nor ra/dec" in w for w in warns)


def test_sesame_failure_warns(monkeypatch):
    import http.client

    import uranometria.core as core

    def boom(desig):
        raise http.client.BadStatusLine("garbled")

    monkeypatch.setattr(core, "sesame", boom)
    objs, warns = core.resolve_objects(["vdB 141"], allow_online=True)
    assert objs == [] and any("Sesame lookup failed" in w for w in warns)

    def oserr(desig):
        raise OSError("connection refused")

    monkeypatch.setattr(core, "sesame", oserr)
    objs, warns = core.resolve_objects(["vdB 141"], allow_online=True)
    assert objs == [] and any("Sesame lookup failed" in w for w in warns)


def test_sesame_parses_response(monkeypatch):
    import io
    import urllib.request

    from uranometria.catalog import sesame

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda req, timeout=15: Resp(b"# header\n%J 303.841 +38.355 = target\n"),
    )
    rec = sesame("vdB 141")
    assert rec["ra"] == pytest.approx(303.841)
    assert rec["dec"] == pytest.approx(38.355)

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=15: Resp(b"nothing here"))
    assert sesame("junk") is None


# ---- review-fixes: rendering branches --------------------------------------


def test_band_object_goes_south_when_two_charts(tmp_path):
    out = tmp_path / "map.html"
    uranometria.generate({"objects": ["M31", "M42", "NGC 104"]}, out, allow_online=False)
    south = out.read_text().split('class="chart hidden" data-hemi="south"')[1]
    assert 'id="mk-1"' in south  # M42 (dec ~ -5) lands on the southern disc
    assert 'id="mk-0"' not in south  # M31 stays north


def test_image_href_branches(tmp_path):
    from uranometria.core import resolve_image

    pic = tmp_path / "a b.jpg"
    pic.write_bytes(b"x")
    assert resolve_image("https://x/y.jpg", "")[0] == "https://x/y.jpg"
    href, err = resolve_image(str(pic), "/elsewhere")
    assert err is None and href.startswith("file://") and "%20" in href


def test_render_without_image_base_warns():
    html, warns = uranometria.render(
        {"objects": [{"id": "M31", "image": "rel/pic.jpg"}]}, allow_online=False
    )
    assert any("no image_base" in w for w in warns)
    assert 'data-img="' not in html  # the JS selector literal is always present


def test_config_knobs(tmp_path):
    out = tmp_path / "map.html"
    uranometria.generate({"objects": ["M31"]}, out, allow_online=False)
    full = out.read_text()
    assert 'class="ecliptic"' in full
    uranometria.generate({"objects": ["M31"], "show_ecliptic": False}, out, allow_online=False)
    assert 'class="ecliptic"' not in out.read_text()
    uranometria.generate({"objects": ["M31"], "mag_limit": 2.0}, out, allow_online=False)
    dim = out.read_text()
    assert dim.count("<circle cx=") < full.count("<circle cx=")
    assert "magnitude 2" in dim


def test_title_entities_survive_case_transforms(tmp_path):
    out = tmp_path / "map.html"
    uranometria.generate({"objects": ["M31"], "title": "Bits & Bobs"}, out, allow_online=False)
    html = out.read_text()
    assert "BITS &amp; BOBS" in html
    assert "&Amp;" not in html and "&AMP;" not in html


# ---- review-fixes: CLI ------------------------------------------------------


def test_cli(tmp_path):
    from uranometria.cli import main

    cfg = tmp_path / "sky.yaml"
    cfg.write_text("objects: [M31]\n")
    assert main([str(cfg), "--offline", "--mirror"]) == 0
    out = tmp_path / "sky.html"  # default output name
    assert "mirrored (globe) view" in out.read_text()


def test_cli_non_mapping_yaml(tmp_path):
    from uranometria.cli import main

    cfg = tmp_path / "bad.yaml"
    cfg.write_text("- just\n- a list\n")
    with pytest.raises(SystemExit, match="not a mapping"):
        main([str(cfg)])
