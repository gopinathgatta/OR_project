"""Raw StudentDropoutDataset -> optimization-ready student-course tables.

Pipeline (each step is recorded in the cleaning report):
 1. extract the ZIP archives and load every yearly CSV
 2. validate record counts against the published dataset description
 3. resolve missing values, drop duplicate and unusable records
 4. standardise course / programme / student identifier formats
 5. keep only the variables needed for flow and demand modelling
 6. build the student-course linkage across years (hashed IDs are kept as keys)
 7. derive outcome and repeat-enrolment indicators used by the models
"""
from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from . import config

# raw column -> clean column. Only flow / progression / demand variables are kept;
# LMS, Wi-Fi and socio-demographic columns are out of scope for capacity planning.
COLUMN_MAP = {
    "dni_hash": "student_id",
    "tit_hash": "programme_id",
    "asi_hash": "course_id",
    "caca": "academic_year",
    "nota_asig_hash": "grade",
    "curso_mas_bajo": "lowest_year_level",
    "curso_mas_alto": "highest_year_level",
    "anyo_inicio_estudios": "start_year",
    "cred_mat_total": "credits_enrolled",
    "cred_sup_total": "credits_passed",
    "cred_sup_tit": "credits_passed_programme",
    "cred_pend_sup_tit": "credits_pending_programme",
    "dedicacion": "study_mode",
    "tipo_ingreso": "admission_type",
    "abandono_hash": "dropout_label",
    "baja_fecha": "withdrawal_date",
    "campus_hash": "campus_id",
}
ID_COLS = ["student_id", "programme_id", "course_id", "campus_id"]
RAW_ID_COLS = [k for k, v in COLUMN_MAP.items() if v in ID_COLS]


@dataclass
class CleaningReport:
    steps: list[dict] = field(default_factory=list)
    validation: dict = field(default_factory=dict)

    def log(self, step: str, detail: str, rows: int | None = None):
        self.steps.append({"step": step, "detail": detail, "rows_after": rows})

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.steps)


@dataclass
class ProcessedData:
    enrolments: pd.DataFrame       # one row per student x course x academic year
    students: pd.DataFrame         # one row per student x academic year
    courses: pd.DataFrame          # one row per course x academic year
    report: CleaningReport


# --------------------------------------------------------------------------- 1
def _iter_csv_payloads(name: str, payload: bytes) -> Iterable[tuple[str, bytes]]:
    """Yield (filename, bytes) for every CSV inside a file, recursing into ZIPs."""
    if name.lower().endswith(".zip") or zipfile.is_zipfile(io.BytesIO(payload)):
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                yield from _iter_csv_payloads(info.filename, zf.read(info))
    elif name.lower().endswith(".csv"):
        yield name, payload


def _source_bytes(src) -> tuple[str, bytes]:
    if isinstance(src, (str, Path)):
        p = Path(src)
        return p.name, p.read_bytes()
    # file-like (e.g. Streamlit UploadedFile)
    return getattr(src, "name", "upload"), src.getvalue() if hasattr(src, "getvalue") else src.read()


def load_raw(sources) -> pd.DataFrame:
    """Load every yearly CSV found in `sources` (paths, folders, ZIPs or uploaded files)."""
    if isinstance(sources, (str, Path)) and Path(sources).is_dir():
        sources = sorted(Path(sources).glob("*.csv")) or sorted(Path(sources).glob("*.zip"))
    if not isinstance(sources, (list, tuple)):
        sources = [sources]
    frames, seen = [], set()
    for src in sources:
        name, payload = _source_bytes(src)
        for csv_name, data in _iter_csv_payloads(name, payload):
            if Path(csv_name).name in seen:
                continue
            seen.add(Path(csv_name).name)
            header = pd.read_csv(io.BytesIO(data), sep=";", nrows=0).columns
            usecols = [c for c in COLUMN_MAP if c in header]
            df = pd.read_csv(
                io.BytesIO(data), sep=";", decimal=",", usecols=usecols,
                dtype={c: str for c in RAW_ID_COLS}, low_memory=False,
            )
            df["source_file"] = Path(csv_name).name
            frames.append(df)
    if not frames:
        raise ValueError("No StudentDropoutDataset CSV files found in the provided sources.")
    return pd.concat(frames, ignore_index=True)


def load_raw_from_project() -> pd.DataFrame:
    csvs = sorted(config.RAW_DIR.glob("dataset_*_hash.csv"))
    if csvs:
        return load_raw(csvs)
    if config.SOURCE_ZIP.exists():
        return load_raw(config.SOURCE_ZIP)
    raise FileNotFoundError("Place 17239943.zip in the project root or CSVs in data/raw/.")


