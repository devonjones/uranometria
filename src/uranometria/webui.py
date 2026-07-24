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
  const toLocal = (cx, cy) => {
    const r = svg.getBoundingClientRect();
    return [vb[0] + (cx - r.left) / r.width * vb[2],
            vb[1] + (cy - r.top) / r.height * vb[3]];
  };
  svg.addEventListener('wheel', e => {
    e.preventDefault();
    const [px, py] = toLocal(e.clientX, e.clientY);
    const f = e.deltaY < 0 ? 1 / 1.25 : 1.25;
    vb[0] = px - (px - vb[0]) * f;
    vb[1] = py - (py - vb[1]) * f;
    vb[2] *= f;
    clamp(); apply();
  }, { passive: false });
  svg.addEventListener('pointerdown', e => {
    pan = [e.clientX, e.clientY, vb[0], vb[1]]; moved = 0;
    svg.setPointerCapture(e.pointerId);
  });
  svg.addEventListener('pointermove', e => {
    if (!pan) return;
    const r = svg.getBoundingClientRect();
    const dx = e.clientX - pan[0], dy = e.clientY - pan[1];
    moved = Math.max(moved, Math.abs(dx) + Math.abs(dy));
    vb[0] = pan[2] - dx / r.width * vb[2];
    vb[1] = pan[3] - dy / r.height * vb[3];
    clamp(); apply();
  });
  svg.addEventListener('pointerup', () => { pan = null; });
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
