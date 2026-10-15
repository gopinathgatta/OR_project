"""Streamlit UI - University Curriculum Flow & Capacity Planning.

    streamlit run app.py
Workflow: upload dataset -> view statistics -> select optimisation model -> view results -> download.
"""
from __future__ import annotations

import io

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from curriculum_planner import config, descriptive as ds, mcdm, preprocessing as pp
from curriculum_planner import scenarios as scn, system_dynamics as sd, viz
from curriculum_planner.capacity import bottleneck_summary, bottleneck_table, modelled_current_sections
from curriculum_planner.optimization import (AHP_CRITERIA, lp_sensitivity_extra_sections,
                                             solve_extra_sections, solve_min_sections)

st.set_page_config(page_title="Curriculum Capacity Planner", page_icon="🎓", layout="wide")
alt.data_transformers.disable_max_rows()
try:
    @alt.theme.register("planner", enable=True)
    def _theme():
        return alt.theme.ThemeConfig(viz.altair_theme())
except AttributeError:  # altair < 5.5
    alt.themes.register("planner", viz.altair_theme)
    alt.themes.enable("planner")

STATUS_COLORS = alt.Scale(domain=["Bottleneck", "At risk", "OK"],
                          range=[viz.STATUS["critical"], viz.STATUS["warning"], viz.SERIES[0]])


def fmt(n, d=0):
    return f"{n:,.{d}f}"


def short(h):
    return f"C-{str(h)[:6]}"


def ahp_widget(labels, key):
    """Pairwise comparison sliders on Saaty's 1-9 scale -> AHP weights with a consistency check."""
    judgements = {}
    for i, a in enumerate(labels):
        for b in labels[i + 1:]:
            v = st.select_slider(f"{a}  vs  {b}", mcdm.SAATY_SCALE, "1", key=f"{key}_{a}_{b}",
                                 help="9 = left far more important, 1 = equal, 1/9 = right far more important")
            judgements[(a, b)] = mcdm.parse_saaty(v)
    r = mcdm.ahp(mcdm.pairwise_matrix(labels, judgements))
    c1, c2 = st.columns([2, 3])
    c1.dataframe(r.weights.to_frame().style.format("{:.3f}"), use_container_width=True)
    c2.markdown(f"λmax = **{r.lambda_max:.3f}** · CI = **{r.ci:.3f}** · CR = **{r.cr:.3f}**")
    if r.consistent:
        c2.success("Consistent judgements (CR ≤ 0.10)")
    else:
        c2.error("Inconsistent judgements (CR > 0.10): revise the comparisons")
    return r


NL = chr(10)   # newline for multi-line st.info() blocks


# --------------------------------------------------------------------------- data
@st.cache_resource(show_spinner="Processing dataset…")
def load_from_upload(key: str, _files):
    first = _files[0]
    name = first.name.lower()
    if name.endswith(".parquet") or name.endswith(".csv.gz"):
        return pp.load_processed(first)
    head = first.getvalue()[:400]
    if name.endswith(".csv") and b"student_id" in head:
        return pp.load_processed(io.BytesIO(first.getvalue()))
    return pp.clean(pp.load_raw(_files))


@st.cache_resource(show_spinner="Loading bundled dataset…")
def load_bundled():
    return pp.load_default()


@st.cache_resource(show_spinner="Calibrating System Dynamics model…")
def calibrate(key, _data):
    return {
        "params": sd.course_flow_parameters(_data.enrolments),
        "sfm": sd.StudentFlowModel.calibrate(_data.students),
        "flows": ds.progression_flows(_data.students),
        "matrix": ds.progression_matrix(_data.students),
        "yearly": ds.by_year(_data.enrolments),
        "val_students": sd.validate_student_flow(_data.students),
        "val_repeat": sd.validate_repeat_flow(_data.enrolments),
    }


# --------------------------------------------------------------------------- sidebar
st.sidebar.title("🎓 Capacity Planner")
st.sidebar.caption("System Dynamics + Integer Programming")
st.sidebar.subheader("Model parameters")
cap = st.sidebar.number_input("Section capacity (students per section)", 10, 300,
                              config.DEFAULT_SECTION_CAPACITY, 5,
                              help="An assumption of the model, not a variable in the dataset.")
