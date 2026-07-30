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


def test_legend_sorted_naturally(tmp_path):
    cfg = {"objects": ["M110", "M2", "M27", "M1"]}
    out = tmp_path / "map.html"
    uranometria.generate(cfg, out, allow_online=False)
    html = out.read_text()
    legend = html.split("OBSERVING RECORD")[1]
    positions = [legend.index(f">{d}<") for d in ("M1", "M2", "M27", "M110")]
    assert positions == sorted(positions)  # M1 < M2 < M27 < M110, not lexicographic


def test_sorted_legend_keeps_original_marker_indices(tmp_path):
    import json

    from PIL import Image

    # config order M110 then M1; natural sort displays M1 first, but every
    # data-target/thumb/annotation key must stay the ORIGINAL index
    Image.new("RGB", (80, 60), (9, 9, 30)).save(tmp_path / "pic.jpg")
    (tmp_path / "pic.jpg.annotations.json").write_text(json.dumps(_sidecar_model()))
    cfg = {
        "objects": [
            {"id": "M110", "image": "pic.jpg"},  # original index 0
            {"id": "M1"},  # original index 1, sorts first
        ],
        "thumbnails": True,
    }
    out = tmp_path / "map.html"
    uranometria.generate(cfg, out, allow_online=False)
    html = out.read_text()
    legend = html.split("OBSERVING RECORD")[1]
    m1_card = legend.split(">M1<")[0].rsplit("<li ", 1)[1]
    m110_card = legend.split(">M110 ")[0].rsplit("<li ", 1)[1]  # PHOTO tag follows
    assert 'data-target="mk-1"' in m1_card  # M1 shows first, keeps index 1
    assert 'data-target="mk-0"' in m110_card
    assert legend.index(">M1<") < legend.index(">M110 ")  # sorted display
    # thumbs and annotations stay keyed to the original index too
    thumbs = html.split('id="chart-thumbs">')[1].split("</script>")[0]
    assert '"mk-0"' in thumbs and '"mk-1"' not in thumbs
    anns = html.split('id="lb-annotations">')[1].split("</script>")[0]
    assert '"mk-0"' in anns


def test_object_links_auto_and_custom(tmp_path):
    cfg = {
        "objects": [
            {"id": "M31"},
            {"id": "M51", "links": {"SEDS": "https://www.messier.seds.org/m/m051.html"}},
            {
                "id": "M1",
                "links": [
                    {"label": "APOD", "url": "https://apod.nasa.gov/apod/astropix.html"},
                    {"label": "evil", "url": "javascript:alert(1)"},
                ],
            },
            {"label": "X-1", "name": "", "type": "Other", "ra": 10.0, "dec": 20.0},
        ]
    }
    out = tmp_path / "map.html"
    warnings = uranometria.generate(cfg, out, allow_online=False)
    assert any("is not http(s)" in w and "M1" in w for w in warnings)
    html = out.read_text()
    # every object gets SIMBAD; Messier objects get Wikipedia
    assert "https://simbad.cds.unistra.fr/simbad/sim-id?Ident=M31" in html
    assert "https://en.wikipedia.org/wiki/Messier_31" in html
    # custom article links survive in both config shapes
    assert 'href="https://www.messier.seds.org/m/m051.html"' in html
    assert ">SEDS</a>" in html
    assert 'href="https://apod.nasa.gov/apod/astropix.html"' in html
    # the javascript: link is gone entirely
    assert "javascript:" not in html
    # nameless manual entry: SIMBAD only, no guessed Wikipedia article
    assert "https://simbad.cds.unistra.fr/simbad/sim-id?Ident=X-1" in html
    assert "https://en.wikipedia.org/wiki/_" not in html


def test_object_links_common_name_and_dot_designation(tmp_path):
    cfg = {
        "objects": [
            {
                "label": "NGC 7380",
                "name": "Wizard Nebula \u00b7 Sh2-142",
                "type": "Emission nebula",
                "ra": 341.8,
                "dec": 58.1,
            }
        ]
    }
    out = tmp_path / "map.html"
    assert uranometria.generate(cfg, out, allow_online=False) == []
    html = out.read_text()
    # the alt designation never belongs in the article guess
    assert "https://en.wikipedia.org/wiki/Wizard_Nebula" in html
    assert "Sh2-142" not in html.split("wiki/")[1][:40]


