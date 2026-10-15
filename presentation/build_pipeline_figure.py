"""End-to-end pipeline diagram for the report and the slide deck.

    python presentation/build_pipeline_figure.py     (run after run_pipeline.py)

Writes outputs/figures/00_pipeline.png (and .pdf for LaTeX). Numbers are read from
outputs/reports/summary.json so the diagram never drifts from the results.
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                      # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch   # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
S = json.loads((ROOT / "outputs" / "reports" / "summary.json").read_text())

BLUE, GREEN, ORANGE = "#2a78d6", "#1baf7a", "#eb6834"
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"
SURFACE, PANEL, EDGE = "#fcfcfb", "#eef4fc", "#c3d7f0"


def n(v, d=0):
    return f"{v:,.{d}f}"


h, proj, bn = S["headline"], S["projection"], S["bottlenecks"]
m1, m2, par = S["model1"], S["model2"], S["parameters"]

STAGES = [
    ("1", "DATA", BLUE, [
        "StudentDropoutDataset (Zenodo)",
        f"{n(h['records'])} enrolment records",
        f"{n(h['students'])} students · {n(h['courses'])} courses",
        "Clean, link, validate counts",
    ]),
    ("2", "FORECAST", BLUE, [
        "Student & course flow model",
        r"$D_c = F_c(1{+}g) + \rho_c R_c$",
        f"{n(proj['demand'])} seats of demand",
        "Split-half validated (4.2% MAPE)",
    ]),
    ("3", "DIAGNOSE", ORANGE, [
        "Demand vs modelled capacity",
        f"{bn['bottleneck_courses']} bottleneck courses",
        f"{bn['at_risk_courses']} more at risk",
        f"{n(bn['projected_unmet_demand'])} students unseated",
    ]),
    ("4", "OPTIMISE", GREEN, None),          # drawn as two sub-boxes
    ("5", "DELIVER", BLUE, [
        "Web interface (Flask)",
        "Report, tables & figures",
        "Excel Solver + hand check",
        "32 automated tests",
    ]),
]

fig, ax = plt.subplots(figsize=(16, 7.2))
fig.patch.set_facecolor(SURFACE)
ax.set_facecolor(SURFACE)
ax.set_xlim(0, 1.8 + 5 * 18.2 + 4 * 3.0 + 1.8)   # fit the five boxes exactly
ax.set_ylim(0, 44)
ax.axis("off")

BW, BH, GAP = 18.2, 17.0, 3.0
Y = 15.0
xs = [1.8 + i * (BW + GAP) for i in range(5)]


def box(x, y, w, hgt, face, edge, lw=1.3, rad=0.6):
    p = FancyBboxPatch((x, y), w, hgt,
                       boxstyle=f"round,pad=0,rounding_size={rad}",
                       facecolor=face, edgecolor=edge, linewidth=lw, zorder=2)
    ax.add_patch(p)
    return p


def arrow(x1, y1, x2, y2, color=MUTED, lw=1.8, style="-|>", rad=0.0, ls="-"):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle=style,
                                 mutation_scale=16, color=color, linewidth=lw,
                                 linestyle=ls, zorder=1,
                                 connectionstyle=f"arc3,rad={rad}"))


# ---------------------------------------------------------------- stage boxes
for i, (num, title, colour, lines) in enumerate(STAGES):
    x = xs[i]
    box(x, Y, BW, BH, PANEL if i != 3 else "#eaf7f1", EDGE if i != 3 else "#bfe6d6")

    # header strip
    box(x, Y + BH - 3.4, BW, 3.4, colour, colour, lw=0)
    ax.text(x + 1.5, Y + BH - 1.7, num, ha="center", va="center",
            fontsize=13, fontweight="bold", color="white", zorder=3)
    ax.text(x + 3.1, Y + BH - 1.7, title, ha="left", va="center",
            fontsize=13, fontweight="bold", color="white", zorder=3)

    if lines is None:
        continue
    for j, line in enumerate(lines):
        ax.text(x + 0.9, Y + BH - 5.3 - j * 2.65, line, ha="left", va="center",
                fontsize=10.5, color=INK2 if j else INK,
                fontweight="semibold" if j == 0 else "normal", zorder=3)

# ---------------------------------------------------------------- stage 4 inner boxes
x4 = xs[3]
sub_h = 5.9
for k, (label, formula, result, col) in enumerate([
    ("Model 1 · Integer",
     r"min $\sum_c x_c$   s.t. $cap\,x_c \geq D_c$",
     f"{n(m1['total_sections'])} sections  ({m1['total_sections'] - m1['current_sections_modelled']:+,})",
     GREEN),
    ("Model 2 · Binary",
     r"max $\sum w_c a_{ck} y_{ck}$   s.t. $\sum y \leq B$",
     f"unseated {n(m2['unmet_demand_before'])} → {n(m2['unmet_demand_after'])}",
     BLUE),
]):
    yb = Y + BH - 4.6 - k * (sub_h + 1.0) - sub_h
    box(x4 + 0.8, yb, BW - 1.6, sub_h, "white", col, lw=1.4, rad=0.4)
    ax.text(x4 + 1.5, yb + sub_h - 1.4, label, ha="left", va="center",
            fontsize=10.5, fontweight="bold", color=col, zorder=3)
    ax.text(x4 + 1.5, yb + sub_h - 3.3, formula, ha="left", va="center",
            fontsize=9.5, color=INK2, zorder=3)
    ax.text(x4 + 1.5, yb + 1.1, result, ha="left", va="center",
            fontsize=10, fontweight="bold", color=INK, zorder=3)

# ---------------------------------------------------------------- flow arrows
for i in range(4):
    arrow(xs[i] + BW + 0.25, Y + BH / 2, xs[i + 1] - 0.25, Y + BH / 2, color="#7f8fa4", lw=2.2)

# ---------------------------------------------------------------- parameters in
par_y = Y - 6.6
PAR_X0, PAR_X1 = xs[1] + 1.0, xs[4] - 1.0
box(PAR_X0, par_y, PAR_X1 - PAR_X0, 4.4, "white", MUTED, lw=1.1, rad=0.4)
ax.text(PAR_X0 + 1.4, par_y + 2.2,
        f"PLANNING PARAMETERS  ·  section capacity = {par['section_capacity']:g} students   "
        f"·  extra-section budget B = {par['extra_sections']}   "
        f"·  demand growth g = {par['first_time_growth']:.0%}",
        ha="left", va="center", fontsize=10.5, color=INK2, zorder=3)
ax.text(PAR_X0 + 1.4, par_y - 1.3,
        "chosen by the planner — not variables in the dataset",
        ha="left", va="center", fontsize=9.5, color=MUTED, style="italic", zorder=3)
for tx in (xs[2] + BW / 2, x4 + BW / 2):
    arrow(tx, par_y + 4.4, tx, Y - 0.3, color=MUTED, lw=1.4, ls=(0, (4, 3)))

# ---------------------------------------------------------------- feedback loop
fb_y = Y + BH + 4.2
arrow(x4 + BW / 2, Y + BH + 0.3, x4 + BW / 2, fb_y, color=ORANGE, lw=1.8, style="-")
arrow(x4 + BW / 2, fb_y, xs[1] + BW / 2, fb_y, color=ORANGE, lw=1.8, style="-")
arrow(xs[1] + BW / 2, fb_y, xs[1] + BW / 2, Y + BH + 0.3, color=ORANGE, lw=1.8)
ax.text((xs[1] + x4 + BW) / 2, fb_y + 1.5,
        "unserved demand returns as next-year backlog  ·  5-year scenario loop",
        ha="center", va="bottom", fontsize=10, color=ORANGE, fontweight="semibold", zorder=3)

ax.text(2.0, 2.2, "Capacity planning only — the models allocate teaching capacity; "
                  "they do not predict which students drop out.",
        ha="left", va="center", fontsize=10, color=MUTED, style="italic")

fig.tight_layout(pad=0.6)
outdir = ROOT / "outputs" / "figures"
outdir.mkdir(parents=True, exist_ok=True)
for ext in ("png", "pdf"):
    fig.savefig(outdir / f"00_pipeline.{ext}", dpi=220, facecolor=SURFACE, bbox_inches="tight")
plt.close(fig)
print(f"wrote {outdir / '00_pipeline.png'} and .pdf")
