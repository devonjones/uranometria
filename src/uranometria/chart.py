"""Polar hemisphere chart: projection, stars, constellation figures, markers.

Every fragment carries its paint as SVG presentation attributes, so a disc
renders the same with the page stylesheet or with no stylesheet at all — the
`standalone_svg()` form is what a native host (Qt's QtSvg, or any SVG Tiny
renderer) can draw. In the HTML page the stylesheet still wins: a CSS rule
always outranks a presentation attribute, so `page.py` keeps full control of
the interactive chart and the attributes are inert there.
"""

import html
import math
import re

# ---------------------------------------------------------------- geometry
CX = CY = 500.0
R_MAX = 470.0
DEC_EDGE = 35.0  # how far past the equator each hemisphere chart reaches
SCALE = R_MAX / (90.0 + DEC_EDGE)
MARKER_R = 8.5  # marker ring radius; a host hit-tests against this

# ---------------------------------------------------------------- palette
# The page's CSS custom properties, minus the `--`, plus `ecliptic` (a literal
# in the stylesheet) and the star tints (literals in `star_color`). Chart paint
# reads from here so a host can theme a standalone disc; `page.py` renders the
# same values into `:root`, and its rules shadow the attributes anyway.
PALETTE = {
    "sky": "#0A0F24",
    "deep": "#070B1B",
    "star": "#E9EDFB",
    "grid": "#232D55",
    "equator": "#39466F",
    "aster": "#3E4F86",
    "conname": "#8492C0",
    "gold": "#E5B958",
    "accent": "#E5B958",
    "ink": "#C7CEE6",
    "dim": "#7C86AC",
    "ecliptic": "#5E4A7D",
    "star_blue": "#C7D9FF",
    "star_yellow": "#FFEDCF",
    "star_orange": "#FFD9AE",
}
FONT_FALLBACK = "sans-serif"

# Palette values and font families reach the output as attribute text, so both
# are whitelisted rather than escaped-and-hoped: a value that is not plainly a
# color or a family name never gets to be markup in the first place.
_COLOR_RE = re.compile(
    r"^(#[0-9A-Fa-f]{3,8}|[A-Za-z]+|rgba?\([0-9%.,\s/]+\)|hsla?\([0-9%.,\s/]+deg?[0-9%.,\s/]*\))$"
)
_FAMILY_RE = re.compile(r"^[A-Za-z0-9 ,._-]+$")


def resolve_palette(palette=None):
    """Merge `palette` over `PALETTE` and return (palette, warnings).

    An unknown key, or a value that is not plainly a color, warns and keeps the
    default — a bad theme costs you the theme, never the chart. Values come back
    escaped for attribute use.
    """
    warnings = []
    merged = dict(PALETTE)
    for key, value in (palette or {}).items():
        if key not in PALETTE:
            warnings.append(f"palette: unknown key {key!r} — ignored")
            continue
        if not isinstance(value, str) or not _COLOR_RE.match(value.strip()):
            warnings.append(
                f"palette: {key} value {value!r} is not a plain color "
                f"— the default {PALETTE[key]} is used"
            )
            continue
        merged[key] = value.strip()
    return {k: html.escape(v, quote=True) for k, v in merged.items()}, warnings


def resolve_font(font_family=None):
    """Family name for chart text as (family, warnings).

    A name only: the output never references a font file, so a value carrying
    anything but a plain family name falls back with a warning.
    """
    if font_family is None:
        return FONT_FALLBACK, []
    if not isinstance(font_family, str) or not _FAMILY_RE.match(font_family.strip()):
        return FONT_FALLBACK, [
            f"font_family: {font_family!r} is not a plain family name — {FONT_FALLBACK} is used"
        ]
    return html.escape(font_family.strip(), quote=True), []


def ra_sign(south=False, mirror=False):
    """Horizontal sense of increasing RA. Sky view (the default) shows the sky
    as seen from Earth: RA runs clockwise on a northern polar disc and
    counterclockwise on a southern one. Mirror view flips both — the
    celestial-globe orientation, matching the view through a star diagonal."""
    return 1.0 if south == mirror else -1.0


