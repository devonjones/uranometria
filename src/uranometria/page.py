"""Assemble the full HTML page: header, hemisphere charts, legend, lightbox."""

import html

import json as _json

from .chart import Chart, DEC_EDGE, accent_value, photo_attrs
from .resources import asset_text, sky_data
from .webui import ANNOTATION_UI_CSS, ANNOTATION_UI_JS, DSO_COLOR_JS, PANZOOM_JS, js_color_map


def _linkrow(o):
    links = o.get("links") or []
    if not links:
        return ""
    anchors = "".join(
        f'<a href="{html.escape(url, quote=True)}" target="_blank"'
        f' rel="noopener">{html.escape(label)}</a>'
        for label, url in links
    )
    return f'\n    <span class="linkrow">{anchors}</span>'


def _legend_html(objects):
    items = []
    for i, o in enumerate(objects):
        meta = o["type"] + (f" — {o['constellation']}" if o["constellation"] else "")
        common = f'<span class="common">{html.escape(o["common"])}</span>' if o["common"] else ""
        accent = accent_value(o)
        attrs = f' style="--accent:{accent}"' if accent else ""
        attrs += photo_attrs(o)
        photo = ' <span class="photo">PHOTO ↗</span>' if o.get("href") else ""
        if o.get("annotation"):
            # model is embedded in this page: open the lightbox in
            # annotation mode instead of leaving for the standalone file
            photo += ' <span class="annlink" role="button" tabindex="0">ANNOTATED</span>'
        elif o.get("annotated_href"):
            photo += (
                f' <a class="annlink" href="{html.escape(o["annotated_href"], quote=True)}"'
                f' target="_blank" rel="noopener">ANNOTATED \u2197</a>'
            )
        items.append(f"""<li data-target="mk-{i}"{attrs}>
  <span class="glyph" aria-hidden="true"><svg viewBox="-14 -14 28 28"><circle r="7" class="ring"/>
    <line x1="4.9" y1="4.9" x2="9.2" y2="9.2"/><line x1="-4.9" y1="4.9" x2="-9.2" y2="9.2"/>
    <line x1="4.9" y1="-4.9" x2="9.2" y2="-9.2"/><line x1="-4.9" y1="-4.9" x2="-9.2" y2="-9.2"/></svg></span>
  <div class="obj"><span class="desig">{html.escape(o["disp"])}{photo}</span>{common}
    <span class="meta">{html.escape(meta)}</span>{_linkrow(o)}
    <span class="coord">{html.escape(o["coord"])}</span></div>
</li>""")
    return "".join(items)


