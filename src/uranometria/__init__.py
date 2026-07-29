"""uranometria — star-atlas style HTML sky charts marking your deep-sky objects.

Library entry points:

    uranometria.generate(config, output)  -> list of warning strings
    uranometria.render(config, image_base=None) -> (html, warnings)
    uranometria.render_svg(config, palette=None, font_family=None) -> (charts, warnings)
    uranometria.resolve_objects(entries)  -> (objects, warnings)

`config` is a dict (or a path to a YAML file) with an `objects` list of
designations and/or fully-specified entries. See `uranometria.core` for the schema.

Module map:

- `uranometria.core`: config resolution, warnings contract, page assembly entry
- `uranometria.catalog`: bundled OpenNGC + Sharpless catalogs and designation parsing
- `uranometria.chart`: the polar projection, SVG chart rendering, and the palette
- `uranometria.page`: the interactive HTML page around the charts
- `uranometria.webui`: shared pan/zoom and annotation-viewer JavaScript
- `uranometria.resources`: bundled data and asset loading
- `uranometria.cli`: the `uranometria` command group
- `uranometria.annotate`: plate-solve and annotation pipeline
  (`uranometria.annotate.model`, `uranometria.annotate.field`,
  `uranometria.annotate.solver`, `uranometria.annotate.render_png`,
  `uranometria.annotate.render_html`)
"""

from .core import SkymapError, generate, render, render_svg, resolve_objects

__version__ = "0.11.0"
__all__ = ["generate", "render", "render_svg", "resolve_objects", "SkymapError", "__version__"]
