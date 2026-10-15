"""System Dynamics models of student flow (annual time step, Euler integration).

Two coupled views of the same stock-and-flow structure:

StudentFlowModel  - programme level. Stocks are students by curriculum stage
                    (Year 1, Year 2, Year 3, Year 4+, Final year = approaching
                    graduation) plus the cumulative Graduated and Withdrawn sinks.
                    Flows: intake, progression, repetition (staying in a stage),
                    graduation and withdrawal. Rates are the observed 2021->2022
                    transition fractions.

CourseFlowModel   - course level, used for capacity planning. For course c:
                        D_c(t)  = F_c (1+g)^t + rho_c * B_c(t)          demand
                        S_c(t)  = min(D_c(t), cap * x_c(t))              served
                        U_c(t)  = D_c(t) - S_c(t)                        unserved
                        B_c(t+1)= (1 - pi_c) S_c(t) + u * U_c(t)         backlog
                    F = first-time enrolments, rho = retake propensity of
                    students who have not yet passed, pi = pass rate,
                    x = sections chosen by the policy (e.g. the IP models).
                    The backlog stock closes the feedback loop: any shortfall
                    in sections adds demand in the following year.

Withdrawal is an *aggregate observed flow rate*; the project does not predict
which individual students drop out.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

from . import config

STAGES = ["Year 1", "Year 2", "Year 3", "Year 4+", "Final year"]
EXITS = ["Graduated", "Withdrawn"]
STAGE_ORDER = {s: i for i, s in enumerate(STAGES)}


def assign_stage(highest_level: pd.Series, programme_length: pd.Series) -> pd.Series:
    lvl = highest_level.fillna(1).clip(lower=1)
    stage = np.where(lvl >= programme_length.fillna(lvl), "Final year",
                     np.select([lvl == 1, lvl == 2, lvl == 3], STAGES[:3], default="Year 4+"))
    return pd.Series(stage, index=highest_level.index)


def student_transitions(students: pd.DataFrame, t0=config.CALIBRATION_FROM, t1=config.CALIBRATION_TO):
    """Return (per-student transitions t0->t1, intake rows at t1)."""
    st = students.copy()
    st["stage"] = assign_stage(st["highest_year_level"], st["programme_length"])
    a = st[st["academic_year"] == t0].set_index("student_id")
    b = st[st["academic_year"] == t1].set_index("student_id")
    tr = a[["stage", "credits_pending_programme", "programme_id"]].rename(columns={"stage": "from_stage"})
    tr["to_stage"] = b["stage"].reindex(tr.index)
    left = tr["to_stage"].isna()
    tr.loc[left, "to_stage"] = np.where(tr.loc[left, "credits_pending_programme"] <= 0, "Graduated", "Withdrawn")

    def flow(r):
        if r.to_stage in EXITS:
            return r.to_stage
        return "Progress" if STAGE_ORDER[r.to_stage] > STAGE_ORDER[r.from_stage] else "Repeat"
    tr["flow"] = [flow(r) for r in tr.itertuples()]
    intake = b.loc[~b.index.isin(a.index), ["stage", "new_entrant"]]
    return tr.reset_index(), intake.reset_index()


@dataclass
class StudentFlowModel:
    P: pd.DataFrame           # rows: STAGES, cols: STAGES + EXITS (row-stochastic)
    intake: pd.Series         # yearly inflow by stage (new entrants + re-entrants)
    base_stocks: pd.Series    # stocks in the base year (t1)
    base_year: int = config.CALIBRATION_TO

    @classmethod
    def calibrate(cls, students: pd.DataFrame, t0=config.CALIBRATION_FROM, t1=config.CALIBRATION_TO):
        tr, intake = student_transitions(students, t0, t1)
        P = pd.crosstab(tr["from_stage"], tr["to_stage"], normalize="index")
        P = P.reindex(index=STAGES, columns=STAGES + EXITS, fill_value=0.0)
        inflow = intake["stage"].value_counts().reindex(STAGES, fill_value=0).astype(float)
        st = students[students["academic_year"] == t1]
        stocks = assign_stage(st["highest_year_level"], st["programme_length"]).value_counts()
        return cls(P, inflow, stocks.reindex(STAGES, fill_value=0).astype(float), t1)

    def step(self, stocks: pd.Series, intake: pd.Series):
        moves = self.P.mul(stocks, axis=0)                       # from x to
        new = moves[STAGES].sum(axis=0) + intake
        diag = pd.Series(np.diag(moves[STAGES].values), index=STAGES)
        upper = np.triu(moves[STAGES].values, k=1).sum()
        lower = np.tril(moves[STAGES].values, k=-1).sum()
        flows = {
            "Intake": intake.sum(),
            "Progressing": upper,
            "Repeating": diag.sum() + lower,
            "Graduating": moves["Graduated"].sum(),
            "Withdrawing": moves["Withdrawn"].sum(),
        }
        return new, flows

    def simulate(self, horizon=config.DEFAULT_HORIZON, intake_growth=0.0,
                 progression_boost=0.0) -> pd.DataFrame:
        """Simulate stocks forward. `progression_boost` moves that share of the repeat
        flow into progression (a what-if for academic support policies)."""
        model = self if progression_boost == 0 else self._with_boost(progression_boost)
        stocks, rows = self.base_stocks.copy(), []
        rows.append({"year": self.base_year, **stocks.to_dict(), "Enrolled": stocks.sum()})
        for k in range(1, horizon + 1):
            stocks, flows = model.step(stocks, self.intake * (1 + intake_growth) ** k)
            rows.append({"year": self.base_year + k, **stocks.to_dict(),
                         "Enrolled": stocks.sum(), **flows})
        return pd.DataFrame(rows)

    def _with_boost(self, b):
        P = self.P.copy()
        for i, s in enumerate(STAGES[:-1]):
            move = P.loc[s, s] * b
            P.loc[s, s] -= move
            P.loc[s, STAGES[i + 1]] += move
        return StudentFlowModel(P, self.intake, self.base_stocks, self.base_year)


def validate_student_flow(students: pd.DataFrame, seed=42) -> pd.DataFrame:
    """Split-half check: calibrate rates on half A, predict half B's t1 stocks and exits."""
    ids = students["student_id"].unique()
    rng = np.random.default_rng(seed)
    a_ids = set(rng.choice(ids, size=len(ids) // 2, replace=False))
    A = students[students["student_id"].isin(a_ids)]
    B = students[~students["student_id"].isin(a_ids)]
    m = StudentFlowModel.calibrate(A)
    trB, intakeB = student_transitions(B)
    s0 = trB["from_stage"].value_counts().reindex(STAGES, fill_value=0).astype(float)
    inflow = intakeB["stage"].value_counts().reindex(STAGES, fill_value=0).astype(float)
    pred, flows = m.step(s0, inflow)
    actual_to = trB["to_stage"].value_counts()
    actual = pd.concat([actual_to.reindex(STAGES, fill_value=0) + inflow,
                        actual_to.reindex(EXITS, fill_value=0)])
    predicted = pd.concat([pred, pd.Series({"Graduated": flows["Graduating"], "Withdrawn": flows["Withdrawing"]})])
    out = pd.DataFrame({"observed": actual, "predicted": predicted.round(1)})
    out["abs_pct_error"] = (out["predicted"] - out["observed"]).abs() / out["observed"] * 100
    return out


# --------------------------------------------------------------------------- course flow
def _shrink(num, den, prior, m=config.SHRINKAGE_STRENGTH):
    return (num + m * prior) / (den + m)


def course_flow_parameters(enrolments: pd.DataFrame, base_year=config.CALIBRATION_TO,
                           prev_year=config.CALIBRATION_FROM) -> pd.DataFrame:
    """Estimate per-course SD parameters from the linked student-course table."""
    cur = enrolments[enrolments["academic_year"] == base_year]
    prev = enrolments[enrolments["academic_year"] == prev_year]
    g = cur.groupby("course_id")
    p = g.agg(programme_id=("programme_id", "first"),
              enrolment=("student_id", "size"),
              passes=("passed", "sum"),
              repeat_enrolments=("repeat_enrolment", "sum"),
              median_year_level=("lowest_year_level", "median")).astype({"passes": float})
    p["not_passed"] = p["enrolment"] - p["passes"]
    p["first_time"] = p["enrolment"] - p["repeat_enrolments"]
    prev_np = (~prev["passed"]).groupby(prev["course_id"]).sum()
    p["prev_not_passed"] = prev_np.reindex(p.index).fillna(0)

    rho_bar = p["repeat_enrolments"].sum() / max(p["prev_not_passed"].sum(), 1)
    pi_bar = p["passes"].sum() / p["enrolment"].sum()
    # hierarchical empirical Bayes: course -> programme -> university
    prog = p.groupby("programme_id")[["repeat_enrolments", "prev_not_passed"]].sum()
    prog_rho = _shrink(prog["repeat_enrolments"], prog["prev_not_passed"], rho_bar)
    p["retake_rate"] = _shrink(p["repeat_enrolments"], p["prev_not_passed"],
                               p["programme_id"].map(prog_rho)).clip(0, 1)
    p["pass_rate"] = _shrink(p["passes"], p["enrolment"], pi_bar).clip(0, 1)
    p["pass_rate_raw"] = p["passes"] / p["enrolment"]
    p["repeat_share"] = p["repeat_enrolments"] / p["enrolment"]
    p = p.reset_index()
    p.attrs.update(global_retake_rate=rho_bar, global_pass_rate=pi_bar, base_year=base_year)
    return p


SectionPolicy = Callable[[int, np.ndarray], np.ndarray]   # (year_index, demand) -> sections


@dataclass
class CourseFlowModel:
    params: pd.DataFrame
    capacity: float = config.DEFAULT_SECTION_CAPACITY
    growth: float = config.DEFAULT_DEMAND_GROWTH
    unserved_return: float = config.DEFAULT_UNSERVED_RETURN
    pass_rate_shift: float = 0.0          # what-if: +0.05 = pass rates improve 5 points
    base_year: int = config.CALIBRATION_TO

    def _pi(self):
        return np.clip(self.params["pass_rate"].to_numpy() + self.pass_rate_shift, 0, 1)

    def demand(self, backlog: np.ndarray, k: int) -> np.ndarray:
        p = self.params
        return p["first_time"].to_numpy() * (1 + self.growth) ** k + p["retake_rate"].to_numpy() * backlog

    def projected_demand(self) -> pd.DataFrame:
        """Next-year demand split into first-time and repeat components."""
        p = self.params
        ft = p["first_time"].to_numpy() * (1 + self.growth)
        rep = p["retake_rate"].to_numpy() * p["not_passed"].to_numpy()
        out = p[["course_id", "programme_id", "enrolment", "first_time", "repeat_enrolments",
                 "not_passed", "pass_rate", "retake_rate", "repeat_share", "median_year_level"]].copy()
        out["demand_first_time"] = ft
        out["demand_repeat"] = rep
        out["demand"] = ft + rep
        return out

    def simulate(self, policy: SectionPolicy, horizon=config.DEFAULT_HORIZON):
        """Run the stock-flow loop. Returns (yearly totals, per-course year-by-year detail)."""
        backlog = self.params["not_passed"].to_numpy(dtype=float)
        pi = self._pi()
        totals, detail = [], []
        for k in range(1, horizon + 1):
            D = self.demand(backlog, k)
            x = np.asarray(policy(k, D), dtype=float)
            C = x * self.capacity
            S = np.minimum(D, C)
            U = D - S
            passed = pi * S
            backlog = (S - passed) + self.unserved_return * U
            year = self.base_year + k
            totals.append({"year": year, "demand": D.sum(), "sections": x.sum(), "capacity": C.sum(),
                           "served": S.sum(), "unserved": U.sum(), "passed": passed.sum(),
                           "backlog_end": backlog.sum(),
                           "courses_short": int((U > 1e-6).sum()),
                           "utilisation": S.sum() / C.sum() if C.sum() else np.nan})
            detail.append(pd.DataFrame({"course_id": self.params["course_id"], "year": year,
                                        "demand": D, "sections": x, "unserved": U}))
        return pd.DataFrame(totals), pd.concat(detail, ignore_index=True)


def validate_repeat_flow(enrolments: pd.DataFrame, seed=42) -> dict:
    """Split-half validation of the repeat-demand flow rho_c * not_passed_c(t-1).

    Retake rates are estimated on half the students and used to predict the number
    of 2022 repeat enrolments of the other half, course by course."""
    ids = enrolments["student_id"].unique()
    rng = np.random.default_rng(seed)
    a_ids = set(rng.choice(ids, size=len(ids) // 2, replace=False))
    inA = enrolments["student_id"].isin(a_ids)
    pa_raw = course_flow_parameters(enrolments[inA])
    rho_bar = pa_raw.attrs["global_retake_rate"]
    pa = pa_raw.set_index("course_id")
    pb = course_flow_parameters(enrolments[~inA]).set_index("course_id")
    prog_rate = pa.groupby("programme_id")["retake_rate"].mean()
    rho = pa["retake_rate"].reindex(pb.index).fillna(pb["programme_id"].map(prog_rate)).fillna(rho_bar)
    pred = rho * pb["prev_not_passed"]
    pred_global = rho_bar * pb["prev_not_passed"]
    obs = pb["repeat_enrolments"]

    def metrics(p):
        ss_res = ((obs - p) ** 2).sum()
        ss_tot = ((obs - obs.mean()) ** 2).sum()
        return {"R2": 1 - ss_res / ss_tot, "MAE": (obs - p).abs().mean(),
                "total_observed": obs.sum(), "total_predicted": p.sum(),
                "total_error_pct": (p.sum() - obs.sum()) / obs.sum() * 100}
    table = pd.DataFrame({"observed": obs, "predicted": pred, "predicted_global_rate": pred_global})
    return {"course_specific": metrics(pred), "global_rate": metrics(pred_global), "table": table}
