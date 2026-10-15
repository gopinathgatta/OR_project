"""Unit tests on a small synthetic dataset in the raw StudentDropoutDataset format."""
import io
import zipfile

import numpy as np
import pandas as pd
import pytest

from curriculum_planner import mcdm, preprocessing as pp, system_dynamics as sd
from curriculum_planner.capacity import bottleneck_table, modelled_current_sections
from curriculum_planner.optimization import (AHP_CRITERIA, lp_sensitivity_extra_sections,
                                             solve_extra_sections, solve_min_sections)


def _raw_year(year, rows):
    df = pd.DataFrame(rows, columns=["dni_hash", "tit_hash", "asi_hash", "nota_asig_hash",
                                     "curso_mas_alto", "cred_pend_sup_tit"])
    df["caca"] = year
    df["curso_mas_bajo"] = df["curso_mas_alto"]
    df["anyo_inicio_estudios"] = year - df["curso_mas_alto"] + 1
    df["abandono_hash"] = "B"
    for c in ["tipo_ingreso", "baja_fecha", "campus_hash", "dedicacion", "cred_mat_total",
              "cred_sup_total", "cred_sup_tit"]:
        df[c] = None
    df["campus_hash"] = "aa"
    df["nota_asig_hash"] = df["nota_asig_hash"].map(lambda v: "" if v is None else str(v).replace(".", ","))
    return df.to_csv(sep=";", index=False).encode()


@pytest.fixture(scope="module")
def data():
    # '1e10' looks numeric: IDs must stay strings
    r21 = [("d1", "f1", "1e10", 4.0, 1, 100), ("d1", "f1", "c2", 7.0, 1, 100),
           ("d2", "f1", "1e10", 8.0, 1, 0), ("d3", "f1", "1e10", None, 2, 50),
           ("d4", "f1", "c2", 3.0, 2, 60)]
    r22 = [("d1", "f1", "1e10", 6.0, 2, 40), ("d3", "f1", "1e10", 2.0, 2, 50),
           ("d5", "f1", "1e10", 9.0, 1, 200), ("d5", "f1", "c2", 9.0, 1, 200),
           ("d5", "f1", "c2", 9.0, 1, 200)]          # duplicate key -> removed
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("dataset_2021_hash.csv", _raw_year(2021, r21))
        z.writestr("dataset_2022_hash.csv", _raw_year(2022, r22))
    buf.name = "test.zip"
    buf.seek(0)
    return pp.clean(pp.load_raw([buf]))


def test_ids_stay_strings(data):
    assert "1e10" in set(data.enrolments["course_id"])


def test_duplicates_removed(data):
    assert len(data.enrolments) == 9
    assert not data.enrolments.duplicated(["student_id", "course_id", "academic_year"]).any()


def test_outcomes_and_repeats(data):
    e = data.enrolments.set_index(["student_id", "course_id", "academic_year"])
    assert e.loc[("d3", "1e10", 2021), "outcome"] == "not_evaluated"
    assert not e.loc[("d3", "1e10", 2021), "passed"]
    assert e.loc[("d1", "1e10", 2022), "repeat_enrolment"]
    assert not e.loc[("d5", "1e10", 2022), "repeat_enrolment"]


def test_student_transitions(data):
    tr, intake = sd.student_transitions(data.students)
    t = tr.set_index("student_id")["to_stage"]
    assert t["d2"] == "Graduated" and t["d4"] == "Withdrawn"
    assert set(intake["student_id"]) == {"d5"}


def test_student_flow_mass_balance(data):
    m = sd.StudentFlowModel.calibrate(data.students)
    assert np.allclose(m.P.sum(axis=1)[m.base_stocks.index[m.P.sum(axis=1) > 0]], 1)
    stocks = pd.Series(100.0, index=sd.STAGES)
    new, flows = m.step(stocks, pd.Series(0.0, index=sd.STAGES))
    rows_used = m.P.sum(axis=1) > 0
    assert new.sum() + flows["Graduating"] + flows["Withdrawing"] == pytest.approx(stocks[rows_used].sum())


def test_course_flow_backlog_feedback():
    p = pd.DataFrame({"course_id": ["a"], "programme_id": ["p"], "enrolment": [100], "first_time": [100.0],
                      "repeat_enrolments": [0], "not_passed": [20.0], "pass_rate": [0.8],
                      "retake_rate": [0.5], "repeat_share": [0.0], "median_year_level": [1.0]})
    m = sd.CourseFlowModel(p, capacity=50)
    tight, _ = m.simulate(lambda k, D: np.array([2]), horizon=3)       # 100 seats
    loose, _ = m.simulate(lambda k, D: np.array([10]), horizon=3)
    assert tight["unserved"].iloc[0] == pytest.approx(10)              # 100 + 0.5*20 - 100
    assert tight["demand"].iloc[1] > loose["demand"].iloc[1]           # shortfall adds demand
    assert loose["unserved"].sum() == 0


