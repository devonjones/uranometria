"""Image annotation: plate-solve a stacked astrophoto and cross-match catalogs.

Requires the [annotate] extra (astropy + astroquery) and the ASTAP command-line
solver (https://www.hnsky.org/astap.htm) with a local star database. Produces a
JSON annotation model that the renderers (PNG, HTML) consume.
"""

from .model import build_model, write_model
from .solver import AstapError, solve

__all__ = ["solve", "build_model", "write_model", "AstapError"]
