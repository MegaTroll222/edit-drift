"""Results table + charts for every model run in a results directory.

results/<benchmark>/<model>/  step01.png ... step40.png, blocked.json (optional), meta.json (optional)
meta.json: {"name": "FLUX 3", "method": "box edit", "endpoint": "...", "params": {...}}
"""
from __future__ import annotations
import json, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from . import metric
from .cli import bench_paths, run_steps

SURFACE, INK, INK2, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#8a8984", "#e6e5e1"
SERIES = "#2a78d6"     # categorical slot 1 (reference palette, light)
CONTEXT = "#d9d8d3"

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
                     "xtick.color": MUTED, "ytick.color": MUTED, "figure.facecolor": SURFACE, "axes.facecolor": SURFACE})


# Vendor colours: reference categorical palette, fixed order (never by rank). Validated light-mode (adjacent CVD ΔE ≥ 9.1).
VENDORS = ["Black Forest Labs", "OpenAI", "Ideogram", "Google", "ByteDance", "xAI", "Alibaba"]
VENDOR_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7"]
OTHER = "#8a8984"


def vendor_color(v):
    return VENDOR_COLORS[VENDORS.index(v)] if v in VENDORS else OTHER


def collect(benchmark, results_dir):
    orig, steps, rois = bench_paths(benchmark)
    rows = []
    for m in sorted(os.listdir(results_dir)):
        d = os.path.join(results_dir, m)
        if not os.path.isdir(d):
            continue
        meta = json.load(open(os.path.join(d, "meta.json"))) if os.path.exists(os.path.join(d, "meta.json")) else {"name": m, "method": ""}
        sp = os.path.join(d, "scores.json")
        if os.path.exists(sp):
            sc = json.load(open(sp))["steps"]
        else:
            sc = metric.chain_scores(orig, run_steps(d, len(steps)), rois)
            json.dump({"summary": metric.summarize(sc), "steps": sc}, open(sp, "w"), indent=1)
        if sc:
            rows.append({"id": m, **meta, "scores": sc, "summary": metric.summarize(sc)})
    return sorted(rows, key=lambda r: r["summary"]["mean_drift"])


def style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis="x" if ax.get_ylabel() == "" else "y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


BADGE = {"Black Forest Labs": "BFL", "OpenAI": "AI", "Ideogram": "Id", "Google": "G", "ByteDance": "BD", "xAI": "xAI", "Alibaba": "Qw"}


def leaderboard(rows, out, title="Image Models Ranked by Edit Fidelity",
                subtitle="Same photo, 40 chained edits, each applied to the previous result · higher is better"):
    """Column leaderboard in the common benchmark-poster format."""
    from matplotlib.patches import FancyBboxPatch
    rows = sorted(rows, key=lambda r: -r["summary"]["fidelity_score"])
    n = len(rows); W = max(10, 1.15 * n + 2.6); H = 6.4
    fig = plt.figure(figsize=(W, H), dpi=170)
    ax = fig.add_axes([0.075, 0.27, 0.9, 0.5])
    vals = [r["summary"]["fidelity_score"] for r in rows]
    cols = [vendor_color(r.get("vendor")) for r in rows]
    x = list(range(n))
    for xi, v, c in zip(x, vals, cols):
        ax.add_patch(FancyBboxPatch((xi - 0.36, 0), 0.72, v, boxstyle="round,pad=0,rounding_size=0.06", mutation_aspect=1 / 14,
                                    facecolor=c, edgecolor="none", zorder=2))
    for xi, v, r in zip(x, vals, rows):
        ax.text(xi, v + 1.6, f"{v:.1f}", ha="center", va="bottom", fontsize=12, fontweight="bold", color=INK, zorder=3)
        b = BADGE.get(r.get("vendor"), "?")
        if v > 14:
            ax.text(xi, v - 6.5, b, ha="center", va="center", fontsize=12 if len(b) < 3 else 10, fontweight="bold", color="white", zorder=3)
    ax.set_xlim(-0.6, n - 0.4); ax.set_ylim(0, 108)
    ax.set_yticks([0, 20, 40, 60, 80, 100])
    ax.set_ylabel("Edit Fidelity Score", fontsize=12, color=INK2)
    ax.set_xticks(x)
    ax.set_xticklabels([(r["name"].rsplit(" ", 1)[0] + "\n" + r["name"].rsplit(" ", 1)[1]) if len(r["name"]) > 17 else r["name"] for r in rows],
                       rotation=35, ha="right", rotation_mode="anchor", fontsize=11, color=INK)
    for s_ in ("top", "right"): ax.spines[s_].set_visible(False)
    ax.spines["left"].set_color(GRID); ax.spines["bottom"].set_color(INK2)
    ax.tick_params(axis="x", length=0, pad=6)
    ax.grid(axis="y", color=GRID, linewidth=0.8, linestyle=(0, (4, 4)), zorder=0); ax.set_axisbelow(True)
    # title, subtitle, legend
    fig.text(0.5, 0.965, title, ha="center", va="top", fontsize=21, fontweight="bold", color=INK)
    fig.text(0.5, 0.895, subtitle, ha="center", va="top", fontsize=12, color=INK2)
    present = [v for v in VENDORS if any(r.get("vendor") == v for r in rows)]
    items = [(v, vendor_color(v), BADGE[v]) for v in present]
    tw = sum(0.035 + 0.0085 * len(v) for v, _, _ in items) + 0.02 * (len(items) - 1)
    lx = 0.5 - tw / 2 * (10 / W) * 1.0
    for v, c, b in items:
        fig.patches.append(FancyBboxPatch((lx, 0.815), 0.022 * 10 / W, 0.038, boxstyle="round,pad=0,rounding_size=0.006",
                                          transform=fig.transFigure, facecolor=c, edgecolor="none"))
        fig.text(lx + 0.011 * 10 / W, 0.834, b, ha="center", va="center", fontsize=6.5 if len(b) > 2 else 7.5, fontweight="bold", color="white")
        fig.text(lx + 0.03 * 10 / W, 0.834, v, ha="left", va="center", fontsize=11, color=INK)
        lx += (0.05 + 0.0085 * len(v)) * 10 / W + 0.012
    fig.text(0.5, 0.025, "Edit Fidelity Score = 100 − mean pixel drift (0–255) in areas no edit touched, over all edits. "
             "Each model used its best documented edit method (mask, box or plain instruction).",
             ha="center", va="bottom", fontsize=8.5, color=MUTED)
    fig.savefig(out, facecolor=SURFACE); plt.close(fig)


