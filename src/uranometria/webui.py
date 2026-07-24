"""Shared web-page building blocks: the annotation palette and the pan/zoom
JavaScript used by the chart page, the lightbox, and the standalone
annotated-image page. Plain strings only; no heavy imports."""

# palette shared by the PNG renderer and the HTML overlays
ANNOTATION_COLORS = {
    "galaxy": "#82B4F5",
    "emission": "#F48FB1",
    "planetary": "#80DEEA",
    "cluster": "#FFCC80",
    "dark": "#B39DDB",
    "other": "#C5CAE9",
    "named_star": "#FFD54F",
    "field_star": "#69F0AE",
    "ink": "#ECEFF4",
    "dim": "#9BA6B5",
}

# attachPanZoom(svg, w, h, onChange): viewBox-based wheel zoom about the
# cursor, drag pan, double-click reset. Sets --z for counter-scaled markers
# and calls onChange after every change. Returns a reset function.
# NOTE: plain string (no f-string) — single braces are literal JS.
PANZOOM_JS = """
function attachPanZoom(svg, w, h, onChange) {
  let vb = [0, 0, w, h], pan = null, moved = 0;
  const maxZ = 8;
  // dragging to pan must never read as text selection (uranometria-8)
  svg.style.userSelect = 'none';
  svg.style.webkitUserSelect = 'none';
  const apply = () => {
    svg.setAttribute('viewBox', vb.join(' '));
    svg.style.setProperty('--z', w / vb[2]);
    svg._vb = vb;
    if (onChange) onChange(vb);
  };
  const clamp = () => {
    vb[2] = Math.min(w, Math.max(w / maxZ, vb[2]));
    vb[3] = vb[2] * (h / w);
    vb[0] = Math.max(0, Math.min(w - vb[2], vb[0]));
    vb[1] = Math.max(0, Math.min(h - vb[3], vb[1]));
  };
  // the element box may be letterboxed (CSS-forced size vs viewBox aspect):
  // map through the true rendered scale, not the raw box dimensions
  const toLocal = (cx, cy) => {
    const r = svg.getBoundingClientRect();
    const s = Math.min(r.width / vb[2], r.height / vb[3]);
    const ox = (r.width - vb[2] * s) / 2, oy = (r.height - vb[3] * s) / 2;
    return [vb[0] + (cx - r.left - ox) / s,
            vb[1] + (cy - r.top - oy) / s];
  };
  svg.addEventListener('wheel', e => {
    e.preventDefault();
    const [px, py] = toLocal(e.clientX, e.clientY);
    const f = e.deltaY < 0 ? 1 / 1.25 : 1.25;
    // clamp the scale FIRST and apply only the factor that survives:
    // at the zoom limits the leftover origin shift used to become a pan
    // toward the cursor (uranometria-9)
    const nz = Math.min(w, Math.max(w / maxZ, vb[2] * f));
    const g = nz / vb[2];
    if (g === 1) return;
    vb[0] = px - (px - vb[0]) * g;
    vb[1] = py - (py - vb[1]) * g;
    vb[2] = nz;
    clamp(); apply();
  }, { passive: false });
  svg.addEventListener('pointerdown', e => {
    pan = [e.clientX, e.clientY, vb[0], vb[1], e.pointerId]; moved = 0;
    const sel = window.getSelection ? window.getSelection() : null;
    if (sel && !sel.isCollapsed) sel.removeAllRanges();
    // capture waits until a real drag: capturing on pointerdown retargets
    // the click to the svg, which made plain clicks on markers dead
  });
  svg.addEventListener('pointermove', e => {
    if (!pan) return;
    if (!e.buttons) { pan = null; return; }  // release landed off-svg pre-capture
    const r = svg.getBoundingClientRect();
    const s = Math.min(r.width / vb[2], r.height / vb[3]);
    const dx = e.clientX - pan[0], dy = e.clientY - pan[1];
    moved = Math.max(moved, Math.abs(dx) + Math.abs(dy));
    if (moved > 4 && !svg.hasPointerCapture(pan[4])) {
      svg.setPointerCapture(pan[4]);
    }
    vb[0] = pan[2] - dx / s;
    vb[1] = pan[3] - dy / s;
    clamp(); apply();
  });
  svg.addEventListener('pointerup', () => { pan = null; });
  svg.addEventListener('pointercancel', () => { pan = null; });
  svg.addEventListener('click', e => {
    if (moved > 5) { e.stopPropagation(); }
    moved = 0;
  }, true);
  svg.addEventListener('dblclick', () => { vb = [0, 0, w, h]; apply(); });
  apply();
  return () => { vb = [0, 0, w, h]; apply(); };
}
"""