def project(ra_deg, dec_deg, south=False, mirror=False):
    """Azimuthal equidistant about the celestial pole, 0h at top."""
    r = (90.0 + dec_deg if south else 90.0 - dec_deg) * SCALE
    a = math.radians(ra_deg)
    return CX + ra_sign(south, mirror) * r * math.sin(a), CY - r * math.cos(a)


def visible(dec, south):
    return dec >= -DEC_EDGE if not south else dec <= DEC_EDGE


def accent_value(o):
    """Escaped per-object accent color, or '' when the object has none."""
    return html.escape(o["color"], quote=True) if o.get("color") else ""


def photo_attrs(o):
    """data-img/data-cap attribute pair for objects with a photo, escaped.
    The single source of truth for these sinks — used by both the chart
    markers and the legend so their escaping cannot drift apart."""
    if not o.get("href"):
        return ""
    return (
        f' data-img="{html.escape(o["href"], quote=True)}"'
        f' data-cap="{html.escape(o["caption"], quote=True)}"'
    )


def star_color(bv, pal=None):
    pal = pal or PALETTE
    try:
        bv = float(bv)
    except (TypeError, ValueError):
        return pal["star"]
    if bv < 0.0:
        return pal["star_blue"]
    if bv < 0.6:
        return pal["star"]
    if bv < 1.2:
        return pal["star_yellow"]
    return pal["star_orange"]


