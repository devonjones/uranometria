"""uranometria — star-atlas style HTML sky charts marking your deep-sky objects.

Library entry points:

    uranometria.generate(config, output)  -> list of warning strings
    uranometria.render(config, image_base=None) -> (html, warnings)
    uranometria.resolve_objects(entries)  -> (objects, warnings)

`config` is a dict (or a path to a YAML file) with an `objects` list of
designations and/or fully-specified entries. See `uranometria.core` for the schema.
"""

from .core import SkymapError, generate, render, resolve_objects

__version__ = "0.6.0"
__all__ = ["generate", "render", "resolve_objects", "SkymapError", "__version__"]