def test_object_links_scalar_config_warns(tmp_path):
    cfg = {"objects": [{"id": "M31", "links": "https://example.org"}]}
    out = tmp_path / "map.html"
    warnings = uranometria.generate(cfg, out, allow_online=False)
    assert any("must be a mapping or a list" in w for w in warnings)


def test_object_links_non_dict_list_item_warns(tmp_path):
    cfg = {"objects": [{"id": "M31", "links": ["https://example.org"]}]}
    out = tmp_path / "map.html"
    warnings = uranometria.generate(cfg, out, allow_online=False)
    assert any("is not a label/url mapping" in w for w in warnings)


def test_object_link_href_quote_escaped(tmp_path):
    cfg = {"objects": [{"id": "M31", "links": {"x": 'https://example.org/"onmouseover="a'}}]}
    out = tmp_path / "map.html"
    uranometria.generate(cfg, out, allow_online=False)
    html = out.read_text()
    assert "https://example.org/&quot;onmouseover=&quot;a" in html
    assert '" onmouseover=' not in html


def test_object_links_url_quoting_and_scheme_case(tmp_path):
    cfg = {
        "objects": [
            {
                "label": "BD+30 3639",
                "name": "Ne&bula #9",
                "type": "Planetary nebula",
                "ra": 200.0,
                "dec": 30.0,
                "links": {"Mirror": "HTTPS://Example.org/page"},
            }
        ]
    }
    out = tmp_path / "map.html"
    assert uranometria.generate(cfg, out, allow_online=False) == []
    html = out.read_text()
    assert "Ident=BD%2B30+3639" in html  # + survives as %2B, space as +
    assert "wiki/Ne%26bula_%239" in html  # & and # cannot reshape the path
    assert 'href="HTTPS://Example.org/page"' in html  # scheme case accepted


def test_object_link_labels_escaped(tmp_path):
    cfg = {"objects": [{"id": "M31", "links": {"<script>boom</script>": "https://example.org/x"}}]}
    out = tmp_path / "map.html"
    uranometria.generate(cfg, out, allow_online=False)
    html = out.read_text()
    assert "<script>boom" not in html
    assert "&lt;script&gt;boom" in html


def test_thumbnails_opt_in(tmp_path):
    from PIL import Image

    Image.new("RGB", (400, 300), (30, 10, 60)).save(tmp_path / "pic.jpg")
    cfg = {"objects": [{"id": "M31", "image": "pic.jpg"}]}
    out = tmp_path / "map.html"

    # default: off — the map is empty and no thumb data URI is embedded
    uranometria.generate(cfg, out, allow_online=False)
    html = out.read_text()
    assert 'id="chart-thumbs">{}</script>' in html

    # opt-in: thumb embedded, tooltip and deep-zoom hooks present
    cfg["thumbnails"] = True
    assert uranometria.generate(cfg, out, allow_online=False) == []
    html = out.read_text()
    start = html.index('id="chart-thumbs">')
    payload = html[start : html.index("</script>", start)]
    assert '"mk-0": "data:image/jpeg;base64,' in payload
    assert 'id="thumbtip"' in html
    assert "ensureMarkerThumbs" in html
    assert "deepzoom" in html
    assert "anchorTipToMarker" in html  # legend hover anchors the big tip
    # at the object's marker on the chart


def test_thumbnails_remote_and_broken_images(tmp_path):
    (tmp_path / "bad.jpg").write_bytes(b"not a jpeg")
    cfg = {
        "objects": [
            {"id": "M31", "image": "https://example.org/far.jpg"},
            {"id": "M51", "image": "bad.jpg"},
        ],
        "thumbnails": True,
    }
    out = tmp_path / "map.html"
    warnings = uranometria.generate(cfg, out, allow_online=False)
    assert sum("thumbnail failed" in w for w in warnings) == 1  # only bad.jpg
    assert not any("M31" in w for w in warnings)  # remote skipped SILENTLY
    html = out.read_text()
    assert 'id="chart-thumbs">{}</script>' in html


