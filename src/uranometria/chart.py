"""Polar hemisphere chart: projection, stars, constellation figures, markers."""

import html
import math

# ---------------------------------------------------------------- geometry
CX = CY = 500.0
R_MAX = 470.0
DEC_EDGE = 35.0  # how far past the equator each hemisphere chart reaches
SCALE = R_MAX / (90.0 + DEC_EDGE)


def project(ra_deg, dec_deg, south=False):
    """Azimuthal equidistant about the celestial pole. Northern charts run RA
    counterclockwise (0h at top); southern charts mirror it clockwise."""
    r = (90.0 + dec_deg if south else 90.0 - dec_deg) * SCALE
    a = math.radians(ra_deg)
    x = CX + r * math.sin(a) if south else CX - r * math.sin(a)
    return x, CY - r * math.cos(a)


def visible(dec, south):
    return dec >= -DEC_EDGE if not south else dec <= DEC_EDGE


def star_color(bv):
    try:
        bv = float(bv)
    except (TypeError, ValueError):
        return "#E9EDFB"
    if bv < 0.0:
        return "#C7D9FF"
    if bv < 0.6:
        return "#E9EDFB"
    if bv < 1.2:
        return "#FFEDCF"
    return "#FFD9AE"


class Chart:
    """One hemisphere disc."""

    def __init__(self, south, sky_data, mag_limit, show_ecliptic):
        self.south = south
        self.data = sky_data
        self.mag_limit = mag_limit
        self.show_ecliptic = show_ecliptic
        self.markers = []  # dicts: x, y, o (object), uid
        self.label_boxes = []  # placed text boxes for collision avoidance
        self.name_boxes = []  # constellation-name boxes

    def p(self, ra, dec):
        return project(ra, dec, self.south)

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
                f'fill="{star_color(f["properties"].get("bv"))}" opacity="{op:.2f}"/>'
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
                                '<path d="M' + " L".join(f"{x:.1f},{y:.1f}" for x, y in run) + '"/>'
                            )
                        run = []
                if len(run) > 1:
                    out.append('<path d="M' + " L".join(f"{x:.1f},{y:.1f}" for x, y in run) + '"/>')
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
                f'<text x="{x:.1f}" y="{y:.1f}" class="cn{rank}" opacity="{op}">'
                f"{html.escape(label)}</text>"
            )
        return "".join(out)

    def grid_svg(self):
        out = []
        decs = (60, 30, 0, -30) if not self.south else (-60, -30, 0, 30)
        for dec in decs:
            r = (90 - dec if not self.south else 90 + dec) * SCALE
            cls = "equator" if dec == 0 else "declin"
            out.append(f'<circle cx="{CX}" cy="{CY}" r="{r:.1f}" class="{cls}"/>')
        for h in range(0, 24, 2):
            a = math.radians(h * 15)
            sx = -math.sin(a) if not self.south else math.sin(a)
            x1, y1 = CX + 12 * sx, CY - 12 * math.cos(a)
            x2, y2 = CX + R_MAX * sx, CY - R_MAX * math.cos(a)
            out.append(
                f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" class="declin"/>'
            )
        return "".join(out)

    def hours_svg(self):
        out = []
        for h in range(0, 24, 2):
            a = math.radians(h * 15)
            sx = -math.sin(a) if not self.south else math.sin(a)
            x, y = CX + (R_MAX + 16) * sx, CY - (R_MAX + 16) * math.cos(a)
            out.append(f'<text x="{x:.1f}" y="{y:.1f}" dy="0.35em">{h}h</text>')
        return "".join(out)

    def declabels_svg(self):
        out = []
        decs = (60, 30, 0, -30) if not self.south else (-60, -30, 0, 30)
        for dec in decs:
            r = (90 - dec if not self.south else 90 + dec) * SCALE
            a = math.radians(15)
            sx = -math.sin(a) if not self.south else math.sin(a)
            x, y = CX + (r - 2) * sx, CY - (r - 2) * math.cos(a)
            t = f"{dec:+d}°" if dec else "0°"
            out.append(f'<text x="{x:.1f}" y="{y:.1f}" dy="-0.4em">{t}</text>')
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
        return f'<path class="ecliptic" d="{d}"/>'

    def markers_svg(self):
        out = []
        for m in self.markers:
            x, y, o, uid = m["x"], m["y"], m["o"], m["uid"]
            dx, dy, anchor = self.place_label(x, y, o["disp"])
            ticks = []
            for ang in (45, 135, 225, 315):
                t = math.radians(ang)
                ticks.append(
                    f'<line x1="{8.5*math.cos(t):.2f}" y1="{8.5*math.sin(t):.2f}" '
                    f'x2="{13*math.cos(t):.2f}" y2="{13*math.sin(t):.2f}"/>'
                )
            style = f"--tx:{x:.1f}px;--ty:{y:.1f}px"
            if o.get("color"):
                style += f';--accent:{html.escape(o["color"], quote=True)}'
            attrs = f' style="{style}"'
            if o.get("href"):
                attrs += (
                    f' data-img="{html.escape(o["href"], quote=True)}"'
                    f' data-cap="{html.escape(o["caption"], quote=True)}"'
                )
            out.append(
                f'<g class="marker{" has-photo" if o.get("href") else ""}" id="mk-{uid}"{attrs}>'
                f'<circle r="8.5" class="halo"/><circle r="8.5" class="ring"/>{"".join(ticks)}'
                f'<text x="{dx}" y="{dy}" text-anchor="{anchor}">{html.escape(o["disp"])}</text></g>'
            )
        return "".join(out)

    def svg(self, heading, hemi=None, hidden=False):
        head = f'<h2 class="hemi">{heading}</h2>' if heading else ""
        label = "southern" if self.south else "northern"
        cls = "chart hidden" if hidden else "chart"
        hemi_attr = f' data-hemi="{hemi}"' if hemi else ""
        return f"""{head}
<div class="{cls}"{hemi_attr}><svg class="sky" viewBox="0 0 1000 1000" role="img"
     aria-label="Polar star chart of the {label} sky with photographed objects marked">
  <circle cx="500" cy="500" r="470" fill="var(--sky)"/>
  <g class="grid">{self.grid_svg()}</g>
  {self.ecliptic_svg()}
  <g class="constellations">{self.lines_svg()}</g>
  <g class="stars">{self.stars_svg()}</g>
  <g class="connames">{self.names_svg()}</g>
  <circle class="rim" cx="500" cy="500" r="470"/>
  <g class="hours">{self.hours_svg()}</g>
  <g class="declabels">{self.declabels_svg()}</g>
  <g class="markers">{self.markers_svg()}</g>
</svg></div>"""
