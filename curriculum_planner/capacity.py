"""Capacity and bottleneck analysis.

Section capacity is a MODEL PARAMETER (default 50 students / section); the dataset
contains no capacity information. Current sections are therefore *modelled* as the
fewest sections that would have seated the observed base-year enrolment:
    s_c = max(1, ceil(E_c / cap)).
A course is a bottleneck when projected demand meets or exceeds that modelled
capacity (utilisation >= threshold), i.e. next year's students would not all fit.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config


def modelled_current_sections(enrolment, capacity=config.DEFAULT_SECTION_CAPACITY) -> np.ndarray:
    e = np.asarray(enrolment, dtype=float)
    return np.maximum(1, np.ceil(e / capacity - 1e-9)).astype(int)


def bottleneck_table(projection: pd.DataFrame, capacity=config.DEFAULT_SECTION_CAPACITY,
                     threshold=config.DEFAULT_BOTTLENECK_THRESHOLD,
                     at_risk=config.DEFAULT_AT_RISK_THRESHOLD) -> pd.DataFrame:
    t = projection.copy()
    t["current_sections"] = modelled_current_sections(t["enrolment"], capacity)
    t["current_capacity"] = t["current_sections"] * capacity
    t["utilisation"] = t["demand"] / t["current_capacity"]
    t["unmet_demand"] = np.maximum(0.0, t["demand"] - t["current_capacity"])
    t["extra_sections_needed"] = np.ceil(t["unmet_demand"] / capacity - 1e-9).astype(int)
    t["status"] = np.select([t["utilisation"] >= threshold, t["utilisation"] >= at_risk],
                            ["Bottleneck", "At risk"], default="OK")
    return t.sort_values(["unmet_demand", "utilisation"], ascending=False).reset_index(drop=True)


def bottleneck_summary(table: pd.DataFrame) -> dict:
    b = table[table["status"] == "Bottleneck"]
    return {
        "courses_modelled": len(table),
        "bottleneck_courses": len(b),
        "at_risk_courses": int((table["status"] == "At risk").sum()),
        "projected_demand": float(table["demand"].sum()),
        "modelled_capacity": float(table["current_capacity"].sum()),
        "projected_unmet_demand": float(table["unmet_demand"].sum()),
        "extra_sections_to_clear": int(table["extra_sections_needed"].sum()),
        "bottleneck_repeat_share": float(b["demand_repeat"].sum() / b["demand"].sum()) if len(b) else 0.0,
        "programmes_affected": int(b["programme_id"].nunique()),
    }
