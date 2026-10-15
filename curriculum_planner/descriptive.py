"""Exploratory / descriptive statistics: enrolment, outcomes, demand and progression."""
from __future__ import annotations

import pandas as pd

from .system_dynamics import STAGES, student_transitions


def headline(enr: pd.DataFrame) -> dict:
    return {
        "records": len(enr),
        "students": enr["student_id"].nunique(),
        "courses": enr["course_id"].nunique(),
        "programmes": enr["programme_id"].nunique(),
        "academic_years": sorted(int(y) for y in enr["academic_year"].unique()),
        "pass_rate": float(enr["passed"].mean()),
    }


def by_year(enr: pd.DataFrame) -> pd.DataFrame:
    g = enr.groupby("academic_year")
    out = g.agg(records=("student_id", "size"), students=("student_id", "nunique"),
                courses=("course_id", "nunique"), programmes=("programme_id", "nunique"),
                mean_grade=("grade", "mean")).reset_index()
    oc = pd.crosstab(enr["academic_year"], enr["outcome"], normalize="index").reset_index()
    out = out.merge(oc, on="academic_year")
    rep = enr[enr["repeat_observable"]].groupby("academic_year")["repeat_enrolment"].mean().rename("repeat_rate")
    return out.merge(rep, on="academic_year", how="left").rename(
        columns={"pass": "pass_rate", "fail": "fail_rate", "not_evaluated": "not_evaluated_rate"})


def course_demand_trend(courses: pd.DataFrame) -> pd.DataFrame:
    """Enrolment per course for each academic year (wide) with change 2021->2022."""
    w = courses.pivot_table(index="course_id", columns="academic_year", values="enrolment", fill_value=0)
    w.columns = [f"enrolment_{c}" for c in w.columns]
    if {"enrolment_2021", "enrolment_2022"} <= set(w.columns):
        w["change_2021_2022"] = w["enrolment_2022"] - w["enrolment_2021"]
    prog = courses.groupby("course_id")["programme_id"].first()
    return w.join(prog).reset_index()


def top_courses(courses: pd.DataFrame, year: int, n=20, by="enrolment") -> pd.DataFrame:
    c = courses[courses["academic_year"] == year]
    cols = ["course_id", "programme_id", "enrolment", "pass_rate", "fail_rate",
            "not_evaluated_rate", "repeat_rate", "repeat_enrolments", "mean_grade"]
    return c.sort_values(by, ascending=False)[cols].head(n).reset_index(drop=True)


def programme_summary(enr: pd.DataFrame, year: int) -> pd.DataFrame:
    e = enr[enr["academic_year"] == year]
    g = e.groupby("programme_id")
    out = g.agg(students=("student_id", "nunique"), courses=("course_id", "nunique"),
                enrolments=("student_id", "size"), pass_rate=("passed", "mean"),
                repeat_enrolments=("repeat_enrolment", "sum"),
                programme_length=("programme_length", "first")).reset_index()
    out["repeat_share"] = out["repeat_enrolments"] / out["enrolments"]
    return out.sort_values("enrolments", ascending=False).reset_index(drop=True)


def progression_matrix(students: pd.DataFrame, normalize=True) -> pd.DataFrame:
    tr, _ = student_transitions(students)
    m = pd.crosstab(tr["from_stage"], tr["to_stage"], normalize="index" if normalize else False)
    cols = [c for c in STAGES + ["Graduated", "Withdrawn"] if c in m.columns]
    return m.reindex(index=STAGES, columns=cols, fill_value=0)


def progression_flows(students: pd.DataFrame) -> pd.DataFrame:
    tr, intake = student_transitions(students)
    f = pd.crosstab(tr["from_stage"], tr["flow"]).reindex(STAGES, fill_value=0)
    f["Total"] = f.sum(axis=1)
    for c in ["Progress", "Repeat", "Graduated", "Withdrawn"]:
        if c in f:
            f[f"{c} %"] = f[c] / f["Total"] * 100
    intake_counts = intake.groupby("stage")["new_entrant"].agg(new_entrants="sum", total="size")
    f = f.join(intake_counts.rename(columns={"total": "Intake (new + re-entry)"}), how="left")
    return f.fillna(0)