growth = st.sidebar.slider("First-time demand growth per year", -0.10, 0.15, config.DEFAULT_DEMAND_GROWTH, 0.01,
                           format="%.2f")
thr = config.DEFAULT_BOTTLENECK_THRESHOLD      # fixed planning assumption
horizon = config.DEFAULT_HORIZON              # fixed simulation horizon (years)
st.sidebar.info(f"Capacity = **{cap}** students/section is a planning **parameter**. The dataset has no "
                "capacity data; current sections are modelled as ⌈2022 enrolment ÷ capacity⌉.")

# --------------------------------------------------------------------------- header
st.title("University Curriculum Flow & Capacity Planning")
st.caption("Finds course capacity bottlenecks and recommends section allocations. "
           "Scope: curriculum flow and capacity planning only. It does not predict which students drop out.")

tabs = st.tabs(["① Data", "② Statistics", "③ Student flow (SD)", "④ Demand & bottlenecks",
                "⑤ Model 1 · Integer", "⑥ Model 2 · Binary", "⑦ Scenarios", "⑧ Download"])

# ① data ---------------------------------------------------------------------------
with tabs[0]:
    st.subheader("Upload dataset")
    st.write("Upload the Zenodo archive **17239943.zip**, the yearly `dataset_YYYY_hash` ZIP/CSV files, "
             "or a pre-processed enrolment table (`.parquet` / `.csv.gz`). Leave empty to use the bundled data.")
    files = st.file_uploader("Dataset files", type=["zip", "csv", "gz", "parquet"], accept_multiple_files=True)
    if files:
        key = "|".join(f"{f.name}:{f.size}" for f in files)
        data = load_from_upload(key, files)
    else:
        key = "bundled"
        data = load_bundled()
    enr = data.enrolments
    h = ds.headline(enr)
    c = st.columns(5)
    c[0].metric("Enrolment records", fmt(h["records"]))
    c[1].metric("Students", fmt(h["students"]))
    c[2].metric("Courses", fmt(h["courses"]))
    c[3].metric("Programmes", fmt(h["programmes"]))
    c[4].metric("Academic years", ", ".join(map(str, h["academic_years"])))
    if data.report.validation:
        st.markdown("**Record counts against the published dataset description**")
        v = pd.DataFrame(data.report.validation).T
        v["match"] = v["match"].map(lambda m: "✅ match" if str(m) == "True" else "⚠️ differs")
        st.dataframe(v, use_container_width=True)
    with st.expander("Pre-processing log", expanded=False):
        st.dataframe(pd.DataFrame(data.report.steps), use_container_width=True, hide_index=True)
    with st.expander("Sample of the cleaned student-course table"):
        st.dataframe(enr.head(200), use_container_width=True, hide_index=True)

cal = calibrate(key, data)
params = cal["params"]
base_year = int(params.attrs.get("base_year", config.CALIBRATION_TO))
cfm = sd.CourseFlowModel(params, cap, growth, base_year=base_year)
proj = cfm.projected_demand()
bt = bottleneck_table(proj, cap, thr, min(thr - 0.1, config.DEFAULT_AT_RISK_THRESHOLD))
bsum = bottleneck_summary(bt)
s0 = modelled_current_sections(proj["enrolment"], cap)

