"""Feature engineering for the bundled CGPA models.

This module is deliberately free of Django imports and imports no numeric
library at module level: it is used by both

* ``ml/train.py`` (offline training, pandas available), and
* ``apps/predictions/services.py`` (online inference inside Django, where the
  ML stack may not be installed),

so that the feature vector produced at training time is the same contract the
API produces at serving time. Any new feature must be added here, then the
models retrained.

How 3 inputs become 14 numbers
-----------------------------
The dataset has **three** measured inputs per student: matric marks, FSc marks,
and a variable-length list of semester SGPAs. A fixed-shape model cannot take a
variable-length list, so the list is summarised into level (mean, last,
weighted mean, min, max), trend (slope, first-to-last delta) and volatility
(std). ``sem_count`` records how many semesters the summary describes.

``admission_avg``, ``admission_gap`` and ``sem_vs_admission`` are linear
combinations of the other features. For a Ridge model they are redundant, which
is exactly why the driver shares shown in the UI are model weights and must not
be described as causal contributions.

The dataset files contain only ``Matric_Marks``, ``FSC_Marks``, ``Sem*_CGPA``
and ``Final_CGPA``. Every average and percentage below is computed at train and
serve time and never stored in the dataset. For semester ``N`` only the first
``N - 1`` SGPAs are read, so no future semester can leak into an earlier
prediction.
"""

from __future__ import annotations

import math

SEMESTER_COUNT = 8

#: Fallback maxima, used **only** when no per-student total is stored (the
#: training datasets have no columns for totals). At serving time the student's
#: own ``AdmissionRecord.matric_total`` / ``fsc_total`` are authoritative; these
#: constants are the single source of truth that ``seed_admissions`` also uses
#: for its defaults, so the two can never drift apart again.
DEFAULT_MATRIC_TOTAL = 1150
DEFAULT_FSC_TOTAL = 1100

RAW_COLUMN = {
    "matric": "Matric_Marks",
    "fsc": "FSC_Marks",
}

NAN = float("nan")


def semester_column(index: int) -> str:
    """``semester_column(1) -> 'Sem1_CGPA'``."""
    return f"Sem{index}_CGPA"


#: Ordered feature names. The order is part of the model contract: the saved
#: pipelines were fitted on a frame with exactly these columns, and the serving
#: loader refuses a manifest whose ``feature_order`` differs.
FEATURE_ORDER: list[str] = [
    "matric_pct",
    "fsc_pct",
    "admission_avg",
    "admission_gap",
    "sem_count",
    "sem_mean",
    "sem_last",
    "sem_weighted",
    "sem_trend",
    "sem_delta",
    "sem_std",
    "sem_min",
    "sem_max",
    "sem_vs_admission",
]


def _trend(values: list[float]) -> float:
    """Least-squares slope of semester GPAs (0.0 with fewer than 2 points)."""
    if len(values) < 2:
        return 0.0
    n = len(values)
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(values) / n
    denominator = sum((x - mean_x) ** 2 for x in xs)
    if denominator == 0:
        return 0.0
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, values))
    return float(numerator / denominator)


def _weighted_mean(values: list[float]) -> float:
    """Recency-weighted mean: the latest semester dominates."""
    weights = [float(i) for i in range(1, len(values) + 1)]
    total = sum(weights)
    return float(sum(w * v for w, v in zip(weights, values)) / total) if total else 0.0


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return float(math.sqrt(sum((v - mean) ** 2 for v in values) / len(values)))


def _percent(obtained, total, fallback_total: float) -> float:
    """Marks -> fraction of the maximum, or NaN when the mark is unknown.

    Missing is represented as NaN, never 0.0: the pipeline's median imputer
    then fills it from the training distribution. Returning 0.0 would tell the
    model the student scored nothing, which is a different (and defamatory)
    claim. A stored total is authoritative; the fallback is only for the
    training data, which has no totals at all.
    """
    if obtained is None:
        return NAN
    try:
        obtained = float(obtained)
    except (TypeError, ValueError):
        return NAN
    if not math.isfinite(obtained):
        return NAN

    denominator = total if total not in (None, 0, "") else fallback_total
    try:
        denominator = float(denominator)
    except (TypeError, ValueError):
        denominator = float(fallback_total)
    if not math.isfinite(denominator) or denominator <= 0:
        return NAN

    return obtained / denominator