def js_color_map():
    """The palette as a JS object literal."""
    inner = ", ".join(f'"{k}": "{v}"' for k, v in ANNOTATION_COLORS.items())
    return "{" + inner + "}"


# dsoColor(type) in JS, mirroring render_png.dso_color (incl. Cl+N-as-cluster)
DSO_COLOR_JS = """
function dsoColor(t, C) {
  t = (t || '').toLowerCase();
  if (t.includes('galaxy')) return C.galaxy;
  if (t.includes('planetary')) return C.planetary;
  if (t.includes('dark')) return C.dark;
  if (t.includes('cluster') || t.includes('association')) return C.cluster;
  if (t.includes('emission') || t.includes('h ii') || t.includes('nebula')) return C.emission;
  return C.other;
}
"""

# marker + spotlight styles shared by the standalone annotated page and the
# chart lightbox; the builder sets font sizes inline
ANNOTATION_UI_CSS = """
.ann { transform:translate(var(--tx),var(--ty)) scale(calc(1 / var(--z,1))); }
.ann circle { fill:none; stroke:currentColor; stroke-width:1.6; }
.ann text { fill:currentColor; font-family:'Plex Mono',monospace;
  font-weight:500; paint-order:stroke; stroke:rgba(0,0,0,0.8); }
svg.focus .ann { opacity:0.25; }
svg.focus .ann.lit { opacity:1; }
"""

