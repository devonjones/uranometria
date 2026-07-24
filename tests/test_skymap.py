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
        ("M102", "M102", 54.35),  # addendum Dup row with no cross-reference
        ("Mel 25", "C41", 15.87),  # Melotte via OpenNGC Identifiers (Hyades)
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
    assert rec["type"] != "Dup"  # raw CSV type string must not reach the legend


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
    assert fmt_coord(360.0, 0).startswith("00h 00m")  # exactly 360 normalizes
    assert fmt_coord(-10.0, 0).startswith("23h 20m")  # negative RA normalizes


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
    from click.testing import CliRunner

    from uranometria.cli import main

    cfg = tmp_path / "sky.yaml"
    cfg.write_text("objects: [M31]\n")
    result = CliRunner().invoke(main, ["chart", str(cfg), "--offline", "--mirror"])
    assert result.exit_code == 0, result.output
    out = tmp_path / "sky.html"  # default output name
    assert "mirrored (globe) view" in out.read_text()


def test_cli_non_mapping_yaml(tmp_path):
    from click.testing import CliRunner

    from uranometria.cli import main

    cfg = tmp_path / "bad.yaml"
    cfg.write_text("- just\n- a list\n")
    result = CliRunner().invoke(main, ["chart", str(cfg)])
    assert result.exit_code != 0
    assert "not a mapping" in result.output


# ---- pr-review-loop round 1 -------------------------------------------------


def test_photo_and_accent_render_at_both_sites(tmp_path):
    (tmp_path / "pic.jpg").write_bytes(b"x")
    cfg = {"objects": [{"id": "M31", "image": "pic.jpg", "color": "#7EC8A0"}]}
    out = tmp_path / "map.html"
    uranometria.generate(cfg, out, allow_online=False)
    html = out.read_text()
    assert html.count('data-img="pic.jpg"') == 2  # chart marker AND legend card
    assert html.count("--accent:#7EC8A0") == 2


def test_sesame_surrogate_designation(monkeypatch):
    import io
    import urllib.request

    from uranometria.catalog import sesame

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=15: Resp(b"no match"))
    assert sesame("\ud800bad") is None  # must not raise UnicodeEncodeError


def test_non_string_entry_degrades(tmp_path):
    warnings = uranometria.generate(
        {"objects": ["M31", 141]}, tmp_path / "m.html", allow_online=False
    )
    assert any("could not resolve" in w for w in warnings)


def test_dec_out_of_range_warns(tmp_path):
    cfg = {"objects": ["M31", {"label": "X", "ra": "10 00 00", "dec": "+95"}]}
    warnings = uranometria.generate(cfg, tmp_path / "m.html", allow_online=False)
    assert any("dec out of range" in w for w in warnings)


def test_nan_mag_limit_raises(tmp_path):
    with pytest.raises(uranometria.SkymapError, match="NaN"):
        uranometria.generate({"objects": ["M31"], "mag_limit": float("nan")}, tmp_path / "m.html")


def test_dict_entry_with_non_string_id(tmp_path):
    warnings = uranometria.generate(
        {"objects": ["M31", {"id": 141}]}, tmp_path / "m.html", allow_online=False
    )
    assert any("could not resolve" in w for w in warnings)


def test_manual_ra_normalized_in_object():
    from uranometria.core import resolve_objects

    objs, _ = resolve_objects([{"label": "X", "ra": 370.0, "dec": 10.0}], allow_online=False)
    assert objs[0]["ra"] == pytest.approx(10.0)
    objs, _ = resolve_objects([{"label": "Y", "ra": -10.0, "dec": 10.0}], allow_online=False)
    assert objs[0]["ra"] == pytest.approx(350.0)


# ---- annotation overlays in the chart lightbox (uranometria-4/5) -----------


def _sidecar_model(pixel_frame="raster0", h=60):
    return {
        "schema": 1,
        "image": "pic.jpg",
        "image_size": [80, h],
        "solved": {"pixel_frame": pixel_frame},
        "objects": [
            {
                "kind": "dso",
                "designation": "M51",
                "aliases": ["NGC 5194"],
                "name": "Whirlpool Galaxy",
                "type": "Galaxy",
                "mag": 8.4,
                "band": "V",
                "dist_ly": 31000000,
                "links": {"simbad": "https://simbad.example/M51"},
                "x": 30.0,
                "y": 10.0,
            },
            {
                "kind": "star",
                "named": False,
                "key": 1,
                "designation": "TYC 1",
                "x": 50.0,
                "y": 20.0,
            },
        ],
        "warnings": [],
    }