def build_features_and_warnings(
    matric_marks,
    fsc_marks,
    semester_cgpas: list[float] | None,
    *,
    matric_total=None,
    fsc_total=None,
) -> tuple[dict[str, float], list[str]]:
    """Build one feature vector plus any data-quality warnings.

    Parameters
    ----------
    matric_marks, fsc_marks:
        Raw admission marks (not percentages), or ``None`` when unrecorded.
    semester_cgpas:
        Completed semester GPAs, oldest first. May be empty (semester 1).
    matric_total, fsc_total:
        The student's own stored maxima. When omitted, the documented
        training defaults are used.

    Missing marks become NaN (so the imputer fires) and a warning is emitted;
    they never become 0.0. Percentages are clamped to [0, 1] and an
    out-of-range value is reported rather than silently accepted.
    """
    warnings: list[str] = []
    sems = [float(s) for s in (semester_cgpas or [])]

    matric_raw = _percent(matric_marks, matric_total, DEFAULT_MATRIC_TOTAL)
    fsc_raw = _percent(fsc_marks, fsc_total, DEFAULT_FSC_TOTAL)

    if math.isnan(matric_raw):
        matric_pct = NAN
    else:
        matric_pct = min(max(matric_raw, 0.0), 1.0)
        if matric_raw != matric_pct:
            warnings.append(
                f"admission_marks_out_of_range: matric ratio {matric_raw:.4f} "
                "clamped to [0, 1]."
            )

    if math.isnan(fsc_raw):
        fsc_pct = NAN
    else:
        fsc_pct = min(max(fsc_raw, 0.0), 1.0)
        if fsc_raw != fsc_pct:
            warnings.append(
                f"admission_marks_out_of_range: fsc ratio {fsc_raw:.4f} "
                "clamped to [0, 1]."
            )

    # A gap or an average built from one known and one unknown mark would be a
    # fabricated number, so both stay NaN unless both marks are present.
    if math.isnan(matric_pct) or math.isnan(fsc_pct):
        admission_avg = NAN
        admission_gap = NAN
    else:
        admission_avg = (matric_pct + fsc_pct) / 2.0
        admission_gap = fsc_pct - matric_pct

    if sems:
        sem_mean = sum(sems) / len(sems)
        sem_last = sems[-1]
        sem_weighted = _weighted_mean(sems)
        sem_std = _std(sems)
        sem_min = min(sems)
        sem_max = max(sems)
        sem_delta = sem_last - sems[0]
        sem_vs_admission = (
            sem_mean - admission_avg * 4.0 if not math.isnan(admission_avg) else NAN
        )
    else:
        # No semester yet is real information (semester 1), not missing data:
        # the training rows for that semester carry the same zeros.
        sem_mean = 0.0
        sem_last = 0.0
        sem_weighted = 0.0
        sem_std = 0.0
        sem_min = 0.0
        sem_max = 0.0
        sem_delta = 0.0
        sem_vs_admission = 0.0

    features = {
        "matric_pct": matric_pct,
        "fsc_pct": fsc_pct,
        "admission_avg": admission_avg,
        "admission_gap": admission_gap,
        "sem_count": float(len(sems)),
        "sem_mean": sem_mean,
        "sem_last": sem_last,
        "sem_weighted": sem_weighted,
        "sem_trend": _trend(sems),
        "sem_delta": sem_delta,
        "sem_std": sem_std,
        "sem_min": sem_min,
        "sem_max": sem_max,
        "sem_vs_admission": sem_vs_admission,
    }
    return features, warnings


def build_features(
    matric_marks,
    fsc_marks,
    semester_cgpas: list[float] | None,
    *,
    matric_total=None,
    fsc_total=None,
) -> dict[str, float]:
    """Convenience wrapper returning only the feature dict."""
    features, _ = build_features_and_warnings(
        matric_marks,
        fsc_marks,
        semester_cgpas,
        matric_total=matric_total,
        fsc_total=fsc_total,
    )
    return features


def build_matrix(
    matric_marks,
    fsc_marks,
    semester_cgpas,
    *,
    matric_totals=None,
    fsc_totals=None,
) -> "object":
    """Vectorised version for training: accepts array-likes of equal length.

    ``semester_cgpas`` is a list of per-student lists. pandas is imported here
    rather than at module import so that serving never needs it unless the
    caller already has it.
    """
    import pandas as pd

    def _at(values, index):
        return None if values is None else values[index]

    features = [
        build_features(
            m,
            f,
            list(sems),
            matric_total=_at(matric_totals, i),
            fsc_total=_at(fsc_totals, i),
        )
        for i, (m, f, sems) in enumerate(zip(matric_marks, fsc_marks, semester_cgpas))
    ]
    return pd.DataFrame(features, columns=FEATURE_ORDER)


def frame_from_raw(df, completed_semesters: int):
    """Build the training matrix from a raw dataset frame.

    ``completed_semesters`` is how many semesters have already been completed
    when the prediction is made: for ``semester_N`` datasets it is ``N - 1``.
    The datasets carry no totals, so the documented defaults apply.
    """
    sems = [
        [row[semester_column(i)] for i in range(1, completed_semesters + 1)]
        for _, row in df.iterrows()
    ]
    return build_matrix(
        df[RAW_COLUMN["matric"]].to_numpy(),
        df[RAW_COLUMN["fsc"]].to_numpy(),
        sems,
    )