def test_thumbnail_absolute_path_with_space(tmp_path):
    from PIL import Image

    img = tmp_path / "my pic.jpg"  # space forces the quote/unquote round-trip
    Image.new("RGB", (40, 30)).save(img)
    cfg = {"objects": [{"id": "M31", "image": str(img)}], "thumbnails": True}
    out = tmp_path / "map.html"
    assert uranometria.generate(cfg, out, allow_online=False) == []
    assert '"mk-0": "data:image/jpeg;base64,' in out.read_text()


def test_thumbnail_respects_exif_orientation(tmp_path):
    import base64

    from PIL import Image

    img = tmp_path / "pic.jpg"
    im = Image.new("RGB", (400, 300), (20, 10, 40))
    exif = im.getexif()
    exif[274] = 6  # rotate 90: browsers display this portrait
    im.save(img, exif=exif)
    cfg = {"objects": [{"id": "M31", "image": "pic.jpg"}], "thumbnails": True}
    out = tmp_path / "map.html"
    uranometria.generate(cfg, out, allow_online=False)
    html = out.read_text()
    start = html.index("data:image/jpeg;base64,") + len("data:image/jpeg;base64,")
    b64 = html[start : html.index('"', start)].encode()
    import io

    tw, th = Image.open(io.BytesIO(base64.b64decode(b64))).size
    assert th > tw  # thumb is portrait, matching how browsers show the photo


def test_thumbnails_pillow_missing_warns_once(tmp_path, monkeypatch):
    import sys

    from PIL import Image

    Image.new("RGB", (40, 30)).save(tmp_path / "a.jpg")
    Image.new("RGB", (40, 30)).save(tmp_path / "b.jpg")
    cfg = {
        "objects": [{"id": "M31", "image": "a.jpg"}, {"id": "M51", "image": "b.jpg"}],
        "thumbnails": True,
    }
    monkeypatch.setitem(sys.modules, "PIL", None)
    warnings = uranometria.generate(cfg, tmp_path / "map.html", allow_online=False)
    assert sum("needs Pillow" in w for w in warnings) == 1  # once, then disabled
    assert 'id="chart-thumbs">{}</script>' in (tmp_path / "map.html").read_text()


def test_no_sidecar_means_empty_map(tmp_path):
    (tmp_path / "pic.jpg").write_bytes(b"x")
    cfg = {"objects": [{"id": "M31", "image": "pic.jpg"}]}
    out = tmp_path / "map.html"
    uranometria.generate(cfg, out, allow_online=False)
    html = out.read_text()
    assert 'id="lb-annotations">{}</script>' in html
    assert "attachPanZoom" in html  # shared pan/zoom present
    assert "userSelect" in html  # drag-to-pan never selects text (u-8)
    assert "const nz" in html  # wheel at the zoom clamp is a no-op (u-9)
    assert "removeAllRanges" in html  # pan start clears a live selection (u-8)
    assert "hasPointerCapture" in html  # capture deferred until a real drag,
    # so plain clicks on markers reach their handlers (u-13)
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
    assert 'class="linkrow"' in html  # article links coexist on the card
    # the anchor guard exists in BOTH the click and keydown handlers, so a
    # SIMBAD link click can never also open the lightbox
    assert html.count("e.target.closest('a[href]')) return") == 2


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


# ---- static SVG render mode (uranometria-14) --------------------------------


def test_render_svg_returns_standalone_document():
    charts, warnings = uranometria.render_svg({"objects": ["M31", "M42"]}, allow_online=False)
    assert warnings == []
    assert [c["hemisphere"] for c in charts] == ["north"]
    svg = charts[0]["svg"]
    assert svg.startswith('<svg xmlns="http://www.w3.org/2000/svg" class="sky"')
    assert 'viewBox="0 0 1000 1000"' in svg and 'width="1000" height="1000"' in svg
    assert svg.endswith("</svg>")
    # Nothing a renderer without CSS (or without a network) could trip over.
    for absent in ("<style", "var(--", "<div", "<h2", "<script", "@import"):
        assert absent not in svg, absent
    # No external reference of any kind. The xmlns URI is a name, not a fetch,
    # so look past the root tag for the attributes that would actually load.
    body = svg[svg.index(">") + 1 :]
    for absent in ("http", "src=", "href=", "url("):
        assert absent not in body, absent