# buildAnnotationUI: the whole annotation viewer, shared by the standalone
# annotated page and the chart lightbox. Builds the SVG overlay and the
# card list from the model, wires hover spotlight, search, and viewport
# filtering. Requires dsoColor (DSO_COLOR_JS) in scope.
# opts: {svg, overlayEl, listEl, countEl, searchEl?, model, colors, labelScale}
# Returns applyFilter, suitable as attachPanZoom's onChange.
ANNOTATION_UI_JS = """
function annColor(o, C) {
  if (o.kind === 'dso') return dsoColor(o.type, C);
  return o.named ? C.named_star : C.field_star;
}
function annFmtLy(ly, approx) {
  if (!ly) return null;
  if (ly < 1e5) {
    if (approx) {
      const mag = Math.pow(10, Math.floor(Math.log10(ly)) - 1);
      return '~' + (Math.round(ly / mag) * mag).toLocaleString('en-US') + ' ly';
    }
    return Math.round(ly).toLocaleString('en-US') + ' ly';
  }
  const m = ly / 1e6;
  return '~' + (m < 10 ? m.toFixed(1) : String(Math.round(m))) + ' Mly';
}
function buildAnnotationUI(opts) {
  const NS = 'http://www.w3.org/2000/svg';
  const model = opts.model, C = opts.colors;
  const w = model.image_size[0], h = model.image_size[1];
  const r = 0.02 * Math.min(w, h);
  const fs = Math.max(12, 0.016 * Math.min(w, h)) * (opts.labelScale || 1);
  const anns = [], cards = [], texts = [];
  opts.listEl.textContent = '';
  model.objects.forEach((o, i) => {
    const color = annColor(o, C);
    const fieldStar = o.kind === 'star' && !o.named;
    const g = document.createElementNS(NS, 'g');
    g.setAttribute('class', 'ann');
    g.style.setProperty('--tx', o.x + 'px');
    g.style.setProperty('--ty', o.y + 'px');
    g.style.color = color;
    const c = document.createElementNS(NS, 'circle');
    c.setAttribute('r', o.kind === 'dso' ? r * 1.4 : o.named ? r : r * 0.6);
    g.appendChild(c);
    const t = document.createElementNS(NS, 'text');
    t.setAttribute('x', r * 1.6);
    t.setAttribute('y', -r * 0.8);
    t.style.fontSize = fs + 'px';
    t.style.strokeWidth = (fs / 4) + 'px';
    t.textContent = fieldStar ? String(o.key) : o.designation;
    g.appendChild(t);
    opts.overlayEl.appendChild(g);
    anns.push(g);
    const li = document.createElement('li');
    li.style.setProperty('--accent', color);
    const box = document.createElement('div');
    box.className = 'obj';
    const desig = document.createElement('span');
    desig.className = 'desig';
    if (fieldStar) {
      const kb = document.createElement('span');
      kb.className = 'keybadge';
      kb.textContent = o.key;
      desig.appendChild(kb);
    }
    desig.appendChild(document.createTextNode(
      [o.designation].concat(o.aliases || []).join(' \u00b7 ')));
    box.appendChild(desig);
    if (o.name) {
      const n = document.createElement('span');
      n.className = 'common';
      n.textContent = o.name;
      box.appendChild(n);
    }
    const bits = [];
    if (o.type) bits.push(o.type);
    if (o.mag != null) bits.push((o.band || '') + '=' + o.mag);
    const d = annFmtLy(o.dist_ly, o.kind === 'dso');
    if (d) bits.push(d);
    if (bits.length) {
      const meta = document.createElement('span');
      meta.className = 'meta';
      meta.textContent = bits.join(' \u00b7 ');
      box.appendChild(meta);
    }
    const linkRow = document.createElement('span');
    linkRow.className = 'linkrow';
    for (const [label, key] of [['SIMBAD', 'simbad'], ['Wikipedia', 'wikipedia']]) {
      const url = (o.links || {})[key];
      if (!url || !/^https?:\\/\\//i.test(url)) continue;
      const a = document.createElement('a');
      a.href = url;
      a.target = '_blank';
      a.rel = 'noopener';
      a.textContent = label;
      linkRow.appendChild(a);
    }
    if (linkRow.childNodes.length) box.appendChild(linkRow);
    li.appendChild(box);
    opts.listEl.appendChild(li);
    cards.push(li);
    // searchable text excludes the link labels: SIMBAD appears on every
    // card, so junk queries like 'sim' would otherwise match everything
    texts.push(
      (desig.textContent + ' ' + (o.name || '') + ' ' + bits.join(' ')).toLowerCase());
    li.addEventListener('mouseenter', () => {
      opts.svg.classList.add('focus');
      g.classList.add('lit');
    });
    li.addEventListener('mouseleave', applyFilter);
  });
  function inView(i) {
    const vb = opts.svg._vb;
    if (!vb || vb[2] >= w - 1) return true;
    const m = 20 / (w / vb[2]);
    const o = model.objects[i];
    return o.x >= vb[0] - m && o.x <= vb[0] + vb[2] + m &&
           o.y >= vb[1] - m && o.y <= vb[1] + vb[3] + m;
  }
  function applyFilter() {
    const q = opts.searchEl ? opts.searchEl.value.trim().toLowerCase() : '';
    const vb = opts.svg._vb;
    const zoomed = vb && vb[2] < w - 1;
    let shown = 0;
    cards.forEach((li, i) => {
      const hit = (!q || texts[i].includes(q)) && inView(i);
      li.style.display = hit ? '' : 'none';
      if (hit) shown++;
      anns[i].classList.toggle('lit', !!q && hit);
    });
    opts.svg.classList.toggle('focus', !!q);
    opts.countEl.textContent = shown < cards.length
      ? shown + ' OF ' + cards.length + ' OBJECTS' + (zoomed ? ' \u00b7 IN VIEW' : '')
      : cards.length + ' OBJECTS';
  }
  if (opts.searchEl) {
    if (opts.searchEl._annFilter)
      opts.searchEl.removeEventListener('input', opts.searchEl._annFilter);
    opts.searchEl._annFilter = applyFilter;
    opts.searchEl.addEventListener('input', applyFilter);
  }
  applyFilter();
  return applyFilter;
}
"""