def _demand(vals, progs=None):
    n = len(vals)
    return pd.DataFrame({"course_id": [f"c{i}" for i in range(n)],
                         "programme_id": progs or ["p"] * n, "demand": vals,
                         "repeat_share": [0.0] * n, "median_year_level": [1.0] * n})


def test_model1_integer_and_minimal():
    d = _demand([0, 10, 50, 51, 149.5])
    r = solve_min_sections(d, capacity=50)
    assert r.allocation["sections"].tolist() == [0, 1, 1, 2, 3]
    assert r.summary["all_integer"] and r.summary["demand_fully_met"]
    assert r.summary["lp_relaxation_sections"] <= r.summary["total_sections"]


def test_model2_budget_and_priority():
    d = _demand([140, 60, 52, 30])
    s0 = np.array([1, 1, 1, 1])                  # unmet: 90, 10, 2, 0
    r = solve_extra_sections(d, s0, extra_sections=2, capacity=50)
    a = r.allocation.set_index("course_id")
    assert a["extra_sections"].sum() == 2
    assert a.loc["c0", "extra_sections"] == 2    # 50 + 40 beats 10
    assert r.summary["unmet_demand_after"] == pytest.approx(12)


def test_model2_programme_fairness():
    d = _demand([200, 200, 120], progs=["f1", "f1", "p2"])
    r = solve_extra_sections(d, np.array([1, 1, 1]), extra_sections=4, capacity=50, max_per_programme=2)
    a = r.allocation.groupby("programme_id")["extra_sections"].sum()
    assert a["f1"] <= 2 and a.sum() == 4


def test_bottleneck_flag():
    proj = _demand([100, 120, 95]).assign(enrolment=[100, 100, 100], demand_repeat=0.0)
    bt = bottleneck_table(proj, capacity=50).set_index("course_id")
    assert bt.loc["c0", "status"] == "Bottleneck"      # demand meets capacity
    assert bt.loc["c1", "unmet_demand"] == 20
    assert bt.loc["c2", "status"] == "At risk"
    assert list(modelled_current_sections([0, 1, 50, 51], 50)) == [1, 1, 1, 2]


# --------------------------------------------------------------- LP sensitivity, AHP
def test_lp_sensitivity_shadow_price():
    d = _demand([140, 60, 52, 30])               # unmet 90, 10, 2, 0 -> sections worth 50, 40, 10, 2
    r = lp_sensitivity_extra_sections(d, np.array([1, 1, 1, 1]), extra_sections=2, capacity=50)
    assert r["lp_objective"] == pytest.approx(90)
    assert r["value_of_last_section"] == pytest.approx(40)
    assert r["value_of_next_section"] == pytest.approx(10)
    assert r["constraints"].iloc[0]["binding"]
    assert 10 - 1e-6 <= r["budget_shadow_price"] <= 40 + 1e-6


def test_ahp_weighted_binary_model():
    d = _demand([110, 110]).assign(repeat_share=[0.0, 0.8])   # same unmet (10), c1 full of repeaters
    W = mcdm.ahp(mcdm.pairwise_matrix(AHP_CRITERIA, {(AHP_CRITERIA[0], AHP_CRITERIA[1]): 5,
                                                     (AHP_CRITERIA[0], AHP_CRITERIA[2]): 5,
                                                     (AHP_CRITERIA[1], AHP_CRITERIA[2]): 1})).weights.values
    r = solve_extra_sections(d, np.array([2, 2]), extra_sections=1, capacity=50, weight_mode="ahp",
                             criteria_weights=W)
    assert r.allocation.set_index("course_id")["extra_sections"].to_dict() == {"c0": 0, "c1": 1}


def test_ahp_consistency():
    labels = ["a", "b", "c"]
    perfect = mcdm.ahp(mcdm.pairwise_matrix(labels, {("a", "b"): 2, ("a", "c"): 4, ("b", "c"): 2}))
    assert perfect.weights.tolist() == pytest.approx([4 / 7, 2 / 7, 1 / 7])
    assert perfect.cr == pytest.approx(0, abs=1e-9) and perfect.consistent
    bad = mcdm.ahp(mcdm.pairwise_matrix(labels, {("a", "b"): 9, ("a", "c"): 1 / 9, ("b", "c"): 9}))
    assert not bad.consistent