class Chart:
    """One hemisphere disc."""

    def __init__(
        self,
        south,
        sky_data,
        mag_limit,
        show_ecliptic,
        mirror=False,
        palette=None,
        font_family=None,
        static=False,
    ):
        """`palette` must already be merged and escaped (`resolve_palette`); its
        values are written straight into attributes. `static` drops the page's
        interactive hooks and works around the gaps in SVG Tiny renderers."""
        self.south = south
        self.mirror = mirror
        self.sign = ra_sign(south, mirror)
        self.data = sky_data
        self.mag_limit = mag_limit
        self.show_ecliptic = show_ecliptic
        self.pal = PALETTE if palette is None else palette
        self.font = font_family or FONT_FALLBACK
        self.static = static
        self.markers = []  # dicts: x, y, o (object), uid, dx, dy, anchor
        self.label_boxes = []  # placed text boxes for collision avoidance
        self.name_boxes = []  # constellation-name boxes
        self._layers_svg = None

    def p(self, ra, dec):
        return project(ra, dec, self.south, self.mirror)

    def add_object(self, o, uid):
        x, y = self.p(o["ra"], o["dec"])
        self.markers.append(dict(x=x, y=y, o=o, uid=uid))

    # ---- label placement -------------------------------------------------
    CANDIDATES = [
        (16, 4, "start"),
        (-16, 4, "end"),
        (0, -14, "middle"),
        (0, 22, "middle"),
        (14, -9, "start"),
        (-14, -9, "end"),
        (14, 16, "start"),
        (-14, 16, "end"),
    ]

    @staticmethod
    def _box(x, y, dx, dy, anchor, text):
        w = len(text) * 7.4
        h = 13.0
        lx, ly = x + dx, y + dy
        x0 = lx - (w if anchor == "end" else w / 2 if anchor == "middle" else 0)
        return (x0, ly - h * 0.75, x0 + w, ly + h * 0.25)

    @staticmethod
    def _overlap(a, b):
        w = min(a[2], b[2]) - max(a[0], b[0])
        h = min(a[3], b[3]) - max(a[1], b[1])
        return w * h if (w > 0 and h > 0) else 0.0

    def place_label(self, x, y, text):
        best, best_score = self.CANDIDATES[0], float("inf")
        for dx, dy, anchor in self.CANDIDATES:
            box = self._box(x, y, dx, dy, anchor, text)
            score = 0.0
            for other in self.label_boxes:
                score += 3.0 * self._overlap(box, other)
            for other in self.name_boxes:
                score += 1.0 * self._overlap(box, other)
            for m in self.markers:
                mbox = (m["x"] - 10, m["y"] - 10, m["x"] + 10, m["y"] + 10)
                score += 2.0 * self._overlap(box, mbox)
            r = math.hypot((box[0] + box[2]) / 2 - CX, (box[1] + box[3]) / 2 - CY)
            if r > R_MAX - 6:
                score += 500.0
            if score < best_score:
                best_score, best = score, (dx, dy, anchor)
                if score == 0:
                    break
        self.label_boxes.append(self._box(x, y, *best, text))
        return best

    # ---- svg fragments ---------------------------------------------------
    def stars_svg(self):
        out = []
        for f in self.data["stars"]:
            mag = f["properties"]["mag"]
            lon, lat = f["geometry"]["coordinates"]
            if mag > self.mag_limit or not visible(lat, self.south):
                continue
            x, y = self.p(lon % 360, lat)
            r = min(5.0, max(0.55, 0.65 + (self.mag_limit - mag) * 0.72))
            op = 1.0 if mag < 3.5 else (0.85 if mag < 4.5 else 0.7)
            out.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.2f}" '
                f'fill="{star_color(f["properties"].get("bv"), self.pal)}" opacity="{op:.2f}"/>'
            )
        return "".join(out)

    def lines_svg(self):
        out = []
        for f in self.data["lines"]:
            for seg in f["geometry"]["coordinates"]:
                run = []
                for lon, lat in seg:
                    if visible(lat, self.south):
                        run.append(self.p(lon % 360, lat))
                    else:
                        if len(run) > 1:
                            out.append(
                                '<path opacity="0.75" d="M'
                                + " L".join(f"{x:.1f},{y:.1f}" for x, y in run)
                                + '"/>'
                            )
                        run = []
                if len(run) > 1:
                    out.append(
                        '<path opacity="0.75" d="M'
                        + " L".join(f"{x:.1f},{y:.1f}" for x, y in run)
                        + '"/>'
                    )
        return "".join(out)

    def names_svg(self):
        out = []
        lim = -30 if not self.south else 30
        for f in self.data["names"]:
            lon, lat = f["geometry"]["coordinates"]
            if (lat < lim) if not self.south else (lat > lim):
                continue
            rank = int(f["properties"].get("rank", 3))
            rank = rank if rank in (1, 2) else 3
            size = {1: 13.5, 2: 11.0, 3: 9.5}[rank]
            op = {1: 0.9, 2: 0.75, 3: 0.6}[rank]
            x, y = self.p(lon % 360, lat)
            label = f["properties"].get("la", f["properties"]["name"]).upper()
            w = len(label) * size * 0.9
            self.name_boxes.append((x - w / 2, y - size, x + w / 2, y + size * 0.3))
            out.append(
                f'<text x="{x:.1f}" y="{y:.1f}" class="cn{rank}" '
                f'font-size="{size:g}" opacity="{op}">'
                f"{html.escape(label)}</text>"
            )
        return "".join(out)

    def grid_svg(self):
        out = []
        decs = (60, 30, 0, -30) if not self.south else (-60, -30, 0, 30)
        for dec in decs:
            r = (90 - dec if not self.south else 90 + dec) * SCALE
            # The group carries the declination paint; only the equator differs.
            cls, extra = "declin", ""
            if dec == 0:
                cls = "equator"
                extra = f' stroke="{self.pal["equator"]}" stroke-width="1.2"'
            out.append(f'<circle cx="{CX}" cy="{CY}" r="{r:.1f}" class="{cls}"{extra}/>')
        for h in range(0, 24, 2):
            a = math.radians(h * 15)
            sx = self.sign * math.sin(a)
            x1, y1 = CX + 12 * sx, CY - 12 * math.cos(a)
            x2, y2 = CX + R_MAX * sx, CY - R_MAX * math.cos(a)
            out.append(
                f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" class="declin"/>'
            )
        return "".join(out)

    def _em_offset(self, y, em, size):
        """Baseline for text nudged by a fraction of an em, as (y, dy-attr).

        The page keeps the nudge in `dy` so it tracks the counter-scaled font
        size as you zoom; the static form folds it into `y`, because SVG Tiny
        renderers ignore `dy` on `<text>`.
        """
        if self.static:
            return f"{y + em * size:.1f}", ""
        return f"{y:.1f}", f' dy="{em:g}em"'

    def hours_svg(self):
        out = []
        for h in range(0, 24, 2):
            a = math.radians(h * 15)
            sx = self.sign * math.sin(a)
            x, y = CX + (R_MAX + 16) * sx, CY - (R_MAX + 16) * math.cos(a)
            ya, dya = self._em_offset(y, 0.35, 12.0)
            out.append(f'<text x="{x:.1f}" y="{ya}"{dya}>{h}h</text>')
        return "".join(out)

    def declabels_svg(self):
        out = []
        decs = (60, 30, 0, -30) if not self.south else (-60, -30, 0, 30)
        for dec in decs:
            r = (90 - dec if not self.south else 90 + dec) * SCALE
            a = math.radians(15)
            sx = self.sign * math.sin(a)
            x, y = CX + (r - 2) * sx, CY - (r - 2) * math.cos(a)
            t = f"{dec:+d}°" if dec else "0°"
            ya, dya = self._em_offset(y, -0.4, 9.5)
            out.append(f'<text x="{x:.1f}" y="{ya}"{dya} opacity="0.9">{t}</text>')
        return "".join(out)

    def ecliptic_svg(self):
        if not self.show_ecliptic:
            return ""
        eps = math.radians(23.4393)
        pts = []
        for i in range(181):
            lam = math.radians(i * 2)
            ra = math.degrees(math.atan2(math.sin(lam) * math.cos(eps), math.cos(lam))) % 360
            dec = math.degrees(math.asin(math.sin(eps) * math.sin(lam)))
            pts.append(self.p(ra, dec))
        d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + " Z"
        return (
            f'<path class="ecliptic" fill="none" stroke="{self.pal["ecliptic"]}" '
            f'stroke-width="1.1" stroke-dasharray="5 5" opacity="0.8" d="{d}"/>'
        )

    def markers_svg(self):
        out = []
        for m in self.markers:
            x, y, o, uid = m["x"], m["y"], m["o"], m["uid"]
            dx, dy, anchor = self.place_label(x, y, o["disp"])
            m["dx"], m["dy"], m["anchor"] = dx, dy, anchor
            ticks = []
            for ang in (45, 135, 225, 315):
                t = math.radians(ang)
                ticks.append(
                    f'<line x1="{MARKER_R * math.cos(t):.2f}" '
                    f'y1="{MARKER_R * math.sin(t):.2f}" '
                    f'x2="{(MARKER_R + 4.5) * math.cos(t):.2f}" '
                    f'y2="{(MARKER_R + 4.5) * math.sin(t):.2f}"/>'
                )
            own = accent_value(o)
            style = f"--tx:{x:.1f}px;--ty:{y:.1f}px" + (f";--accent:{own}" if own else "")
            accent = own or self.pal["accent"]
            # The children sit about the origin: the page positions the group with
            # a CSS transform (which also counter-scales it at zoom, and outranks
            # this attribute), the attribute is what places it with no stylesheet.
            attrs = (
                f' style="{style}" transform="translate({x:.1f},{y:.1f})"'
                f' fill="none" stroke="{accent}" stroke-width="1.4"'
            ) + ("" if self.static else photo_attrs(o))
            label = html.escape(o["disp"])
            tattrs = f'x="{dx}" y="{dy}" text-anchor="{anchor}" font-size="12" font-weight="500"'
            text = f'<text {tattrs} fill="{accent}" stroke="none">{label}</text>'
            if self.static:
                # No paint-order in SVG Tiny, so the halo is a second copy of the
                # label underneath; stroking the glyph itself smears it illegible.
                text = (
                    f'<text {tattrs} fill="none" stroke="{self.pal["sky"]}" '
                    f'stroke-width="3" stroke-linejoin="round">{label}</text>'
                ) + text
            out.append(
                f'<g class="marker{" has-photo" if o.get("href") else ""}" id="mk-{uid}"{attrs}>'
                f'<circle r="{MARKER_R:g}" class="halo" stroke-width="5" opacity="0.14"/>'
                f'<circle r="{MARKER_R:g}" class="ring"/>{"".join(ticks)}{text}</g>'
            )
        return "".join(out)

    def _layers(self):
        """Every drawing layer, in paint order, built once.

        Order is load-bearing twice over: the rim goes down after the stars, and
        the constellation names must precede the markers because their boxes feed
        label-collision scoring. `place_label` records as it goes, so emitting a
        second time would re-place every label — hence the cache.
        """
        if self._layers_svg is None:
            p = self.pal
            self._layers_svg = f"""
  <circle class="disc" cx="{CX:g}" cy="{CY:g}" r="{R_MAX:g}" fill="{p['sky']}"/>
  <g class="grid" fill="none" stroke="{p['grid']}" stroke-width="0.8">{self.grid_svg()}</g>
  {self.ecliptic_svg()}
  <g class="constellations" fill="none" stroke="{p['aster']}" stroke-width="1"
     stroke-linecap="round">{self.lines_svg()}</g>
  <g class="stars">{self.stars_svg()}</g>
  <g class="connames" fill="{p['conname']}" text-anchor="middle">{self.names_svg()}</g>
  <circle class="rim" cx="{CX:g}" cy="{CY:g}" r="{R_MAX:g}" fill="none"
          stroke="{p['equator']}" stroke-width="1.6"/>
  <g class="hours" fill="{p['dim']}" font-size="12" text-anchor="middle">{self.hours_svg()}</g>
  <g class="declabels" fill="{p['dim']}" font-size="9.5"
     text-anchor="middle">{self.declabels_svg()}</g>
  <g class="markers">{self.markers_svg()}</g>"""
        return self._layers_svg

    def placements(self):
        """The markers with the label offsets the placer settled on. Emits the
        layers first if that has not happened yet, since placement is decided
        there."""
        self._layers()
        return self.markers

    def svg(self, heading, hemi=None, hidden=False):
        head = f'<h2 class="hemi">{heading}</h2>' if heading else ""
        label = "southern" if self.south else "northern"
        cls = "chart hidden" if hidden else "chart"
        hemi_attr = f' data-hemi="{hemi}"' if hemi else ""
        return f"""{head}
<div class="{cls}"{hemi_attr}><svg class="sky" viewBox="0 0 {CX * 2:g} {CY * 2:g}" role="img"
     aria-label="Polar star chart of the {label} sky with photographed objects marked">\
{self._layers()}
</svg></div>"""

    def standalone_svg(self):
        """This disc as a complete SVG document.

        Namespaced root, an opaque background where the page had one on `body`,
        and paint carried entirely by presentation attributes — so a renderer
        with no CSS at all (SVG Tiny: Qt's QtSvg and friends) draws it the way a
        browser draws the HTML page. No stylesheet, no script, and no external
        reference of any kind. `id="mk-N"` survives, so a host can also ask its
        renderer for a marker's bounds by element id.
        """
        label = "southern" if self.south else "northern"
        size = f"{CX * 2:g}"
        return f"""<svg xmlns="http://www.w3.org/2000/svg" class="sky" \
viewBox="0 0 {size} {size}" width="{size}" height="{size}" font-family="{self.font}" \
role="img" aria-label="Polar star chart of the {label} sky with photographed objects marked">
  <rect x="0" y="0" width="{size}" height="{size}" fill="{self.pal['deep']}"/>\
{self._layers()}
</svg>"""


def assign_charts(
    objects,
    sky,
    *,
    mag_limit,
    show_ecliptic,
    mirror=False,
    palette=None,
    font_family=None,
    static=False,
):
    """The hemisphere discs an object list needs, north first, with every object
    placed on its own disc.

    One derivation serves the HTML page and the standalone SVG; a second copy of
    which objects land on which disc would drift.
    """
    kw = dict(mirror=mirror, palette=palette, font_family=font_family, static=static)
    need_south = any(o["dec"] < -DEC_EDGE for o in objects)
    need_north = any(o["dec"] > DEC_EDGE for o in objects) or not need_south
    charts = []
    if need_north:
        charts.append(Chart(False, sky, mag_limit, show_ecliptic, **kw))
    if need_south:
        charts.append(Chart(True, sky, mag_limit, show_ecliptic, **kw))

    for i, o in enumerate(objects):
        if len(charts) == 2:
            chart = charts[0] if o["dec"] >= 0 else charts[1]
        else:
            chart = charts[0]
        chart.add_object(o, i)
    return charts