def test_render_svg_paints_every_layer():
    # Every shape that takes its paint from the stylesheet in the HTML page must
    # carry it as an attribute here. Miss a fill="none" and the shape becomes a
    # black disc over the chart, which is why these are pinned exactly.
    svg = uranometria.render_svg({"objects": ["M31"]}, allow_online=False)[0][0]["svg"]
    assert '<rect x="0" y="0" width="1000" height="1000" fill="#070B1B"/>' in svg
    assert '<circle class="disc" cx="500" cy="500" r="470" fill="#0A0F24"/>' in svg
    assert '<g class="grid" fill="none" stroke="#232D55" stroke-width="0.8">' in svg
    assert 'class="equator" stroke="#39466F" stroke-width="1.2"/>' in svg
    assert '<g class="constellations" fill="none" stroke="#3E4F86" stroke-width="1"' in svg
    assert '<path opacity="0.75" d="M' in svg
    assert 'class="ecliptic" fill="none" stroke="#5E4A7D" stroke-width="1.1"' in svg
    assert 'stroke-dasharray="5 5" opacity="0.8"' in svg
    assert '<circle class="rim" cx="500" cy="500" r="470" fill="none"' in svg
    assert '<g class="connames" fill="#8492C0" text-anchor="middle">' in svg
    assert '<g class="hours" fill="#7C86AC" font-size="12" text-anchor="middle">' in svg
    assert '<g class="declabels" fill="#7C86AC" font-size="9.5"' in svg
    assert 'class="cn1" font-size="13.5"' in svg


def test_render_svg_folds_em_offsets_into_y(tmp_path):
    from uranometria.chart import CY, R_MAX

    svg = uranometria.render_svg({"objects": ["M31"]}, allow_online=False)[0][0]["svg"]
    assert "dy=" not in svg  # SVG Tiny renderers ignore dy on <text>
    # 0h sits at the top, so its baseline is the tick y plus 0.35 of 12px.
    assert f'<text x="500.0" y="{CY - (R_MAX + 16) + 0.35 * 12:.1f}">0h</text>' in svg
    # The HTML page keeps dy, so the nudge tracks the font size as you zoom.
    out = tmp_path / "map.html"
    uranometria.generate({"objects": ["M31"]}, out, allow_online=False)
    html = out.read_text()
    assert 'dy="0.35em"' in html and 'dy="-0.4em"' in html


def test_render_svg_marker_label_gets_halo_underneath(tmp_path):
    svg = uranometria.render_svg({"objects": ["M31"]}, allow_online=False)[0][0]["svg"]
    # Two copies: the sky-colored halo first, then the glyph over it. Stroking
    # the glyph directly needs paint-order, which SVG Tiny does not have.
    assert svg.count(">M31</text>") == 2
    assert 'fill="none" stroke="#0A0F24" stroke-width="3" stroke-linejoin="round"' in svg
    assert svg.index('stroke-width="3" stroke-linejoin="round"') < svg.index(
        'fill="#E5B958" stroke="none"'
    )
    # The page has paint-order, so it keeps a single label.
    out = tmp_path / "map.html"
    uranometria.generate({"objects": ["M31"]}, out, allow_online=False)
    assert out.read_text().count(">M31</text>") == 1


def test_render_svg_marker_carries_transform_and_text_metrics():
    svg = uranometria.render_svg({"objects": ["M31"]}, allow_online=False)[0][0]["svg"]
    assert 'transform="translate(534.0,319.9)"' in svg  # not stacked at the origin
    assert 'style="--tx:534.0px;--ty:319.9px"' in svg  # the page's hook survives
    assert 'font-size="12" font-weight="500"' in svg
    assert 'font-family="sans-serif"' in svg
    assert 'stroke="#E5B958" stroke-width="1.4"' in svg


