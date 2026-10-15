"""End-to-end batch run: preprocessing -> EDA -> SD -> bottlenecks -> IP -> scenarios -> reports.

    python run_pipeline.py                 # defaults (capacity 50, 50 extra sections)
    python run_pipeline.py --capacity 60 --extra 80 --growth 0.02 --reprocess
"""
from __future__ import annotations

import argparse
import json
import time

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from curriculum_planner import config, descriptive as ds, preprocessing as pp
from curriculum_planner import scenarios as scn, system_dynamics as sd, viz
from curriculum_planner.capacity import bottleneck_summary, bottleneck_table, modelled_current_sections
from curriculum_planner import mcdm
from curriculum_planner.optimization import (AHP_CRITERIA, lp_sensitivity_extra_sections,
                                             solve_extra_sections, solve_min_sections)

T, F, R = config.TABLE_DIR, config.FIGURE_DIR, config.REPORT_DIR


def short(h):  # display label for hashed course ids
    return f"C-{h[:6]}"


def main(a):
    t0 = time.time()
    for d in (T, F, R):
        d.mkdir(parents=True, exist_ok=True)
    viz.apply_style()

    # 1-2 preprocessing --------------------------------------------------------------
    if a.reprocess or not (config.PROCESSED_DIR / "student_course_enrolments.parquet").exists():
        data = pp.clean(pp.load_raw_from_project())
        pp.save(data)
    else:
        data = pp.load_default()
    enr, stu, crs = data.enrolments, data.students, data.courses
    print(f"[1] data: {len(enr):,} enrolment records")

    # 3 descriptive ----------------------------------------------------------------
    yearly = ds.by_year(enr)
    yearly.to_csv(T / "eda_by_year.csv", index=False)
    ds.course_demand_trend(crs).to_csv(T / "eda_course_demand_trend.csv", index=False)
    ds.top_courses(crs, 2022, 30).to_csv(T / "eda_top_courses_2022.csv", index=False)
    ds.programme_summary(enr, 2022).to_csv(T / "eda_programme_summary_2022.csv", index=False)
    crs.to_csv(T / "course_year_statistics.csv", index=False)
    flows = ds.progression_flows(stu)
    flows.to_csv(T / "progression_flows_2021_2022.csv")
    pm = ds.progression_matrix(stu)
    pm.to_csv(T / "progression_transition_matrix.csv")
    rb = ds.repeat_burden(enr, 2022)

    # 4 system dynamics ----------------------------------------------------------------
    sfm = sd.StudentFlowModel.calibrate(stu)
    sim = sfm.simulate(a.horizon, a.growth)
    sim.to_csv(T / "sd_student_flow_simulation.csv", index=False)
    val_st = sd.validate_student_flow(stu)
    val_st.to_csv(T / "validation_student_flow.csv")
    val_rep = sd.validate_repeat_flow(enr)
    val_rep["table"].to_csv(T / "validation_repeat_flow_by_course.csv")
    params = sd.course_flow_parameters(enr)
    params.to_csv(T / "sd_course_parameters.csv", index=False)
    cfm = sd.CourseFlowModel(params, a.capacity, a.growth)
    proj = cfm.projected_demand()
    print(f"[4] SD: projected {config.PLANNING_YEAR} demand {proj['demand'].sum():,.0f}")

    # 5 capacity & bottlenecks --------------------------------------------------------
    bt = bottleneck_table(proj, a.capacity)
    bsum = bottleneck_summary(bt)
    bt.to_csv(T / "capacity_bottleneck_table.csv", index=False)
    bt[bt["status"] == "Bottleneck"].to_csv(T / "bottleneck_courses.csv", index=False)
    print(f"[5] bottlenecks: {bsum['bottleneck_courses']} courses, unmet {bsum['projected_unmet_demand']:.0f}")

    # 6 optimisation ------------------------------------------------------------------
    r1 = solve_min_sections(proj[["course_id", "programme_id", "demand"]], a.capacity)
    s0 = modelled_current_sections(proj["enrolment"], a.capacity)
    m1 = r1.allocation.assign(current_sections=s0, change_vs_current=r1.allocation["sections"] - s0)
    m1.to_csv(T / "model1_minimum_sections.csv", index=False)
    r1.summary.update(current_sections_modelled=int(s0.sum()),
                      courses_needing_more=int((m1["change_vs_current"] > 0).sum()),
                      courses_can_release=int((m1["change_vs_current"] < 0).sum()),
                      sections_added=int(m1["change_vs_current"].clip(lower=0).sum()),
                      sections_released=int(-m1["change_vs_current"].clip(upper=0).sum()))
    r2 = solve_extra_sections(proj, s0, a.extra, a.capacity)
    r2.allocation.to_csv(T / "model2_extra_section_allocation.csv", index=False)
    r2f = solve_extra_sections(proj, s0, a.extra, a.capacity, max_per_programme=a.max_per_programme)
    r2r = solve_extra_sections(proj, s0, a.extra, a.capacity, weight_mode="repeat_weighted")
    print(f"[6] Model 1: {r1.summary['total_sections']} sections; Model 2: unmet "
          f"{r2.summary['unmet_demand_before']:.0f} -> {r2.summary['unmet_demand_after']:.0f}")

    # 6b LP sensitivity and AHP weights for the binary model ------------------------------
    sens_lp = lp_sensitivity_extra_sections(proj, s0, a.extra, a.capacity)
    sens_lp["constraints"].query("not constraint.str.startswith('Order')", engine="python").to_csv(
        T / "lp_sensitivity_constraints.csv", index=False)
    sens_lp["variables"].to_csv(T / "lp_sensitivity_variables.csv", index=False)
    sens_lp["budget_ranging"].to_csv(T / "lp_sensitivity_budget_ranging.csv", index=False)
    # illustrative AHP judgements (the UI lets the planner enter their own)
    c = AHP_CRITERIA
    ahp_c = mcdm.ahp(mcdm.pairwise_matrix(c, {(c[0], c[1]): 3, (c[0], c[2]): 5, (c[1], c[2]): 2}))
    r2a = solve_extra_sections(proj, s0, a.extra, a.capacity, weight_mode="ahp",
                               criteria_weights=ahp_c.weights.values)
    ahp_c.weights.rename("weight").to_frame().assign(lambda_max=ahp_c.lambda_max, ci=ahp_c.ci,
                                                     cr=ahp_c.cr).to_csv(T / "ahp_weights.csv")
    print(f"[6b] LP shadow price of budget {sens_lp['budget_shadow_price']:.2f}; AHP CR {ahp_c.cr:.3f}")

    # 7 scenarios & sensitivity ------------------------------------------------------------
    sens_cap = scn.sensitivity_capacity(params, growth=a.growth)
    sens_bud = scn.sensitivity_budget(params, capacity=a.capacity, growth=a.growth)
    sens_gro = scn.sensitivity_growth(params, capacity=a.capacity, budget=a.extra)
    comp, traj = scn.compare_scenarios(params, scn.default_scenarios(a.capacity, a.extra, a.growth, a.horizon))
    for name, df in [("sensitivity_capacity", sens_cap), ("sensitivity_budget", sens_bud),
                     ("sensitivity_growth", sens_gro), ("scenario_comparison", comp),
                     ("scenario_trajectories", traj)]:
        df.to_csv(T / f"{name}.csv", index=False)
    print("[7] scenarios done")

    # figures ---------------------------------------------------------------------------
    figures(yearly, flows, sim, proj, bt, sens_cap, sens_bud, traj, val_rep, a)

    # summary + reports -----------------------------------------------------------------
    summary = {
        "parameters": {"section_capacity": a.capacity, "first_time_growth": a.growth,
                       "extra_sections": a.extra, "horizon": a.horizon,
                       "bottleneck_threshold": config.DEFAULT_BOTTLENECK_THRESHOLD,
                       "max_per_programme_variant": a.max_per_programme,
                       "note": "capacity is a model parameter; it is not in the dataset"},
        "validation_counts": data.report.validation,
        "headline": {k: (v if not isinstance(v, (np.integer, np.floating)) else v.item())
                     for k, v in ds.headline(enr).items()},
        "repeat_burden_2022": rb,
        "sd_rates": {"global_retake_rate": params.attrs["global_retake_rate"],
                     "global_pass_rate": params.attrs["global_pass_rate"]},
        "validation_repeat_flow": {k: {kk: float(vv) for kk, vv in val_rep[k].items()}
                                   for k in ("course_specific", "global_rate")},
        "validation_student_flow_mape": float(val_st["abs_pct_error"].mean()),
        "projection": {"demand": float(proj["demand"].sum()),
                       "first_time": float(proj["demand_first_time"].sum()),
                       "repeat": float(proj["demand_repeat"].sum())},
        "bottlenecks": bsum, "model1": r1.summary, "model2": r2.summary,
        "model2_fair": r2f.summary, "model2_repeat_weighted": r2r.summary,
        "model2_ahp_weighted": r2a.summary,
        "lp_sensitivity": {k: sens_lp[k] for k in ("lp_objective", "budget_shadow_price",
                                                     "value_of_last_section", "value_of_next_section")},
        "ahp": {"criteria_weights": ahp_c.weights.to_dict(), "criteria_cr": ahp_c.cr},
    }
    (R / "summary.json").write_text(json.dumps(summary, indent=2, default=float))
    with pd.ExcelWriter(R / "capacity_planning_results.xlsx") as xw:
        pd.DataFrame(data.report.steps).to_excel(xw, sheet_name="Cleaning log", index=False)
        yearly.to_excel(xw, sheet_name="EDA by year", index=False)
        flows.to_excel(xw, sheet_name="Progression flows")
        sim.to_excel(xw, sheet_name="SD student flow", index=False)
        bt.head(500).to_excel(xw, sheet_name="Bottlenecks (top 500)", index=False)
        m1.to_excel(xw, sheet_name="Model 1 sections", index=False)
        r2.allocation[r2.allocation["unmet_before"] > 0].to_excel(xw, sheet_name="Model 2 allocation", index=False)
        sens_lp["constraints"].query("not constraint.str.startswith('Order')", engine="python").to_excel(
            xw, sheet_name="LP sens - constraints", index=False)
        sens_lp["variables"].to_excel(xw, sheet_name="LP sens - variables", index=False)
        sens_lp["budget_ranging"].to_excel(xw, sheet_name="LP sens - budget ranging", index=False)
        comp.to_excel(xw, sheet_name="Scenario comparison", index=False)
        sens_cap.to_excel(xw, sheet_name="Sens - capacity", index=False)
        sens_bud.to_excel(xw, sheet_name="Sens - extra sections", index=False)
        sens_gro.to_excel(xw, sheet_name="Sens - growth", index=False)
        val_st.to_excel(xw, sheet_name="Validation - stocks")
    write_report(summary, yearly, flows, val_st, comp, sens_cap, sens_bud, sens_gro, bt)
    print(f"done in {time.time() - t0:.0f}s -> {config.OUTPUT_DIR}")


