"""Project-wide defaults.

Everything in MODEL PARAMETERS is an *assumption of the planning model*, not a
dataset variable. In particular, section capacity does not exist in the
StudentDropoutDataset; it is set here and can be changed in the UI.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
OUTPUT_DIR = ROOT / "outputs"
TABLE_DIR = OUTPUT_DIR / "tables"
FIGURE_DIR = OUTPUT_DIR / "figures"
REPORT_DIR = OUTPUT_DIR / "reports"
SOURCE_ZIP = ROOT / "17239943.zip"

# Figures reported for the StudentDropoutDataset (Zenodo 10.5281/zenodo.17239943)
EXPECTED_COUNTS = {
    "records": 464_739,
    "students": 39_364,
    "courses": 4_989,
    "programmes": 163,
    "academic_years": 3,
}
ACADEMIC_YEARS = (2018, 2021, 2022)
CALIBRATION_FROM, CALIBRATION_TO = 2021, 2022  # the only consecutive pair
PLANNING_YEAR = 2023

PASS_MARK = 5.0  # Spanish 0-10 grading scale

# ---------------------------- MODEL PARAMETERS ------------------------------
DEFAULT_SECTION_CAPACITY = 50     # students per section (assumption)
DEFAULT_DEMAND_GROWTH = 0.0       # annual growth of first-time enrolments
DEFAULT_BOTTLENECK_THRESHOLD = 1.0   # demand / capacity at or above this = bottleneck
DEFAULT_AT_RISK_THRESHOLD = 0.9      # demand / capacity at or above this = at risk
DEFAULT_EXTRA_SECTIONS = 50       # Model 2 budget of additional sections
DEFAULT_HORIZON = 5               # years simulated by the SD model
DEFAULT_UNSERVED_RETURN = 1.0     # share of unserved students who still need the course
SHRINKAGE_STRENGTH = 10           # pseudo-observations for empirical-Bayes rate smoothing
