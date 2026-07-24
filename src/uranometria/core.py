"""Public library API: resolve an object list and render/write the chart.

Typical use from another project:

    import uranometria

    config = {
        "title": "My Sky",
        "objects": [
            "M31",                                   # bare designation
            {"id": "Sh2-142", "label": "NGC 7380"},  # lookup + overrides
            {"label": "X-1", "name": "My target",    # fully manual entry
             "type": "Nebula", "constellation": "Cygnus",
             "ra": "20h15m22s", "dec": "+38 21 18",
             "image": "photos/x1.jpg", "color": "#7EC8A0"},
        ],
    }
    warnings = uranometria.generate(config, "out/map.html")

`generate` also accepts a path to a YAML file as its first argument.
"""

import http.client
import json
import math
import os
import re
import urllib.parse

from .catalog import Catalog, fmt_coord, parse_angle, sesame
from .page import build_page


class SkymapError(Exception):
    """Raised when a chart cannot be produced at all (e.g. no resolvable objects)."""


_catalog = None


def _get_catalog():
    global _catalog
    if _catalog is None:
        _catalog = Catalog()
    return _catalog


def resolve_objects(entries, *, allow_online=True):
    """Resolve config object entries to full records. Returns (objects, warnings)."""
    catalog = _get_catalog()
    objects, warnings = [], []
    for e in entries:
        if not isinstance(e, dict):
            e = {"id": str(e)}  # bare designations, incl. YAML numbers like `- 141`
        elif "id" in e and not isinstance(e["id"], str):
            e = dict(e, id=str(e["id"]))
        o = None
        if "ra" in e and "dec" in e:
            try:
                ra = parse_angle(e["ra"], True)
                dec = parse_angle(e["dec"], False)
            except ValueError as err:
                warnings.append(
                    f"{e.get('label') or e.get('id', '?')}: bad ra/dec ({err}) — skipped"
                )
                continue
            if not -90.0 <= dec <= 90.0:
                warnings.append(
                    f"{e.get('label') or e.get('id', '?')}: dec out of range "
                    f"({e['dec']!r}) — skipped"
                )
                continue
            o = dict(
                disp=e.get("label") or e.get("id", "?"),
                ra=ra % 360.0,
                dec=dec,
                type=e.get("type", "Deep-sky object"),
                constellation=e.get("constellation", ""),
                common=e.get("name", ""),
            )
        elif "id" in e:
            o = catalog.lookup(e["id"])
            if o is None and allow_online:
                try:
                    o = sesame(e["id"])
                except (OSError, http.client.HTTPException) as err:
                    warnings.append(
                        f"{e['id']}: not in bundled catalogs and Sesame "
                        f"lookup failed ({err}) — skipped"
                    )
                    continue
                if o is not None:
                    warnings.append(f"{e['id']}: resolved via CDS Sesame (online)")
            if o is None:
                warnings.append(f"{e['id']}: could not resolve — skipped")
                continue
            for src, dst in (
                ("label", "disp"),
                ("name", "common"),
                ("type", "type"),
                ("constellation", "constellation"),
            ):
                if e.get(src):
                    o[dst] = e[src]
        else:
            warnings.append(f"entry {e!r} has neither 'id' nor ra/dec — skipped")
            continue
        o["image"] = e.get("image")
        o["annotations"] = e.get("annotations")
        o["annotated"] = e.get("annotated")
        o["color"] = e.get("color")
        o["coord"] = fmt_coord(o["ra"], o["dec"])
        objects.append(o)
    return objects, warnings


def resolve_image(url, base_dir):
    """Turn a config image reference into an href usable from the output HTML.
    Returns (href, error). Relative paths (and file:// with a relative path)
    resolve against base_dir — the output file's directory — and must exist."""
    url = str(url)
    if re.match(r"https?://", url):
        return url, None
    path = url[7:] if url.startswith("file://") else url
    full = path if os.path.isabs(path) else os.path.join(base_dir, path)
    if not os.path.isfile(full):
        return None, f"image not found at {full}"
    if os.path.isabs(path):
        return "file://" + urllib.parse.quote(path), None
    return urllib.parse.quote(path), None


