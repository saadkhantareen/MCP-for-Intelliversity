"""Train the bundled CGPA models — one per "current semester".

The university does not train anything and cannot supply its own dataset: the
eight models shipped with the application are trained here, once, from the
generated datasets, and deployed as ``joblib`` artifacts. At request time the
server only turns a student's academic record into the same feature vector and
calls the model for their current semester.

Honest evaluation
-----------------
The dataset is split FIRST, once per semester, into an 80/20 train/hold-out
partition with ``train_test_split(test_size=0.2, random_state=42)``. Everything
that can influence the choice of model — the 5-fold cross-validation
leaderboard, the residual distribution, the 90% band half-width and the
residual standard deviation — is computed on the **training split only**. The
hold-out split is then touched to score, unchanged:

* the selected estimator,
* four naive baselines (mean, admission-only linear, last SGPA, persistence),
* the admission-only vs all-feature ablation,
* the guardrail (post-processing rule),
* the empirical coverage of the 90% band, before and after the guardrail,
* the at-risk probability calibration at CGPA 2.0.

The estimator that is *shipped* (``sem{N}.joblib``) is refit on **100% of the
rows**. The reported ``holdout`` numbers therefore describe the training-split
model, not the shipped one; the two differ only by the extra 20% of rows. This
distinction is recorded in ``manifest.json`` (``training.shipped_refit``).

Usage (from the backend root)::

    uv run --no-project --python 3.12 --with-requirements ml/requirements-train.txt python ml/train.py

Debugging pass (Ridge/ElasticNet/KNN only, skips the tree ensembles)::

    uv run --no-project --python 3.12 --with-requirements ml/requirements-train.txt python ml/train.py --fast

Outputs:
    ml/artifacts/sem{1..8}.joblib     fitted sklearn Pipeline (imputer + scaler + model)
    ml/artifacts/manifest.json        schema_version 2 contract; written last, atomically
    ml/metrics.csv                    CV leaderboard on the training split
    ml/evaluation/baselines.csv       selected model + four naive baselines, same test split
    ml/evaluation/ablation.csv        admission-only vs all-14-feature Ridge
    ml/evaluation/guardrail_impact.csv  MAE / fire rate before-after, split by reason
    ml/evaluation/coverage.csv        empirical coverage of the 90% band, before/after
    ml/evaluation/at_risk_calibration.csv  predicted P(final<2.0) vs observed, deciles
    ml/evaluation/eda.json            residual distribution diagnostics
    ml/evaluation/summary.json        headline numbers per semester
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.base import clone
from sklearn.ensemble import (
    ExtraTreesRegressor,
    GradientBoostingRegressor,
    HistGradientBoostingRegressor,
    RandomForestRegressor,
)
from sklearn.impute import SimpleImputer
from sklearn.linear_model import ElasticNet, Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import KFold, cross_val_predict, train_test_split
from sklearn.neighbors import KNeighborsRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ML_DIR = Path(__file__).resolve().parent
DATASET_DIR = BACKEND_ROOT.parent / "model prediction"
ARTIFACT_DIR = ML_DIR / "artifacts"
EVALUATION_DIR = ML_DIR / "evaluation"
METRICS_CSV = ML_DIR / "metrics.csv"

sys.path.insert(0, str(BACKEND_ROOT))

from apps.predictions import policy  # noqa: E402
from apps.predictions.feature_engineering import (  # noqa: E402
    FEATURE_ORDER,
    SEMESTER_COUNT,
    frame_from_raw,
    semester_column,
)

# ---------------------------------------------------------------------------
# Contract constants. Do not change these: the shipped model must stay
# comparable to the previous one and the manifest is a serving contract.
# ---------------------------------------------------------------------------
RANDOM_STATE = 42
TARGET = "Final_CGPA"
TEST_SIZE = 0.2
CV_FOLDS = 5
SCHEMA_VERSION = 2

#: Admission-only feature set used by the baseline and one half of the ablation.
ADMISSION_FEATURES = ["matric_pct", "fsc_pct", "admission_avg", "admission_gap"]
ADMISSION_FEATURE_INDICES = [FEATURE_ORDER.index(name) for name in ADMISSION_FEATURES]

#: Quantiles of |training OOF residual| recorded for the interval calibration.
ABS_RESIDUAL_QUANTILES = (0.5, 0.8, 0.9, 0.95)
ABS_RESIDUAL_QUANTILE_LABELS = ("0.5", "0.8", "0.9", "0.95")

#: Quality cuts for the 90% band and the at-risk probability.
COVERAGE_TARGET = 0.90
CGPA_LO = 0.0
CGPA_HI = 4.0


# ---------------------------------------------------------------------------
# Model zoo
# ---------------------------------------------------------------------------
def model_zoo(fast: bool = False) -> dict[str, object]:
    """Candidate estimators.

    ``--fast`` keeps only the cheap estimators (Ridge/ElasticNet/KNN) while
    debugging; the shipped leaderboard must come from a full run.

    On this dataset the linear models win and the tree ensembles are
    consistently worse out-of-fold: ``Final_CGPA`` was generated as a smooth
    function of the admission marks plus noise, so there is no non-linear
    structure for the ensembles to find and their extra variance only hurts.
    The ensembles are kept as an honest benchmark, not because they are
    expected to win. (The old docstring claimed the opposite; that was the
    discarded model's result, not the shipped one.)
    """
    zoo: dict[str, object] = {
        "Ridge": Ridge(alpha=1.0),
        "ElasticNet": ElasticNet(alpha=0.01, l1_ratio=0.5, max_iter=5000),
        "KNN": KNeighborsRegressor(n_neighbors=15),
    }
    if fast:
        return zoo

    zoo["RandomForest"] = RandomForestRegressor(
        n_estimators=300, min_samples_leaf=2, n_jobs=-1, random_state=RANDOM_STATE
    )
    zoo["ExtraTrees"] = ExtraTreesRegressor(
        n_estimators=300, min_samples_leaf=1, n_jobs=-1, random_state=RANDOM_STATE
    )
    zoo["GradientBoosting"] = GradientBoostingRegressor(
        n_estimators=200, learning_rate=0.05, max_depth=3, random_state=RANDOM_STATE
    )
    zoo["HistGradientBoosting"] = HistGradientBoostingRegressor(
        max_iter=300, learning_rate=0.05, random_state=RANDOM_STATE
    )
    try:  # xgboost is optional: the app must still train without it
        from xgboost import XGBRegressor

        zoo["XGBoost"] = XGBRegressor(
            n_estimators=400,
            learning_rate=0.05,
            max_depth=4,
            subsample=0.9,
            colsample_bytree=0.9,
            n_jobs=-1,
            random_state=RANDOM_STATE,
            tree_method="hist",
        )
    except ImportError:  # pragma: no cover
        print("! xgboost not installed, skipping it")
    return zoo


def make_pipeline(estimator) -> Pipeline:
    """The exact serving pipeline: median impute -> standardise -> regress."""
    return Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("model", estimator),
        ]
    )


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _temp_path(path: Path) -> Path:
    """A uniquely named temporary file in the same directory as ``path``."""
    descriptor, name = tempfile.mkstemp(
        dir=str(path.parent), prefix=path.name + ".", suffix=".tmp"
    )
    os.close(descriptor)
    return Path(name)


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    """Write ``payload`` to ``path`` via a temp file + ``os.replace``.

    A reader never observes a half-written file: the rename is atomic on the
    same filesystem.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = _temp_path(path)
    try:
        temporary.write_bytes(payload)
        os.replace(temporary, path)
    finally:
        if temporary.exists():  # only when the write/replace failed
            temporary.unlink()


def atomic_write_text(path: Path, text: str) -> None:
    atomic_write_bytes(path, text.encode("utf-8"))


def atomic_write_json(path: Path, payload: object) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2, allow_nan=False) + "\n")


