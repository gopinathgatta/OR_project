"""Shared chart styling (validated categorical palette, recessive chrome)."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
BLUE_RAMP = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
STATUS = {"good": "#0ca30c", "warning": "#fab219", "serious": "#ec835a", "critical": "#d03b3b"}
INK, INK2, MUTED, GRID, AXIS, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
BASELINE_GREY = "#898781"

POLICY_COLORS = {"status_quo": BASELINE_GREY, "model2": SERIES[0], "model1": SERIES[2]}


def apply_style():
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "font.family": ["Segoe UI", "DejaVu Sans", "sans-serif"], "font.size": 10,
        "axes.edgecolor": AXIS, "axes.linewidth": 0.8, "axes.labelcolor": INK2,
        "axes.titlesize": 12, "axes.titleweight": "semibold", "axes.titlecolor": INK,
        "axes.titlelocation": "left", "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "axes.grid.axis": "y", "grid.color": GRID, "grid.linewidth": 0.6,
        "xtick.color": MUTED, "ytick.color": MUTED, "xtick.labelcolor": INK2, "ytick.labelcolor": INK2,
        "legend.frameon": False, "legend.fontsize": 9, "lines.linewidth": 2,
        "axes.prop_cycle": plt.cycler(color=SERIES),
    })


def altair_theme():
    return {"config": {
        "background": "transparent",
        "range": {"category": SERIES, "ramp": BLUE_RAMP},
        "axis": {"gridColor": GRID, "domainColor": AXIS, "tickColor": AXIS, "labelColor": INK2,
                 "titleColor": INK2, "labelFontSize": 11, "titleFontSize": 11},
        "legend": {"labelColor": INK2, "titleColor": INK2, "orient": "top"},
        "view": {"stroke": None},
        "line": {"strokeWidth": 2}, "point": {"size": 64, "filled": True},
        "bar": {"cornerRadiusEnd": 4},
    }}
