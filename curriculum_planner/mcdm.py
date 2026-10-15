"""Multicriteria decision-making: Analytic Hierarchy Process (AHP).

Used to weight the course-priority criteria of Model 2, the binary programming model
(repeat-student share, first-year course, low pass rate).

Method (Saaty):
  1. pairwise comparison matrix A, a_ij = importance of i over j on the 1-9 scale, a_ji = 1 / a_ij
  2. weights = normalised principal eigenvector of A
  3. lambda_max = principal eigenvalue;  CI = (lambda_max - n) / (n - 1);  CR = CI / RI(n)
  4. the judgements are acceptably consistent when CR <= 0.10
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

import numpy as np
import pandas as pd

# Saaty's random consistency index RI(n)
RANDOM_INDEX = {1: 0.0, 2: 0.0, 3: 0.58, 4: 0.90, 5: 1.12, 6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45, 10: 1.49}
SAATY_SCALE = ["1/9", "1/7", "1/5", "1/3", "1", "3", "5", "7", "9"]


@dataclass
class AHPResult:
    weights: pd.Series
    matrix: pd.DataFrame
    lambda_max: float
    ci: float
    cr: float

    @property
    def consistent(self) -> bool:
        return self.cr <= 0.10


def parse_saaty(v) -> float:
    return float(Fraction(str(v)))


def pairwise_matrix(labels: list[str], judgements: dict[tuple[str, str], float]) -> pd.DataFrame:
    """Build the reciprocal matrix from the upper-triangle judgements {(i, j): a_ij}."""
    n = len(labels)
    A = np.ones((n, n))
    pos = {l: i for i, l in enumerate(labels)}
    for (a, b), v in judgements.items():
        A[pos[a], pos[b]] = v
        A[pos[b], pos[a]] = 1 / v
    return pd.DataFrame(A, index=labels, columns=labels)


def ahp(matrix: pd.DataFrame) -> AHPResult:
    A = matrix.to_numpy(dtype=float)
    n = len(A)
    vals, vecs = np.linalg.eig(A)
    i = int(np.argmax(vals.real))
    w = np.abs(vecs[:, i].real)
    w = w / w.sum()
    lam = float(vals[i].real)
    ci = max(0.0, (lam - n) / (n - 1)) if n > 2 else 0.0   # clip round-off below zero
    ri = RANDOM_INDEX.get(n, 1.49)
    cr = ci / ri if ri > 0 else 0.0
    return AHPResult(pd.Series(w, index=matrix.index, name="weight"), matrix, lam, ci, cr)