# ② statistics ------------------------------------------------------------------------
with tabs[1]:
    st.subheader("Descriptive statistics")
    y = cal["yearly"]
    st.dataframe(y.style.format({"mean_grade": "{:.2f}", "pass_rate": "{:.1%}", "fail_rate": "{:.1%}",
                                 "not_evaluated_rate": "{:.1%}", "repeat_rate": "{:.1%}",
                                 "records": "{:,}", "students": "{:,}"}),
                 use_container_width=True, hide_index=True)
    col1, col2 = st.columns(2)
    long = y.melt("academic_year", ["pass_rate", "fail_rate", "not_evaluated_rate"], "outcome", "share")
    long["outcome"] = long["outcome"].map({"pass_rate": "Passed", "fail_rate": "Failed",
                                           "not_evaluated_rate": "Not evaluated"})
    col1.altair_chart(alt.Chart(long, title="Course outcomes by year").mark_bar(size=48).encode(
        x=alt.X("academic_year:O", title=None),
        y=alt.Y("share:Q", stack="normalize", axis=alt.Axis(format="%"), title="share of enrolments"),
        color=alt.Color("outcome:N", sort=["Passed", "Failed", "Not evaluated"], title=None),
        order=alt.Order("outcome:N", sort="descending"),
        tooltip=["academic_year", "outcome", alt.Tooltip("share:Q", format=".1%")]), use_container_width=True)
    cy = data.courses[data.courses["academic_year"] == base_year]
    col2.altair_chart(alt.Chart(cy, title=f"Distribution of course enrolment, {base_year}").mark_bar().encode(
        x=alt.X("enrolment:Q", bin=alt.Bin(maxbins=40), title="students per course"),
        y=alt.Y("count():Q", title="courses"), tooltip=[alt.Tooltip("count():Q", title="courses")]),
        use_container_width=True)

    st.markdown(f"**Highest-demand courses, {base_year}**")
    top = ds.top_courses(data.courses, base_year, 25)
    st.dataframe(top.style.format({"pass_rate": "{:.1%}", "fail_rate": "{:.1%}", "not_evaluated_rate": "{:.1%}",
                                   "repeat_rate": "{:.1%}", "mean_grade": "{:.2f}"}),
                 use_container_width=True, hide_index=True)
    st.divider()
    st.markdown("#### Generate statistics on demand")
    with st.form("on_demand_stats"):
        f1, f2, f3, f4 = st.columns([2, 2, 3, 1])
        years = sorted(enr["academic_year"].dropna().unique().tolist())
        q_years = f1.multiselect("Academic year(s)", years, years)
        progs = ["All programmes"] + sorted(enr["programme_id"].dropna().unique().tolist())
        q_prog = f2.selectbox("Programme", progs)
        q_stat = f3.selectbox("Statistic", list(ds.ON_DEMAND_STATS))
        q_top = f4.number_input("Top N", 5, 200, 20, 5)
        go = st.form_submit_button("Generate", type="primary")
    if go:
        sub = enr[enr["academic_year"].isin(q_years)]
        if q_prog != "All programmes":
            sub = sub[sub["programme_id"] == q_prog]
        if sub.empty:
            st.warning("No records match this selection.")
        else:
            out = ds.on_demand(sub, q_stat, int(q_top))
            st.caption(f"{q_stat}: {len(sub):,} records, {sub['student_id'].nunique():,} students, "
                       f"{sub['course_id'].nunique():,} courses")
            st.dataframe(out, use_container_width=True, hide_index=True)
            st.download_button("Download this table (CSV)", out.to_csv(index=False).encode(),
                               "statistics.csv", "text/csv")

# ③ student flow --------------------------------------------------------------------
with tabs[2]:
    st.subheader("System Dynamics student-flow model")
    st.markdown("Stocks: students in **Year 1, Year 2, Year 3, Year 4+** and **Final year** (approaching graduation). "
                "Flows: intake, progression, repetition, graduation, withdrawal. Rates are the observed "
                f"{config.CALIBRATION_FROM}→{config.CALIBRATION_TO} transition fractions.")
    c1, c2 = st.columns(2)
    boost = c2.slider("What-if: share of repeaters who progress instead", 0.0, 0.5, 0.0, 0.05)
    ig = c1.slider("Intake growth per year", -0.10, 0.15, growth, 0.01, format="%.2f", key="ig")
    sim = cal["sfm"].simulate(horizon, ig, boost)
    long = sim.melt("year", sd.STAGES, "stage", "students")
    st.altair_chart(alt.Chart(long, title="Projected student stocks").mark_line(point=True).encode(
        x=alt.X("year:O", title=None), y=alt.Y("students:Q"), color=alt.Color("stage:N", sort=sd.STAGES),
        tooltip=["year", "stage", alt.Tooltip("students:Q", format=",.0f")]), use_container_width=True)
    fl = sim.dropna().melt("year", ["Progressing", "Repeating", "Graduating", "Withdrawing"], "flow", "students")
    st.altair_chart(alt.Chart(fl, title="Annual flows").mark_bar().encode(
        x=alt.X("year:O", title=None), xOffset="flow:N", y="students:Q",
        color=alt.Color("flow:N", sort=["Progressing", "Repeating", "Graduating", "Withdrawing"]),
        tooltip=["year", "flow", alt.Tooltip("students:Q", format=",.0f")]), use_container_width=True)
    c1, c2 = st.columns(2)
    c1.markdown("**Observed transition matrix** (row = stage in 2021)")
    c1.dataframe(cal["matrix"].style.format("{:.1%}"), use_container_width=True)
    c2.markdown("**Validation (split-half): rates from half A predict half B**")
    c2.dataframe(cal["val_students"].style.format({"observed": "{:,.0f}", "predicted": "{:,.0f}",
                                                   "abs_pct_error": "{:.1f}%"}), use_container_width=True)