def build_page(cfg, objects):
    mag_limit = float(cfg.get("mag_limit", 5.0))
    show_ecl = bool(cfg.get("show_ecliptic", True))
    mirror = bool(cfg.get("mirror", False))
    data = sky_data()

    need_south = any(o["dec"] < -DEC_EDGE for o in objects)
    need_north = any(o["dec"] > DEC_EDGE for o in objects) or not need_south
    charts = []
    if need_north:
        charts.append(Chart(False, data, mag_limit, show_ecl, mirror=mirror))
    if need_south:
        charts.append(Chart(True, data, mag_limit, show_ecl, mirror=mirror))

    for i, o in enumerate(objects):
        if len(charts) == 2:
            chart = charts[0] if o["dec"] >= 0 else charts[1]
        else:
            chart = charts[0]
        chart.add_object(o, i)

    two = len(charts) == 2
    if two:
        chart_html = (
            '<div class="hemitoggle" id="hemitoggle">'
            '<button class="active" data-hemi="north">NORTHERN</button>'
            '<button data-hemi="south">SOUTHERN</button></div>'
            + charts[0].svg("", hemi="north")
            + charts[1].svg("", hemi="south", hidden=True)
        )
    else:
        chart_html = charts[0].svg("")

    n = len(objects)
    default_title = (
        "THE NIGHT SKY" if two else ("THE SOUTHERN SKY" if charts[0].south else "THE NORTHERN SKY")
    )
    # case-transform first, escape last — transforming escaped text corrupts
    # the entity names themselves (&amp; -> &Amp;)
    raw_title = str(cfg.get("title", default_title))
    title = html.escape(raw_title.upper())
    tab_title = html.escape(raw_title.title())
    default_sub = f"{n} DEEP-SKY OBJECT{'S' if n != 1 else ''} · EPOCH J2000"
    subtitle = html.escape(str(cfg.get("subtitle", default_sub)).upper())

    def b64(fn):
        return asset_text(fn + ".b64")

    annotations = {f"mk-{i}": o["annotation"] for i, o in enumerate(objects) if o.get("annotation")}
    thumbs = {f"mk-{i}": o["thumb"] for i, o in enumerate(objects) if o.get("thumb")}
    thumbs_json = _json.dumps(thumbs, allow_nan=False).replace("<", "\\u003c")
    # </script> can never appear inside the JSON payload
    # \u003c-escape every "<" so no payload string can toy with the HTML
    # script-data parser states (e.g. "<!--<script" double-escape tricks)
    annotations_json = _json.dumps(annotations, allow_nan=False).replace("<", "\\u003c")
    ann_label_scale = float(cfg.get("annotation_label_scale", 1.0))

    panzoom_js = PANZOOM_JS
    dso_color_js = DSO_COLOR_JS
    ann_ui_js = ANNOTATION_UI_JS
    ann_ui_css = ANNOTATION_UI_CSS
    ann_colors = js_color_map()

    return f"""<title>{tab_title} — Photographed Objects</title>
<style>
@font-face {{ font-family:'Marcellus'; font-style:normal; font-weight:400;
  src:url(data:font/woff2;base64,{b64("marcellus-normal-400.woff2")}) format('woff2'); }}
@font-face {{ font-family:'Plex Mono'; font-style:normal; font-weight:400;
  src:url(data:font/woff2;base64,{b64("plexmono-normal-400.woff2")}) format('woff2'); }}
@font-face {{ font-family:'Plex Mono'; font-style:normal; font-weight:500;
  src:url(data:font/woff2;base64,{b64("plexmono-normal-500.woff2")}) format('woff2'); }}
:root {{
  --sky:#0A0F24; --deep:#070B1B; --star:#E9EDFB; --grid:#232D55; --equator:#39466F;
  --aster:#3E4F86; --conname:#8492C0; --gold:#E5B958; --accent:#E5B958;
  --ink:#C7CEE6; --dim:#7C86AC;
}}
html {{ background:var(--deep); }}
body {{ margin:0; background:var(--deep); color:var(--ink);
  font-family:'Plex Mono',monospace; -webkit-font-smoothing:antialiased; }}
.wrap {{ max-width:1400px; margin:0 auto; padding:20px 24px;
  height:100vh; box-sizing:border-box; display:flex; flex-direction:column; }}
.layout {{ flex:1 1 0; min-height:0; display:grid;
  grid-template-columns:minmax(0,1fr) 330px; gap:26px; }}
.charts {{ min-height:0; overflow-y:auto; scrollbar-width:thin;
  display:flex; flex-direction:column; }}
.panel {{ min-height:0; display:flex; flex-direction:column; }}
.panel .scroll {{ flex:1 1 0; overflow-y:auto; scrollbar-width:thin; min-height:0;
  border-top:1px solid var(--grid); padding-top:10px; }}
.charts, .panel .scroll {{ scrollbar-color:var(--grid) transparent; }}
@media (max-width:960px) {{
  .wrap {{ height:auto; display:block; }}
  .layout {{ grid-template-columns:1fr; display:block; }}
  .panel .scroll {{ overflow:visible; }}
  .chart {{ flex:none; }}
  .chart svg {{ max-height:none; width:100%; }}
}}
header {{ text-align:center; margin-bottom:18px; flex:none; }}
header h1 {{ font-family:'Marcellus',serif; font-weight:400; color:var(--star);
  font-size:clamp(28px,4.5vw,44px); letter-spacing:0.14em; margin:0; text-wrap:balance; }}
header .sub {{ color:var(--dim); font-size:12.5px; letter-spacing:0.08em; margin-top:14px; }}
header .rule {{ width:220px; height:1px; margin:14px auto 0;
  background:linear-gradient(90deg,transparent,var(--gold),transparent); opacity:0.7; }}
.hemi {{ font-family:'Marcellus',serif; font-weight:400; color:var(--star); text-align:center;
  font-size:16px; letter-spacing:0.26em; margin:16px 0 6px; flex:none; }}
.chart {{ display:flex; justify-content:center; flex:1 1 auto; min-height:0; }}
.chart.hidden {{ display:none; }}
.hemitoggle {{ display:flex; justify-content:center; margin:0 0 12px; flex:none; }}
.hemitoggle button {{ font-family:'Plex Mono',monospace; font-size:11px;
  letter-spacing:0.18em; color:var(--dim); background:var(--sky);
  border:1px solid var(--grid); padding:7px 18px; cursor:pointer; }}
.hemitoggle button + button {{ border-left:none; }}
.hemitoggle button.active {{ color:var(--gold); border-color:var(--gold); }}
.hemitoggle button + button.active {{ border-left:1px solid var(--gold); }}
.hemitoggle button:focus-visible {{ outline:1px solid var(--star); }}
.chart svg {{ display:block; width:auto; height:auto; max-width:100%;
  max-height:100%; cursor:grab; touch-action:none; }}
.chart svg:active {{ cursor:grabbing; }}
.zoomhint {{ text-align:center; color:var(--dim); font-size:10px;
  letter-spacing:0.08em; margin:8px 0 0; flex:none; }}
svg text {{ font-family:'Plex Mono',monospace; }}
.connames .cn1 {{ font-size:calc(13.5px / var(--z,1)); }}
.connames .cn2 {{ font-size:calc(11px / var(--z,1)); }}
.connames .cn3 {{ font-size:calc(9.5px / var(--z,1)); }}
.constellations path {{ stroke:var(--aster); stroke-width:1; fill:none; opacity:0.75;
  stroke-linecap:round; vector-effect:non-scaling-stroke; }}
.grid circle, .grid line, .rim, .ecliptic {{ vector-effect:non-scaling-stroke; }}
.connames text {{ font-family:'Marcellus',serif; fill:var(--conname);
  letter-spacing:0.18em; text-anchor:middle; }}
.grid .declin {{ stroke:var(--grid); stroke-width:0.8; fill:none; }}
.grid .equator {{ stroke:var(--equator); stroke-width:1.2; fill:none; }}
.rim {{ stroke:var(--equator); stroke-width:1.6; fill:none; }}
.hours text {{ fill:var(--dim); font-size:calc(12px / var(--z,1)); text-anchor:middle; }}
.declabels text {{ fill:var(--dim); font-size:calc(9.5px / var(--z,1)); text-anchor:middle; opacity:0.9; }}
.ecliptic {{ stroke:#5E4A7D; stroke-width:1.1; fill:none; stroke-dasharray:5 5; opacity:0.8; }}
.marker .ring {{ stroke:var(--accent); stroke-width:1.4; fill:none; }}
.marker .halo {{ stroke:var(--accent); stroke-width:5; fill:none; opacity:0.14; }}
.marker line {{ stroke:var(--accent); stroke-width:1.4; }}
.marker text {{ fill:var(--accent); font-size:12px; font-weight:500; letter-spacing:0.04em;
  paint-order:stroke; stroke:var(--sky); stroke-width:3px; }}
.marker {{ transition:opacity .2s;
  transform:translate(var(--tx),var(--ty)) scale(calc(1 / var(--z,1))); }}
.marker.has-photo {{ cursor:zoom-in; }}
.marker.has-photo:hover .halo {{ opacity:0.35; }}
svg.focus .marker {{ opacity:0.25; }}
svg.focus .marker.lit {{ opacity:1; }}
svg.focus .marker.lit .halo {{ opacity:0.35; }}
.legend h2 {{ font-family:'Marcellus',serif; font-weight:400; color:var(--star);
  font-size:15px; letter-spacing:0.22em; text-align:center; margin:0 0 14px; }}
.search {{ width:100%; box-sizing:border-box; margin-bottom:12px;
  background:var(--sky); border:1px solid var(--grid); color:var(--star);
  font-family:'Plex Mono',monospace; font-size:12.5px; padding:9px 12px; outline:none; }}
.search:focus {{ border-color:var(--accent); }}
.search::placeholder {{ color:var(--dim); }}
.legend .count {{ color:var(--dim); font-size:10px; letter-spacing:0.1em;
  margin:0 0 10px 2px; }}
.legend ul {{ list-style:none; margin:0; padding:0 6px 6px 0; display:grid;
  grid-template-columns:1fr; gap:8px; }}
.legend li {{ display:flex; gap:12px; align-items:flex-start; padding:11px 13px;
  border:1px solid var(--grid); background:var(--sky); cursor:default; transition:border-color .2s; }}
.legend li:hover {{ border-color:var(--accent); }}
.legend li[data-img] {{ cursor:zoom-in; }}
.legend .glyph {{ flex:none; width:26px; height:26px; margin-top:2px; }}
.legend .glyph svg {{ width:100%; height:100%; }}
.legend .glyph .ring {{ stroke:var(--accent); stroke-width:1.6; fill:none; }}
.legend .glyph line {{ stroke:var(--accent); stroke-width:1.6; }}
.legend .obj {{ display:flex; flex-direction:column; gap:3px; min-width:0; }}
.legend .desig {{ color:var(--accent); font-weight:500; font-size:13px; letter-spacing:0.05em; }}
.legend .photo {{ color:var(--dim); font-size:9px; letter-spacing:0.14em; margin-left:8px; }}
.legend .annlink {{ color:var(--dim); font-size:9px; letter-spacing:0.14em; margin-left:8px;
  text-decoration:none; border-bottom:1px dotted var(--dim); cursor:pointer; }}
.legend .annlink:hover {{ color:var(--gold); border-color:var(--gold); }}
.legend li:hover .photo {{ color:var(--accent); }}
.legend .common {{ font-family:'Marcellus',serif; color:var(--star); font-size:15px; }}
.legend .meta {{ color:var(--ink); font-size:11px; }}
.legend .coord {{ color:var(--dim); font-size:11px; font-variant-numeric:tabular-nums; }}
.legend .linkrow a {{ color:var(--dim); font-size:9.5px; letter-spacing:0.1em;
  text-decoration:none; border-bottom:1px dotted var(--dim); margin-right:10px; }}
.legend .linkrow a:hover {{ color:var(--gold); border-color:var(--gold); }}
.lightbox {{ position:fixed; inset:0; z-index:10; display:flex; align-items:center;
  justify-content:center; background:rgba(4,6,16,0.93); cursor:zoom-out; }}
.lightbox[hidden] {{ display:none; }}
.lb-stage {{ display:flex; flex-direction:row; align-items:stretch; gap:14px;
  max-width:96vw; cursor:auto; }}
#lb-svg {{ max-width:94vw; max-height:78vh; border:1px solid var(--equator);
  box-shadow:0 12px 60px rgba(0,0,0,0.7); background:#000; cursor:grab;
  touch-action:none; display:block; }}
#lb-svg:active {{ cursor:grabbing; }}
.lb-tools {{ display:flex; gap:10px; min-height:26px; align-items:center; }}
.lb-btn {{ font-family:'Plex Mono',monospace; font-size:10px; letter-spacing:0.16em;
  color:var(--dim); background:var(--sky); border:1px solid var(--grid);
  padding:5px 14px; cursor:pointer; }}
.lb-btn.on {{ color:var(--gold); border-color:var(--gold); }}
.lb-hint {{ color:var(--dim); font-size:9px; letter-spacing:0.1em; }}
{ann_ui_css}
.lb-hide-ann #lb-overlay, .lb-hide-ann #lb-panel {{ display:none; }}
.lb-viewer {{ display:flex; flex-direction:column; align-items:center; gap:12px; min-width:0; }}
#lb-panel {{ width:270px; max-height:82vh; display:flex; flex-direction:column;
  background:var(--deep); border:1px solid var(--grid); padding:12px; }}
#lb-panel[hidden] {{ display:none; }}
.lb-count {{ color:var(--dim); font-size:9.5px; letter-spacing:0.1em; margin:0 0 8px 2px; }}
.lb-scroll {{ flex:1 1 0; overflow-y:auto; min-height:0; scrollbar-width:thin;
  scrollbar-color:var(--grid) transparent; }}
#lb-panel .search {{ margin-bottom:8px; font-size:11px; padding:6px 10px; }}
#lb-cards {{ list-style:none; margin:0; padding:0 4px 0 0; display:grid; gap:6px; }}
#lb-cards li {{ padding:8px 10px; border:1px solid var(--grid); background:var(--sky); }}
#lb-cards li:hover {{ border-color:var(--accent); }}
#lb-cards .obj {{ display:flex; flex-direction:column; gap:3px; }}
#lb-cards .desig {{ color:var(--accent); font-weight:500; font-size:11.5px; }}
#lb-cards .keybadge {{ display:inline-block; min-width:14px; text-align:center;
  border:1px solid var(--accent); font-size:9px; margin-right:7px; padding:0 3px; }}
#lb-cards .common {{ font-family:'Marcellus',serif; color:var(--star); font-size:13px; }}
#lb-cards .meta {{ color:var(--ink); font-size:10px; }}
#lb-cards .linkrow a {{ color:var(--dim); font-size:9.5px; letter-spacing:0.08em;
  text-decoration:none; border-bottom:1px dotted var(--dim); margin-right:8px; }}
#lb-cards .linkrow a:hover {{ color:var(--gold); border-color:var(--gold); }}
.lightbox.lb-max .lb-stage {{ width:96vw; height:94vh; max-width:none; }}
.lb-max .lb-viewer {{ flex:1 1 0; min-width:0; align-self:stretch; }}
.lb-max #lb-svg {{ flex:1 1 0; min-height:0; width:100%; height:100%;
  max-width:none; max-height:none; }}
.lb-max #lb-panel {{ max-height:none; }}
@media (max-width:900px) {{
  .lb-stage {{ flex-direction:column; overflow-y:auto; max-height:94vh; }}
  #lb-panel {{ width:auto; max-height:30vh; }}
}}
.marker image.thumb {{ display:none; }}
svg.sky.deepzoom .marker image.thumb {{ display:block; }}
#thumbtip {{ position:fixed; z-index:20; display:none; cursor:zoom-in;
  border:1px solid var(--equator); background:var(--deep); padding:3px;
  box-shadow:0 6px 24px rgba(0,0,0,0.6); }}
#thumbtip img {{ display:block; width:112px; height:auto; }}
.lightbox figcaption {{ text-align:center; }}
.lightbox .cap-name {{ font-family:'Marcellus',serif; color:var(--star); font-size:18px;
  letter-spacing:0.08em; }}
.lightbox .cap-sub {{ color:var(--dim); font-size:11.5px; margin-top:6px; letter-spacing:0.06em; }}
footer {{ margin-top:14px; text-align:center; color:var(--dim); font-size:10px;
  letter-spacing:0.06em; line-height:1.8; flex:none; }}
@media (prefers-reduced-motion:reduce) {{ .marker,.legend li {{ transition:none; }} }}
</style>
<div class="wrap">
<header>
  <h1>{title}</h1>
  <div class="sub">{subtitle}</div>
  <div class="rule"></div>
</header>
<div class="layout">
<div class="charts">
{chart_html}
<p class="zoomhint">SCROLL TO ZOOM · DRAG TO PAN · DOUBLE-CLICK TO RESET</p>
<footer>
  Azimuthal equidistant projection centered on the celestial pole{" (each hemisphere charted to decl. ±" + str(int(DEC_EDGE)) + "° past the equator)" if two else ""} · stars to magnitude {mag_limit:g} · {"mirrored (globe) view" if mirror else "sky view, as seen from Earth"}.<br>
  Catalog data: OpenNGC (CC-BY-SA), Sharpless via VizieR · star &amp; constellation data: d3-celestial (BSD).
</footer>
</div>
<aside class="panel legend">
  <h2>OBSERVING RECORD</h2>
  <input class="search" id="search" type="search" placeholder="Search objects…"
         aria-label="Search objects">
  <p class="count" id="count">{len(objects)} OBJECTS</p>
  <div class="scroll"><ul>{_legend_html(objects)}</ul></div>
</aside>
</div>
<div class="lightbox" id="lightbox" hidden>
  <div class="lb-stage">
    <div class="lb-viewer">
      <div class="lb-tools">
        <button id="lb-ann" class="lb-btn" hidden>ANNOTATIONS ON</button>
        <button id="lb-expand" class="lb-btn">EXPAND \u2922</button>
        <span class="lb-hint">SCROLL TO ZOOM \u00b7 DRAG TO PAN \u00b7 CLICK OUTSIDE OR ESC TO CLOSE</span>
      </div>
      <svg id="lb-svg" viewBox="0 0 1 1" role="img" aria-label="photograph"></svg>
      <figcaption><div class="cap-name" id="lb-name"></div><div class="cap-sub" id="lb-sub"></div></figcaption>
    </div>
    <aside id="lb-panel" hidden>
      <input class="search" id="lb-search" type="search" placeholder="Search objects\u2026"
             aria-label="Search annotated objects">
      <p class="lb-count" id="lb-count"></p>
      <div class="lb-scroll"><ul id="lb-cards"></ul></div>
    </aside>
  </div>
</div>
<script type="application/json" id="lb-annotations">{annotations_json}</script>
<script type="application/json" id="chart-thumbs">{thumbs_json}</script>
<div id="thumbtip"><img alt=""></div>
</div>
<script>
// ---- filtering: search text AND current zoom viewport ----------------
const searchBox = document.getElementById('search');
const countEl = document.getElementById('count');
const cards = Array.from(document.querySelectorAll('.legend li')).map(li => {{
  const mk = document.getElementById(li.dataset.target);
  return {{
    li, mk,
    svg: mk ? mk.closest('svg') : null,
    x: mk ? parseFloat(mk.style.getPropertyValue('--tx')) : 0,
    y: mk ? parseFloat(mk.style.getPropertyValue('--ty')) : 0,
    text: li.textContent.toLowerCase(),
  }};
}});
function inView(c) {{
  if (!c.svg || !c.svg._vb) return true;
  const [vx, vy, vw, vh] = c.svg._vb;
  if (vw >= 999) return true;                        // not zoomed
  const m = 15 / (1000 / vw);                        // marker slop in svg units
  return c.x >= vx - m && c.x <= vx + vw + m && c.y >= vy - m && c.y <= vy + vh + m;
}}
function chartShown(c) {{
  return !c.svg || !c.svg.closest('.chart').classList.contains('hidden');
}}
function anyZoomed() {{
  return Array.from(document.querySelectorAll('.chart:not(.hidden) svg.sky'))
    .some(s => s._vb && s._vb[2] < 999);
}}
function applyFilter() {{
  const q = searchBox.value.trim().toLowerCase();
  const zoomed = anyZoomed();
  let shown = 0;
  cards.forEach(c => {{
    const hit = (!q || c.text.includes(q)) && chartShown(c) && inView(c);
    c.li.style.display = hit ? '' : 'none';
    if (hit) shown++;
    if (c.mk) c.mk.classList.toggle('lit', !!q && hit);
  }});
  document.querySelectorAll('svg.sky').forEach(s => s.classList.toggle('focus', !!q));
  countEl.textContent = shown < cards.length
    ? `${{shown}} OF ${{cards.length}} OBJECTS${{zoomed ? ' · IN VIEW' : ''}}`
    : `${{cards.length}} OBJECTS`;
}}
searchBox.addEventListener('input', applyFilter);

// ---- hemisphere toggle (only present when both discs exist) ----------
const hemiToggle = document.getElementById('hemitoggle');
if (hemiToggle) {{
  hemiToggle.querySelectorAll('button').forEach(btn => {{
    btn.addEventListener('click', () => {{
      hemiToggle.querySelectorAll('button').forEach(b =>
        b.classList.toggle('active', b === btn));
      document.querySelectorAll('.chart[data-hemi]').forEach(ch =>
        ch.classList.toggle('hidden', ch.dataset.hemi !== btn.dataset.hemi));
      applyFilter();
    }});
  }});
}}

// ---- legend hover spotlight (restores filter state on leave) ---------
cards.forEach(c => {{
  if (!c.mk) return;
  c.li.addEventListener('mouseenter', () => {{ c.svg.classList.add('focus'); c.mk.classList.add('lit'); }});
  c.li.addEventListener('mouseleave', applyFilter);
}});

// ---- pan & zoom (shared) ---------------------------------------------
{panzoom_js}
{dso_color_js}
// ---- thumbnails: deep-zoom marker thumbs + hover tooltip (opt-in) -----
const THUMBS = JSON.parse(document.getElementById('chart-thumbs').textContent);
const DEEP_ZOOM = 4;

function ensureMarkerThumbs(svg) {{
  if (svg._thumbed) return;
  svg._thumbed = true;
  svg.querySelectorAll('.marker').forEach(m => {{
    const t = THUMBS[m.id];
    if (!t) return;
    const im = document.createElementNS('http://www.w3.org/2000/svg', 'image');
    im.setAttribute('href', t);
    im.setAttribute('x', 12);
    im.setAttribute('y', -68);
    im.setAttribute('width', 56);
    im.setAttribute('height', 56);
    im.setAttribute('class', 'thumb');
    // before the <text> so the haloed label stays legible on top; markers
    // near the viewport edge may clip the thumb (hover tooltip still works)
    m.insertBefore(im, m.querySelector('text'));
  }});
}}

const tip = document.getElementById('thumbtip');
const tipImg = tip.querySelector('img');
let lastTipEv = null;
let tipKey = null;
let tipHide = null;
tipImg.addEventListener('load', () => {{ if (lastTipEv) moveTip(lastTipEv); }});
function hideTipSoon() {{
  clearTimeout(tipHide);
  tipHide = setTimeout(() => {{ tip.style.display = 'none'; tipKey = null; }}, 120);
}}
tip.addEventListener('mouseenter', () => clearTimeout(tipHide));
tip.addEventListener('mouseleave', hideTipSoon);
tip.addEventListener('click', () => {{
  const mk = tipKey && document.getElementById(tipKey);
  tip.style.display = 'none';
  if (mk && mk.dataset.img) {{
    openLightbox(mk.dataset.img, (mk.dataset.cap || '').split('|'), ANNOTATIONS[tipKey]);
  }}
}});
function moveTip(ev) {{
  lastTipEv = ev;
  const pad = 14;
  const r = tip.getBoundingClientRect();
  let x = ev.clientX + pad, y = ev.clientY + pad;
  if (x + r.width > innerWidth - 4) x = ev.clientX - r.width - pad;
  if (y + r.height > innerHeight - 4) y = ev.clientY - r.height - pad;
  tip.style.left = x + 'px';
  tip.style.top = y + 'px';
}}
if (Object.keys(THUMBS).length) {{
  document.querySelectorAll('.marker, .legend li[data-target]').forEach(el => {{
    const key = el.id || el.dataset.target;
    if (!THUMBS[key]) return;
    el.addEventListener('mouseenter', ev => {{
      clearTimeout(tipHide);
      tipKey = key;
      tipImg.src = THUMBS[key];
      tip.style.display = 'block';
      moveTip(ev);
    }});
    el.addEventListener('mousemove', moveTip);
    el.addEventListener('mouseleave', hideTipSoon);
  }});
}}

document.querySelectorAll('svg.sky').forEach(svg => {{
  attachPanZoom(svg, 1000, 1000, vb => {{
    const deep = 1000 / vb[2] >= DEEP_ZOOM;
    if (deep) ensureMarkerThumbs(svg);
    svg.classList.toggle('deepzoom', deep);
    applyFilter();
  }});
}});

// ---- lightbox: zoom/pan image, optional annotation overlay -------------
const ANN_COLORS = {ann_colors};
const ANNOTATIONS = JSON.parse(document.getElementById('lb-annotations').textContent);
const lb = document.getElementById('lightbox');
const lbStage = lb.querySelector('.lb-stage');
const lbName = document.getElementById('lb-name');
const lbSub = document.getElementById('lb-sub');
const lbAnnBtn = document.getElementById('lb-ann');
const lbExpandBtn = document.getElementById('lb-expand');
const lbPanel = document.getElementById('lb-panel');
const lbCards = document.getElementById('lb-cards');
const lbCount = document.getElementById('lb-count');
const lbSearch = document.getElementById('lb-search');
const SVGNS = 'http://www.w3.org/2000/svg';
let annOn = sessionStorage.getItem('uranometria-annotations') !== 'off';
let annShown = annOn;

function setAnn(on, persist) {{
  annShown = on;
  if (persist) {{
    annOn = on;
    sessionStorage.setItem('uranometria-annotations', on ? 'on' : 'off');
  }}
  lbStage.classList.toggle('lb-hide-ann', !on);
  lbAnnBtn.textContent = on ? 'ANNOTATIONS ON' : 'ANNOTATIONS OFF';
  lbAnnBtn.classList.toggle('on', on);
}}
lbAnnBtn.addEventListener('click', () => setAnn(!annShown, true));
let lbMax = false;
function setMax(on) {{
  lbMax = on;
  lb.classList.toggle('lb-max', on);
  lbExpandBtn.textContent = on ? 'SHRINK \u2921' : 'EXPAND \u2922';
  lbExpandBtn.classList.toggle('on', on);
}}
lbExpandBtn.addEventListener('click', () => setMax(!lbMax));
lbStage.addEventListener('click', e => e.stopPropagation());

const ANN_LABEL_SCALE = {ann_label_scale};
{ann_ui_js}

let openSeq = 0;
function openLightbox(src, cap, ann, forceAnn) {{
  lbName.textContent = cap[0] || '';
  lbSub.textContent = cap[1] || '';
  const seq = ++openSeq;
  const probe = new Image();
  const show = (w, h, failed) => {{
    if (seq !== openSeq) return;  // a newer click already superseded this load
    const old = document.getElementById('lb-svg');
    const svg = document.createElementNS(SVGNS, 'svg');
    svg.setAttribute('id', 'lb-svg');
    svg.setAttribute('role', 'img');
    const im = document.createElementNS(SVGNS, 'image');
    im.setAttribute('href', src);
    im.setAttribute('width', w);
    im.setAttribute('height', h);
    svg.appendChild(im);
    const usable =
      !failed && ann && ann.image_size && ann.image_size[0] === w && ann.image_size[1] === h;
    lbAnnBtn.hidden = !usable;
    lbPanel.hidden = !usable;
    old.replaceWith(svg);
    let onChange = null;
    if (usable) {{
      const gEl = document.createElementNS(SVGNS, 'g');
      gEl.setAttribute('id', 'lb-overlay');
      svg.appendChild(gEl);
      lbSearch.value = '';
      onChange = buildAnnotationUI({{
        svg,
        overlayEl: gEl,
        listEl: lbCards,
        countEl: lbCount,
        searchEl: lbSearch,
        model: ann,
        colors: ANN_COLORS,
        labelScale: ANN_LABEL_SCALE,
      }});
    }} else {{
      lbCards.textContent = '';
    }}
    setAnn(usable && (annOn || forceAnn), false);
    attachPanZoom(svg, w, h, onChange);
    lb.hidden = false;
  }};
  probe.onload = () => show(probe.naturalWidth, probe.naturalHeight);
  probe.onerror = () => show(800, 600, true);  // open anyway: caption, empty stage
  probe.src = src;
}}

document.querySelectorAll('[data-img]').forEach(el => {{
  el.addEventListener('click', e => {{
    if (e.target.closest && e.target.closest('a[href]')) return;
    const annEl = e.target.closest ? e.target.closest('.annlink') : null;
    const cap = (el.dataset.cap || '').split('|');
    const key = el.id || el.dataset.target;
    openLightbox(el.dataset.img, cap, ANNOTATIONS[key], !!annEl);
  }});
  el.addEventListener('keydown', e => {{
    if (e.key !== 'Enter' || !e.target.classList || !e.target.classList.contains('annlink')) return;
    const cap = (el.dataset.cap || '').split('|');
    const key = el.id || el.dataset.target;
    openLightbox(el.dataset.img, cap, ANNOTATIONS[key], true);
  }});
}});
function closeLightbox() {{
  openSeq++;  // a dismissal also invalidates any pending image load
  lb.hidden = true;
}}
lb.addEventListener('click', closeLightbox);
document.addEventListener('keydown', e => {{
  if (e.key !== 'Escape' || lb.hidden) return;
  if (e.target === lbSearch && lbSearch.value) {{
    lbSearch.value = '';
    lbSearch.dispatchEvent(new Event('input'));
  }} else {{
    closeLightbox();
  }}
}});
</script>
"""
