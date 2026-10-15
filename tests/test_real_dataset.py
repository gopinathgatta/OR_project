"""End-to-end tests on the real StudentDropoutDataset (skipped if the raw data is absent).

The input is the raw Zenodo archive 17239943.zip, the same file a user uploads in the app. Every model
answer is checked independently of the solver:
  * Model 1 (Integer Programming): integer, demand met, and equal to the closed-form optimum ceil(D / cap)
  * Model 2 (Binary Programming): budget, ordering and programme caps respected; without programme caps
    the optimum equals the sum of the B largest section gains (the gains fall within each course, so the
    greedy choice is optimal), and with caps it is never better than that bound
  * LP sensitivity: the shadow price of the budget lies between the values of section B and section B + 1

    python -m pytest tests/test_real_dataset.py -v -s
"""
import io
import math

import numpy as np
import pandas as pd
import pytest

from curriculum_planner import config, mcdm, preprocessing as pp, system_dynamics as sd
from curriculum_planner.capacity import bottleneck_table, modelled_current_sections
from curriculum_planner.optimization import (AHP_CRITERIA, lp_sensitivity_extra_sections,
                                             solve_extra_sections, solve_min_sections)

pytestmark = pytest.mark.skipif(not config.SOURCE_ZIP.exists(), reason="17239943.zip not in project root")


@pytest.fixture(scope="module")
def data():
    """Load exactly as the app does for an uploaded archive."""
    upload = io.BytesIO(config.SOURCE_ZIP.read_bytes())
    upload.name = config.SOURCE_ZIP.name
    return pp.clean(pp.load_raw([upload]))


@pytest.fixture(scope="module")
def params(data):
    return sd.course_flow_parameters(data.enrolments)


def _proj(params, cap, growth=0.0):
    proj = sd.CourseFlowModel(params, cap, growth).projected_demand()
    return proj, modelled_current_sections(proj["enrolment"], cap)


# --------------------------------------------------------------------------- data
def test_dataset_counts_match_publication(data):
    v = data.report.validation
    print("\n" + pd.DataFrame(v).T.to_string())
    assert all(str(r["match"]) == "True" for r in v.values())


def test_upload_matches_bundled_processed_data(data):
    bundled = pp.load_default().enrolments
    cols = ["student_id", "course_id", "academic_year", "outcome", "repeat_enrolment"]
    a = data.enrolments[cols].sort_values(cols[:3]).reset_index(drop=True)
    b = bundled[cols].sort_values(cols[:3]).reset_index(drop=True)
    pd.testing.assert_frame_equal(a, b, check_dtype=False)


def test_forecast_is_consistent(params):
    proj, _ = _proj(params, 50)
    assert (proj["demand"] >= proj["demand_first_time"]).all()
    assert np.allclose(proj["demand"], proj["first_time"] + proj["retake_rate"] * proj["not_passed"])
    assert proj["demand"].sum() == pytest.approx(161_620, rel=1e-3)


# --------------------------------------------------------------------------- Model 1
@pytest.mark.parametrize("cap,buffer", [(30, 0.0), (50, 0.0), (50, 0.10), (80, 0.0), (120, 0.05)])
def test_model1_integer_programming(params, cap, buffer):
    proj, _ = _proj(params, cap)
    r = solve_min_sections(proj[["course_id", "programme_id", "demand"]], cap, buffer)
    x = r.allocation["sections"].to_numpy()
    D = proj["demand"].to_numpy() * (1 + buffer)
    closed_form = np.where(D > 0, np.maximum(1, np.ceil(D / cap - 1e-9)), 0)
    print(f"\nModel 1  cap={cap:>3} buffer={buffer:.2f}: {x.sum():,} sections "
          f"(LP {r.summary['lp_relaxation_sections']:,.1f}), utilisation {r.summary['mean_utilisation']:.1%}")
    assert r.summary["all_integer"] and r.summary["demand_fully_met"]
    assert (cap * x >= D - 1e-6).all()
    assert (x == closed_form).all()                                 # proven optimum
    assert r.summary["lp_relaxation_sections"] <= x.sum()