# --------------------------------------------------------------------------- figures
def _save(fig, name):
    fig.tight_layout()
    fig.savefig(F / f"{name}.png", dpi=180)
    plt.close(fig)


def figures(yearly, flows, sim, proj, bt, sens_cap, sens_bud, traj, val_rep, a):
    C = viz.SERIES
    # outcomes by year (100% stacked bars)
    fig, ax = plt.subplots(figsize=(7, 3.6))
    yrs = yearly["academic_year"].astype(str)
    bottom = np.zeros(len(yrs))
    for col, lab, c in [("pass_rate", "Passed", C[0]), ("fail_rate", "Failed", C[1]),
                        ("not_evaluated_rate", "Not evaluated", C[2])]:
        v = yearly[col].to_numpy() * 100
        ax.bar(yrs, v, bottom=bottom, color=c, label=lab, width=0.55, edgecolor=viz.SURFACE, linewidth=2)
        for x, b, h in zip(yrs, bottom, v):
            ax.text(x, b + h / 2, f"{h:.1f}%", ha="center", va="center", color="white", fontsize=9)
        bottom += v
    ax.set_ylabel("% of course enrolments"); ax.set_ylim(0, 100)
    ax.set_title("Course outcomes by academic year")
    ax.legend(ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.1))
    _save(fig, "01_outcomes_by_year")

    # progression flows by stage
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    stages = flows.index.tolist()
    left = np.zeros(len(stages))
    for col, c in zip(["Progress %", "Repeat %", "Graduated %", "Withdrawn %"], C):
        v = flows[col].to_numpy()
        ax.barh(stages, v, left=left, color=c, label=col.replace(" %", ""), height=0.6,
                edgecolor=viz.SURFACE, linewidth=2)
        for y, l, w in zip(stages, left, v):
            if w >= 6:
                ax.text(l + w / 2, y, f"{w:.0f}%", ha="center", va="center", color="white", fontsize=8.5)
        left += v
    ax.invert_yaxis(); ax.set_xlim(0, 100); ax.grid(axis="x"); ax.grid(axis="y", visible=False)
    ax.set_xlabel("% of students in stage (2021 → 2022)")
    ax.set_title("Student progression by curriculum stage")
    ax.legend(ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.18))
    _save(fig, "02_progression_by_stage")

    # SD stocks over time
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    for s, c in zip(sd.STAGES, C):
        ax.plot(sim["year"], sim[s], color=c, marker="o", ms=4, label=s)
        ax.annotate(s, (sim["year"].iloc[-1], sim[s].iloc[-1]), xytext=(6, 0),
                    textcoords="offset points", va="center", fontsize=8.5, color=viz.INK2)
    ax.set_xlim(sim["year"].min() - 0.2, sim["year"].max() + 1.1)
    ax.set_xticks(sim["year"])
    ax.set_ylabel("students"); ax.set_title("System Dynamics projection of student stocks")
    _save(fig, "03_sd_student_stocks")

    # top demand courses: first-time vs repeat, against modelled capacity
    top = bt.sort_values("demand", ascending=False).head(15).iloc[::-1]
    fig, ax = plt.subplots(figsize=(7.5, 5))
    y = [short(c) for c in top["course_id"]]
    ax.barh(y, top["demand_first_time"], color=C[0], label="First-time demand", height=0.62,
            edgecolor=viz.SURFACE, linewidth=2)
    ax.barh(y, top["demand_repeat"], left=top["demand_first_time"], color=C[1], label="Repeat demand",
            height=0.62, edgecolor=viz.SURFACE, linewidth=2)
    ax.scatter(top["current_capacity"], y, marker="|", s=260, color=viz.INK, linewidths=2,
               label=f"Modelled capacity ({a.capacity}/section)", zorder=3)
    ax.grid(axis="x"); ax.grid(axis="y", visible=False)
    ax.set_xlabel(f"students, projected {config.PLANNING_YEAR}")
    ax.set_title("Highest-demand courses: first-time vs repeat demand")
    ax.legend(ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.12), fontsize=8.5)
    _save(fig, "04_top_course_demand")

    # utilisation distribution
    fig, ax = plt.subplots(figsize=(7, 3.6))
    u = bt["utilisation"].clip(upper=1.4)
    ax.hist(u, bins=np.arange(0, 1.45, 0.05), color=C[0], edgecolor=viz.SURFACE, linewidth=1.5)
    ax.axvline(config.DEFAULT_BOTTLENECK_THRESHOLD, color=viz.STATUS["critical"], lw=1.5, ls="--")
    ax.text(1.01, ax.get_ylim()[1] * 0.9, f"Bottleneck ≥ 100%\n{(bt['status'] == 'Bottleneck').sum()} courses",
            color=viz.INK2, fontsize=9)
    ax.set_xlabel("projected demand ÷ modelled capacity"); ax.set_ylabel("courses")
    ax.set_title("Capacity utilisation across courses")
    _save(fig, "05_utilisation_distribution")

    # budget sensitivity
    fig, ax = plt.subplots(figsize=(7, 3.6))
    ax.plot(sens_bud["extra_sections"], sens_bud["unmet_demand_after"], color=C[0], marker="o", ms=5)
    ax.axvline(a.extra, color=viz.MUTED, lw=1, ls=":")
    ax.text(a.extra, ax.get_ylim()[1] * 0.95, f"  default budget = {a.extra}", color=viz.INK2, fontsize=9, va="top")
    ax.set_xlabel("additional sections available (B)"); ax.set_ylabel("students with unmet demand")
    ax.set_title("Model 2: unmet demand vs additional sections")
    _save(fig, "06_sensitivity_extra_sections")

    # capacity sensitivity - bottleneck count
    fig, ax = plt.subplots(figsize=(7, 3.6))
    ax.bar(sens_cap["capacity"].astype(str), sens_cap["bottleneck_courses"], color=C[0], width=0.55)
    for x, v in zip(sens_cap["capacity"].astype(str), sens_cap["bottleneck_courses"]):
        ax.text(x, v, f"{v}", ha="center", va="bottom", fontsize=9, color=viz.INK2)
    ax.set_xlabel("section capacity parameter (students per section)"); ax.set_ylabel("bottleneck courses")
    ax.set_title("Bottleneck courses vs section-capacity assumption")
    _save(fig, "07_sensitivity_capacity")

    # model 1 sections vs capacity (IP vs LP relaxation, same unit)
    fig, ax = plt.subplots(figsize=(7, 3.6))
    ax.plot(sens_cap["capacity"], sens_cap["model1_sections"], color=C[0], marker="o", label="Integer solution (Model 1)")
    ax.plot(sens_cap["capacity"], sens_cap["lp_relaxation_sections"], color=C[1], marker="o", ls="--",
            label="LP relaxation (fractional, infeasible in practice)")
    ax.set_xlabel("section capacity parameter"); ax.set_ylabel("total sections")
    ax.set_title("Minimum sections required vs section capacity")
    ax.legend()
    _save(fig, "08_model1_sections_vs_capacity")

    # scenario comparison: cumulative unserved (bars) + backlog trajectories (lines)
    names = list(dict.fromkeys(traj["scenario"]))
    cum = traj.groupby("scenario", sort=False)["unserved"].sum().reindex(names)
    colors = [viz.BASELINE_GREY] + [C[i % len(C)] for i in range(len(names) - 1)]
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    ax.barh(names[::-1], cum.values[::-1], color=colors[::-1], height=0.6)
    for y, v in zip(names[::-1], cum.values[::-1]):
        ax.text(v, y, f"  {v:,.0f}", va="center", fontsize=9, color=viz.INK2)
    ax.set_xscale("symlog", linthresh=100)
    ax.grid(axis="x"); ax.grid(axis="y", visible=False)
    ax.set_xlabel(f"cumulative students not seated, {config.PLANNING_YEAR}–{config.PLANNING_YEAR + a.horizon - 1} (log scale)")
    ax.set_title("Scenario comparison: cumulative unserved demand")
    _save(fig, "09_scenario_unserved")

    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    for name, c in zip(names, colors):
        if "intake" in name:
            continue
        g = traj[traj["scenario"] == name]
        ax.plot(g["year"], g["backlog_end"], marker="o", ms=4, color=c, label=name)
    ax.set_xticks(sorted(traj["year"].unique()))
    ax.set_ylabel("students still needing a course")
    ax.set_title("Backlog stock (failed or unserved enrolments) by scenario")
    ax.legend(ncol=2, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.1))
    _save(fig, "09b_scenario_backlog")

    # validation scatter
    t = val_rep["table"]
    fig, ax = plt.subplots(figsize=(4.8, 4.4))
    ax.scatter(t["observed"], t["predicted"], s=14, alpha=0.5, color=C[0], edgecolors="none")
    lim = max(t["observed"].max(), t["predicted"].max()) * 1.05
    ax.plot([0, lim], [0, lim], color=viz.MUTED, lw=1, ls="--")
    ax.set_xlim(0, lim); ax.set_ylim(0, lim); ax.grid(axis="x")
    ax.set_xlabel("observed 2022 repeat enrolments (hold-out half)")
    ax.set_ylabel("predicted")
    ax.set_title(f"Repeat-flow validation  R² = {val_rep['course_specific']['R2']:.2f}")
    _save(fig, "10_validation_repeat_flow")