def test_render_svg_objects_carry_placement():
    from uranometria.chart import project

    charts, _ = uranometria.render_svg({"objects": ["M31"]}, allow_online=False)
    o = charts[0]["objects"][0]
    objects, _ = uranometria.resolve_objects(["M31"], allow_online=False)
    px, py = project(objects[0]["ra"], objects[0]["dec"])
    assert (o["x"], o["y"]) == (round(px, 1), round(py, 1))
    assert o["uid"] == 0 and o["id"] == "mk-0"
    assert f'id="{o["id"]}"' in charts[0]["svg"]
    assert o["disp"] == "M31" and o["image"] is None
    assert o["label"]["anchor"] in ("start", "end", "middle")


def test_render_svg_orientation_follows_config():
    from uranometria.chart import CX

    entry = {"label": "X", "ra": 90.0, "dec": 10.0}
    sky = uranometria.render_svg({"objects": [entry]}, allow_online=False)[0]
    assert sky[0]["objects"][0]["x"] > CX  # RA 6h right of center on a northern disc
    mirrored = uranometria.render_svg({"objects": [entry], "mirror": True}, allow_online=False)[0]
    assert mirrored[0]["objects"][0]["x"] < CX


def test_render_svg_two_hemispheres_split():
    charts, _ = uranometria.render_svg({"objects": ["M31", "M42", "NGC 104"]}, allow_online=False)
    assert [c["hemisphere"] for c in charts] == ["north", "south"]
    north, south = charts
    assert 'id="mk-1"' in south["svg"] and 'id="mk-1"' not in north["svg"]  # M42, dec ~ -5
    assert 'id="mk-0"' in north["svg"]  # M31 stays north
    uids = [o["uid"] for c in charts for o in c["objects"]]
    assert sorted(uids) == [0, 1, 2]  # one key space across both discs


def test_assign_charts_hemisphere_split():
    from uranometria.chart import assign_charts
    from uranometria.resources import sky_data

    def charts_for(names):
        objects, _ = uranometria.resolve_objects(names, allow_online=False)
        return objects, assign_charts(objects, sky_data(), mag_limit=5.0, show_ecliptic=True)

    objects, charts = charts_for(["M31", "M42"])
    assert [c.south for c in charts] == [False]  # single disc takes everything
    assert len(charts[0].markers) == 2
    objects, charts = charts_for(["M31", "M42", "NGC 104"])
    assert [c.south for c in charts] == [False, True]  # north first
    assert [m["o"]["disp"] for m in charts[0].markers] == ["M31"]
    assert [m["o"]["disp"] for m in charts[1].markers] == ["M42", "NGC 104"]


def test_render_svg_honors_chart_config():
    plain = uranometria.render_svg({"objects": ["M31"]}, allow_online=False)[0][0]["svg"]
    no_ecl = uranometria.render_svg(
        {"objects": ["M31"], "show_ecliptic": False}, allow_online=False
    )[0][0]["svg"]
    assert 'class="ecliptic"' in plain and 'class="ecliptic"' not in no_ecl
    dim = uranometria.render_svg({"objects": ["M31"], "mag_limit": 2.0}, allow_online=False)[0][0][
        "svg"
    ]
    assert dim.count("<circle cx=") < plain.count("<circle cx=")


def test_render_svg_palette_overrides_and_unknown_key_warns():
    charts, warnings = uranometria.render_svg(
        {"objects": ["M31"]},
        palette={"aster": "#123456", "bogus": "#ffffff"},
        allow_online=False,
    )
    svg = charts[0]["svg"]
    assert 'stroke="#123456"' in svg and "#3E4F86" not in svg
    assert any("bogus" in w and "unknown" in w for w in warnings)


def test_render_svg_palette_rejects_css_injection():
    charts, warnings = uranometria.render_svg(
        {"objects": ["M31"]},
        palette={"sky": '#000" onload="alert(1)', "grid": "url(http://evil/x.png)"},
        allow_online=False,
    )
    svg = charts[0]["svg"]
    assert len(warnings) == 2 and all("not a plain color" in w for w in warnings)
    assert "onload=" not in svg and "http" not in svg[svg.index(">") + 1 :]
    assert 'fill="#0A0F24"' in svg and 'stroke="#232D55"' in svg  # defaults kept