def test_annotation_sidecar_discovery_and_flip(tmp_path):
    import json

    (tmp_path / "pic.jpg").write_bytes(b"\xff\xd8fake")
    (tmp_path / "pic.jpg.annotations.json").write_text(
        json.dumps(_sidecar_model(pixel_frame="fits0"))
    )
    cfg = {"objects": [{"id": "M31", "image": "pic.jpg"}]}
    out = tmp_path / "map.html"
    warnings = uranometria.generate(cfg, out, allow_online=False)
    assert warnings == []
    html = out.read_text()
    assert 'id="lb-annotations"' in html
    assert '"mk-0"' in html  # the annotation map carries this object
    assert '"y": 49.0' in html or '"y": 49' in html  # fits0 flipped: 59 - 10
    # enriched payload for the lightbox panel survives the embed
    assert "NGC 5194" in html
    assert "Whirlpool Galaxy" in html
    assert '"dist_ly": 31000000' in html
    assert "simbad.example/M51" in html
    assert 'id="lb-panel"' in html
    assert 'id="lb-cards"' in html
    assert 'id="lb-search"' in html  # panel search, same as the standalone page
    # embedded model: the legend ANNOTATED tag opens the lightbox in
    # annotation mode instead of linking out
    assert '<span class="annlink" role="button"' in html
    assert 'id="lb-ann"' in html and 'id="lb-expand"' in html
    assert "buildAnnotationUI" in html  # shared annotation viewer
    assert "svg.focus .ann" in html  # hover spotlight styles present


def test_annotation_sidecar_raster_no_flip(tmp_path):
    import json

    (tmp_path / "pic.jpg").write_bytes(b"x")
    (tmp_path / "pic.jpg.annotations.json").write_text(json.dumps(_sidecar_model()))
    cfg = {"objects": [{"id": "M31", "image": "pic.jpg"}]}
    out = tmp_path / "map.html"
    uranometria.generate(cfg, out, allow_online=False)
    assert '"y": 10' in out.read_text()


def test_annotation_explicit_path_and_bad_json(tmp_path):
    import json

    (tmp_path / "pic.jpg").write_bytes(b"x")
    (tmp_path / "custom.json").write_text(json.dumps(_sidecar_model()))
    cfg = {"objects": [{"id": "M31", "image": "pic.jpg", "annotations": "custom.json"}]}
    out = tmp_path / "map.html"
    assert uranometria.generate(cfg, out, allow_online=False) == []
    assert '"mk-0"' in out.read_text()

    (tmp_path / "pic.jpg.annotations.json").write_text("{not json")
    cfg = {"objects": [{"id": "M31", "image": "pic.jpg"}]}
    warnings = uranometria.generate(cfg, out, allow_online=False)
    assert any("sidecar unreadable" in w for w in warnings)


def test_annotation_label_scale_must_be_finite(tmp_path):
    import pytest

    (tmp_path / "pic.jpg").write_bytes(b"x")
    cfg = {
        "objects": [{"id": "M31", "image": "pic.jpg"}],
        "annotation_label_scale": float("inf"),
    }
    with pytest.raises(uranometria.SkymapError, match="finite"):
        uranometria.generate(cfg, tmp_path / "map.html", allow_online=False)


def test_annotation_label_scale_must_be_numeric(tmp_path):
    import pytest

    (tmp_path / "pic.jpg").write_bytes(b"x")
    for bad in ("big", ["x"]):
        cfg = {
            "objects": [{"id": "M31", "image": "pic.jpg"}],
            "annotation_label_scale": bad,
        }
        with pytest.raises(uranometria.SkymapError, match="must be a number"):
            uranometria.generate(cfg, tmp_path / "map.html", allow_online=False)


def test_annotations_json_escapes_all_angle_brackets(tmp_path):
    import json

    (tmp_path / "pic.jpg").write_bytes(b"x")
    m = _sidecar_model()
    m["objects"][0]["name"] = "<!--<script>evil"
    (tmp_path / "pic.jpg.annotations.json").write_text(json.dumps(m))
    cfg = {"objects": [{"id": "M31", "image": "pic.jpg"}]}
    out = tmp_path / "map.html"
    uranometria.generate(cfg, out, allow_online=False)
    html = out.read_text()
    start = html.index('id="lb-annotations">') + len('id="lb-annotations">')
    payload = html[start : html.index("</script>", start)]
    assert "<" not in payload  # every < is backslash-u003c escaped
    assert r"\u003c!--\u003cscript" in payload


@pytest.mark.parametrize(
    "field,value",
    [("y", float("nan")), ("mag", float("inf")), ("dist_ly", float("nan"))],
)
def test_nan_in_sidecar_warns_not_breaks(tmp_path, field, value):
    import json

    (tmp_path / "pic.jpg").write_bytes(b"x")
    m = _sidecar_model()
    m["objects"][0][field] = value  # Python json accepts these; browsers don't
    (tmp_path / "pic.jpg.annotations.json").write_text(json.dumps(m))
    cfg = {"objects": [{"id": "M31", "image": "pic.jpg"}]}
    out = tmp_path / "map.html"
    warnings = uranometria.generate(cfg, out, allow_online=False)
    assert any("sidecar unreadable" in w for w in warnings)
    html = out.read_text()
    assert 'id="lb-annotations">{}</script>' in html  # payload stays parseable
    assert "NaN" not in html.split('id="lb-annotations">')[1].split("</script>")[0]