def atomic_dump_joblib(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = _temp_path(path)
    try:
        joblib.dump(payload, temporary, compress=3)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def regression_metrics(y_true, y_pred) -> dict[str, float]:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    return {
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "r2": float(r2_score(y_true, y_pred)),
    }


def skewness(values) -> float | None:
    """Population skewness (third standardised moment)."""
    values = np.asarray(values, dtype=float)
    deviation = values - values.mean()
    sigma = values.std(ddof=0)
    if sigma == 0:
        return None
    return float(np.mean((deviation / sigma) ** 3))


def excess_kurtosis(values) -> float | None:
    """Excess kurtosis (fourth standardised moment minus 3)."""
    values = np.asarray(values, dtype=float)
    deviation = values - values.mean()
    sigma = values.std(ddof=0)
    if sigma == 0:
        return None
    return float(np.mean((deviation / sigma) ** 4) - 3.0)


def correlation(a, b) -> float | None:
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    if a.size < 2 or b.size != a.size:
        return None
    if not np.all(np.isfinite(a)) or not np.all(np.isfinite(b)):
        return None
    if a.std() == 0 or b.std() == 0:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def band(centre: float, half_width: float) -> tuple[float, float]:
    """The serving band: clamp the centre to 0..4, then clamp the edges.

    Mirrors ``policy.interval_and_risk`` so the coverage measured here is the
    coverage the API actually reports.
    """
    centre = float(centre)
    centre = min(max(centre, CGPA_LO), CGPA_HI)
    low = max(CGPA_LO, centre - half_width)
    high = min(CGPA_HI, centre + half_width)
    if high < low:  # only possible with a negative half-width; keep sane
        low, high = high, low
    return low, high


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def load_semester(
    semester: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, list[list[float]], Path]:
    """Raw frame, feature matrix, target, per-row semester history, source path."""
    path = DATASET_DIR / f"dataset_semester_{semester}.xlsx"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} is missing. The eight datasets must live in 'model prediction/'."
        )
    raw = pd.read_excel(path)
    completed = semester - 1

    # ``frame_from_raw`` is the shared training/serving feature contract: for
    # semester N it reads Sem1..Sem(N-1), so no future semester can leak.
    X = frame_from_raw(raw, completed_semesters=completed)
    y = raw[TARGET].astype(float)

    columns = [semester_column(i) for i in range(1, completed + 1)]
    if columns:
        history = [[float(value) for value in row] for row in raw[columns].to_numpy()]
    else:
        history = [[] for _ in range(len(raw))]
    return raw, X, y, history, path