def bar_final(rows, out):
    fig, ax = plt.subplots(figsize=(9, 0.48 * len(rows) + 1.4), dpi=160)
    names = [f"{r['name']}  ·  {r['method']}" if r.get("method") else r["name"] for r in rows]
    vals = [r["summary"]["mean_drift"] for r in rows]
    y = range(len(rows))
    ax.barh(list(y), vals, color=SERIES, height=0.62)
    for i, v in enumerate(vals):
        ax.text(v + max(vals) * 0.01, i, f"{v:.1f}", va="center", color=INK, fontsize=10)
    ax.set_yticks(list(y)); ax.set_yticklabels(names, color=INK); ax.invert_yaxis()
    ax.set_xlabel("Mean drift across all edits (pixel change in untouched areas, 0–255) — lower is better")
    ax.spines["left"].set_visible(False); ax.tick_params(axis="y", length=0)
    style(ax); ax.grid(axis="y", visible=False)
    fig.tight_layout(); fig.savefig(out, facecolor=SURFACE); plt.close(fig)


def small_multiples(rows, out, cols=4):
    n = len(rows); rws = (n + cols - 1) // cols
    ymax = max(s["drift"] for r in rows for s in r["scores"]) * 1.05
    fig, axs = plt.subplots(rws, cols, figsize=(3.2 * cols, 2.5 * rws), dpi=160, sharex=True, sharey=True)
    axs = axs.flatten() if n > 1 else [axs]
    for k, ax in enumerate(axs):
        if k >= n:
            ax.axis("off"); continue
        r = rows[k]
        for o in rows:
            if o is not r:
                ax.plot([s["step"] for s in o["scores"]], [s["drift"] for s in o["scores"]], color=CONTEXT, linewidth=1)
        xs = [s["step"] for s in r["scores"]]; ys = [s["drift"] for s in r["scores"]]
        ax.plot(xs, ys, color=SERIES, linewidth=2, solid_capstyle="round")
        bl = [s for s in r["scores"] if s["blocked"]]
        if bl:
            ax.scatter([s["step"] for s in bl], [s["drift"] for s in bl], s=14, marker="x", color=INK2, linewidths=1, zorder=3)
        ax.set_title(r["name"], fontsize=11, color=INK, loc="left", pad=4)
        ax.text(0.02, 0.86, f"final {r['summary']['final_drift']:.1f}" + (f" · {len(bl)} refused" if bl else ""),
                transform=ax.transAxes, fontsize=9, color=INK2)
        ax.set_ylim(0, ymax); ax.set_xlim(1, max(xs + [40]))
        for s in ("top", "right"): ax.spines[s].set_visible(False)
        ax.grid(axis="y", color=GRID, linewidth=0.8); ax.set_axisbelow(True)
    fig.supxlabel("Edit number (each edit applied to the previous result)", color=INK2, fontsize=10)
    fig.supylabel("Drift (0–255)", color=INK2, fontsize=10)
    fig.tight_layout(); fig.savefig(out, facecolor=SURFACE); plt.close(fig)


def table_md(rows):
    h = "| Rank | Model | Vendor | Method | Edit Fidelity Score ↑ | Mean drift ↓ | Final drift ↓ | Drift / edit | Refused edits |\n|---|---|---|---|---|---|---|---|---|\n"
    for i, r in enumerate(rows, 1):
        s = r["summary"]
        h += f"| {i} | {r['name']} | {r.get('vendor','')} | {r.get('method','')} | **{s['fidelity_score']:.1f}** | {s['mean_drift']:.1f} | {s['final_drift']:.1f} | {s['slope_per_edit']:.2f} | {s['blocked_steps']} / {s['steps']} |\n"
    return h


def build(benchmark, results_dir, out):
    os.makedirs(out, exist_ok=True)
    rows = collect(benchmark, results_dir)
    leaderboard(rows, os.path.join(out, "leaderboard.png"))
    bar_final(rows, os.path.join(out, "drift_score.png"))
    small_multiples(rows, os.path.join(out, "drift_curves.png"))
    md = table_md(rows); open(os.path.join(out, "results.md"), "w").write(md)
    json.dump([{"id": r["id"], "name": r["name"], "method": r.get("method"), **r["summary"]} for r in rows],
              open(os.path.join(out, "results.json"), "w"), indent=1)
    print(md)