def test_explicit_annotations_missing_warns(tmp_path):
    (tmp_path / "pic.jpg").write_bytes(b"x")
    cfg = {"objects": [{"id": "M31", "image": "pic.jpg", "annotations": "nope.json"}]}
    out = tmp_path / "map.html"
    warnings = uranometria.generate(cfg, out, allow_online=False)
    assert any("annotations file not found" in w for w in warnings)
    assert 'id="lb-annotations">{}</script>' in out.read_text()  # chart still builds


def test_explicit_annotations_with_remote_image(tmp_path):
    import json

    (tmp_path / "m.json").write_text(json.dumps(_sidecar_model()))
    cfg = {
        "objects": [{"id": "M31", "image": "https://example.org/pic.jpg", "annotations": "m.json"}]
    }
    out = tmp_path / "map.html"
    assert uranometria.generate(cfg, out, allow_online=False) == []
    assert '"mk-0"' in out.read_text()  # model embedded despite remote hero


def test_remote_hero_without_annotations_key(tmp_path):
    cfg = {"objects": [{"id": "M31", "image": "https://example.org/pic.jpg"}]}
    out = tmp_path / "map.html"
    assert uranometria.generate(cfg, out, allow_online=False) == []
    assert 'id="lb-annotations">{}</script>' in out.read_text()


def test_remote_annotated_url_passthrough(tmp_path):
    (tmp_path / "pic.jpg").write_bytes(b"x")
    cfg = {
        "objects": [{"id": "M31", "image": "pic.jpg", "annotated": "https://example.org/m51.html"}]
    }
    out = tmp_path / "map.html"
    assert uranometria.generate(cfg, out, allow_online=False) == []
    assert 'href="https://example.org/m51.html"' in out.read_text()


def test_no_sidecar_means_empty_map(tmp_path):
    (tmp_path / "pic.jpg").write_bytes(b"x")
    cfg = {"objects": [{"id": "M31", "image": "pic.jpg"}]}
    out = tmp_path / "map.html"
    uranometria.generate(cfg, out, allow_online=False)
    html = out.read_text()
    assert 'id="lb-annotations">{}</script>' in html
    assert "attachPanZoom" in html  # shared pan/zoom present
    assert 'id="lb-ann"' in html  # toggle exists (hidden until usable)


def test_annotated_page_link(tmp_path):
    (tmp_path / "pic.jpg").write_bytes(b"x")
    (tmp_path / "m51_page.html").write_text("<title>x</title>")
    cfg = {"objects": [{"id": "M51", "image": "pic.jpg", "annotated": "m51_page.html"}]}
    out = tmp_path / "map.html"
    assert uranometria.generate(cfg, out, allow_online=False) == []
    html = out.read_text()
    # no embedded model here, so the external page is still the best we have
    assert 'href="m51_page.html"' in html
    assert "ANNOTATED" in html
    assert "lb-annpage" not in html  # lightbox carries annotations itself now


def test_annotated_link_prefers_embedded_viewer(tmp_path):
    import json

    (tmp_path / "pic.jpg").write_bytes(b"x")
    (tmp_path / "pic.jpg.annotations.json").write_text(json.dumps(_sidecar_model()))
    (tmp_path / "m51_page.html").write_text("<title>x</title>")
    cfg = {"objects": [{"id": "M51", "image": "pic.jpg", "annotated": "m51_page.html"}]}
    out = tmp_path / "map.html"
    assert uranometria.generate(cfg, out, allow_online=False) == []
    html = out.read_text()
    assert '<span class="annlink" role="button"' in html  # in-page viewer wins
    assert 'href="m51_page.html"' not in html  # external link not emitted


def test_annotated_page_auto_discovery_and_missing(tmp_path):
    (tmp_path / "pic.jpg").write_bytes(b"x")
    (tmp_path / "pic_annotated.html").write_text("<title>x</title>")
    cfg = {"objects": [{"id": "M31", "image": "pic.jpg"}]}
    out = tmp_path / "map.html"
    uranometria.generate(cfg, out, allow_online=False)
    assert 'href="pic_annotated.html"' in out.read_text()

    cfg = {"objects": [{"id": "M31", "image": "pic.jpg", "annotated": "missing.html"}]}
    warnings = uranometria.generate(cfg, out, allow_online=False)
    assert any("annotated page not found" in w for w in warnings)
    assert 'class="annlink"' not in out.read_text()  # no link rendered
