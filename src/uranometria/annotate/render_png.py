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


def fmt_dist_ly(ly):
    """Human distance: plain ly inside the galaxy, Mly beyond."""
    if not ly:
        return None
    if ly < 1e5:
        return f"{ly:,.0f} ly"
    m = ly / 1e6
    return f"~{m:.1f} Mly" if m < 10 else f"~{m:.0f} Mly"


def dso_color(type_str):
    t = (type_str or "").lower()
    if "galaxy" in t:
        return COLORS["galaxy"]
    if "planetary" in t:
        return COLORS["planetary"]
    if "dark" in t:
        return COLORS["dark"]
    if "cluster" in t or "association" in t:
        # BEFORE the nebula check: on annotated images the Sharpless nebula
        # appears as its own labeled object, so Cl+N entries (NGC 7380) read
        # as the cluster. (The sky-chart sample's Cl+N-as-nebula preference
        # is a chart-config concern, unaffected.)
        return COLORS["cluster"]
    if "emission" in t or "h ii" in t or "nebula" in t:
        return COLORS["emission"]
    return COLORS["other"]


def _load_image(path):
    """Return an HxW or HxWx3 float array in [0,1], display-stretched."""
    import numpy as np

    p = os.fspath(path)
    if p.lower().endswith((".fit", ".fits", ".fts")):
        from astropy.io import fits

        with fits.open(p) as hdul:
            data = next((h.data for h in hdul if h.data is not None and h.data.ndim >= 2), None)
        if data is None:
            raise ValueError(f"no image data in {p}")
        data = data.astype("float32")
        while data.ndim == 3 and data.shape[0] == 1:  # (1, H, W) -> (H, W)
            data = data[0]
        if data.ndim == 3 and data.shape[0] in (3, 4):  # planes -> (H, W, 3)
            data = data[:3].transpose(1, 2, 0)
        # processed stacks are already nonlinear: anchor black near the sky
        # background (median) and white at the bright tail, mild gamma lift.
        # nan-safe: drizzled stacks carry NaN borders
        lo = float(np.nanpercentile(data, 45.0))
        hi = float(np.nanpercentile(data, 99.85))
        if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
            lo, hi = 0.0, 1.0
        out = np.clip((np.nan_to_num(data, nan=lo) - lo) / (hi - lo), 0.0, 1.0) ** 0.8
        return out
    from PIL import Image

    with Image.open(p) as im:
        return np.asarray(im.convert("RGB"), dtype="float32") / 255.0


def _hms(ra_deg):
    total = round((ra_deg % 360.0) * 240) % 86400  # integer seconds of RA
    h, rem = divmod(total, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02d}h{m:02d}m{sec:02d}s"


def _dms(dec_deg):
    sign = "+" if dec_deg >= 0 else "−"
    total = round(abs(dec_deg) * 3600)
    d, rem = divmod(total, 3600)
    m, sec = divmod(rem, 60)
    return f"{sign}{d}°{m:02d}′{sec:02d}″"


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


def needs_flip(model_frame, image_path):
    """True when the model's pixel frame and the image's native frame differ
    (e.g. a fits0 model composited onto an exported top-down JPEG)."""
    is_fits = os.fspath(image_path).lower().endswith((".fit", ".fits", ".fts"))
    return (model_frame or "fits0") != ("fits0" if is_fits else "raster0")