# --------------------------------------------------------------------- 2 - 7
def validate_counts(raw: pd.DataFrame) -> dict:
    observed = {
        "records": len(raw),
        "students": raw["dni_hash"].nunique(),
        "courses": raw["asi_hash"].nunique(),
        "programmes": raw["tit_hash"].nunique(),
        "academic_years": raw["caca"].nunique(),
    }
    return {
        k: {"expected": config.EXPECTED_COUNTS[k], "observed": int(v),
            "match": int(v) == config.EXPECTED_COUNTS[k]}
        for k, v in observed.items()
    }


def _standardise_id(s: pd.Series) -> pd.Series:
    s = s.astype("string").str.strip().str.lower()
    return s.where(s.str.fullmatch(r"[0-9a-f]+"), pd.NA)


def clean(raw: pd.DataFrame) -> ProcessedData:
    rep = CleaningReport()
    rep.validation = validate_counts(raw)
    rep.log("load", f"{raw['source_file'].nunique()} yearly files loaded", len(raw))

    df = raw.rename(columns=COLUMN_MAP).drop(columns=["source_file"])

    # 4. identifiers: lowercase hex strings, no whitespace; invalid -> missing
    for c in ID_COLS:
        df[c] = _standardise_id(df[c])
    df["academic_year"] = pd.to_numeric(df["academic_year"], errors="coerce").astype("Int64")
    rep.log("standardise_ids", "IDs stripped, lower-cased, validated as hexadecimal hashes", len(df))

    # 3. unusable / duplicate records
    key = ["student_id", "course_id", "academic_year"]
    n0 = len(df)
    df = df.dropna(subset=["student_id", "programme_id", "course_id", "academic_year"])
    rep.log("drop_missing_keys", f"{n0 - len(df)} rows without a student, course, programme or year removed", len(df))
    n0 = len(df)
    df = df.drop_duplicates()
    rep.log("drop_exact_duplicates", f"{n0 - len(df)} exact duplicate rows removed", len(df))
    n0 = len(df)
    df = df.sort_values(key).drop_duplicates(subset=key, keep="first")
    rep.log("drop_key_duplicates", f"{n0 - len(df)} duplicate student-course-year records removed", len(df))

    # missing values
    n_grade_na = int(df["grade"].isna().sum())
    df["grade_missing"] = df["grade"].isna()
    df["outcome"] = np.select(
        [df["grade"].isna(), df["grade"] >= config.PASS_MARK],
        ["not_evaluated", "pass"], default="fail",
    )
    df["passed"] = df["outcome"].eq("pass")
    rep.log("grades", f"{n_grade_na} missing grades kept as 'not_evaluated' (no credit earned; "
                      "they re-enrol at the same rate as fails, so they count as not passed)", len(df))
    df["admission_type"] = df["admission_type"].fillna("UNKNOWN")
    df["withdrawn_in_year"] = df["withdrawal_date"].notna()
    df["withdrawal_date"] = pd.to_datetime(df["withdrawal_date"], errors="coerce")
    df["dropout_label"] = df["dropout_label"].map({"A": True, "B": False})
    num_cols = ["credits_enrolled", "credits_passed", "credits_passed_programme",
                "credits_pending_programme", "highest_year_level", "lowest_year_level", "start_year"]
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    rep.log("missing_values", "admission_type NA -> 'UNKNOWN'; withdrawal date NA -> not withdrawn; "
                              "anyo_ingreso dropped (duplicates start_year)", len(df))

    # programme length = highest curriculum year observed in the programme
    prog_len = df.groupby("programme_id")["highest_year_level"].max().rename("programme_length")
    df = df.join(prog_len, on="programme_id")

    # 6. cross-year linkage on hashed student x course keys
    years = sorted(df["academic_year"].dropna().unique().tolist())
    pairs = set(zip(df["student_id"], df["course_id"], df["academic_year"]))
    prev_year = {y: years[i - 1] for i, y in enumerate(years) if i > 0}
    consecutive = {y: p for y, p in prev_year.items() if y - p == 1}

    def _taken_in(year_lookup):
        return np.array([
            (s, c, year_lookup.get(y)) in pairs if year_lookup.get(y) is not None else False
            for s, c, y in zip(df["student_id"], df["course_id"], df["academic_year"])
        ])
    # repeat enrolment is only identifiable when the previous academic year is in the data
    df["repeat_enrolment"] = _taken_in(consecutive)
    df["repeat_observable"] = df["academic_year"].isin(list(consecutive))
    df["taken_in_earlier_file"] = _taken_in(prev_year)
    rep.log("linkage", f"student-course trajectories linked across {years}; repeat enrolment "
                       f"identifiable for {sorted(consecutive)} (previous year present)", len(df))

    keep = ["student_id", "programme_id", "course_id", "campus_id", "academic_year", "grade",
            "grade_missing", "outcome", "passed", "repeat_enrolment", "repeat_observable",
            "taken_in_earlier_file", "lowest_year_level", "highest_year_level", "programme_length",
            "start_year", "credits_enrolled", "credits_passed", "credits_passed_programme",
            "credits_pending_programme", "study_mode", "admission_type", "dropout_label",
            "withdrawn_in_year", "withdrawal_date"]
    df = df[keep].reset_index(drop=True)
    rep.log("select_variables", f"{len(keep)} modelling variables retained", len(df))

    students = build_student_table(df)
    courses = build_course_table(df)
    rep.log("course_statistics", f"{len(courses)} course-year statistic rows built", len(df))
    return ProcessedData(df, students, courses, rep)


