"""Standalone interactive HTML page for one annotated image.

One self-contained file: the photograph (embedded as a data URI), the
annotation overlay drawn in SVG, pan/zoom with counter-scaled markers, a
LABELS toggle, and a searchable sidebar with catalog links. Shares its
interaction code and palette with the sky-chart pages.
"""

import base64
import html
import io
import json
import os

from ..resources import asset_text
from ..webui import ANNOTATION_COLORS, PANZOOM_JS
from .render_png import _load_image, dso_color, fmt_dist_ly, needs_flip
from .render_png import _default_title, _hms, _dms


def _image_data_uri(image_path):
    """Displayable data URI for the image: original bytes for rasters, a
    stretched JPEG render for FITS."""
    p = os.fspath(image_path)
    if p.lower().endswith((".fit", ".fits", ".fts")):
        import numpy as np
        from PIL import Image

        arr = _load_image(p)  # stretched floats, array row 0 first
        arr8 = (np.clip(arr, 0, 1) * 255).astype("uint8")
        im = Image.fromarray(
            arr8 if arr8.ndim == 3 else arr8, mode="RGB" if arr8.ndim == 3 else "L"
        )
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=90)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    ext = os.path.splitext(p)[1].lower().lstrip(".")
    mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "tif": "tiff", "tiff": "tiff"}.get(
        ext, "jpeg"
    )
    with open(p, "rb") as f:
        return f"data:image/{mime};base64," + base64.b64encode(f.read()).decode()


def _obj_color(o):
    if o["kind"] == "dso":
        return dso_color(o.get("type"))
    return ANNOTATION_COLORS["named_star"] if o.get("named") else ANNOTATION_COLORS["field_star"]


def _overlay_svg(objects, w, h):
    r = 0.02 * min(w, h)
    parts = []
    for o in objects:
        color = html.escape(_obj_color(o), quote=True)
        label = str(o["key"]) if o["kind"] == "star" and not o.get("named") else o["designation"]
        radius = r * 1.4 if o["kind"] == "dso" else (r if o.get("named") else r * 0.6)
        parts.append(
            f'<g class="ann" style="--tx:{o["x"]:.1f}px;--ty:{o["y"]:.1f}px;color:{color}">'
            f'<circle r="{radius:.1f}"/>'
            f'<text x="{r * 1.6:.1f}" y="{-r * 0.8:.1f}">{html.escape(label)}</text></g>'
        )
    return "".join(parts)


def _sidebar_cards(objects):
    cards = []
    for i, o in enumerate(objects):
        color = html.escape(_obj_color(o), quote=True)
        title = html.escape(o["designation"])
        if o.get("aliases"):
            title += " · " + html.escape(" · ".join(o["aliases"]))
        name = f'<span class="common">{html.escape(o["name"])}</span>' if o.get("name") else ""
        bits = []
        if o.get("type"):
            bits.append(html.escape(o["type"]))
        if o.get("mag") is not None:
            bits.append(f"{html.escape(o.get('band', ''))}={o['mag']}")
        dist = fmt_dist_ly(o.get("dist_ly"))
        if dist:
            bits.append(html.escape(dist))
        links = []
        for label, key in (("SIMBAD", "simbad"), ("Wikipedia", "wikipedia")):
            url = (o.get("links") or {}).get(key)
            if url:
                links.append(
                    f'<a href="{html.escape(url, quote=True)}" target="_blank" rel="noopener">{label}</a>'
                )
        key_badge = (
            f'<span class="keybadge">{o["key"]}</span>'
            if o["kind"] == "star" and not o.get("named")
            else ""
        )
        cards.append(
            f'<li data-ann="{i}" style="--accent:{color}">'
            f'<div class="obj"><span class="desig">{key_badge}{title}</span>{name}'
            f'<span class="meta">{" · ".join(bits)}</span>'
            f'<span class="linkrow">{" ".join(links)}</span></div></li>'
        )
    return "".join(cards)


