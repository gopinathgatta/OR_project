"""Scenario and sensitivity analysis: the SD model and IP models run together in a loop.

Each simulated year the SD course-flow model produces demand D(t); a policy picks the
sections x(t); the resulting shortfall feeds the backlog and therefore D(t+1).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import config
from .capacity import bottleneck_summary, bottleneck_table, modelled_current_sections
from .optimization import solve_extra_sections, solve_min_sections
from .system_dynamics import CourseFlowModel


@dataclass
class Scenario:
    name: str
    capacity: float = config.DEFAULT_SECTION_CAPACITY
    growth: float = config.DEFAULT_DEMAND_GROWTH
    extra_sections: int = config.DEFAULT_EXTRA_SECTIONS
    pass_rate_shift: float = 0.0
    policy: str = "model2"         # status_quo | model1 | model2
    max_per_programme: int | None = None
    weight_mode: str = "uniform"
    horizon: int = config.DEFAULT_HORIZON
    notes: str = ""


def make_policy(name, model: CourseFlowModel, extra_sections=0, max_per_programme=None,
                weight_mode="uniform"):
    s0 = modelled_current_sections(model.params["enrolment"], model.capacity)
    frame = model.params[["course_id", "programme_id", "repeat_share", "median_year_level"]].copy()

    if name == "status_quo":
        return lambda k, D: s0
    if name == "model1":
        def p1(k, D):
            f = frame.assign(demand=D)
            return solve_min_sections(f, model.capacity).allocation["sections"].to_numpy()
        return p1
    if name == "model2":
        def p2(k, D):
            f = frame.assign(demand=D)
            r = solve_extra_sections(f, s0, extra_sections, model.capacity,
                                     max_per_programme=max_per_programme, weight_mode=weight_mode)
            return s0 + r.allocation["extra_sections"].to_numpy()
        return p2
    raise ValueError(name)


def run_scenario(params: pd.DataFrame, sc: Scenario, base_year=config.CALIBRATION_TO):
    m = CourseFlowModel(params, sc.capacity, sc.growth, pass_rate_shift=sc.pass_rate_shift,
                        base_year=base_year)
    pol = make_policy(sc.policy, m, sc.extra_sections, sc.max_per_programme, sc.weight_mode)
    totals, detail = m.simulate(pol, sc.horizon)
    totals.insert(0, "scenario", sc.name)
    return totals, detail


def compare_scenarios(params, scenarios: list[Scenario], base_year=config.CALIBRATION_TO):
    rows, all_totals = [], []
    for sc in scenarios:
        t, _ = run_scenario(params, sc, base_year)
        all_totals.append(t)
        rows.append({
            "scenario": sc.name, "policy": sc.policy, "capacity": sc.capacity,
            "growth": sc.growth, "extra_sections": sc.extra_sections if sc.policy == "model2" else 0,
            "pass_rate_shift": sc.pass_rate_shift,
            "first_year_demand": t["demand"].iloc[0],
            "first_year_unserved": t["unserved"].iloc[0],
            "cumulative_unserved": t["unserved"].sum(),
            "mean_sections_per_year": t["sections"].mean(),
            "mean_utilisation": t["utilisation"].mean(),
            "final_backlog": t["backlog_end"].iloc[-1],
            "final_year_demand": t["demand"].iloc[-1],
            "notes": sc.notes,
        })
    return pd.DataFrame(rows), pd.concat(all_totals, ignore_index=True)


def default_scenarios(capacity=config.DEFAULT_SECTION_CAPACITY, budget=config.DEFAULT_EXTRA_SECTIONS,
                      growth=config.DEFAULT_DEMAND_GROWTH, horizon=config.DEFAULT_HORIZON):
    kw = dict(capacity=capacity, growth=growth, horizon=horizon)
    return [
        Scenario("S0 Status quo", policy="status_quo", notes="modelled current sections kept fixed", **kw),
        Scenario("S1 Limited extra (Model 2)", policy="model2", extra_sections=budget,
                 notes=f"{budget} extra sections per year, re-optimised annually", **kw),
        Scenario("S2 Double budget (Model 2)", policy="model2", extra_sections=2 * budget, **kw),
        Scenario("S3 Full coverage (Model 1)", policy="model1", notes="minimum sections meeting all demand", **kw),
        Scenario("S4 Model 2 + pass +5pp", policy="model2", extra_sections=budget, pass_rate_shift=0.05,
                 notes="extra sections plus academic support raising pass rates 5 points", **kw),
        Scenario("S5 Model 2, intake +5%/yr", policy="model2", extra_sections=budget,
                 capacity=capacity, growth=growth + 0.05, horizon=horizon, notes="demand growth stress test"),
    ]


# --------------------------------------------------------------------------- sensitivity
def sensitivity_capacity(params, capacities=(30, 40, 50, 60, 75, 100), growth=0.0,
                         base_year=config.CALIBRATION_TO):
    rows = []
    for cap in capacities:
        m = CourseFlowModel(params, cap, growth, base_year=base_year)
        proj = m.projected_demand()
        bt = bottleneck_table(proj, cap)
        s = bottleneck_summary(bt)
        r1 = solve_min_sections(proj[["course_id", "programme_id", "demand"]], cap)
        rows.append({"capacity": cap, "bottleneck_courses": s["bottleneck_courses"],
                     "at_risk_courses": s["at_risk_courses"],
                     "unmet_demand_status_quo": s["projected_unmet_demand"],
                     "current_sections_modelled": int(bt["current_sections"].sum()),
                     "model1_sections": r1.summary["total_sections"],
                     "lp_relaxation_sections": r1.summary["lp_relaxation_sections"],
                     "model1_utilisation": r1.summary["mean_utilisation"],
                     "extra_sections_to_clear": s["extra_sections_to_clear"]})
    return pd.DataFrame(rows)


def sensitivity_budget(params, budgets=(0, 5, 10, 25, 50, 75, 100, 150, 200, 300),
                       capacity=config.DEFAULT_SECTION_CAPACITY, growth=0.0,
                       weight_mode="uniform", base_year=config.CALIBRATION_TO):
    m = CourseFlowModel(params, capacity, growth, base_year=base_year)
    proj = m.projected_demand()
    s0 = modelled_current_sections(proj["enrolment"], capacity)
    rows = []
    for B in budgets:
        r = solve_extra_sections(proj, s0, B, capacity, weight_mode=weight_mode)
        rows.append({"extra_sections": B, **r.summary})
    out = pd.DataFrame(rows)
    out["marginal_coverage_per_section"] = (out["demand_covered"].diff() / out["extra_sections"].diff()).round(2)
    return out


def sensitivity_growth(params, growths=(-0.05, 0.0, 0.02, 0.05, 0.10),
                       capacity=config.DEFAULT_SECTION_CAPACITY, budget=config.DEFAULT_EXTRA_SECTIONS,
                       base_year=config.CALIBRATION_TO):
    rows = []
    for g in growths:
        m = CourseFlowModel(params, capacity, g, base_year=base_year)
        proj = m.projected_demand()
        bt = bottleneck_table(proj, capacity)
        s = bottleneck_summary(bt)
        r2 = solve_extra_sections(proj, bt.set_index("course_id").loc[proj["course_id"], "current_sections"].to_numpy(),
                                  budget, capacity)
        rows.append({"growth": g, "projected_demand": s["projected_demand"],
                     "bottleneck_courses": s["bottleneck_courses"],
                     "unmet_demand_status_quo": s["projected_unmet_demand"],
                     "unmet_after_model2": r2.summary["unmet_demand_after"],
                     "extra_sections_to_clear": s["extra_sections_to_clear"]})
    return pd.DataFrame(rows)