# ④ demand & bottlenecks ------------------------------------------------------------
with tabs[3]:
    st.subheader(f"Projected course demand {base_year + 1} and bottlenecks")
    st.latex(r"D_c = F_c(1+g) + \rho_c\,B_c \qquad \text{bottleneck if } D_c \ge \theta \cdot cap \cdot s_c")
    m = st.columns(5)
    m[0].metric("Projected demand (seats)", fmt(bsum["projected_demand"]))
    m[1].metric("Of which repeat demand", fmt(proj["demand_repeat"].sum()))
    m[2].metric("Bottleneck courses", bsum["bottleneck_courses"])
    m[3].metric("At-risk courses", bsum["at_risk_courses"])
    m[4].metric("Projected unmet demand", fmt(bsum["projected_unmet_demand"]))
    vr = cal["val_repeat"]
    st.caption(f"Repeat-demand flow validation (split-half): R² = {vr['course_specific']['R2']:.2f} "
               f"(single global rate: {vr['global_rate']['R2']:.2f}).")

    bt_plot = bt.assign(label=bt["course_id"].map(short), util=bt["utilisation"].clip(upper=1.5))
    st.altair_chart(alt.Chart(bt_plot, title="Demand vs modelled capacity (each dot is a course)").mark_circle(size=40, opacity=0.7).encode(
        x=alt.X("current_capacity:Q", title="modelled capacity (seats)", scale=alt.Scale(type="sqrt")),
        y=alt.Y("demand:Q", title="projected demand", scale=alt.Scale(type="sqrt")),
        color=alt.Color("status:N", scale=STATUS_COLORS, title="Status"),
        tooltip=["label", "programme_id", alt.Tooltip("demand:Q", format=",.0f"), "current_capacity",
                 alt.Tooltip("utilisation:Q", format=".0%"), alt.Tooltip("unmet_demand:Q", format=",.0f")]),
        use_container_width=True)

    status = st.multiselect("Show status", ["Bottleneck", "At risk", "OK"], ["Bottleneck", "At risk"])
    view = bt[bt["status"].isin(status)]
    st.dataframe(view[["course_id", "programme_id", "status", "enrolment", "demand", "demand_first_time",
                       "demand_repeat", "current_sections", "current_capacity", "utilisation", "unmet_demand",
                       "extra_sections_needed", "pass_rate", "retake_rate"]].style.format({
        "demand": "{:,.1f}", "demand_first_time": "{:,.1f}", "demand_repeat": "{:,.1f}",
        "utilisation": "{:.0%}", "unmet_demand": "{:,.1f}", "pass_rate": "{:.0%}", "retake_rate": "{:.0%}"}),
        use_container_width=True, hide_index=True, height=380)