# --------------------------------------------------------------------------- report
def _md(df, floatfmt=".2f"):
    return df.to_markdown(floatfmt=floatfmt) if hasattr(df, "to_markdown") else df.to_string()


def _pct(df, cols):
    df = df.copy()
    for c in cols:
        df[c] = df[c].map(lambda v: f"{v:+.0%}" if v else "0%")
    return df


def write_report(s, yearly, flows, val_st, comp, sens_cap, sens_bud, sens_gro, bt):
    comp = _pct(comp, ["growth", "pass_rate_shift"])
    sens_gro = _pct(sens_gro, ["growth"])
    b, m1, m2 = s["bottlenecks"], s["model1"], s["model2"]
    vr = s["validation_repeat_flow"]
    top = bt[bt["status"] == "Bottleneck"].head(10)[
        ["course_id", "programme_id", "enrolment", "demand", "demand_repeat", "current_capacity",
         "utilisation", "unmet_demand", "extra_sections_needed"]]
    lines = [
        "# Results and Validation Report",
        "",
        "Auto-generated by `run_pipeline.py`. Every number below comes from the processed dataset.",
        "",
        "## Parameters",
        f"- Section capacity: **{s['parameters']['section_capacity']} students/section** (model parameter, not a dataset variable)",
        f"- First-time demand growth: {s['parameters']['first_time_growth']:.1%} per year",
        f"- Additional sections available (Model 2): {s['parameters']['extra_sections']}",
        f"- Planning year: {config.PLANNING_YEAR}; SD calibrated on {config.CALIBRATION_FROM}→{config.CALIBRATION_TO}",
        "",
        "## 1. Dataset validation",
        _md(pd.DataFrame(s["validation_counts"]).T),
        "",
        "## 2. Descriptive statistics by year",
        _md(yearly, ".3f"),
        "",
        f"Repeat enrolments in 2022: **{s['repeat_burden_2022']['repeat_enrolments']:,}** "
        f"({s['repeat_burden_2022']['share_of_enrolments']:.1%} of enrolments); "
        f"{s['repeat_burden_2022']['students_repeating_any_course']:,} students "
        f"({s['repeat_burden_2022']['share_of_students']:.1%}) retook at least one course.",
        "",
        "## 3. Student progression (2021 → 2022)",
        _md(flows, ".1f"),
        "",
        "## 4. System Dynamics validation",
        "### 4a. Student-flow stocks (split-half: rates from half A, predict half B)",
        _md(val_st, ".2f"),
        f"\nMean absolute percentage error across stocks/exits: **{s['validation_student_flow_mape']:.1f}%**.",
        "",
        "### 4b. Repeat-demand flow (split-half, per course)",
        f"- Course-specific retake rates: R² = **{vr['course_specific']['R2']:.3f}**, MAE = {vr['course_specific']['MAE']:.2f} students/course, "
        f"total bias = {vr['course_specific']['total_error_pct']:+.1f}%",
        f"- Single university-wide rate: R² = {vr['global_rate']['R2']:.3f}, MAE = {vr['global_rate']['MAE']:.2f}, "
        f"total bias = {vr['global_rate']['total_error_pct']:+.1f}%",
        "- Course-specific rates explain far more between-course variation; their small upward bias "
        "errs toward providing capacity (conservative for planning).",
        "",
        f"## 5. Projected demand {config.PLANNING_YEAR}",
        f"- Total course demand: **{s['projection']['demand']:,.0f}** seats "
        f"({s['projection']['first_time']:,.0f} first-time + {s['projection']['repeat']:,.0f} repeat)",
        "",
        "## 6. Bottlenecks (demand ≥ modelled capacity)",
        f"- Courses modelled: {b['courses_modelled']:,}; **bottlenecks: {b['bottleneck_courses']}**; at risk (≥90%): {b['at_risk_courses']}",
        f"- Projected unmet demand at current modelled sections: **{b['projected_unmet_demand']:,.0f} students**",
        f"- Extra sections needed to clear every bottleneck: {b['extra_sections_to_clear']}; programmes affected: {b['programmes_affected']}",
        f"- Repeat share of demand in bottleneck courses: {b['bottleneck_repeat_share']:.1%}",
        "",
        "Top 10 bottleneck courses:",
        _md(top.set_index("course_id"), ".2f"),
        "",
        "## 7. Model 1 – Minimum Section Allocation",
        "- **Decision variable:** x_c = sections opened for course c (integer ≥ 1)",
        "- **Objective:** minimise Σ_c x_c — the total number of sections opened",
        "- **Target:** every student seated — cap·x_c ≥ D_c for every course",
        f"- **Measure of effectiveness:** unmet demand = **{m1['unmet_demand']:,.0f} students** "
        f"(coverage achieved {m1['achieved_coverage']:.2%}; courses short: {m1['courses_short']})",
        f"- Minimum sections to meet all demand: **{m1['total_sections']:,}** (modelled current: {m1['current_sections_modelled']:,})",
        f"- Courses needing more sections: {m1['courses_needing_more']} (+{m1['sections_added']}); "
        f"courses that can release sections: {m1['courses_can_release']} (−{m1['sections_released']})",
        f"- LP relaxation: {m1['lp_relaxation_sections']:,.1f} fractional sections → integrality gap {m1['integrality_gap_sections']:,.1f} sections",
        f"- Mean utilisation of allocated seats: {m1['mean_utilisation']:.1%}; "
        f"all integer: {m1['all_integer']}; demand fully met: {m1['demand_fully_met']}",
        f"- Solver: {m1['solver_status']}",
        "",
        "## 8. Model 2 – Limited Additional Capacity Allocation",
        "- **Decision variable:** y_ck ∈ {0,1} = open the k-th extra section for course c?",
        "- **Objective:** maximise Σ_c Σ_k w_c·a_ck·y_ck — weighted demand covered",
        f"- **Target:** budget ceiling Σ y_ck ≤ B = {m2['extra_sections_available']} sections",
        f"- **Measure of effectiveness:** unmet demand {m2['unmet_demand_before']:,.0f} → "
        f"**{m2['unmet_demand_after']:,.0f} students**",
        f"- Budget: {m2['extra_sections_available']} sections; used {m2['extra_sections_used']} across {m2['courses_receiving_sections']} courses",
        f"- Unmet demand: {m2['unmet_demand_before']:,.0f} → **{m2['unmet_demand_after']:,.0f}** students "
        f"({m2['unmet_reduction_pct']:.1f}% reduction); courses still short: {m2['courses_short_before']} → {m2['courses_short_after']}",
        f"- With a fairness cap of {s['parameters']['max_per_programme_variant']} extra sections per programme: unmet after = "
        f"{s['model2_fair']['unmet_demand_after']:,.0f}",
        f"- Repeat-weighted priority: unmet after = {s['model2_repeat_weighted']['unmet_demand_after']:,.0f}",
        "",
        "## 9. Sensitivity analysis",
        "### Section capacity", _md(sens_cap.set_index("capacity"), ".1f"),
        "### Additional sections (Model 2)",
        _md(sens_bud[["extra_sections", "extra_sections_used", "unmet_demand_after", "demand_covered",
                      "unmet_reduction_pct", "courses_short_after", "marginal_coverage_per_section"]].set_index("extra_sections"), ".1f"),
        "### First-time demand growth", _md(sens_gro.set_index("growth"), ".1f"),
        "",
        f"## 10. Scenario comparison ({config.PLANNING_YEAR}–{config.PLANNING_YEAR + s['parameters']['horizon'] - 1})",
        _md(comp.drop(columns=["notes"]).set_index("scenario"), ".1f"),
        "",
        "## Figures",
        *[f"![{p.stem}](../figures/{p.name})" for p in sorted(F.glob("*.png"))],
    ]
    (R / "results_and_validation_report.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--capacity", type=float, default=config.DEFAULT_SECTION_CAPACITY)
    ap.add_argument("--growth", type=float, default=config.DEFAULT_DEMAND_GROWTH)
    ap.add_argument("--extra", type=int, default=config.DEFAULT_EXTRA_SECTIONS)
    ap.add_argument("--horizon", type=int, default=config.DEFAULT_HORIZON)
    ap.add_argument("--max-per-programme", type=int, default=5)
    ap.add_argument("--reprocess", action="store_true")
    main(ap.parse_args())
