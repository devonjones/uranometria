"""Assemble the full HTML page: header, hemisphere charts, legend, lightbox."""

import html

import json as _json

from .chart import Chart, DEC_EDGE, accent_value, photo_attrs
from .resources import asset_text, sky_data
from .webui import DSO_COLOR_JS, PANZOOM_JS, js_color_map


def _legend_html(objects):
    items = []
    for i, o in enumerate(objects):
        meta = o["type"] + (f" — {o['constellation']}" if o["constellation"] else "")
        common = f'<span class="common">{html.escape(o["common"])}</span>' if o["common"] else ""
        accent = accent_value(o)
        attrs = f' style="--accent:{accent}"' if accent else ""
        attrs += photo_attrs(o)
        photo = ' <span class="photo">PHOTO ↗</span>' if o.get("href") else ""
        items.append(f"""<li data-target="mk-{i}"{attrs}>
  <span class="glyph" aria-hidden="true"><svg viewBox="-14 -14 28 28"><circle r="7" class="ring"/>
    <line x1="4.9" y1="4.9" x2="9.2" y2="9.2"/><line x1="-4.9" y1="4.9" x2="-9.2" y2="9.2"/>
    <line x1="4.9" y1="-4.9" x2="9.2" y2="-9.2"/><line x1="-4.9" y1="-4.9" x2="-9.2" y2="-9.2"/></svg></span>
  <div class="obj"><span class="desig">{html.escape(o["disp"])}{photo}</span>{common}
    <span class="meta">{html.escape(meta)}</span>
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
    # </script> can never appear inside the JSON payload
    annotations_json = _json.dumps(annotations).replace("</", "<\\/")

    panzoom_js = PANZOOM_JS
    dso_color_js = DSO_COLOR_JS
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
.legend .search {{ width:100%; box-sizing:border-box; margin-bottom:12px;
  background:var(--sky); border:1px solid var(--grid); color:var(--star);
  font-family:'Plex Mono',monospace; font-size:12.5px; padding:9px 12px; outline:none; }}
.legend .search:focus {{ border-color:var(--accent); }}
.legend .search::placeholder {{ color:var(--dim); }}
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
.legend li:hover .photo {{ color:var(--accent); }}
.legend .common {{ font-family:'Marcellus',serif; color:var(--star); font-size:15px; }}
.legend .meta {{ color:var(--ink); font-size:11px; }}
.legend .coord {{ color:var(--dim); font-size:11px; font-variant-numeric:tabular-nums; }}
.lightbox {{ position:fixed; inset:0; z-index:10; display:flex; align-items:center;
  justify-content:center; background:rgba(4,6,16,0.93); cursor:zoom-out; }}
.lightbox[hidden] {{ display:none; }}
.lb-stage {{ display:flex; flex-direction:column; align-items:center; gap:12px;
  max-width:94vw; cursor:auto; }}
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
.ann {{ transform:translate(var(--tx),var(--ty)) scale(calc(1 / var(--z,1))); }}
.ann circle {{ fill:none; stroke:currentColor; stroke-width:1.6; }}
.ann text {{ fill:currentColor; font-family:'Plex Mono',monospace; font-size:13px;
  font-weight:500; paint-order:stroke; stroke:rgba(0,0,0,0.8); stroke-width:3px; }}
.lb-hide-labels #lb-overlay {{ display:none; }}
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
    <div class="lb-tools">
      <button id="lb-labels" class="lb-btn" hidden>LABELS OFF</button>
      <span class="lb-hint">SCROLL TO ZOOM \u00b7 DRAG TO PAN \u00b7 CLICK OUTSIDE OR ESC TO CLOSE</span>
    </div>
    <svg id="lb-svg" viewBox="0 0 1 1" role="img" aria-label="photograph"></svg>
    <figcaption><div class="cap-name" id="lb-name"></div><div class="cap-sub" id="lb-sub"></div></figcaption>
  </div>
</div>
<script type="application/json" id="lb-annotations">{annotations_json}</script>
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
document.querySelectorAll('svg.sky').forEach(svg => {{
  attachPanZoom(svg, 1000, 1000, applyFilter);
}});

// ---- lightbox: zoom/pan image, optional annotation overlay -------------
const ANN_COLORS = {ann_colors};
const ANNOTATIONS = JSON.parse(document.getElementById('lb-annotations').textContent);
const lb = document.getElementById('lightbox');
const lbStage = lb.querySelector('.lb-stage');
const lbName = document.getElementById('lb-name');
const lbSub = document.getElementById('lb-sub');
const lbLabelsBtn = document.getElementById('lb-labels');
const SVGNS = 'http://www.w3.org/2000/svg';
let labelsOn = sessionStorage.getItem('uranometria-labels') === 'on';

function setLabels(on) {{
  labelsOn = on;
  sessionStorage.setItem('uranometria-labels', on ? 'on' : 'off');
  lbStage.classList.toggle('lb-hide-labels', !on);
  lbLabelsBtn.textContent = on ? 'LABELS ON' : 'LABELS OFF';
  lbLabelsBtn.classList.toggle('on', on);
}}
lbLabelsBtn.addEventListener('click', () => setLabels(!labelsOn));
lbStage.addEventListener('click', e => e.stopPropagation());

function annColor(o) {{
  if (o.kind === 'dso') return dsoColor(o.type, ANN_COLORS);
  return o.named ? ANN_COLORS.named_star : ANN_COLORS.field_star;
}}

function buildOverlay(gEl, ann, w, h) {{
  const r = 0.02 * Math.min(w, h);
  ann.objects.forEach(o => {{
    const g = document.createElementNS(SVGNS, 'g');
    g.setAttribute('class', 'ann');
    g.style.setProperty('--tx', o.x + 'px');
    g.style.setProperty('--ty', o.y + 'px');
    g.style.color = annColor(o);
    const c = document.createElementNS(SVGNS, 'circle');
    c.setAttribute('r', o.kind === 'dso' ? r * 1.4 : o.named ? r : r * 0.6);
    g.appendChild(c);
    const t = document.createElementNS(SVGNS, 'text');
    t.setAttribute('x', r * 1.6);
    t.setAttribute('y', -r * 0.8);
    t.textContent = o.kind === 'star' && !o.named ? String(o.key) : o.designation;
    g.appendChild(t);
    gEl.appendChild(g);
  }});
}}

function openLightbox(src, cap, ann) {{
  lbName.textContent = cap[0] || '';
  lbSub.textContent = cap[1] || '';
  const probe = new Image();
  probe.onload = () => {{
    const w = probe.naturalWidth, h = probe.naturalHeight;
    const old = document.getElementById('lb-svg');
    const svg = document.createElementNS(SVGNS, 'svg');
    svg.setAttribute('id', 'lb-svg');
    svg.setAttribute('role', 'img');
    const im = document.createElementNS(SVGNS, 'image');
    im.setAttribute('href', src);
    im.setAttribute('width', w);
    im.setAttribute('height', h);
    svg.appendChild(im);
    const usable = ann && ann.image_size && ann.image_size[0] === w && ann.image_size[1] === h;
    if (usable) {{
      const gEl = document.createElementNS(SVGNS, 'g');
      gEl.setAttribute('id', 'lb-overlay');
      buildOverlay(gEl, ann, w, h);
      svg.appendChild(gEl);
    }}
    lbLabelsBtn.hidden = !usable;
    setLabels(usable && labelsOn);
    old.replaceWith(svg);
    attachPanZoom(svg, w, h, null);
    lb.hidden = false;
  }};
  probe.src = src;
}}

document.querySelectorAll('[data-img]').forEach(el => {{
  el.addEventListener('click', () => {{
    const cap = (el.dataset.cap || '').split('|');
    const key = el.id || el.dataset.target;
    openLightbox(el.dataset.img, cap, ANNOTATIONS[key]);
  }});
}});
function closeLightbox() {{ lb.hidden = true; }}
lb.addEventListener('click', closeLightbox);
document.addEventListener('keydown', e => {{ if (e.key === 'Escape') closeLightbox(); }});
</script>
"""