# --------------------------------------------------------------------------- Model 2
CASES = [  # cap, budget B, max per programme M, weights
    (50, 10, None, "uniform"), (50, 50, None, "uniform"), (50, 100, None, "uniform"),
    (30, 50, None, "uniform"), (80, 20, None, "uniform"), (50, 50, 5, "uniform"),
    (50, 50, None, "repeat_weighted"), (50, 50, None, "early_stage"), (50, 50, None, "ahp"),
]


@pytest.mark.parametrize("cap,B,M,wmode", CASES)
def test_model2_binary_programming(params, cap, B, M, wmode):
    proj, s0 = _proj(params, cap)
    cw = None
    if wmode == "ahp":
        c = AHP_CRITERIA
        cw = mcdm.ahp(mcdm.pairwise_matrix(c, {(c[0], c[1]): 3, (c[0], c[2]): 5, (c[1], c[2]): 2})).weights.values
    r = solve_extra_sections(proj, s0, B, cap, max_per_programme=M, weight_mode=wmode, criteria_weights=cw)
    a, sm = r.allocation, r.summary
    U = np.maximum(0, proj["demand"].to_numpy() - cap * s0)

    # feasibility
    assert a["extra_sections"].sum() <= B
    assert (a["extra_sections"] >= 0).all()
    assert np.allclose(a["unmet_after"], a["unmet_before"] - a["covered_demand"])
    assert (a["unmet_after"] >= -1e-6).all()
    assert (a["covered_demand"] <= np.minimum(U, cap * a["extra_sections"]) + 1e-6).all()
    if M:
        assert a.groupby("programme_id")["extra_sections"].sum().max() <= M

    # optimality against an independent bound: the B largest section gains
    gains = np.sort(np.concatenate([np.minimum(cap, u - cap * np.arange(math.ceil(u / cap - 1e-9)))
                                    for u in U if u > 0]))[::-1]
    best = gains[:B].sum()
    covered = a["covered_demand"].sum()
    print(f"\nModel 2  cap={cap:>3} B={B:>3} M={M} {wmode:<15}: unmet {sm['unmet_demand_before']:,.1f} -> "
          f"{sm['unmet_demand_after']:,.1f} ({sm['extra_sections_used']} sections, bound {best:,.1f})")
    assert covered <= best + 1e-6
    if wmode == "uniform" and M is None:
        assert covered == pytest.approx(best, abs=1e-6)              # proven optimum


def test_lp_sensitivity_on_real_data(params):
    proj, s0 = _proj(params, 50)
    rep = lp_sensitivity_extra_sections(proj, s0, 50, 50)
    ip = solve_extra_sections(proj, s0, 50, 50)
    sp, last, nxt = rep["budget_shadow_price"], rep["value_of_last_section"], rep["value_of_next_section"]
    print(f"\nLP sensitivity: LP {rep['lp_objective']:,.2f} vs IP {ip.objective:,.2f}; shadow price {sp:.3f} "
          f"(section 50 = {last:.3f}, section 51 = {nxt:.3f})")
    assert ip.objective <= rep["lp_objective"] + 1e-6
    assert min(last, nxt) - 1e-6 <= sp <= max(last, nxt) + 1e-6
    assert (rep["budget_ranging"]["value_of_this_section"].dropna().diff().dropna() <= 1e-6).all()


def test_bottlenecks_match_model2_input(params):
    proj, s0 = _proj(params, 50)
    bt = bottleneck_table(proj, 50)
    r = solve_extra_sections(proj, s0, 50, 50)
    assert bt["unmet_demand"].sum() == pytest.approx(r.summary["unmet_demand_before"])
    assert (bt["status"] == "Bottleneck").sum() == 68
