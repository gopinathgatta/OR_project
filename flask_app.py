"""Flask web interface for the curriculum capacity planning project.

Pages: Dashboard, Dataset, Model 1 (Integer Programming), Model 2 (Binary Programming),
Manual & Excel verification.

The heavy work (preprocessing, System Dynamics calibration, demand projection) is done by
run_pipeline.py and cached in outputs/. This app reads those results and re-solves the two
optimisation models live for whatever parameters the user sets, which takes well under a second.

Run with:  python flask_app.py       then open http://127.0.0.1:5000
"""
from __future__ import annotations

import json
from functools import lru_cache

import pandas as pd
from flask import Flask, Response, render_template, request

from curriculum_planner import config
from curriculum_planner.capacity import (bottleneck_summary, bottleneck_table,
                                         modelled_current_sections)
from curriculum_planner.optimization import solve_extra_sections, solve_min_sections

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True   # pick up template edits without a restart
app.jinja_env.auto_reload = True

# ------------------------------------------------------------------ cached data
@lru_cache(maxsize=1)
def projection() -> pd.DataFrame:
    """Projected course demand, as produced by the pipeline."""
    df = pd.read_csv(config.TABLE_DIR / "capacity_bottleneck_table.csv")
    return df


@lru_cache(maxsize=1)
def summary() -> dict:
    return json.loads((config.REPORT_DIR / "summary.json").read_text())


@lru_cache(maxsize=1)
def course_stats() -> pd.DataFrame:
    return pd.read_csv(config.TABLE_DIR / "course_year_statistics.csv")


@lru_cache(maxsize=1)
def yearly() -> pd.DataFrame:
    return pd.read_csv(config.TABLE_DIR / "eda_by_year.csv")


def fmt(x, nd=0):
    try:
        return f"{float(x):,.{nd}f}"
    except (TypeError, ValueError):
        return "-"


app.jinja_env.filters["num"] = fmt


# ------------------------------------------------------------------ model solving
def _base(capacity: float):
    """Projection plus the modelled current sections at this capacity."""
    proj = projection().copy()
    s0 = modelled_current_sections(proj["enrolment"], capacity)
    return proj, s0


def run_model1(capacity: float, buffer: float):
    proj, s0 = _base(capacity)
    r = solve_min_sections(proj[["course_id", "programme_id", "demand"]], capacity, buffer)
    alloc = r.allocation.assign(current_sections=s0,
                                change=r.allocation["sections"] - s0)
    return r, alloc, int(s0.sum())


def run_model2(capacity: float, budget: int, max_per_prog: int, weights: str):
    proj, s0 = _base(capacity)
    r = solve_extra_sections(proj, s0, budget, capacity,
                             max_per_programme=max_per_prog or None, weight_mode=weights)
    return r, r.allocation


# ------------------------------------------------------------------ routes
@app.route("/")
def index():
    """Dashboard: headline numbers and the Model 1 vs Model 2 comparison."""
    s = summary()
    cap = config.DEFAULT_SECTION_CAPACITY
    r1, _, current = run_model1(cap, 0.0)
    r2, _ = run_model2(cap, config.DEFAULT_EXTRA_SECTIONS, 0, "uniform")
    return render_template(
        "index.html", title="Dashboard", s=s, cap=cap,
        m1=r1.summary, m2=r2.summary, current=current,
        headline=s["headline"], proj=s["projection"], bn=s["bottlenecks"],
        yearly=yearly().to_dict(orient="records"),
    )


@app.route("/dataset")
def dataset():
    """Dataset explorer plus statistics generated on demand."""
    df = course_stats()
    year = request.args.get("year", type=int) or int(df["academic_year"].max())
    stat = request.args.get("stat", "enrolment")
    topn = request.args.get("topn", type=int) or 20

    sub = df[df["academic_year"] == year]
    valid = {"enrolment", "pass_rate", "fail_rate", "repeat_rate", "mean_grade",
             "repeat_enrolments", "not_evaluated_rate"}
    stat = stat if stat in valid else "enrolment"
    table = (sub[["course_id", "programme_id", "enrolment", "pass_rate", "fail_rate",
                  "repeat_rate", "mean_grade"]]
             .sort_values(stat, ascending=False).head(topn))
    return render_template(
        "dataset.html", title="Dataset", rows=table.to_dict(orient="records"),
        years=sorted(df["academic_year"].unique().tolist()), year=year,
        stat=stat, topn=topn, stats=sorted(valid),
        n_records=len(sub), n_students=int(sub["enrolment"].sum()),
        n_courses=sub["course_id"].nunique(), n_programmes=sub["programme_id"].nunique(),
        yearly=yearly().to_dict(orient="records"),
    )


