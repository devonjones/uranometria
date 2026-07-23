"""Access to bundled catalog data and font assets (package resources)."""

from functools import lru_cache
from importlib.resources import files
import json

_PKG = files("uranometria")


def data_text(name: str) -> str:
    return (_PKG / "data" / name).read_text(encoding="utf-8")


def asset_text(name: str) -> str:
    return (_PKG / "assets" / name).read_text(encoding="utf-8")


@lru_cache(maxsize=None)
def data_json(name: str):
    return json.loads(data_text(name))


@lru_cache(maxsize=1)
def sky_data() -> dict:
    """Star positions, constellation lines, and constellation names."""
    return dict(
        stars=data_json("stars.6.json")["features"],
        lines=data_json("constellations.lines.json")["features"],
        names=data_json("constellations.json")["features"],
    )