# ⑤ Model 1 – Integer Programming ----------------------------------------------
with tabs[4]:
    st.subheader("Model 1 · Integer Programming — Minimum Section Allocation")
    st.caption("**The question:** *what is the ideal?* — there is no budget limit and every student must get a seat. The model finds the cheapest way to achieve that.")
    st.caption("Integer Programming: the number of sections x_c of each course is a whole number ≥ 0.")
    st.latex(r"\min \sum_c x_c \quad \text{s.t.}\; cap\cdot x_c \ge (1+\beta)D_c,\; x_c\ge 1,\; x_c\in\mathbb{Z}_+")
    d1, d2, d3 = st.columns(3)
    with d1.container(border=True):
        st.markdown("**① DECISION VARIABLE**")
        st.caption("what we choose")
        st.markdown("How many sections to open for **each course**.")
        st.code("x_c  =  0, 1, 2, 3 …", language=None)
        st.caption("A whole number — you cannot open half a section.")
    with d2.container(border=True):
        st.markdown("**② OBJECTIVE**")
        st.caption("what we optimise")
        st.markdown("Open as **few** sections as possible.")
        st.code("minimise   Σ x_c", language=None)
        st.caption("Fewer sections = less staff, rooms and timetable.")
    with d3.container(border=True):
        st.markdown("**③ TARGET**")
        st.caption("the rule we must obey")
        st.markdown("**Every student gets a seat** in every course.")
        st.code("cap · x_c  ≥  D_c", language=None)
        st.caption("Seats provided must cover the projected demand of each course.")
    with st.expander("Advanced: demand safety buffer β"):
        buffer = st.slider("Demand safety buffer β — plan for this much more demand than projected",
                           0.0, 0.25, 0.0, 0.01, key="m1_beta")
    r1 = solve_min_sections(proj[["course_id", "programme_id", "demand"]], cap, buffer)
    res = r1.allocation.assign(current_sections=s0, change=r1.allocation["sections"] - s0)
    k = st.columns(5)
    k[0].metric("Minimum total sections", fmt(r1.summary["total_sections"]),
                f"{r1.summary['total_sections'] - s0.sum():+,} vs modelled current")
    k[1].metric("Unmet demand", fmt(r1.summary["unmet_demand"]),
                f"coverage {r1.summary['achieved_coverage']:.2%}", delta_color="off")
    k[2].metric("LP relaxation", fmt(r1.summary["lp_relaxation_sections"], 1))
    k[3].metric("Courses needing more", int((res["change"] > 0).sum()))
    k[4].metric("Seat utilisation", f"{r1.summary['mean_utilisation']:.0%}")
    st.caption(f"Solver: {r1.status}. All integer: {r1.summary['all_integer']}; "
               f"demand fully met: {r1.summary['demand_fully_met']}.")
    st.session_state["opt_m1"] = res
    chg = res[res["change"] != 0].sort_values("change")
    st.dataframe(chg[["course_id", "programme_id", "demand", "current_sections", "sections", "change",
                      "capacity", "utilisation"]].style.format({"demand": "{:,.1f}", "utilisation": "{:.0%}"}),
                 use_container_width=True, hide_index=True, height=380)