def _annotation_sidecar(o, base_dir):
    """Load and normalize an annotation model for an object's photo: the
    explicit `annotations:` path, or `<image>.annotations.json` beside the
    image. Returns a compact display-frame dict, or None."""
    img = str(o.get("image") or "")
    if o.get("annotations"):
        # explicit key: honored even for remote images (the lightbox size
        # guard validates at view time), and a missing file is a warning,
        # not a silent drop
        ann_path = str(o["annotations"])
        if not os.path.isabs(ann_path):
            ann_path = os.path.join(base_dir, ann_path)
        if not os.path.isfile(ann_path):
            raise FileNotFoundError(f"annotations file not found: {ann_path}")
    else:
        if not img or re.match(r"https?://", img):
            return None
        img_path = img[7:] if img.startswith("file://") else img
        if not os.path.isabs(img_path):
            img_path = os.path.join(base_dir, img_path)
        ann_path = img_path + ".annotations.json"
        if not os.path.isfile(ann_path):
            return None
    with open(ann_path) as f:
        model = json.load(f)
    width, height = model["image_size"]
    flip = model.get("solved", {}).get("pixel_frame", "fits0") == "fits0"

    def _finite(v):
        return isinstance(v, (int, float)) and math.isfinite(v)

    objects = []
    for a in model.get("objects", []):
        # Python's json is lenient about NaN/Infinity but browsers reject
        # them, which would kill the whole page script at view time
        if not (_finite(a["x"]) and _finite(a["y"])):
            raise ValueError("non-finite object coordinates")
        for k in ("mag", "dist_ly"):
            if a.get(k) is not None and not _finite(a[k]):
                raise ValueError(f"non-finite {k}")
        objects.append(
            {
                "kind": a.get("kind"),
                "designation": a.get("designation"),
                "aliases": a.get("aliases") or [],
                "name": a.get("name"),
                "type": a.get("type"),
                "named": a.get("named"),
                "key": a.get("key"),
                "mag": a.get("mag"),
                "band": a.get("band"),
                "dist_ly": a.get("dist_ly"),
                "links": a.get("links") or {},
                "x": a["x"],
                "y": ((height - 1) - a["y"]) if flip else a["y"],
            }
        )
    return {"image_size": [width, height], "objects": objects}


def _annotated_page(o, base_dir):
    """Href for the object's interactive annotated page: the explicit
    `annotated:` path, or `<image stem>_annotated.html` beside the image."""
    if o.get("annotated"):
        page = str(o["annotated"])
        if re.match(r"https?://", page):
            return page, None
        full = page if os.path.isabs(page) else os.path.join(base_dir, page)
        if not os.path.isfile(full):
            return None, f"annotated page not found at {full}"
        return urllib.parse.quote(page), None
    img = str(o.get("image") or "")
    if not img or re.match(r"https?://", img):
        return None, None
    img_path = img[7:] if img.startswith("file://") else img
    candidate = os.path.splitext(img_path)[0] + "_annotated.html"
    full = candidate if os.path.isabs(candidate) else os.path.join(base_dir, candidate)
    if os.path.isfile(full):
        return urllib.parse.quote(candidate), None
    return None, None


def _load_config(config):
    if isinstance(config, dict):
        return config
    import yaml

    with open(config) as f:
        return yaml.safe_load(f)


def render(config, *, image_base=None, allow_online=True):
    """Render the chart and return (html, warnings).

    config: a dict (see module docstring) or a path to a YAML file.
    image_base: directory that relative `image` paths resolve against — pass
        the directory you intend to write the HTML into. If None, entries with
        relative image paths are rendered without their photo (with a warning).
    """
    cfg = _load_config(config)
    entries = cfg.get("objects") or []
    if not entries:
        raise SkymapError("config has no 'objects' list")
    try:
        mag_limit = float(cfg.get("mag_limit", 5.0))
    except (TypeError, ValueError):
        raise SkymapError(f"mag_limit must be a number, got {cfg.get('mag_limit')!r}") from None
    if math.isnan(mag_limit):
        raise SkymapError("mag_limit must be a number, got NaN")
    try:
        ann_scale = float(cfg.get("annotation_label_scale", 1.0))
    except (TypeError, ValueError):
        raise SkymapError(
            f"annotation_label_scale must be a number, got {cfg.get('annotation_label_scale')!r}"
        ) from None
    if not math.isfinite(ann_scale):
        raise SkymapError("annotation_label_scale must be a finite number")
    objects, warnings = resolve_objects(entries, allow_online=allow_online)
    if not objects:
        raise SkymapError("no objects could be resolved")

    for o in objects:
        if not o.get("image"):
            continue
        if (
            image_base is None
            and not re.match(r"https?://", str(o["image"]))
            and not os.path.isabs(str(o["image"]).removeprefix("file://"))
        ):
            warnings.append(
                f"{o['disp']}: relative image path with no image_base " f"— rendered without photo"
            )
            continue
        href, err = resolve_image(o["image"], image_base or "")
        if err:
            warnings.append(
                f"{o['disp']}: {err} (paths resolve relative to "
                f"{image_base}) — rendered without photo"
            )
        else:
            o["href"] = href
            name = f" — {o['common']}" if o["common"] else ""
            o["caption"] = f"{o['disp']}{name}|{o['type']}   ·   {o['coord']}"
            try:
                o["annotation"] = _annotation_sidecar(o, image_base or "")
            except (OSError, ValueError, KeyError, TypeError) as err:
                warnings.append(
                    f"{o['disp']}: annotation sidecar unreadable ({err}) — photo shown without overlay"
                )
            page_href, err = _annotated_page(o, image_base or "")
            if err:
                warnings.append(f"{o['disp']}: {err} — link omitted")
            elif page_href:
                o["annotated_href"] = page_href

    return build_page(cfg, objects), warnings


def generate(config, output, *, allow_online=True):
    """Render the chart and write it to `output`. Returns the list of warnings.

    Relative `image` paths in the config resolve against `output`'s directory
    and are validated at build time.
    """
    output = os.fspath(output)
    out_dir = os.path.dirname(os.path.abspath(output))
    page, warnings = render(config, image_base=out_dir, allow_online=allow_online)
    with open(output, "w") as f:
        f.write(page)
    return warnings
