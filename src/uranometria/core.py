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
        if isinstance(e, str):
            e = {"id": e}
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
            o = dict(
                disp=e.get("label") or e.get("id", "?"),
                ra=ra,
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
        float(cfg.get("mag_limit", 5.0))
    except (TypeError, ValueError):
        raise SkymapError(f"mag_limit must be a number, got {cfg.get('mag_limit')!r}") from None
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