# ⑥ Model 2 – Binary Programming ------------------------------------------------
with tabs[5]:
    st.subheader("Model 2 · Binary Programming — Limited Additional Capacity")
    st.caption("**The question:** *what can we afford?* — the budget of extra sections is fixed, so the model decides where they do the most good.")
    st.caption("Binary (0-1) Programming: y_ck = 1 if the k-th extra section is opened for course c, "
               "otherwise 0. Each candidate section is a knapsack item and the budget B is the knapsack.")
    st.latex(r"\max \sum_{c,k} w_c\,a_{ck}\,y_{ck}\;\; \text{s.t.} \sum y_{ck}\le B,\; y_{ck}\le y_{c,k-1},"
             r"\; \sum_{c\in p} y_{ck}\le M_p,\; y_{ck}\in\{0,1\}")
    d1, d2, d3 = st.columns(3)
    with d1.container(border=True):
        st.markdown("**① DECISION VARIABLE**")
        st.caption("what we choose")
        st.markdown("For each possible extra section: **open it, or not?**")
        st.code("y = 1   open it" + NL + "y = 0   do not", language=None)
        st.caption("Yes/no only — this is the binary (0-1) model.")
    with d2.container(border=True):
        st.markdown("**② OBJECTIVE**")
        st.caption("what we optimise")
        st.markdown("Seat as **many** students as possible with the sections we have.")
        st.code("maximise   Σ w · (students seated)", language=None)
        st.caption("w = course priority weight (set under Advanced).")
    with d3.container(border=True):
        st.markdown("**③ TARGET**")
        st.caption("the rule we must obey — set it here")
        B = st.number_input("Extra sections available (budget B)", 0, 2000,
                            config.DEFAULT_EXTRA_SECTIONS, 5, key="m2_B")
        st.code(f"Σ y  ≤  {B}", language=None)
        st.caption(f"At most {B} extra sections may be opened in total.")
    with st.expander("Advanced: fairness cap and priority weights"):
        a1, a2 = st.columns(2)
        M = a1.number_input("Max extra sections per programme (0 = no limit)", 0, 500, 0, key="m2_M")
        wmode = a2.selectbox("Priority weights", ["uniform", "repeat_weighted", "early_stage", "ahp"],
                             key="m2_w",
                             help="repeat_weighted: favour courses whose demand is mostly repeaters; "
                                  "early_stage: favour first-year courses; ahp: weights from your AHP "
                                  "pairwise comparisons")
    cw = None
    if wmode == "ahp":
        with st.expander("AHP: weight the course-priority criteria", expanded=True):
            st.caption("Course weight w_c = 1 + Σ W_k · score_k(c), where score_k(c) ∈ [0, 1] is the "
                       "course's repeat-student share, first-year flag, and 1 − pass rate.")
            cw = ahp_widget(AHP_CRITERIA, "m2").weights.values
    r2 = solve_extra_sections(proj, s0, B, cap, max_per_programme=M or None, weight_mode=wmode,
                              criteria_weights=cw)
    sm = r2.summary
    k = st.columns(5)
    k[0].metric("Unmet demand before", fmt(sm["unmet_demand_before"]))
    k[1].metric("Unmet demand after", fmt(sm["unmet_demand_after"]), f"-{sm['unmet_reduction_pct']:.1f}%",
                delta_color="inverse")
    k[2].metric("Sections used", f"{sm['extra_sections_used']} / {B}")
    k[3].metric("Courses still short", f"{sm['courses_short_after']} (was {sm['courses_short_before']})")
    k[4].metric("Sections to clear all", sm["sections_needed_to_clear_all"])
    st.caption(f"Solver: {r2.status}")
    res = r2.allocation
    st.session_state["opt_m2"] = res
    alloc = res[res["unmet_before"] > 0].sort_values("unmet_before", ascending=False)
    top = alloc.head(25).assign(label=lambda d: d["course_id"].map(short))
    long = top.melt(["label"], ["covered_demand", "unmet_after"], "part", "students")
    long["part"] = long["part"].map({"covered_demand": "Covered by extra sections", "unmet_after": "Still unmet"})
    st.altair_chart(alt.Chart(long, title="Unmet demand per bottleneck course: covered vs remaining").mark_bar().encode(
        y=alt.Y("label:N", sort=top["label"].tolist(), title=None), x=alt.X("students:Q", stack=True),
        color=alt.Color("part:N", scale=alt.Scale(range=[viz.SERIES[0], viz.SERIES[1]]), title=None),
        tooltip=["label", "part", alt.Tooltip("students:Q", format=",.1f")]), use_container_width=True)
    st.dataframe(alloc[["course_id", "programme_id", "demand", "current_sections", "unmet_before",
                        "extra_sections", "covered_demand", "unmet_after"]].style.format(
        {"demand": "{:,.1f}", "unmet_before": "{:,.1f}", "covered_demand": "{:,.1f}", "unmet_after": "{:,.1f}"}),
        use_container_width=True, hide_index=True, height=380)

    with st.expander("LP sensitivity report (shadow prices, reduced costs, budget ranging)"):
        sr = lp_sensitivity_extra_sections(proj, s0, B, cap, max_per_programme=M or None,
                                           weight_mode=wmode, criteria_weights=cw)
        if sr["constraints"].empty:
            st.info("No unmet demand, so there is nothing to analyse.")
        else:
            st.markdown(
                f"The LP relaxation (0 ≤ y ≤ 1) seats **{sr['lp_objective']:,.1f}** weighted students "
                f"against **{r2.objective:,.1f}** for the integer model. **Shadow price of the budget = "
                f"{sr['budget_shadow_price']:.2f}**, the extra students seated by one more section. "
                f"Section {B} is worth {sr['value_of_last_section']:.2f} students, and section {B + 1} "
                f"would be worth {sr['value_of_next_section']:.2f}. The value falls as B grows "
                "(diminishing returns).")
            rc = sr["budget_ranging"].dropna()
            st.altair_chart(alt.Chart(rc, title="Budget ranging: value of each additional section").mark_bar().encode(
                x=alt.X("budget_B:O", title="section number (budget B)"),
                y=alt.Y("value_of_this_section:Q", title="students seated by this section"),
                color=alt.condition(alt.datum.budget_B <= B, alt.value(viz.SERIES[0]), alt.value(viz.BASELINE_GREY)),
                tooltip=["budget_B", alt.Tooltip("value_of_this_section:Q", format=".2f"),
                         alt.Tooltip("lp_objective:Q", format=",.1f")]), use_container_width=True)
            cons = sr["constraints"]
            st.markdown("**Constraints** (binding constraints have a positive shadow price)")
            st.dataframe(cons[~cons["constraint"].str.startswith("Order")].style.format(
                {"final_value": "{:,.2f}", "rhs": "{:,.0f}", "shadow_price": "{:.3f}"}),
                use_container_width=True, hide_index=True)
            st.markdown("**Variable cells** (reduced cost: how much a section's value must rise before "
                        "it enters the plan; 0 for sections in the plan)")
            st.dataframe(sr["variables"].assign(label=lambda d: d["course_id"].map(short))
                         .sort_values("objective_coeff", ascending=False).style.format(
                {"students_covered": "{:,.1f}", "objective_coeff": "{:,.2f}", "final_value": "{:.2f}",
                 "reduced_cost": "{:.3f}"}), use_container_width=True, hide_index=True, height=300)