def render_html(model, image_path, output, *, title=None):
    """Write the standalone annotated-image page. Returns the output path."""
    if not isinstance(model, dict):
        with open(model) as f:
            model = json.load(f)
    w, h = model["image_size"]

    # normalize object coordinates into the displayed raster's frame:
    # rasters display as-is; FITS renders via _load_image in array order,
    # which matches fits0 directly, so flipping is only needed cross-kind
    objects = [dict(o) for o in model["objects"]]
    if needs_flip(model["solved"].get("pixel_frame"), image_path):
        for o in objects:
            o["y"] = (h - 1) - o["y"]

    solved = model["solved"]
    page_title = title or _default_title(model)
    solve_line = (
        f"plate-solved {_hms(solved['center_ra'])} {_dms(solved['center_dec'])}"
        f" · {solved['scale_arcsec_px']:.2f}″/px"
        f" · {solved['fov_deg'][0]:.2f}°×{solved['fov_deg'][1]:.2f}° FOV"
        f" · {solved.get('solver', 'ASTAP')}"
    )
    data_uri = _image_data_uri(image_path)
    n_obj = len(objects)

    def b64(fn):
        return asset_text(fn + ".b64")

    return_path = os.fspath(output)
    page = f"""<title>{html.escape(page_title)} — Annotated</title>
<style>
@font-face {{ font-family:'Marcellus'; font-style:normal; font-weight:400;
  src:url(data:font/woff2;base64,{b64("marcellus-normal-400.woff2")}) format('woff2'); }}
@font-face {{ font-family:'Plex Mono'; font-style:normal; font-weight:400;
  src:url(data:font/woff2;base64,{b64("plexmono-normal-400.woff2")}) format('woff2'); }}
@font-face {{ font-family:'Plex Mono'; font-style:normal; font-weight:500;
  src:url(data:font/woff2;base64,{b64("plexmono-normal-500.woff2")}) format('woff2'); }}
:root {{
  --sky:#0A0F24; --deep:#070B1B; --star:#E9EDFB; --grid:#232D55; --equator:#39466F;
  --gold:#E5B958; --accent:#E5B958; --ink:#C7CEE6; --dim:#7C86AC;
}}
html {{ background:var(--deep); }}
body {{ margin:0; background:var(--deep); color:var(--ink);
  font-family:'Plex Mono',monospace; -webkit-font-smoothing:antialiased; }}
.wrap {{ max-width:1500px; margin:0 auto; padding:20px 24px; height:100vh;
  box-sizing:border-box; display:flex; flex-direction:column; }}
header {{ text-align:center; margin-bottom:14px; flex:none; }}
header h1 {{ font-family:'Marcellus',serif; font-weight:400; color:var(--star);
  font-size:clamp(22px,3.5vw,34px); letter-spacing:0.12em; margin:0; }}
header .sub {{ color:var(--dim); font-size:11.5px; letter-spacing:0.08em; margin-top:8px; }}
.layout {{ flex:1 1 0; min-height:0; display:grid;
  grid-template-columns:minmax(0,1fr) 330px; gap:24px; }}
.stage {{ min-height:0; display:flex; flex-direction:column; }}
.stage .tools {{ display:flex; gap:10px; align-items:center; margin-bottom:8px; flex:none; }}
#img-svg {{ flex:1 1 auto; min-height:0; width:100%; background:#000;
  border:1px solid var(--grid); cursor:grab; touch-action:none; }}
#img-svg:active {{ cursor:grabbing; }}
.btn {{ font-family:'Plex Mono',monospace; font-size:10px; letter-spacing:0.16em;
  color:var(--dim); background:var(--sky); border:1px solid var(--grid);
  padding:5px 14px; cursor:pointer; }}
.btn.on {{ color:var(--gold); border-color:var(--gold); }}
.hint {{ color:var(--dim); font-size:9px; letter-spacing:0.1em; }}
.ann {{ transform:translate(var(--tx),var(--ty)) scale(calc(1 / var(--z,1))); }}
.ann circle {{ fill:none; stroke:currentColor; stroke-width:1.6; }}
.ann text {{ fill:currentColor; font-family:'Plex Mono',monospace; font-size:13px;
  font-weight:500; paint-order:stroke; stroke:rgba(0,0,0,0.8); stroke-width:3px; }}
.hide-labels #overlay {{ display:none; }}
svg.focus .ann {{ opacity:0.25; }}
svg.focus .ann.lit {{ opacity:1; }}
.panel {{ min-height:0; display:flex; flex-direction:column; }}
.panel h2 {{ font-family:'Marcellus',serif; font-weight:400; color:var(--star);
  font-size:15px; letter-spacing:0.22em; text-align:center; margin:0 0 12px; }}
.search {{ width:100%; box-sizing:border-box; margin-bottom:10px;
  background:var(--sky); border:1px solid var(--grid); color:var(--star);
  font-family:'Plex Mono',monospace; font-size:12px; padding:8px 12px; outline:none; }}
.search:focus {{ border-color:var(--accent); }}
.count {{ color:var(--dim); font-size:10px; letter-spacing:0.1em; margin:0 0 8px 2px; }}
.scroll {{ flex:1 1 0; overflow-y:auto; scrollbar-width:thin; min-height:0;
  border-top:1px solid var(--grid); padding-top:8px;
  scrollbar-color:var(--grid) transparent; }}
.panel ul {{ list-style:none; margin:0; padding:0 6px 6px 0; display:grid; gap:7px; }}
.panel li {{ padding:10px 12px; border:1px solid var(--grid); background:var(--sky);
  transition:border-color .2s; }}
.panel li:hover {{ border-color:var(--accent); }}
.obj {{ display:flex; flex-direction:column; gap:3px; }}
.desig {{ color:var(--accent); font-weight:500; font-size:12.5px; letter-spacing:0.04em; }}
.keybadge {{ display:inline-block; min-width:16px; text-align:center;
  border:1px solid var(--accent); font-size:10px; margin-right:8px; padding:0 3px; }}
.common {{ font-family:'Marcellus',serif; color:var(--star); font-size:14px; }}
.meta {{ font-size:10.5px; }}
.linkrow a {{ color:var(--dim); font-size:10px; letter-spacing:0.08em;
  text-decoration:none; border-bottom:1px dotted var(--dim); margin-right:10px; }}
.linkrow a:hover {{ color:var(--gold); border-color:var(--gold); }}
footer {{ margin-top:10px; text-align:center; color:var(--dim); font-size:9.5px;
  letter-spacing:0.06em; flex:none; }}
@media (max-width:960px) {{
  .wrap {{ height:auto; display:block; }}
  .layout {{ display:block; }}
  #img-svg {{ height:70vh; }}
  .scroll {{ overflow:visible; }}
}}
</style>
<div class="wrap">
<header>
  <h1>{html.escape(page_title.upper())}</h1>
  <div class="sub">{html.escape(solve_line.upper())}</div>
</header>
<div class="layout">
<div class="stage">
  <div class="tools">
    <button id="labels" class="btn on">LABELS ON</button>
    <span class="hint">SCROLL TO ZOOM · DRAG TO PAN · DOUBLE-CLICK TO RESET</span>
  </div>
  <svg id="img-svg" viewBox="0 0 {w} {h}" role="img" aria-label="{html.escape(page_title, quote=True)}">
    <image href="{data_uri}" width="{w}" height="{h}"/>
    <g id="overlay">{_overlay_svg(objects, w, h)}</g>
  </svg>
</div>
<aside class="panel">
  <h2>IN THIS IMAGE</h2>
  <input class="search" id="search" type="search" placeholder="Search objects…" aria-label="Search objects">
  <p class="count" id="count">{n_obj} OBJECTS</p>
  <div class="scroll"><ul id="cards">{_sidebar_cards(objects)}</ul></div>
</aside>
</div>
<footer>Generated by uranometria · solve: {html.escape(solved.get("solver", "ASTAP"))} · OpenNGC · Gaia DR3 · SIMBAD</footer>
</div>
<script>
{PANZOOM_JS}
const svg = document.getElementById('img-svg');
attachPanZoom(svg, {w}, {h}, null);

const stage = document.querySelector('.stage');
const labelsBtn = document.getElementById('labels');
labelsBtn.addEventListener('click', () => {{
  const on = !labelsBtn.classList.contains('on');
  labelsBtn.classList.toggle('on', on);
  labelsBtn.textContent = on ? 'LABELS ON' : 'LABELS OFF';
  stage.classList.toggle('hide-labels', !on);
}});

const anns = Array.from(document.querySelectorAll('.ann'));
const cards = Array.from(document.querySelectorAll('#cards li'));
const searchBox = document.getElementById('search');
const countEl = document.getElementById('count');
function applySearch() {{
  const q = searchBox.value.trim().toLowerCase();
  let shown = 0;
  cards.forEach((li, i) => {{
    const hit = !q || li.textContent.toLowerCase().includes(q);
    li.style.display = hit ? '' : 'none';
    if (hit) shown++;
    if (anns[i]) anns[i].classList.toggle('lit', !!q && hit);
  }});
  svg.classList.toggle('focus', !!q);
  countEl.textContent = q ? `${{shown}} OF ${{cards.length}} OBJECTS` : `${{cards.length}} OBJECTS`;
}}
searchBox.addEventListener('input', applySearch);
cards.forEach((li, i) => {{
  li.addEventListener('mouseenter', () => {{ svg.classList.add('focus'); anns[i] && anns[i].classList.add('lit'); }});
  li.addEventListener('mouseleave', applySearch);
}});
</script>
"""
    with open(return_path, "w") as f:
        f.write(page)
    return return_path
