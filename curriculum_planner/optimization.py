"""Integer Programming models for course capacity allocation (HiGHS via scipy.optimize.milp).

Model 1 - Minimum Section Allocation (IP)
    OBJECTIVE   min  sum_c x_c                       total sections opened
    TARGET      every student seated: the seats provided must cover projected demand
    min   sum_c x_c
    s.t.  cap * x_c >= (1 + buffer) * D_c            for all c   (demand fully met)
          x_c >= 1                                   for all c with D_c > 0
          x_c in Z+

Model 2 - Limited Additional Capacity Allocation (Binary IP)
    U_c   = max(0, D_c - cap * s_c)                  unmet demand at current sections s_c
    y_ck  = 1 if the k-th additional section goes to course c   (k = 1..K_c)
    a_ck  = min(cap, U_c - (k-1) cap)                students covered by that section
    max   sum_c sum_k w_c a_ck y_ck                  weighted demand coverage
    s.t.  sum_c sum_k y_ck <= B                      extra-section budget
          y_ck <= y_c,k-1                            sections are opened in order
          sum_{c in p} sum_k y_ck <= M_p             optional per-programme cap (fairness)
          y_ck in {0,1}
    Maximising coverage is equivalent to minimising total unmet demand
    sum_c U_c - sum_ck a_ck y_ck.

LP sensitivity analysis - LP relaxation of Model 2: shadow prices, allowable range of the
    budget, reduced costs (lp_sensitivity_extra_sections).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, linprog, milp
from scipy.sparse import coo_matrix, csr_matrix

from . import config


@dataclass
class SolveResult:
    allocation: pd.DataFrame
    objective: float
    status: str
    summary: dict


# --------------------------------------------------------------------------- model 1
def solve_min_sections(demand: pd.DataFrame, capacity=config.DEFAULT_SECTION_CAPACITY,
                       buffer=0.0, time_limit=60) -> SolveResult:
    """Minimise total sections subject to seating all projected demand.

    `demand` needs columns course_id, demand (and optionally programme_id).
    """
    D_raw = demand["demand"].to_numpy(dtype=float)
    D = D_raw * (1 + buffer)                 # planning demand, after the safety buffer
    target = D                               # TARGET: seats the allocation must provide
    n = len(D)
    lb = np.where(D_raw > 0, 1.0, 0.0)
    cons = LinearConstraint(_diag(np.full(n, float(capacity))), lb=target, ub=np.inf)
    res = milp(c=np.ones(n), constraints=[cons], integrality=np.ones(n),
               bounds=Bounds(lb, np.inf), options={"time_limit": time_limit})
    if res.x is None:
        raise RuntimeError(f"Model 1 failed: {res.message}")
    x = np.round(res.x).astype(int)
    lp = milp(c=np.ones(n), constraints=[cons], integrality=np.zeros(n), bounds=Bounds(lb, np.inf))

    out = demand.copy()
    out["sections"] = x
    out["capacity"] = x * capacity
    out["target_seats"] = target
    out["utilisation"] = np.where(out["capacity"] > 0, D_raw / out["capacity"], np.nan)
    out["spare_seats"] = out["capacity"] - D_raw
    out["unmet_demand"] = np.maximum(0.0, D_raw - out["capacity"])
    unmet = float(out["unmet_demand"].sum())
    total_demand = float(D_raw.sum())
    summary = {
        "total_sections": int(x.sum()),
        "lp_relaxation_sections": float(lp.fun) if lp.x is not None else np.nan,
        "integrality_gap_sections": float(x.sum() - lp.fun) if lp.x is not None else np.nan,
        "total_demand": total_demand,
        "target_seats": float(target.sum()),
        "total_capacity": float(out["capacity"].sum()),
        "mean_utilisation": float(total_demand / out["capacity"].sum()),
        "unmet_demand": unmet,
        "achieved_coverage": float(1 - unmet / total_demand) if total_demand else 1.0,
        "courses_short": int((out["unmet_demand"] > 1e-6).sum()),
        "all_integer": bool(np.allclose(res.x, x)),
        "target_met": bool((out["capacity"] + 1e-6 >= target).all()),
        "demand_fully_met": bool(unmet <= 1e-6),
        "solver_status": res.message,
    }
    return SolveResult(out, float(res.fun), res.message, summary)


def _diag(v):
    n = len(v)
    return csr_matrix((v, (np.arange(n), np.arange(n))), shape=(n, n))


# --------------------------------------------------------------------------- model 2
AHP_CRITERIA = ["Repeat-student share", "First-year course", "Low pass rate"]


def course_criteria(df: pd.DataFrame) -> pd.DataFrame:
    """Score of every course on each AHP criterion, each in [0, 1]."""
    low_pass = (1 - df["pass_rate"].fillna(1)).clip(0, 1) if "pass_rate" in df else pd.Series(0.0, df.index)
    return pd.DataFrame({
        "Repeat-student share": df["repeat_share"].fillna(0).clip(0, 1).to_numpy(),
        "First-year course": (df["median_year_level"].fillna(9) <= 1).to_numpy(dtype=float),
        "Low pass rate": low_pass.to_numpy(dtype=float),
    })


def priority_weights(df: pd.DataFrame, mode="uniform", strength=1.0, criteria_weights=None) -> np.ndarray:
    if mode == "ahp":                   # w_c = 1 + sum_k W_k * score_kc, with W_k from the AHP
        W = np.full(len(AHP_CRITERIA), 1 / len(AHP_CRITERIA)) if criteria_weights is None \
            else np.asarray(criteria_weights, dtype=float)
        return 1 + strength * course_criteria(df)[AHP_CRITERIA].to_numpy() @ W
    if mode == "repeat_weighted":      # courses whose demand is dominated by repeaters delay progression
        return 1 + strength * df["repeat_share"].fillna(0).to_numpy()
    if mode == "early_stage":           # first-year courses gate every later stage
        return 1 + strength * (df["median_year_level"].fillna(9) <= 1).to_numpy(dtype=float)
    return np.ones(len(df))


def _candidate_sections(demand, current_sections, capacity, k_max, max_per_course=None):
    """Candidate extra sections (c, k) and the students a_ck each would seat."""
    D = demand["demand"].to_numpy(dtype=float)
    s = np.asarray(current_sections, dtype=float)
    U = np.maximum(0.0, D - capacity * s)
    K = np.minimum(np.ceil(U / capacity - 1e-9).astype(int), int(k_max))
    if max_per_course:
        K = np.minimum(K, int(max_per_course))
    course_idx = np.repeat(np.arange(len(D)), K)
    k = np.concatenate([np.arange(1, kk + 1) for kk in K]) if K.sum() else np.array([], int)
    gain = np.minimum(capacity, U[course_idx] - (k - 1) * capacity) if len(k) else np.array([])
    return s, U, course_idx, k, gain


def _m2_constraints(demand, course_idx, k, extra_sections, max_per_programme):
    """Model 2 rows as  A y <= ub, with a readable name per row (used by the sensitivity report)."""
    nv = len(k)
    rows, cols, vals, ubs, names = [], [], [], [], []
    r = 0
    # budget
    rows += [r] * nv; cols += list(range(nv)); vals += [1.0] * nv
    ubs.append(float(extra_sections)); names.append("Budget: total extra sections"); r += 1
    # ordering y_ck - y_c,k-1 <= 0
    for j in np.where(k > 1)[0]:
        rows += [r, r]; cols += [j, j - 1]; vals += [1.0, -1.0]; ubs.append(0.0)
        names.append(f"Order: {demand['course_id'].iat[course_idx[j]]} section {k[j]}"); r += 1
    # programme fairness
    if max_per_programme:
        prog = demand["programme_id"].to_numpy()[course_idx]
        for p in np.unique(prog):
            idx = np.where(prog == p)[0]
            if len(idx) > max_per_programme:
                rows += [r] * len(idx); cols += idx.tolist(); vals += [1.0] * len(idx)
                ubs.append(float(max_per_programme)); names.append(f"Programme cap: {p}"); r += 1
    A = coo_matrix((vals, (rows, cols)), shape=(r, nv)).tocsr()
    return A, np.array(ubs), names


def solve_extra_sections(demand: pd.DataFrame, current_sections: np.ndarray,
                         extra_sections=config.DEFAULT_EXTRA_SECTIONS,
                         capacity=config.DEFAULT_SECTION_CAPACITY,
                         max_per_programme: int | None = None, max_per_course: int | None = None,
                         weight_mode="uniform", weight_strength=1.0, criteria_weights=None,
                         time_limit=60) -> SolveResult:
    s, U, course_idx, k, gain = _candidate_sections(demand, current_sections, capacity,
                                                    extra_sections, max_per_course)
    w = priority_weights(demand, weight_mode, weight_strength, criteria_weights)
    out = demand.copy()
    out["current_sections"] = s.astype(int)
    out["unmet_before"] = U
    if len(k) == 0 or extra_sections <= 0:
        out["extra_sections"] = 0
        out["covered_demand"] = 0.0
        out["unmet_after"] = U
        return SolveResult(out, 0.0, "nothing to allocate", _m2_summary(out, extra_sections, capacity))

    A, ubs, _ = _m2_constraints(demand, course_idx, k, extra_sections, max_per_programme)
    res = milp(c=-(w[course_idx] * gain), constraints=[LinearConstraint(A, -np.inf, ubs)],
               integrality=np.ones(len(k)), bounds=Bounds(0, 1), options={"time_limit": time_limit})
    if res.x is None:
        raise RuntimeError(f"Model 2 failed: {res.message}")
    y = np.round(res.x).astype(int)
    extra = np.bincount(course_idx, weights=y, minlength=len(U)).astype(int)
    covered = np.bincount(course_idx, weights=y * gain, minlength=len(U))
    out["extra_sections"] = extra
    out["covered_demand"] = covered
    out["unmet_after"] = U - covered
    out["weight"] = w
    return SolveResult(out, float(-res.fun), res.message, _m2_summary(out, extra_sections, capacity))


# --------------------------------------------------------------- LP sensitivity analysis
def lp_sensitivity_extra_sections(demand: pd.DataFrame, current_sections: np.ndarray,
                                  extra_sections=config.DEFAULT_EXTRA_SECTIONS,
                                  capacity=config.DEFAULT_SECTION_CAPACITY,
                                  max_per_programme: int | None = None,
                                  weight_mode="uniform", criteria_weights=None, range_width=10) -> dict:
    """Sensitivity report of the LP relaxation of Model 2 (0 <= y <= 1), laid out like a
    spreadsheet Solver report: final value, shadow price and binding status of every constraint,
    reduced cost of every candidate section, and a ranging table for the budget B.

    Shadow price of the budget = extra (weighted) students seated by one more section. Each
    y_ck <= 1, so the objective is piecewise linear in B with a breakpoint at every whole section;
    the ranging table therefore lists the marginal value of each section around B."""
    B = int(extra_sections)
    s, U, course_idx, k, gain = _candidate_sections(demand, current_sections, capacity, B + range_width + 1)
    empty = {"constraints": pd.DataFrame(), "variables": pd.DataFrame(), "budget_ranging": pd.DataFrame(),
             "lp_objective": 0.0, "budget_shadow_price": 0.0}
    if len(k) == 0:
        return empty
    w = priority_weights(demand, weight_mode, 1.0, criteria_weights)
    c = -(w[course_idx] * gain)

    def solve(b):
        A, ubs, names = _m2_constraints(demand, course_idx, k, b, max_per_programme)
        return linprog(c, A_ub=A, b_ub=ubs, bounds=(0, 1), method="highs"), A, ubs, names

    res, A, ubs, names = solve(B)
    duals = -res.ineqlin.marginals                   # >= 0: objective gain per unit of RHS
    lhs = A @ res.x
    cons = pd.DataFrame({"constraint": names, "final_value": lhs, "rhs": ubs, "shadow_price": duals,
                         "binding": np.isclose(lhs, ubs, atol=1e-6)})
    var = pd.DataFrame({"course_id": demand["course_id"].to_numpy()[course_idx], "section_k": k,
                        "students_covered": gain, "objective_coeff": -c, "final_value": res.x,
                        "reduced_cost": -(res.upper.marginals + res.lower.marginals)})

    bs = list(range(max(0, B - range_width), B + range_width + 1))
    obj = [float(-solve(b)[0].fun) for b in bs]
    rng = pd.DataFrame({"budget_B": bs, "lp_objective": obj})
    rng["value_of_this_section"] = rng["lp_objective"].diff()          # marginal value of section b
    return {"constraints": cons, "variables": var, "budget_ranging": rng,
            "lp_objective": float(-res.fun), "budget_shadow_price": float(duals[0]),
            "value_of_next_section": float(obj[bs.index(B) + 1] - obj[bs.index(B)]),
            "value_of_last_section": float(obj[bs.index(B)] - obj[bs.index(B) - 1]) if B > 0 else 0.0}


def _m2_summary(out, B, capacity):
    before, after = out["unmet_before"].sum(), out["unmet_after"].sum()
    return {
        "extra_sections_available": int(B),
        "extra_sections_used": int(out["extra_sections"].sum()),
        "unmet_demand_before": float(before),
        "unmet_demand_after": float(after),
        "demand_covered": float(before - after),
        "unmet_reduction_pct": float((before - after) / before * 100) if before else 0.0,
        "demand_coverage_pct": float(1 - after / out["demand"].sum()) * 100,
        "courses_short_before": int((out["unmet_before"] > 1e-6).sum()),
        "courses_short_after": int((out["unmet_after"] > 1e-6).sum()),
        "courses_receiving_sections": int((out["extra_sections"] > 0).sum()),
        "sections_needed_to_clear_all": int(np.ceil(out["unmet_before"] / capacity - 1e-9).sum()),
    }