# ⑦ scenarios ----------------------------------------------------------------------
with tabs[6]:
    st.subheader("Scenario comparison and sensitivity")
    st.write("Each year the SD model projects demand, a policy picks the sections, and any shortfall "
             "returns as next year's backlog (the feedback loop).")
    B_s = st.number_input("Additional-section budget used in scenarios", 0, 2000, config.DEFAULT_EXTRA_SECTIONS, 5,
                          key="bs")

    @st.cache_data(show_spinner="Running scenarios…")
    def run_scen(key, cap, B, growth, horizon):
        return scn.compare_scenarios(params, scn.default_scenarios(cap, B, growth, horizon), base_year)
    comp, traj = run_scen(key, cap, B_s, growth, horizon)
    st.dataframe(comp.drop(columns=["capacity"]).style.format({
        "growth": "{:+.0%}", "pass_rate_shift": "{:+.0%}", "first_year_demand": "{:,.0f}",
        "first_year_unserved": "{:,.0f}", "cumulative_unserved": "{:,.0f}", "mean_sections_per_year": "{:,.0f}",
        "mean_utilisation": "{:.1%}", "final_backlog": "{:,.0f}", "final_year_demand": "{:,.0f}"}),
        use_container_width=True, hide_index=True)
    names = comp["scenario"].tolist()
    shown = st.multiselect("Scenarios to plot", names, names[:5])
    t = traj[traj["scenario"].isin(shown)]
    sc_scale = alt.Scale(domain=names, range=[viz.BASELINE_GREY] + viz.SERIES[: len(names) - 1])
    c1, c2 = st.columns(2)
    c1.altair_chart(alt.Chart(t, title="Unserved demand").mark_line(point=True).encode(
        x=alt.X("year:O", title=None), y=alt.Y("unserved:Q", title="students not seated"),
        color=alt.Color("scenario:N", scale=sc_scale, legend=alt.Legend(orient="bottom", columns=2)),
        tooltip=["scenario", "year", alt.Tooltip("unserved:Q", format=",.0f")]), use_container_width=True)
    c2.altair_chart(alt.Chart(t, title="Backlog stock").mark_line(point=True).encode(
        x=alt.X("year:O", title=None), y=alt.Y("backlog_end:Q", title="students still needing a course",
                                               scale=alt.Scale(zero=False)),
        color=alt.Color("scenario:N", scale=sc_scale, legend=alt.Legend(orient="bottom", columns=2)),
        tooltip=["scenario", "year", alt.Tooltip("backlog_end:Q", format=",.0f")]), use_container_width=True)

    st.markdown("#### Sensitivity analysis")
    s1, s2 = st.columns(2)

    @st.cache_data(show_spinner=False)
    def sens(key, cap, growth):
        return (scn.sensitivity_capacity(params, growth=growth, base_year=base_year),
                scn.sensitivity_budget(params, capacity=cap, growth=growth, base_year=base_year),
                scn.sensitivity_growth(params, capacity=cap, base_year=base_year))
    sc_cap, sc_bud, sc_gro = sens(key, cap, growth)
    s1.altair_chart(alt.Chart(sc_cap, title="Bottleneck courses vs section capacity").mark_bar(size=36).encode(
        x=alt.X("capacity:O", title="students per section"), y=alt.Y("bottleneck_courses:Q", title="courses"),
        tooltip=["capacity", "bottleneck_courses", "model1_sections", "unmet_demand_status_quo"]),
        use_container_width=True)
    s2.altair_chart(alt.Chart(sc_bud, title="Unmet demand vs additional sections (Model 2)").mark_line(point=True).encode(
        x=alt.X("extra_sections:Q", title="additional sections B"), y=alt.Y("unmet_demand_after:Q", title="students"),
        tooltip=["extra_sections", alt.Tooltip("unmet_demand_after:Q", format=",.0f"),
                 alt.Tooltip("unmet_reduction_pct:Q", format=".1f")]), use_container_width=True)
    st.session_state["scenario_tables"] = {"scenario_comparison": comp, "scenario_trajectories": traj,
                                           "sensitivity_capacity": sc_cap, "sensitivity_budget": sc_bud,
                                           "sensitivity_growth": sc_gro}