# ---------------------------------------------------------------------------
# Per-semester honest evaluation
# ---------------------------------------------------------------------------
def run_semester(semester: int, zoo: dict[str, object]) -> dict:
    """Evaluate one semester and return manifest/eval payloads.

    The split happens first; the hold-out partition is only ever *predicted*
    on below. The model-selection CV is confined to the training partition.
    """
    print(f"\n=== semester {semester} (completed: {semester - 1}) " + "=" * 30)
    raw, X, y, history, dataset_path = load_semester(semester)
    n_rows = len(X)
    print(f"rows={n_rows} features={X.shape[1]}")

    # --- SPLIT FIRST -------------------------------------------------------
    # Splitting the index array with the same seed produces exactly the
    # partition ``train_test_split(X, y, ...)`` would; the index form is used
    # so the raw semester histories stay aligned with their feature rows.
    row_index = np.arange(n_rows)
    train_index, test_index = train_test_split(
        row_index, test_size=TEST_SIZE, random_state=RANDOM_STATE
    )

    # Everything below fits and predicts on plain float arrays. The serving
    # path calls ``pipeline.predict([[f0, ..., f13]])`` with a Python list, so
    # the fitted pipeline must NOT carry scikit-learn feature-name metadata;
    # otherwise every request emits "X does not have valid feature names".
    # The feature-order contract lives in manifest.json -> feature_order, not
    # in the pickled sklearn state.
    feature_values = X.to_numpy(dtype=float)
    target_values = y.to_numpy(dtype=float)
    X_train = feature_values[train_index]
    X_test = feature_values[test_index]
    y_train_np = target_values[train_index]
    y_test_np = target_values[test_index]
    history_train = [history[int(i)] for i in train_index]
    history_test = [history[int(i)] for i in test_index]
    print(f"train={len(train_index)} test={len(test_index)}")

    # --- MODEL SELECTION: 5-fold CV on the TRAINING SPLIT ONLY ------------
    kfold = KFold(n_splits=CV_FOLDS, shuffle=True, random_state=RANDOM_STATE)
    leaderboard: list[dict] = []
    oof_by_model: dict[str, np.ndarray] = {}
    for name, estimator in zoo.items():
        started = time.time()
        oof = cross_val_predict(
            make_pipeline(estimator), X_train, y_train_np, cv=kfold, n_jobs=1
        )
        oof_by_model[name] = oof
        leaderboard.append(
            {
                "model": name,
                **regression_metrics(y_train_np, oof),
                "seconds": round(time.time() - started, 1),
            }
        )
    leaderboard_df = pd.DataFrame(leaderboard).sort_values(
        ["r2", "mae"], ascending=[False, True]
    )
    leaderboard_df = leaderboard_df.reset_index(drop=True)
    leaderboard_df["selected"] = leaderboard_df["model"] == leaderboard_df.iloc[0]["model"]
    print(leaderboard_df[["model", "mae", "rmse", "r2", "seconds"]].to_string(index=False))

    best_name = str(leaderboard_df.iloc[0]["model"])
    selected_cv = {
        "r2": float(leaderboard_df.iloc[0]["r2"]),
        "mae": float(leaderboard_df.iloc[0]["mae"]),
    }
    print(f"-> selected by training-split CV: {best_name}")

    # Training-split out-of-fold residuals of the SELECTED model. These drive
    # the residual standard deviation, the 90% band and the EDA statistics.
    selected_oof = np.asarray(oof_by_model[best_name], dtype=float)
    train_residuals = y_train_np - selected_oof
    abs_train_residuals = np.abs(train_residuals)
    residual_std = float(np.std(train_residuals, ddof=1))
    abs_quantile_values = [
        float(q) for q in np.quantile(abs_train_residuals, ABS_RESIDUAL_QUANTILES)
    ]
    abs_quantile_map = dict(zip(ABS_RESIDUAL_QUANTILE_LABELS, abs_quantile_values))
    half_width = float(abs_quantile_map["0.9"])

    # --- HOLD-OUT: refit on the training split, score once on the test split
    holdout_pipeline = make_pipeline(clone(zoo[best_name]))
    holdout_pipeline.fit(X_train, y_train_np)
    raw_pred = np.asarray(holdout_pipeline.predict(X_test), dtype=float)
    holdout = regression_metrics(y_test_np, raw_pred)
    print(
        f"hold-out  MAE={holdout['mae']:.4f}  RMSE={holdout['rmse']:.4f}  "
        f"R2={holdout['r2']:.4f}  (train-split model, never used for selection)"
    )

    # --- BASELINES on the same test split ---------------------------------
    train_mean = float(y_train_np.mean())
    baselines: dict[str, dict] = {}

    mean_prediction = np.full(len(y_test_np), train_mean, dtype=float)
    baselines["mean"] = {**regression_metrics(y_test_np, mean_prediction), "fallback_rows": 0}

    admission_pipeline = make_pipeline(Ridge(alpha=1.0))
    admission_pipeline.fit(
        X_train[:, ADMISSION_FEATURE_INDICES], y_train_np
    )
    admission_pred = np.asarray(
        admission_pipeline.predict(X_test[:, ADMISSION_FEATURE_INDICES]), dtype=float
    )
    baselines["admission_only_linear"] = {
        **regression_metrics(y_test_np, admission_pred),
        "fallback_rows": 0,
    }

    fallback_rows = int(sum(1 for row in history_test if not row))
    last_sgpa_prediction = np.array(
        [row[-1] if row else train_mean for row in history_test], dtype=float
    )
    baselines["last_sgpa"] = {
        **regression_metrics(y_test_np, last_sgpa_prediction),
        "fallback_rows": fallback_rows,
    }

    persistence_prediction = np.array(
        [float(np.mean(row)) if row else train_mean for row in history_test],
        dtype=float,
    )
    baselines["current_cgpa_persistence"] = {
        **regression_metrics(y_test_np, persistence_prediction),
        "fallback_rows": fallback_rows,
    }

    # --- ABLATION: admission-only Ridge vs all-14-feature Ridge ------------
    full_feature_pipeline = make_pipeline(Ridge(alpha=1.0))
    full_feature_pipeline.fit(X_train, y_train_np)
    all_feature_pred = np.asarray(full_feature_pipeline.predict(X_test), dtype=float)
    ablation = {
        "admission_only": {
            key: baselines["admission_only_linear"][key] for key in ("mae", "rmse", "r2")
        },
        "all_features": regression_metrics(y_test_np, all_feature_pred),
    }

    # --- GUARDRAIL IMPACT on the test split -------------------------------
    guarded = np.empty(len(raw_pred), dtype=float)
    fired = np.zeros(len(raw_pred), dtype=bool)
    reasons_per_row: list[set[str]] = []
    reason_counts: dict[str, int] = {}
    for position, (prediction, row_history) in enumerate(zip(raw_pred, history_test)):
        result = policy.guardrail(float(prediction), row_history)
        guarded[position] = (
            float(prediction) if result["value"] is None else float(result["value"])
        )
        fired[position] = bool(result["applied"])
        reasons = set(result["reasons"])
        reasons_per_row.append(reasons)
        for reason in result["reasons"]:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1

    fire_rate = float(fired.mean())
    guardrail_mae_before = float(mean_absolute_error(y_test_np, raw_pred))
    guardrail_mae_after = float(mean_absolute_error(y_test_np, guarded))
    guardrail = {
        "fire_rate": fire_rate,
        "mae_before": guardrail_mae_before,
        "mae_after": guardrail_mae_after,
    }
    print(
        f"guardrail fire={fire_rate:.3%}  MAE {guardrail_mae_before:.4f} -> "
        f"{guardrail_mae_after:.4f}  (reasons: {reason_counts or 'none'})"
    )

    # --- BAND COVERAGE BEFORE / AFTER THE GUARDRAIL -----------------------
    def empirical_coverage(centres) -> float:
        bounds = [band(float(centre), half_width) for centre in centres]
        lows = np.array([low for low, _ in bounds], dtype=float)
        highs = np.array([high for _, high in bounds], dtype=float)
        return float(np.mean((y_test_np >= lows) & (y_test_np <= highs)))

    coverage_before = empirical_coverage(raw_pred)
    coverage_after = empirical_coverage(guarded)
    print(
        f"90% band coverage before={coverage_before:.3%} after={coverage_after:.3%} "
        f"(target {COVERAGE_TARGET:.0%}, half-width={half_width:.4f})"
    )

    # --- AT-RISK CALIBRATION at 2.0 ---------------------------------------
    threshold = float(policy.AT_RISK_THRESHOLD)
    at_risk_probability = np.array(
        [
            policy.interval_and_risk(float(prediction), half_width, residual_std)[1]
            for prediction in raw_pred
        ],
        dtype=float,
    )
    observed_positive = (y_test_np < threshold).astype(float)
    order = np.argsort(at_risk_probability, kind="mergesort")
    deciles = np.array_split(order, 10)
    at_risk_rows: list[dict] = []
    for decile, positions in enumerate(deciles, start=1):
        at_risk_rows.append(
            {
                "semester": semester,
                "risk_decile": decile,  # 1 = lowest mean predicted risk
                "n_rows": int(len(positions)),
                "predicted_prob_mean": float(at_risk_probability[positions].mean()),
                "predicted_prob_min": float(at_risk_probability[positions].min()),
                "predicted_prob_max": float(at_risk_probability[positions].max()),
                "observed_positive_rate": float(observed_positive[positions].mean()),
                "observed_positive_count": int(observed_positive[positions].sum()),
                "at_risk_threshold": threshold,
            }
        )
    brier_score = float(np.mean((at_risk_probability - observed_positive) ** 2))

    # --- EDA: residual distribution (training-split OOF only) -------------
    last_semester_train = np.array(
        [row[-1] if row else np.nan for row in history_train], dtype=float
    )
    has_last_semester = np.isfinite(last_semester_train)
    residual_vs_last_semester = (
        correlation(
            train_residuals[has_last_semester], last_semester_train[has_last_semester]
        )
        if int(has_last_semester.sum()) >= 2
        else None
    )
    eda = {
        "semester": semester,
        "model": best_name,
        "n_train_rows": int(len(y_train_np)),
        "residual_mean": float(train_residuals.mean()),
        "residual_std_ddof1": residual_std,
        "skewness": skewness(train_residuals),
        "excess_kurtosis": excess_kurtosis(train_residuals),
        "abs_residual_quantiles": abs_quantile_map,
        "signed_residual_quantiles": {
            str(q): float(np.quantile(train_residuals, q))
            for q in (0.05, 0.25, 0.5, 0.75, 0.95)
        },
        "heteroscedasticity": {
            "diagnostic": "corr(|residual|, prediction)",
            "value": correlation(abs_train_residuals, selected_oof),
            "note": (
                "Diagnostic only, on training-split out-of-fold predictions. "
                "A near-zero value is consistent with homoscedasticity but does "
                "NOT prove it; a clearly non-zero value would disprove it."
            ),
        },
        "residual_vs_last_semester_sgpa": {
            "correlation": residual_vs_last_semester,
            "column": (
                semester_column(semester - 1) if semester > 1 else None
            ),
            "n_rows": int(has_last_semester.sum()),
            "note": (
                "None for semester 1: no semester has been completed, so there "
                "is no last SGPA."
                if semester == 1
                else None
            ),
        },
        "interval_90_source": "0.90 quantile of |training-split OOF residual|",
        "residual_std_source": "training-split OOF residual std (ddof=1)",
    }

    # --- SHIP: refit the selected model on ALL rows ------------------------
    ship_pipeline = make_pipeline(clone(zoo[best_name]))
    ship_pipeline.fit(feature_values, target_values)
    print(f"-> shipped pipeline refit on 100% of rows ({n_rows})")

    # ------------------------------------------------------------------
    # Flattened rows for the CSV evaluation artifacts
    # ------------------------------------------------------------------
    selected_label = best_name
    baseline_rows = [
        {
            "semester": semester,
            "selected_model": selected_label,
            "baseline": name,
            "n_test_rows": int(len(y_test_np)),
            "mae": values["mae"],
            "rmse": values["rmse"],
            "r2": values["r2"],
            "fallback_rows": values["fallback_rows"],
            "n_features": (
                len(ADMISSION_FEATURES) if name == "admission_only_linear" else None
            ),
        }
        for name, values in baselines.items()
    ]
    baseline_rows.append(
        {
            "semester": semester,
            "selected_model": selected_label,
            "baseline": "selected_model_holdout",
            "n_test_rows": int(len(y_test_np)),
            "mae": holdout["mae"],
            "rmse": holdout["rmse"],
            "r2": holdout["r2"],
            "fallback_rows": 0,
            "n_features": len(FEATURE_ORDER),
        }
    )

    ablation_rows = [
        {
            "semester": semester,
            "feature_set": "admission_only",
            "model": "Ridge(alpha=1.0)",
            "n_features": len(ADMISSION_FEATURES),
            "n_test_rows": int(len(y_test_np)),
            "mae": ablation["admission_only"]["mae"],
            "rmse": ablation["admission_only"]["rmse"],
            "r2": ablation["admission_only"]["r2"],
            "delta_mae_vs_admission_only": 0.0,
        },
        {
            "semester": semester,
            "feature_set": "all_14_features",
            "model": "Ridge(alpha=1.0)",
            "n_features": len(FEATURE_ORDER),
            "n_test_rows": int(len(y_test_np)),
            "mae": ablation["all_features"]["mae"],
            "rmse": ablation["all_features"]["rmse"],
            "r2": ablation["all_features"]["r2"],
            "delta_mae_vs_admission_only": (
                ablation["all_features"]["mae"] - ablation["admission_only"]["mae"]
            ),
        },
    ]

    def guardrail_row(subset: str, mask) -> dict:
        count = int(np.sum(mask))
        if count == 0:
            return {
                "semester": semester,
                "subset": subset,
                "n_rows": 0,
                "share_of_test_rows": 0.0,
                "mae_before": None,
                "mae_after": None,
                "mae_delta": None,
                "fire_rate": None,
            }
        before = float(mean_absolute_error(y_test_np[mask], raw_pred[mask]))
        after = float(mean_absolute_error(y_test_np[mask], guarded[mask]))
        return {
            "semester": semester,
            "subset": subset,
            "n_rows": count,
            "share_of_test_rows": float(count / len(y_test_np)),
            "mae_before": before,
            "mae_after": after,
            "mae_delta": after - before,
            "fire_rate": float(fired[mask].mean()),
        }

    guardrail_rows = [
        guardrail_row("all_test_rows", np.ones(len(y_test_np), dtype=bool)),
        guardrail_row("guardrail_fired", fired),
        guardrail_row("guardrail_not_fired", ~fired),
    ]
    for reason in ("history_drop_cap", "range_clamp"):
        mask = np.array([reason in reasons for reasons in reasons_per_row], dtype=bool)
        guardrail_rows.append(guardrail_row(reason, mask))

    coverage_rows = []
    for stage, centres, label in (
        ("before_guardrail", raw_pred, "raw_prediction"),
        ("after_guardrail", guarded, "guarded_prediction"),
    ):
        bounds = [band(float(centre), half_width) for centre in centres]
        lows = np.array([low for low, _ in bounds], dtype=float)
        highs = np.array([high for _, high in bounds], dtype=float)
        covered = (y_test_np >= lows) & (y_test_np <= highs)
        coverage_rows.append(
            {
                "semester": semester,
                "stage": stage,
                "n_test_rows": int(len(y_test_np)),
                "covered_rows": int(covered.sum()),
                "empirical_coverage": float(covered.mean()),
                "target_coverage": COVERAGE_TARGET,
                "half_width_90": half_width,
                "interval_centred_on": label,
                "clipped_to": "[0, 4]",
            }
        )

    summary_semester = {
        "model": best_name,
        "n_rows": int(n_rows),
        "n_train_rows": int(len(train_index)),
        "n_test_rows": int(len(test_index)),
        "cv": selected_cv,
        "holdout": holdout,
        "residual_std": residual_std,
        "interval_90": half_width,
        "baselines": baselines,
        "ablation_delta_mae_all_minus_admission": (
            ablation["all_features"]["mae"] - ablation["admission_only"]["mae"]
        ),
        "best_baseline": min(
            (name for name in baselines), key=lambda name: baselines[name]["mae"]
        ),
        "guardrail": guardrail,
        "coverage": {
            "before": coverage_before,
            "after": coverage_after,
            "target": COVERAGE_TARGET,
        },
        "at_risk": {
            "threshold": threshold,
            "observed_positive_rate": float(observed_positive.mean()),
            "observed_positive_count": int(observed_positive.sum()),
            "predicted_prob_mean": float(at_risk_probability.mean()),
            "brier_score": brier_score,
        },
    }

    dataset_meta = {
        "file": dataset_path.name,
        "sha256": sha256_file(dataset_path),
        "rows": int(n_rows),
    }

    return {
        "semester": semester,
        "ship_pipeline": ship_pipeline,
        "manifest": {
            "model": best_name,
            "completed_semesters": semester - 1,
            "n_rows": int(n_rows),
            "cv": selected_cv,
            "holdout": holdout,
            "residual_std": residual_std,
            "abs_residual_quantiles": abs_quantile_values,
            "interval_90": half_width,
            "leaderboard": leaderboard_df.to_dict(orient="records"),
            "baselines": baselines,
            "ablation": ablation,
            "guardrail": guardrail,
            "coverage": {
                "before": coverage_before,
                "after": coverage_after,
                "target": COVERAGE_TARGET,
            },
        },
        "leaderboard_rows": [
            {"semester": semester, **record}
            for record in leaderboard_df.to_dict(orient="records")
        ],
        "baseline_rows": baseline_rows,
        "ablation_rows": ablation_rows,
        "guardrail_rows": guardrail_rows,
        "coverage_rows": coverage_rows,
        "at_risk_rows": at_risk_rows,
        "eda": eda,
        "summary": summary_semester,
        "dataset": dataset_meta,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Train the eight bundled CGPA models with an honest evaluation."
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help=(
            "debug mode: evaluate only Ridge/ElasticNet/KNN and skip "
            "RandomForest, ExtraTrees, GradientBoosting, HistGradientBoosting "
            "and XGBoost. The shipped artifacts must come from a full run."
        ),
    )
    args = parser.parse_args(argv)
    mode = "fast" if args.fast else "full"

    run_started = time.time()
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    EVALUATION_DIR.mkdir(parents=True, exist_ok=True)

    zoo = model_zoo(fast=args.fast)
    print(f"=== training mode: {mode} ===")
    print(f"model zoo ({len(zoo)}): {', '.join(zoo)}")
    print(f"python={platform.python_version()} scikit-learn={sklearn.__version__} "
          f"pandas={pd.__version__} numpy={np.__version__}")

    manifest: dict = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target": TARGET,
        "feature_order": list(FEATURE_ORDER),
        "policy": dict(policy.DEFAULT_POLICY),
        "training": {
            "script": "ml/train.py",
            "random_state": RANDOM_STATE,
            "test_size": TEST_SIZE,
            "cv_folds": CV_FOLDS,
            "mode": mode,
            "selection": "cv_r2_then_mae_on_train_split",
            "shipped_refit": "all_rows",
            "zoo": list(zoo),
        },
        "library_versions": {
            "python": platform.python_version(),
            "scikit-learn": sklearn.__version__,
            "pandas": pd.__version__,
            "numpy": np.__version__,
        },
        "datasets": {},
        "semesters": {},
    }

    leaderboard_rows: list[dict] = []
    baseline_rows: list[dict] = []
    ablation_rows: list[dict] = []
    guardrail_rows: list[dict] = []
    coverage_rows: list[dict] = []
    at_risk_rows: list[dict] = []
    eda_semesters: dict[str, dict] = {}
    summary_semesters: dict[str, dict] = {}

    for semester in range(1, SEMESTER_COUNT + 1):
        result = run_semester(semester, zoo)

        # Artifact first: hashed AFTER the atomic write, so the manifest can
        # never describe a file that does not exist or is half-written.
        artifact_path = ARTIFACT_DIR / f"sem{semester}.joblib"
        atomic_dump_joblib(artifact_path, result["ship_pipeline"])
        artifact_sha256 = sha256_file(artifact_path)

        entry = dict(result["manifest"])
        entry["artifact"] = artifact_path.name
        entry["sha256"] = artifact_sha256
        # Keep the documented key order: artifact and hash first.
        manifest["semesters"][str(semester)] = {
            "artifact": entry["artifact"],
            "sha256": entry["sha256"],
            "model": entry["model"],
            "completed_semesters": entry["completed_semesters"],
            "n_rows": entry["n_rows"],
            "cv": entry["cv"],
            "holdout": entry["holdout"],
            "residual_std": entry["residual_std"],
            "abs_residual_quantiles": entry["abs_residual_quantiles"],
            "interval_90": entry["interval_90"],
            "leaderboard": entry["leaderboard"],
            "baselines": entry["baselines"],
            "ablation": entry["ablation"],
            "guardrail": entry["guardrail"],
            "coverage": entry["coverage"],
        }
        manifest["datasets"][str(semester)] = result["dataset"]

        leaderboard_rows.extend(result["leaderboard_rows"])
        baseline_rows.extend(result["baseline_rows"])
        ablation_rows.extend(result["ablation_rows"])
        guardrail_rows.extend(result["guardrail_rows"])
        coverage_rows.extend(result["coverage_rows"])
        at_risk_rows.extend(result["at_risk_rows"])
        eda_semesters[str(semester)] = result["eda"]
        summary_semesters[str(semester)] = result["summary"]

    elapsed_seconds = time.time() - run_started
    generated_at = manifest["generated_at"]

    # --- evaluation artifacts (written before the manifest) ---------------
    atomic_write_text(
        METRICS_CSV,
        pd.DataFrame(leaderboard_rows)[
            ["semester", "model", "mae", "rmse", "r2", "seconds", "selected"]
        ].to_csv(index=False),
    )
    atomic_write_text(
        EVALUATION_DIR / "baselines.csv",
        pd.DataFrame(baseline_rows)[
            [
                "semester",
                "selected_model",
                "baseline",
                "n_test_rows",
                "mae",
                "rmse",
                "r2",
                "fallback_rows",
                "n_features",
            ]
        ].to_csv(index=False),
    )
    atomic_write_text(
        EVALUATION_DIR / "ablation.csv",
        pd.DataFrame(ablation_rows).to_csv(index=False),
    )
    atomic_write_text(
        EVALUATION_DIR / "guardrail_impact.csv",
        pd.DataFrame(guardrail_rows)[
            [
                "semester",
                "subset",
                "n_rows",
                "share_of_test_rows",
                "mae_before",
                "mae_after",
                "mae_delta",
                "fire_rate",
            ]
        ].to_csv(index=False),
    )
    atomic_write_text(
        EVALUATION_DIR / "coverage.csv",
        pd.DataFrame(coverage_rows).to_csv(index=False),
    )
    atomic_write_text(
        EVALUATION_DIR / "at_risk_calibration.csv",
        pd.DataFrame(at_risk_rows).to_csv(index=False),
    )

    eda_payload = {
        "generated_at": generated_at,
        "model": "selected model per semester, refit on the training split only",
        "residual_source": (
            "out-of-fold predictions from 5-fold CV on the training split; the "
            "hold-out split is never used for any statistic in this file"
        ),
        "semesters": eda_semesters,
    }
    atomic_write_json(EVALUATION_DIR / "eda.json", eda_payload)

    summary_payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "run": {
            "script": "ml/train.py",
            "mode": mode,
            "wall_clock_seconds": round(elapsed_seconds, 1),
            "random_state": RANDOM_STATE,
            "test_size": TEST_SIZE,
            "cv_folds": CV_FOLDS,
            "shipped_model_refit": "all_rows",
            "reported_holdout_model": "training_split_refit",
            "zoo": list(zoo),
        },
        "semesters": summary_semesters,
    }
    atomic_write_json(EVALUATION_DIR / "summary.json", summary_payload)

    # --- manifest LAST, atomically ----------------------------------------
    atomic_write_json(ARTIFACT_DIR / "manifest.json", manifest)
    final_sha = sha256_file(ARTIFACT_DIR / "manifest.json")

    print("\n" + "=" * 72)
    print(f"mode={mode}  elapsed={elapsed_seconds:.1f}s")
    print(f"manifest sha256={final_sha}")
    print(f"artifacts: {ARTIFACT_DIR}")
    print(f"evaluation: {EVALUATION_DIR}")
    print(f"written: metrics.csv, baselines.csv, ablation.csv, guardrail_impact.csv,")
    print(f"         coverage.csv, at_risk_calibration.csv, eda.json, summary.json")


if __name__ == "__main__":
    main()