def _short_desig(desig, width=20):
    """Fit a designation into a table column; Gaia ids keep their tail."""
    if len(desig) <= width:
        return desig
    if desig.startswith("Gaia"):
        return f"Gaia …{desig[-(width - 6):]}"
    return desig[: width - 1] + "…"


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

    flip = needs_flip(model["solved"].get("pixel_frame"), image_path)
    if flip:
        model = dict(model)
        model["objects"] = [dict(o, y=(H - 1) - o["y"]) for o in model["objects"]]
        solved_flipped = dict(model["solved"])
        if solved_flipped.get("cd"):
            (a, b), (c, d) = solved_flipped["cd"]
            solved_flipped["cd"] = [[a, -b], [c, -d]]
        model["solved"] = solved_flipped

    s_scale = min(1.0, max_width / W)
    panel_px = 560
    fig_w_px = int(W * s_scale) + panel_px
    fig_h_px = int(H * s_scale)
    dpi = 100
    fig = plt.figure(figsize=(fig_w_px / dpi, fig_h_px / dpi), dpi=dpi, facecolor="black")
    ax = fig.add_axes([0, 0, W * s_scale / fig_w_px, 1])
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
        arm = 0.045 * min(W, H)
        ox, oy = max(1.6 * arm, 0.04 * W), 0.10 * H + 1.6 * arm
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

    # every labeled object gets an exclusion circle, drawn or not, so leader
    # lines can avoid crossing neighbors (a preference, not a hard rule)
    exclusions = (
        [(o["x"], o["y"], 0.030 * min(W, H)) for o in dsos]
        + [(o["x"], o["y"], 0.022 * H) for o in named]
        + [(o["x"], o["y"], 0.014 * H) for o in field]
    )

    def _seg_crossings(x1, y1, x2, y2, skip_xy):
        hits = 0
        vx, vy = x2 - x1, y2 - y1
        vv = vx * vx + vy * vy or 1.0
        for ex, ey, er in exclusions:
            if abs(ex - skip_xy[0]) < 0.5 and abs(ey - skip_xy[1]) < 0.5:
                continue  # the object being labeled
            t = max(0.0, min(1.0, ((ex - x1) * vx + (ey - y1) * vy) / vv))
            px, py = x1 + t * vx, y1 + t * vy
            if math.hypot(ex - px, ey - py) < er:
                hits += 1
        return hits

    def leader_label(x, y, text, color, r_gap=0.035):
        # candidate directions: repulsion from neighbors first, then a fan;
        # score each by exclusion-circle crossings and pick the cleanest
        rx = ry = 0.0
        for px, py, _ in exclusions:
            ddx, ddy = x - px, y - py
            d2 = ddx * ddx + ddy * ddy
            if d2 < 1.0 or d2 > (0.30 * min(W, H)) ** 2:
                continue
            rx += ddx / d2
            ry += ddy / d2
        cands = []
        if math.hypot(rx, ry) > 1e-9:
            cands.append((rx / math.hypot(rx, ry), ry / math.hypot(rx, ry)))
        ndx, ndy = x - cx, y - cy
        nn = math.hypot(ndx, ndy)
        if nn > 1e-9:
            cands.append((ndx / nn, ndy / nn))
        for k in range(8):
            ang = k * math.pi / 4 + 0.4
            cands.append((math.cos(ang), math.sin(ang)))

        best = None
        for i, (dx, dy) in enumerate(cands):
            lx = x + dx * r_gap * W * 1.6 + (0.02 * W if dx >= 0 else -0.02 * W)
            ly = y + dy * r_gap * H * 1.6
            lx = min(max(lx, 0.03 * W), 0.97 * W)
            ly = min(max(ly, 0.07 * H), 0.95 * H)
            score = 10 * _seg_crossings(x, y, lx, ly, (x, y)) + 0.1 * i
            if best is None or score < best[0]:
                best = (score, lx, ly)
            if score < 0.5:
                break
        _, lx, ly = best
        ha = "left" if lx >= x else "right"
        if lx > 0.85 * W:
            ha = "right"  # keep text inside the frame near the panel edge
        elif lx < 0.15 * W:
            ha = "left"
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
        dist = f", {fmt_dist_ly(o['dist_ly'])}" if o.get("dist_ly") else ""
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
        kx, kha = (x + 0.016 * H, "left") if x < 0.94 * W else (x - 0.016 * H, "right")
        ax.text(
            kx,
            y - 0.012 * H,
            str(o["key"]),
            color=COLORS["field_star"],
            fontsize=10,
            family="monospace",
            ha=kha,
            zorder=10,
        )

    # ---- legend panel: two-pass layout so content exactly fills ----------
    lax = fig.add_axes([W * s_scale / fig_w_px, 0, 1 - W * s_scale / fig_w_px, 1])
    lax.axis("off")

    entries = []

    def add(text, color=COLORS["ink"], size=11, dy=1.0, weight="normal"):
        entries.append((text, color, size, dy, weight))

    add("LEGEND", size=15, dy=1.9, weight="bold")
    if dsos or named:
        add("Deep-sky objects", size=12, dy=1.5, weight="bold")
        for o in named:
            dist = f", {fmt_dist_ly(o['dist_ly'])}" if o.get("dist_ly") else ""
            add(
                f"\u25cf {o['designation']}   {o['band']}={o['mag']:.2f}{dist}",
                COLORS["named_star"],
                dy=1.35,
            )
        for o in dsos:
            color = dso_color(o.get("type"))
            desigs = " \u00b7 ".join([o["designation"]] + (o.get("aliases") or []))
            add(
                f"\u2014 {desigs}" + (f"  {o['name']}" if o.get("name") else ""),
                color,
                dy=1.05,
            )
            detail = o.get("type") or "Deep-sky object"
            dist = fmt_dist_ly(o.get("dist_ly"))
            if dist:
                detail += f", {dist}"
            add(f"   {detail}", color, size=9.5, dy=1.35)
    if field:
        add(" ", dy=0.5)
        add("Field stars (Gaia DR3 via VizieR)", size=12, dy=1.5, weight="bold")
        add(
            f"{'#':>2} {'designation':<20} {'mag':>5} {'dist ly':>8}",
            COLORS["dim"],
            size=9.5,
            dy=1.15,
        )
        for o in field:
            dist = f"{o['dist_ly']:,}" if o.get("dist_ly") else "\u2014"
            add(
                f"{o['key']:>2} {_short_desig(o['designation']):<20} {o['mag']:>5.1f} {dist:>8}",
                COLORS["field_star"],
                size=9.5,
                dy=1.05,
            )
    add(" ", dy=0.9)
    add(
        f"Solve: {solved['solver']} \u00b7 OpenNGC \u00b7 Gaia DR3 \u00b7 SIMBAD",
        COLORS["dim"],
        size=9,
        dy=1.1,
    )
    add(
        f"{solved['scale_arcsec_px']:.2f}\u2033/px \u00b7 {fw:.2f}\u00b0\u00d7{fh:.2f}\u00b0 FOV",
        COLORS["dim"],
        size=9,
    )

    # compact top-aligned lines at fixed physical size; shrink only when the
    # content would genuinely overflow the panel
    total_dy = sum(e[3] for e in entries)
    lh = (15.5 * 1.5) / fig_h_px  # ~11pt line at dpi 100, in axes fraction
    fscale = 1.0
    if lh * total_dy > 0.90:
        fscale = 0.90 / (lh * total_dy)
        lh *= fscale
    yc = 0.97
    for text, color, size, dy, weight in entries:
        lax.text(
            0.06,
            yc,
            text,
            color=color,
            fontsize=size * fscale,
            family="monospace",
            fontweight=weight,
            va="top",
            transform=lax.transAxes,
        )
        yc -= lh * dy

    fig.savefig(output, dpi=dpi, facecolor="black")
    plt.close(fig)
    return os.fspath(output)