# ⑧ download -----------------------------------------------------------------------
with tabs[7]:
    st.subheader("Download results")
    tables = {"bottleneck_table": bt, "projected_demand": proj, "sd_course_parameters": params,
              "progression_flows": cal["flows"].reset_index(), "descriptive_by_year": cal["yearly"]}
    for _k, _name in (("opt_m1", "model1_allocation"), ("opt_m2", "model2_allocation")):
        if _k in st.session_state:
            tables[_name] = st.session_state[_k]
    tables.update(st.session_state.get("scenario_tables", {}))
    xbuf = io.BytesIO()
    with pd.ExcelWriter(xbuf) as xw:
        pd.DataFrame({"parameter": ["section_capacity", "first_time_growth", "bottleneck_threshold", "horizon",
                                    "note"],
                      "value": [cap, growth, thr, horizon,
                                "capacity is a model parameter, not a dataset variable"]}).to_excel(
            xw, sheet_name="parameters", index=False)
        for n, df in tables.items():
            df.head(100_000).to_excel(xw, sheet_name=n[:31], index=False)
    st.download_button("⬇️ All results (Excel workbook)", xbuf.getvalue(), "capacity_planning_results.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")
    cols = st.columns(3)
    for i, (n, df) in enumerate(tables.items()):
        cols[i % 3].download_button(f"{n}.csv", df.to_csv(index=False).encode(), f"{n}.csv", "text/csv",
                                    key=f"dl_{n}")

    @st.cache_data(show_spinner="Compressing cleaned dataset…")
    def cleaned_parquet(key):
        b = io.BytesIO()
        enr.to_parquet(b, index=False)
        return b.getvalue()
    if st.toggle("Prepare cleaned student-course dataset for download"):
        st.download_button("⬇️ Cleaned student-course dataset (.parquet)", cleaned_parquet(key),
                           "student_course_enrolments.parquet", "application/octet-stream")