def test_render_svg_font_family_validated():
    charts, warnings = uranometria.render_svg(
        {"objects": ["M31"]}, font_family="IBM Plex Mono", allow_online=False
    )
    assert 'font-family="IBM Plex Mono"' in charts[0]["svg"] and warnings == []
    charts, warnings = uranometria.render_svg(
        {"objects": ["M31"]},
        font_family='x"; @import url(http://evil/f.css)',
        allow_online=False,
    )
    assert any("not a plain family name" in w for w in warnings)
    assert "@import" not in charts[0]["svg"]
    assert 'font-family="sans-serif"' in charts[0]["svg"]


def test_render_svg_hostile_label_is_inert():
    entry = {"label": "<img src=x onerror=alert(1)>", "ra": 10.0, "dec": 41.0}
    svg = uranometria.render_svg({"objects": [entry]}, allow_online=False)[0][0]["svg"]
    assert "<img" not in svg
    assert svg.count("&lt;img src=x onerror=alert(1)&gt;") == 2  # halo + glyph


def test_render_svg_object_color_wins_over_palette():
    entry = {"id": "M31", "color": "#7EC8A0"}
    svg = uranometria.render_svg({"objects": [entry]}, allow_online=False)[0][0]["svg"]
    assert 'stroke="#7EC8A0"' in svg and 'fill="#7EC8A0"' in svg
    assert "--accent:#7EC8A0" in svg


def test_chart_layers_are_idempotent():
    from uranometria.chart import assign_charts
    from uranometria.resources import sky_data

    objects, _ = uranometria.resolve_objects(["M31", "M81", "M101"], allow_online=False)
    chart = assign_charts(objects, sky_data(), mag_limit=5.0, show_ecliptic=True)[0]
    first = chart.standalone_svg()
    assert chart.standalone_svg() == first  # a second emit must not re-place labels
    assert len(chart.label_boxes) == len(chart.markers)


def test_html_chart_keeps_css_classes_and_gains_attributes(tmp_path):
    # The page's stylesheet outranks a presentation attribute, so the attributes
    # added for the SVG mode are inert here: the classes and hooks stay put.
    out = tmp_path / "map.html"
    uranometria.generate({"objects": ["M31", "NGC 104"]}, out, allow_online=False)
    html = out.read_text()
    assert 'class="ecliptic"' in html and 'stroke-dasharray="5 5"' in html
    assert 'class="disc"' in html and ".disc {" in html
    assert "--tx:" in html and 'id="mk-0"' in html
    assert html.count('<svg class="sky"') == 2
    assert 'class="chart hidden" data-hemi="south"' in html


def test_cli_svg_writes_one_file_per_hemisphere(tmp_path):
    from click.testing import CliRunner

    from uranometria.cli import main

    cfg = tmp_path / "sky.yaml"
    cfg.write_text("objects: [M31, M42]\n")
    runner = CliRunner()
    result = runner.invoke(main, ["chart", str(cfg), "--offline", "--svg"])
    assert result.exit_code == 0, result.output
    single = tmp_path / "sky.svg"
    assert single.exists() and single.read_text().startswith("<svg xmlns=")
    assert not (tmp_path / "sky.html").exists()  # --svg replaces the HTML

    cfg.write_text('objects: [M31, "NGC 104"]\n')
    result = runner.invoke(main, ["chart", str(cfg), "--offline", "--svg"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "sky.north.svg").exists() and (tmp_path / "sky.south.svg").exists()
    assert "sky.north.svg" in result.output and "sky.south.svg" in result.output


def test_cli_svg_explicit_path(tmp_path):
    from click.testing import CliRunner

    from uranometria.cli import main

    cfg = tmp_path / "sky.yaml"
    cfg.write_text("objects: [M31]\n")
    runner = CliRunner()
    for arg in (str(tmp_path / "out.svg"), str(tmp_path / "out")):
        (tmp_path / "out.svg").unlink(missing_ok=True)
        result = runner.invoke(main, ["chart", str(cfg), "--offline", "--svg", arg])
        assert result.exit_code == 0, result.output
        assert (tmp_path / "out.svg").exists()
