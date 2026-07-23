"""Assemble the full HTML page: header, hemisphere charts, legend, lightbox."""

import html

from .chart import Chart, DEC_EDGE
from .resources import asset_text, sky_data


def _legend_html(objects):
    items = []
    for i, o in enumerate(objects):
        meta = o["type"] + (f" — {o['constellation']}" if o["constellation"] else "")
        common = f'<span class="common">{html.escape(o["common"])}</span>' if o["common"] else ""
        attrs = f' style="--accent:{html.escape(o["color"], quote=True)}"' if o.get("color") else ""
        photo = ""
        if o.get("href"):
            attrs += (
                f' data-img="{html.escape(o["href"], quote=True)}"'
                f' data-cap="{html.escape(o["caption"], quote=True)}"'
            )
            photo = ' <span class="photo">PHOTO ↗</span>'
        items.append(f"""<li data-target="mk-{i}"{attrs}>
  <span class="glyph" aria-hidden="true"><svg viewBox="-14 -14 28 28"><circle r="7" class="ring"/>
    <line x1="4.9" y1="4.9" x2="9.2" y2="9.2"/><line x1="-4.9" y1="4.9" x2="-9.2" y2="9.2"/>
    <line x1="4.9" y1="-4.9" x2="9.2" y2="-9.2"/><line x1="-4.9" y1="-4.9" x2="-9.2" y2="-9.2"/></svg></span>
  <div class="obj"><span class="desig">{html.escape(o["disp"])}{photo}</span>{common}
    <span class="meta">{html.escape(meta)}</span>
    <span class="coord">{o["coord"]}</span></div>
</li>""")
    return "".join(items)


def build_page(cfg, objects):
    mag_limit = float(cfg.get("mag_limit", 5.0))
    show_ecl = bool(cfg.get("show_ecliptic", True))
    data = sky_data()

    need_south = any(o["dec"] < -DEC_EDGE for o in objects)
    need_north = any(o["dec"] > DEC_EDGE for o in objects) or not need_south
    charts = []
    if need_north:
        charts.append(Chart(False, data, mag_limit, show_ecl))
    if need_south:
        charts.append(Chart(True, data, mag_limit, show_ecl))

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
    title = html.escape(str(cfg.get("title", default_title))).upper()
    default_sub = f"{n} DEEP-SKY OBJECT{'S' if n != 1 else ''} · EPOCH J2000"
    subtitle = html.escape(str(cfg.get("subtitle", default_sub))).upper()

    def b64(fn):
        return asset_text(fn + ".b64")

    return f"""<title>{title.title()} — Photographed Objects</title>
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
.lightbox figure {{ margin:0; display:flex; flex-direction:column; align-items:center; gap:16px;
  max-width:94vw; }}
.lightbox img {{ max-width:94vw; max-height:80vh; border:1px solid var(--equator);
  box-shadow:0 12px 60px rgba(0,0,0,0.7); }}
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
  Azimuthal equidistant projection centered on the celestial pole{" (each hemisphere charted to decl. ±" + str(int(DEC_EDGE)) + "° past the equator)" if two else ""} · stars to magnitude {mag_limit:g}.<br>
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
  <figure>
    <img id="lb-img" src="" alt="">
    <figcaption><div class="cap-name" id="lb-name"></div><div class="cap-sub" id="lb-sub"></div></figcaption>
  </figure>
</div>
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

// ---- pan & zoom ------------------------------------------------------
document.querySelectorAll('svg.sky').forEach(svg => {{
  let vb = [0, 0, 1000, 1000], pan = null, moved = 0;
  svg._vb = vb;
  const apply = () => {{
    svg.setAttribute('viewBox', vb.join(' '));
    svg.style.setProperty('--z', 1000 / vb[2]);
    svg._vb = vb;
    applyFilter();
  }};
  const clamp = () => {{
    vb[2] = vb[3] = Math.min(1000, Math.max(125, vb[2]));
    vb[0] = Math.max(0, Math.min(1000 - vb[2], vb[0]));
    vb[1] = Math.max(0, Math.min(1000 - vb[3], vb[1]));
  }};
  const toSvg = (cx, cy) => {{
    const r = svg.getBoundingClientRect();
    return [vb[0] + (cx - r.left) / r.width * vb[2],
            vb[1] + (cy - r.top) / r.height * vb[3]];
  }};
  svg.addEventListener('wheel', e => {{
    e.preventDefault();
    const [px, py] = toSvg(e.clientX, e.clientY);
    const f = e.deltaY < 0 ? 1 / 1.25 : 1.25;
    vb[0] = px - (px - vb[0]) * f;
    vb[1] = py - (py - vb[1]) * f;
    vb[2] *= f; vb[3] = vb[2];
    clamp(); apply();
  }}, {{ passive: false }});
  svg.addEventListener('pointerdown', e => {{
    pan = [e.clientX, e.clientY, vb[0], vb[1]]; moved = 0;
    svg.setPointerCapture(e.pointerId);
  }});
  svg.addEventListener('pointermove', e => {{
    if (!pan) return;
    const r = svg.getBoundingClientRect();
    const dx = e.clientX - pan[0], dy = e.clientY - pan[1];
    moved = Math.max(moved, Math.abs(dx) + Math.abs(dy));
    vb[0] = pan[2] - dx / r.width * vb[2];
    vb[1] = pan[3] - dy / r.height * vb[3];
    clamp(); apply();
  }});
  svg.addEventListener('pointerup', () => {{ pan = null; }});
  svg.addEventListener('click', e => {{
    if (moved > 5) e.stopPropagation();   // a drag is not a marker click
    moved = 0;
  }}, true);
  svg.addEventListener('dblclick', () => {{ vb = [0, 0, 1000, 1000]; apply(); }});
}});
const lb = document.getElementById('lightbox');
const lbImg = document.getElementById('lb-img');
const lbName = document.getElementById('lb-name');
const lbSub = document.getElementById('lb-sub');
document.querySelectorAll('[data-img]').forEach(el => {{
  el.addEventListener('click', () => {{
    const cap = (el.dataset.cap || '').split('|');
    lbImg.src = el.dataset.img;
    lbImg.alt = cap[0] || '';
    lbName.textContent = cap[0] || '';
    lbSub.textContent = cap[1] || '';
    lb.hidden = false;
  }});
}});
lb.addEventListener('click', () => {{ lb.hidden = true; lbImg.src = ''; }});
document.addEventListener('keydown', e => {{ if (e.key === 'Escape') {{ lb.hidden = true; lbImg.src = ''; }} }});
</script>
"""