def build_student_table(enr: pd.DataFrame) -> pd.DataFrame:
    g = enr.groupby(["student_id", "academic_year"], sort=False)
    st = g.agg(
        programme_id=("programme_id", "first"),
        highest_year_level=("highest_year_level", "max"),
        programme_length=("programme_length", "first"),
        start_year=("start_year", "first"),
        courses_enrolled=("course_id", "size"),
        courses_passed=("passed", "sum"),
        repeat_courses=("repeat_enrolment", "sum"),
        credits_pending_programme=("credits_pending_programme", "first"),
        dropout_label=("dropout_label", "first"),
        withdrawn_in_year=("withdrawn_in_year", "max"),
    ).reset_index()
    st["new_entrant"] = st["start_year"].eq(st["academic_year"])
    return st


def build_course_table(enr: pd.DataFrame) -> pd.DataFrame:
    """Course-year statistics: enrolment, outcomes and repetition."""
    g = enr.groupby(["course_id", "academic_year"])
    c = g.agg(
        programme_id=("programme_id", "first"),
        enrolment=("student_id", "size"),
        passes=("passed", "sum"),
        fails=("outcome", lambda s: (s == "fail").sum()),
        not_evaluated=("outcome", lambda s: (s == "not_evaluated").sum()),
        repeat_enrolments=("repeat_enrolment", "sum"),
        repeat_observable=("repeat_observable", "first"),
        mean_grade=("grade", "mean"),
        median_year_level=("lowest_year_level", "median"),
    ).reset_index()
    c["not_passed"] = c["enrolment"] - c["passes"]
    c["pass_rate"] = c["passes"] / c["enrolment"]
    c["fail_rate"] = c["fails"] / c["enrolment"]
    c["not_evaluated_rate"] = c["not_evaluated"] / c["enrolment"]
    c["repeat_rate"] = np.where(c["repeat_observable"], c["repeat_enrolments"] / c["enrolment"], np.nan)
    c["first_time_enrolment"] = np.where(c["repeat_observable"], c["enrolment"] - c["repeat_enrolments"], np.nan)
    return c


# ---------------------------------------------------------------- persistence
def save(pd_: ProcessedData, out_dir: Path = config.PROCESSED_DIR):
    out_dir.mkdir(parents=True, exist_ok=True)
    pd_.enrolments.to_parquet(out_dir / "student_course_enrolments.parquet", index=False)
    pd_.students.to_parquet(out_dir / "student_year.parquet", index=False)
    pd_.courses.to_parquet(out_dir / "course_year_statistics.parquet", index=False)
    pd_.enrolments.to_csv(out_dir / "student_course_enrolments.csv.gz", index=False, compression="gzip")
    pd_.courses.to_csv(out_dir / "course_year_statistics.csv", index=False)
    pd_.report.to_frame().to_csv(out_dir / "cleaning_log.csv", index=False)
    pd.DataFrame(pd_.report.validation).T.to_csv(out_dir / "count_validation.csv")


def load_processed(path_or_file) -> ProcessedData:
    """Load a saved enrolment table (parquet or csv[.gz]) and rebuild derived tables."""
    name = str(getattr(path_or_file, "name", path_or_file))
    if name.endswith(".parquet"):
        enr = pd.read_parquet(path_or_file)
    else:
        enr = pd.read_csv(path_or_file, dtype={c: str for c in ID_COLS},
                          compression="gzip" if name.endswith(".gz") else "infer")
    rep = CleaningReport()
    rep.log("load_processed", f"pre-processed enrolment table loaded from {Path(name).name}", len(enr))
    return ProcessedData(enr, build_student_table(enr), build_course_table(enr), rep)


def load_default() -> ProcessedData:
    p = config.PROCESSED_DIR / "student_course_enrolments.parquet"
    if p.exists():
        data = load_processed(p)
        log = config.PROCESSED_DIR / "cleaning_log.csv"
        if log.exists():
            data.report.steps = pd.read_csv(log).to_dict("records")
        val = config.PROCESSED_DIR / "count_validation.csv"
        if val.exists():
            data.report.validation = pd.read_csv(val, index_col=0).to_dict("index")
        return data
    data = clean(load_raw_from_project())
    save(data)
    return data
