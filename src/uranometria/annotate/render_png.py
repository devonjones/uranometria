"""Annotated PNG renderer: the annotation model composited onto the image,
with a side legend panel, title bar, N/E compass, and scale bar.

Everything draws in array-index coordinates (the model's "fits0" frame maps
1:1 onto the loaded array), so image and annotations can never disagree.
The compass derives from the solved CD matrix, which makes it correct for
any rotation or mirror flip.
"""

import json
import math
import os

# palette: keep in the same family as the chart pages
COLORS = {
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


def dso_color(type_str):
    t = (type_str or "").lower()
    if "galaxy" in t:
        return COLORS["galaxy"]
    if "planetary" in t:
        return COLORS["planetary"]
    if "dark" in t:
        return COLORS["dark"]
    if "emission" in t or "h ii" in t or "nebula" in t:
        # deliberately BEFORE cluster: "Cluster + nebula" objects (M42, NGC 7380)
        # read as nebulae, per the house preference
        return COLORS["emission"]
    if "cluster" in t or "association" in t:
        return COLORS["cluster"]
    return COLORS["other"]


def _load_image(path):
    """Return an HxW or HxWx3 float array in [0,1], display-stretched."""
    import numpy as np

    p = os.fspath(path)
    if p.lower().endswith((".fit", ".fits", ".fts")):
        from astropy.io import fits

        with fits.open(p) as hdul:
            data = next(h.data for h in hdul if h.data is not None and h.data.ndim >= 2)
        data = data.astype("float32")
        if data.ndim == 3 and data.shape[0] in (3, 4):  # planes -> (H, W, 3)
            data = data[:3].transpose(1, 2, 0)
        # processed stacks are already nonlinear: anchor black near the sky
        # background (median) and white at the bright tail, mild gamma lift
        lo = float(np.percentile(data, 45.0))
        hi = float(np.percentile(data, 99.85))
        if hi <= lo:
            hi = lo + 1e-6
        out = np.clip((data - lo) / (hi - lo), 0.0, 1.0) ** 0.8
        return out
    from PIL import Image

    with Image.open(p) as im:
        return np.asarray(im.convert("RGB"), dtype="float32") / 255.0


def _hms(ra_deg):
    rh = (ra_deg % 360.0) / 15.0
    h = int(rh)
    m = int((rh - h) * 60)
    s = ((rh - h) * 60 - m) * 60
    return f"{h:02d}h{m:02d}m{s:02.0f}s"


def _dms(dec_deg):
    sign = "+" if dec_deg >= 0 else "−"
    ad = abs(dec_deg)
    d = int(ad)
    m = int((ad - d) * 60)
    s = ((ad - d) * 60 - m) * 60
    return f"{sign}{d}°{m:02d}′{s:02.0f}″"


def compass_vectors(cd):
    """Unit pixel-space direction vectors for celestial North and East.
    CD maps pixel steps to tangent-plane (east, north) degrees; its inverse
    maps sky directions back to pixels, so flips and rotation come out right."""
    (a, b), (c, d) = cd
    det = a * d - b * c
    if det == 0:
        raise ValueError("degenerate CD matrix")
    inv = [[d / det, -b / det], [-c / det, a / det]]
    east = (inv[0][0], inv[1][0])
    north = (inv[0][1], inv[1][1])

    def unit(v):
        n = math.hypot(*v)
        return (v[0] / n, v[1] / n)

    return unit(north), unit(east)


def _load_model(model):
    if isinstance(model, dict):
        return model
    with open(model) as f:
        return json.load(f)


def _default_title(model):
    dsos = [o for o in model["objects"] if o["kind"] == "dso"]
    if not dsos:
        return model["image"]
    w, h = model["image_size"]
    cx, cy = w / 2, h / 2
    lead = min(dsos, key=lambda o: (o["x"] - cx) ** 2 + (o["y"] - cy) ** 2)
    name = f" / {lead['name']}" if lead.get("name") else ""
    return f"{lead['designation']}{name}"


def render_png(model, image_path, output, *, title=None, max_width=2000):
    """Composite the annotation model onto the image and write a PNG."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle

    model = _load_model(model)
    img = _load_image(image_path)
    H, W = img.shape[:2]
    mw, mh = model["image_size"]
    if (W, H) != (mw, mh):
        raise ValueError(
            f"image is {W}x{H} but the model was built for {mw}x{mh} — "
            "annotate and render must use the same image"
        )

    s = min(1.0, max_width / W)
    panel_px = 560
    fig_w_px = int(W * s) + panel_px
    fig_h_px = int(H * s)
    dpi = 100
    fig = plt.figure(figsize=(fig_w_px / dpi, fig_h_px / dpi), dpi=dpi, facecolor="black")
    ax = fig.add_axes([0, 0, W * s / fig_w_px, 1])
    ax.imshow(img, origin="upper", cmap="gray" if img.ndim == 2 else None, aspect="auto")
    ax.set_xlim(0, W)
    ax.set_ylim(H, 0)  # array coords, row 0 at top
    ax.axis("off")

    solved = model["solved"]
    fw, fh = solved["fov_deg"]
    title = title or _default_title(model)
    ax.text(
        0.02 * W,
        0.035 * H,
        f"{title} — plate-solved: {_hms(solved['center_ra'])} {_dms(solved['center_dec'])}"
        f" · {solved['scale_arcsec_px']:.2f}″/px · {fw:.2f}°×{fh:.2f}° FOV",
        color="white",
        fontsize=13,
        family="monospace",
        va="top",
        bbox=dict(facecolor="black", alpha=0.75, edgecolor="#666", pad=6),
        zorder=10,
    )

    # ---- compass (from the CD matrix; honest under flips) ----------------
    if solved.get("cd"):
        north, east = compass_vectors(solved["cd"])
        ox, oy = 0.055 * W, 0.16 * H
        arm = 0.045 * H
        for vec, lab in ((north, "N"), (east, "E")):
            ax.annotate(
                "",
                xy=(ox + vec[0] * arm, oy + vec[1] * arm),
                xytext=(ox, oy),
                arrowprops=dict(color="white", arrowstyle="-|>", lw=1.6),
                zorder=10,
            )
            ax.text(
                ox + vec[0] * arm * 1.3,
                oy + vec[1] * arm * 1.3,
                lab,
                color="white",
                fontsize=12,
                family="monospace",
                ha="center",
                va="center",
                zorder=10,
            )

    # ---- scale bar (10 arcmin, bottom left) -------------------------------
    bar_px = 600.0 / solved["scale_arcsec_px"]
    if bar_px < 0.5 * W:
        bx, by = 0.03 * W, 0.955 * H
        ax.plot([bx, bx + bar_px], [by, by], color="white", lw=2, zorder=10)
        ax.text(
            bx + bar_px / 2,
            by - 0.012 * H,
            "10′",
            color="white",
            fontsize=11,
            family="monospace",
            ha="center",
            zorder=10,
        )

    # ---- objects ----------------------------------------------------------
    cx, cy = W / 2, H / 2
    dsos = [o for o in model["objects"] if o["kind"] == "dso"]
    named = [o for o in model["objects"] if o["kind"] == "star" and o.get("named")]
    field = [o for o in model["objects"] if o["kind"] == "star" and not o.get("named")]

    label_slot = [0]

    def leader_label(x, y, text, color, r_gap=0.035):
        # push the label outward from image center; clamp inside the frame
        dx, dy = x - cx, y - cy
        n = math.hypot(dx, dy) or 1.0
        if n < 0.10 * min(W, H):
            # too near the center for a radial push: fan out by slot angle
            ang = label_slot[0] * (2 * math.pi / 7) + 0.4
            label_slot[0] += 1
            dx, dy, n = math.cos(ang), math.sin(ang), 1.0
            r_gap *= 2.2
        lx = x + dx / n * r_gap * W + (0.02 * W if dx >= 0 else -0.02 * W)
        ly = y + dy / n * r_gap * H
        lx = min(max(lx, 0.03 * W), 0.97 * W)
        ly = min(max(ly, 0.07 * H), 0.95 * H)
        ha = "left" if lx >= x else "right"
        ax.plot([x, lx], [y, ly], color=color, lw=1.0, alpha=0.9, zorder=9)
        ax.text(
            lx,
            ly,
            text,
            color=color,
            fontsize=12,
            family="monospace",
            fontweight="bold",
            ha=ha,
            va="center",
            zorder=10,
        )

    for o in dsos:
        color = dso_color(o.get("type"))
        label = o["designation"] + (f"\n({o['name']})" if o.get("name") else "")
        leader_label(o["x"], o["y"], label, color)

    for o in named:
        x, y = o["x"], o["y"]
        ax.add_patch(
            Circle((x, y), 0.02 * H, fill=False, color=COLORS["named_star"], lw=1.6, zorder=9)
        )
        dist = f", {round(o['dist_pc'] * 3.2616)} ly" if o.get("dist_pc") else ""
        sp = o.get("type", "").replace("Star", "").strip(" ()")
        leader_label(
            x,
            y,
            f"{o['designation']}\n{o['band']}={o['mag']:.2f}" + (f" {sp}" if sp else "") + dist,
            COLORS["named_star"],
            r_gap=0.05,
        )

    for o in field:
        x, y = o["x"], o["y"]
        ax.add_patch(
            Circle((x, y), 0.012 * H, fill=False, color=COLORS["field_star"], lw=1.2, zorder=9)
        )
        ax.text(
            x + 0.016 * H,
            y - 0.012 * H,
            str(o["key"]),
            color=COLORS["field_star"],
            fontsize=10,
            family="monospace",
            zorder=10,
        )

    # ---- legend panel ------------------------------------------------------
    lax = fig.add_axes([W * s / fig_w_px, 0, 1 - W * s / fig_w_px, 1])
    lax.axis("off")
    lax.set_xlim(0, 1)
    lax.set_ylim(0, 1)

    yc = 0.96
    n_lines = 4 + 2 * (len(dsos) + len(named)) + (3 + len(field) if field else 0) + 6
    lh = min(0.028, 0.88 / max(n_lines, 1))  # shrink to fit, never overflow

    def line(text, color=COLORS["ink"], size=11, dy=1.0, x=0.07, weight="normal"):
        nonlocal yc
        lax.text(
            x,
            yc,
            text,
            color=color,
            fontsize=size,
            family="monospace",
            fontweight=weight,
            va="top",
            transform=lax.transAxes,
        )
        yc -= lh * dy

    line("LEGEND", size=15, weight="bold", dy=1.8)
    if dsos or named:
        line("Deep-sky objects", size=12, weight="bold", dy=1.5)
        for o in named:
            dist = f", {round(o['dist_pc'] * 3.2616)} ly" if o.get("dist_pc") else ""
            line(f"● {o['designation']}  — bright star", COLORS["named_star"])
            line(f"   {o['band']}={o['mag']:.2f}{dist}", COLORS["named_star"], size=10, dy=1.5)
        for o in dsos:
            color = dso_color(o.get("type"))
            name = f"  {o['name']}" if o.get("name") else ""
            line(f"— {o['designation']}{name}", color)
            line(f"   {o['type']}", color, size=10, dy=1.4)
    if field:
        yc -= lh * 0.6
        line("Field stars (Gaia DR3 via VizieR)", size=12, weight="bold", dy=1.5)
        line(f"{'#':>2} {'designation':<20} {'mag':>5} {'dist':>7}", COLORS["dim"], size=10)
        for o in field:
            dist = f"{o['dist_pc']}pc" if o.get("dist_pc") else "—"
            line(
                f"{o['key']:>2} {o['designation']:<20} {o['mag']:>5.1f} {dist:>7}",
                COLORS["field_star"],
                size=10,
            )
    yc = max(yc, 0.10)
    line(" ", dy=0.5)
    line(f"Solve: {solved['solver']} · OpenNGC · Gaia DR3 · SIMBAD", COLORS["dim"], size=9)
    line(
        f"{solved['scale_arcsec_px']:.2f}″/px · {fw:.2f}°×{fh:.2f}° FOV",
        COLORS["dim"],
        size=9,
    )

    fig.savefig(output, dpi=dpi, facecolor="black")
    plt.close(fig)
    return os.fspath(output)