def repeat_burden(enr: pd.DataFrame, year: int) -> dict:
    e = enr[(enr["academic_year"] == year) & enr["repeat_observable"]]
    st = e.groupby("student_id")["repeat_enrolment"].sum()
    return {"repeat_enrolments": int(e["repeat_enrolment"].sum()),
            "share_of_enrolments": float(e["repeat_enrolment"].mean()) if len(e) else float("nan"),
            "students_repeating_any_course": int((st > 0).sum()),
            "share_of_students": float((st > 0).mean()) if len(st) else float("nan")}


# ------------------------------------------------------------------ on-demand statistics (UI)
def _outcome_summary(e, n):
    return by_year(e).round(4)


def _course_ranking(e, n):
    g = e.groupby(["academic_year", "course_id"])
    t = g.agg(programme_id=("programme_id", "first"), enrolment=("student_id", "size"),
              pass_rate=("passed", "mean"), repeat_enrolments=("repeat_enrolment", "sum"),
              mean_grade=("grade", "mean")).reset_index()
    return (t.sort_values(["academic_year", "enrolment"], ascending=[True, False])
             .groupby("academic_year").head(n).round(3))


def _grade_distribution(e, n):
    bins = [0, 2, 4, 5, 6, 7, 8, 9, 10.01]
    labels = ["0-2", "2-4", "4-5", "5-6", "6-7", "7-8", "8-9", "9-10"]
    g = pd.cut(e["grade"], bins, right=False, labels=labels).cat.add_categories("not evaluated")
    g = g.fillna("not evaluated")
    t = pd.crosstab(g, e["academic_year"], normalize="columns").round(4)
    t.columns = [f"share {c}" for c in t.columns]
    return t.reset_index(names="grade band")


def _repeat_analysis(e, n):
    e = e[e["repeat_observable"]]
    if e.empty:
        return pd.DataFrame({"note": ["Repeat enrolments are observable only for 2022 (the year after 2021)."]})
    t = e.groupby("course_id").agg(programme_id=("programme_id", "first"), enrolment=("student_id", "size"),
                                   repeat_enrolments=("repeat_enrolment", "sum"))
    t["repeat_share"] = (t["repeat_enrolments"] / t["enrolment"]).round(3)
    return t.sort_values("repeat_enrolments", ascending=False).head(n).reset_index()


def _programme_comparison(e, n):
    t = e.groupby("programme_id").agg(students=("student_id", "nunique"), courses=("course_id", "nunique"),
                                      enrolments=("student_id", "size"), pass_rate=("passed", "mean"),
                                      mean_grade=("grade", "mean"), repeat_enrolments=("repeat_enrolment", "sum"))
    return t.sort_values("enrolments", ascending=False).head(n).round(3).reset_index()


def _descriptive_summary(e, n):
    cols = ["grade", "credits_enrolled", "credits_passed", "highest_year_level"]
    return e[[c for c in cols if c in e]].describe().T.round(2).reset_index(names="variable")


ON_DEMAND_STATS = {
    "Outcome summary by year": _outcome_summary,
    "Course demand ranking (top N per year)": _course_ranking,
    "Grade distribution": _grade_distribution,
    "Repeat-enrolment analysis (top N courses)": _repeat_analysis,
    "Programme comparison (top N)": _programme_comparison,
    "Descriptive statistics of numeric variables": _descriptive_summary,
}


def on_demand(enr: pd.DataFrame, stat: str, n: int = 20) -> pd.DataFrame:
    """Statistic chosen in the UI, computed on the user's filtered selection."""
    return ON_DEMAND_STATS[stat](enr, n)