@app.route("/model1")
def model1():
    """Integer Programming: minimum section allocation."""
    cap = request.args.get("capacity", type=float) or config.DEFAULT_SECTION_CAPACITY
    buffer = request.args.get("buffer", type=float) or 0.0
    r, alloc, current = run_model1(cap, buffer)
    changed = alloc[alloc["change"] != 0].sort_values("change")
    return render_template(
        "model1.html", title="Model 1 - Integer Programming", cap=cap, buffer=buffer,
        s=r.summary, current=current, status=r.status,
        rows=changed.head(60).to_dict(orient="records"),
        n_more=int((alloc["change"] > 0).sum()), n_less=int((alloc["change"] < 0).sum()),
        chart_labels=[c[:8] for c in changed.head(15)["course_id"]],
        chart_demand=changed.head(15)["demand"].round(1).tolist(),
        chart_capacity=changed.head(15)["capacity"].tolist(),
    )


@app.route("/model2")
def model2():
    """Binary (0-1) Programming: allocation of a limited number of extra sections."""
    cap = request.args.get("capacity", type=float) or config.DEFAULT_SECTION_CAPACITY
    budget = request.args.get("budget", type=int)
    budget = config.DEFAULT_EXTRA_SECTIONS if budget is None else budget
    maxprog = request.args.get("maxprog", type=int) or 0
    r, alloc = run_model2(cap, budget, maxprog, "uniform")
    short = alloc[alloc["unmet_before"] > 0].sort_values("unmet_before", ascending=False)
    top = short.head(15)
    return render_template(
        "model2.html", title="Model 2 - Binary Programming", cap=cap, budget=budget,
        maxprog=maxprog, s=r.summary, status=r.status,
        rows=short.head(60).to_dict(orient="records"),
        chart_labels=[c[:8] for c in top["course_id"]],
        chart_covered=top["covered_demand"].round(1).tolist(),
        chart_remaining=top["unmet_after"].round(1).tolist(),
    )


@app.route("/compare")
def compare():
    """Model 1 against Model 2: what each one answers, and what each one costs."""
    cap = request.args.get("capacity", type=float) or config.DEFAULT_SECTION_CAPACITY
    budget = request.args.get("budget", type=int)
    budget = config.DEFAULT_EXTRA_SECTIONS if budget is None else budget

    r1, alloc1, current = run_model1(cap, 0.0)
    r2, _ = run_model2(cap, budget, 0, "uniform")
    bt = bottleneck_table(projection(), cap)
    bs = bottleneck_summary(bt)

    # how Model 2 approaches Model 1 as the budget grows
    clear = int(bs["extra_sections_to_clear"])
    budgets = sorted({0, 5, 10, 25, budget, clear, clear + 25})
    sweep = []
    for b in budgets:
        if b < 0:
            continue
        rr, _ = run_model2(cap, b, 0, "uniform")
        sweep.append({"budget": b,
                      "unmet": round(rr.summary["unmet_demand_after"], 1),
                      "used": rr.summary["extra_sections_used"],
                      "short": rr.summary["courses_short_after"]})

    return render_template(
        "compare.html", title="Model 1 vs Model 2", cap=cap, budget=budget,
        m1=r1.summary, m2=r2.summary, current=current, bs=bs,
        status_quo=bs["projected_unmet_demand"], clear=clear,
        n_more=int((alloc1["change"] > 0).sum()), n_less=int((alloc1["change"] < 0).sum()),
        sweep=sweep,
        sweep_labels=[r["budget"] for r in sweep],
        sweep_values=[r["unmet"] for r in sweep],
    )


@app.route("/favicon.ico")
def favicon():
    return Response(status=204)


if __name__ == "__main__":
    app.run(debug=False, port=5000)
