"""Inference service for the bundled CGPA models.

The models are **pre-trained and shipped with the application**. A university
never trains, tunes, or supplies data of its own: the eight pipelines in
``ml/artifacts`` are the product's, exactly like a vendor-supplied pricing
engine. At request time this module only

1. reads the student's own record from the tenant database,
2. converts it to the feature vector the models were trained on, and
3. returns the prediction.

Scope, stated plainly: the models were trained on **synthetic data only**.
Neither the model nor this service has been validated against real student
cohorts. Every response therefore carries a disclaimer, and the numbers are an
estimate, not a result.

Artifact trust model: the joblib files ship with the release and are trusted to
the same degree as the application code. That trust is *checked*, not assumed:
each file is hashed against ``manifest.json``, its basename is allowlisted, and
the manifest's feature order and scikit-learn version must match the running
process. A mismatch raises and the endpoint answers 503 rather than serving a
prediction the contract does not describe.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import threading
import time
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from apps.predictions import policy
from apps.predictions.feature_engineering import (
    DEFAULT_FSC_TOTAL,
    DEFAULT_MATRIC_TOTAL,
    FEATURE_ORDER,
    SEMESTER_COUNT,
    build_features_and_warnings,
)

logger = logging.getLogger(__name__)

#: Basename allowlist. Anything else in the manifest is rejected: the loader
#: must never be talked into opening an arbitrary path.
ARTIFACT_PATTERN = re.compile(r"^sem([1-8])\.joblib$")

#: Re-entrant: get_pipeline() holds this while resolving the manifest, which
#: itself takes the lock. A plain Lock deadlocks on the first prediction.
_lock = threading.RLock()
_pipelines: dict[int, object] = {}
_manifest: dict | None = None
_hash_cache: dict[tuple[str, int, int], str] = {}

#: Process-lifetime counters, exposed for tests and operators. No PII.
_counters = {
    "predictions": 0,
    "guardrail_fired": 0,
    "admission_missing": 0,
    "artifact_load_failures": 0,
    "not_meaningful": 0,
}


class ArtifactError(ImproperlyConfigured):
    """The shipped model bundle is missing, unreadable, or inconsistent."""


class InvalidSemester(ValueError):
    """The requested semester cannot be served for this student."""


def get_counters() -> dict:
    return dict(_counters)


def reset_counters() -> None:
    for key in _counters:
        _counters[key] = 0


def artifacts_dir() -> Path:
    return Path(settings.ML_ARTIFACTS_DIR)


def _sha256_file(path: Path) -> str:
    stat = path.stat()
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    cached = _hash_cache.get(key)
    if cached:
        return cached
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    value = digest.hexdigest()
    _hash_cache[key] = value
    return value


def load_manifest() -> dict:
    """Load, validate and cache ``manifest.json`` written by ``ml/train.py``."""
    global _manifest
    if _manifest is not None:
        return _manifest

    with _lock:
        if _manifest is not None:
            return _manifest

        path = artifacts_dir() / "manifest.json"
        if not path.is_file():
            raise ArtifactError(
                f"No model manifest at {path}. Run `python ml/train.py` before serving."
            )
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ArtifactError(f"manifest.json is not valid JSON: {exc}") from exc
        except OSError as exc:
            raise ArtifactError(f"manifest.json could not be read: {exc}") from exc

        if manifest.get("schema_version") != 2:
            raise ArtifactError(
                "manifest.json has an unsupported schema_version; "
                "retrain with the current ml/train.py."
            )
        if manifest.get("feature_order") != FEATURE_ORDER:
            raise ArtifactError(
                "manifest feature_order does not match the serving contract; "
                "the artifacts and this build are out of sync."
            )

        expected = f"{_sklearn_major_minor()}"
        recorded = str(manifest.get("library_versions", {}).get("scikit-learn", ""))
        if _major_minor(recorded) != expected:
            raise ArtifactError(
                f"scikit-learn {recorded or 'unknown'} trained these artifacts but "
                f"{expected} is installed; predictions are not guaranteed compatible."
            )

        _manifest = manifest
    return _manifest


def _major_minor(version: str) -> str:
    parts = str(version).split(".")
    return ".".join(parts[:2]) if len(parts) >= 2 else str(version)


def _sklearn_major_minor() -> str:
    try:
        import sklearn  # imported lazily: only needed when serving predictions
    except ImportError as exc:  # narrow image without the ML stack
        raise ArtifactError(
            "scikit-learn is not installed in this deployment, so the shipped "
            "models cannot be served."
        ) from exc

    return _major_minor(sklearn.__version__)


def semester_meta(semester: int) -> dict:
    manifest = load_manifest()
    meta = manifest.get("semesters", {}).get(str(semester))
    if not meta:
        raise ArtifactError(f"Manifest has no model for semester {semester}")
    return meta


def _verified_path(semester: int, meta: dict) -> Path:
    name = str(meta.get("artifact", ""))
    match = ARTIFACT_PATTERN.match(name)
    if not match or int(match.group(1)) != semester:
        raise ArtifactError(
            f"manifest artifact name {name!r} is not an allowlisted sem{N}.joblib"
        )

    root = artifacts_dir().resolve()
    path = (root / name).resolve()
    if path.parent != root:
        raise ArtifactError(f"artifact {name!r} resolves outside the artifacts directory")
    if not path.is_file():
        raise ArtifactError(f"artifact {name!r} is missing from {root}")

    expected = str(meta.get("sha256") or "")
    if not expected:
        raise ArtifactError(f"manifest has no sha256 for {name!r}; retrain the models")
    actual = _sha256_file(path)
    if actual != expected:
        raise ArtifactError(
            f"artifact {name!r} does not match its manifest hash "
            f"(expected {expected[:12]}…, found {actual[:12]}…)"
        )
    return path


def get_pipeline(semester: int):
    """Return the verified, fitted pipeline for a 'current semester' (1-8)."""
    if not 1 <= semester <= SEMESTER_COUNT:
        raise InvalidSemester(f"semester must be between 1 and {SEMESTER_COUNT}")

    with _lock:
        if semester in _pipelines:
            return _pipelines[semester]

        meta = semester_meta(semester)
        path = _verified_path(semester, meta)

        import joblib  # lazy: a non-ML deployment can import this module

        try:
            pipeline = joblib.load(path)
        except Exception as exc:  # unpickling, version, or corrupt file
            _counters["artifact_load_failures"] += 1
            logger.error("artifact_load_failed semester=%s file=%s error=%s",
                         semester, path.name, type(exc).__name__)
            raise ArtifactError(f"artifact {path.name!r} could not be loaded: {exc}") from exc

        feature_count = getattr(pipeline, "n_features_in_", None)
        if feature_count is not None and int(feature_count) != len(FEATURE_ORDER):
            raise ArtifactError(
                f"artifact {path.name!r} expects {feature_count} features but the "
                f"serving contract has {len(FEATURE_ORDER)}"
            )

        _pipelines[semester] = pipeline
        return pipeline


# --------------------------------------------------------------------------
# Provenance and health
# --------------------------------------------------------------------------


def _model_version(meta: dict, manifest: dict) -> dict:
    """Content hash + training timestamp. A timestamp alone cannot tell you
    whether the file on disk is the one that produced an old response."""
    digest = str(meta.get("sha256") or "")
    trained_at = str(manifest.get("generated_at") or "")
    return {
        "name": meta.get("model", "unknown"),
        "version": f"{digest[:12]}+{trained_at}" if digest else trained_at,
        "version_hash": digest,
        "trained_at": trained_at,
    }


def health_check() -> dict:
    """Verify every shipped artifact: presence, hash, loadability."""
    semesters: dict[str, dict] = {}
    try:
        manifest = load_manifest()
    except ArtifactError as exc:
        return {
            "ok": False,
            "error": str(exc),
            "semesters": {
                str(n): {"ok": False, "error": "manifest unavailable"}
                for n in range(1, SEMESTER_COUNT + 1)
            },
        }

    for semester in range(1, SEMESTER_COUNT + 1):
        entry = {"ok": False, "sha256": None, "error": None}
        try:
            meta = semester_meta(semester)
            path = _verified_path(semester, meta)
            entry["sha256"] = _sha256_file(path)
            get_pipeline(semester)
            entry["ok"] = True
        except ArtifactError as exc:
            entry["error"] = str(exc)
        semesters[str(semester)] = entry

    ok = all(entry["ok"] for entry in semesters.values())
    return {
        "ok": ok,
        "checked_at": manifest.get("generated_at"),
        "schema_version": manifest.get("schema_version"),
        "semesters": semesters,
    }


def model_info(include_health: bool = True) -> dict:
    """Provenance for the admin portal: which model serves which semester, how
    it scored offline, and (optionally) the per-artifact health verdict."""
    manifest = load_manifest()
    payload = {
        "target": manifest["target"],
        "generated_at": manifest["generated_at"],
        "schema_version": manifest.get("schema_version"),
        "library_versions": manifest["library_versions"],
        "policy": manifest.get("policy", policy.DEFAULT_POLICY),
        "data_scope": "synthetic training data only; not validated on real cohorts",
        "semesters": {
            sem: {
                "model": meta["model"],
                "completed_semesters": meta["completed_semesters"],
                "cv_r2": round(meta["cv"]["r2"], 4),
                "holdout_mae": round(meta["holdout"]["mae"], 4),
                "holdout_r2": round(meta["holdout"]["r2"], 4),
                "artifact_sha256": str(meta.get("sha256") or ""),
            }
            for sem, meta in manifest["semesters"].items()
        },
    }
    if include_health:
        payload["health"] = health_check()
    return payload


# --------------------------------------------------------------------------
# Student -> features
# --------------------------------------------------------------------------


def _term_key(record):
    """Deterministic ordering inside one tenant.

    ``start_date`` alone ties when two terms start the same day (a common data
    entry artefact); the name and the primary key break the tie so the history
    order is stable across requests.
    """
    term = record.term
    return (
        term.start_date,
        getattr(term, "name", "") or "",
        str(term.id),
    )


def semester_history(student, records=None) -> tuple[list[float], list[str]]:
    """Completed semester GPAs, oldest first, plus data-quality anomalies.

    Completion is decided from the term record's ``status``:

    * ``ENROLLED`` with ``sgpa == 0`` → in progress, skipped.
    * ``COMPLETED`` / ``FAILED`` / ``DROPPED_OUT`` → finalised. A finalised
      ``0.0`` is a genuine fail and is kept as ``0.0``; it is not "ungraded".
    * ``ENROLLED`` with ``sgpa > 0`` → kept, because tenants that never
      finalise the status flag would otherwise lose their whole history.

    Known limitation: there is no separate "finalised" boolean on
    ``StudentTermRecord``, so a deferred term that is still marked ``ENROLLED``
    is indistinguishable from a term in progress and is treated as absent. The
    remaining semesters are not compressed to hide the gap, but the gap itself
    is not represented in the feature vector either.
    """
    if records is None:
        records = student.term_records.select_related("term").all()

    ordered = sorted(records, key=_term_key)

    history: list[float] = []
    anomalies: list[str] = []
    seen_terms: set = set()

    for record in ordered:
        if record.term_id in seen_terms:
            anomalies.append("semester_history_duplicate_term")
            continue
        seen_terms.add(record.term_id)

        try:
            sgpa = float(record.sgpa)
        except (TypeError, ValueError):
            anomalies.append("semester_history_non_numeric")
            continue

        finalised = record.status not in ("ENROLLED", None, "")
        if not finalised and sgpa == 0:
            continue  # term in progress
        if not math.isfinite(sgpa):
            anomalies.append("semester_history_non_finite")
            continue
        if sgpa < 0 or sgpa > 4:
            anomalies.append("semester_history_out_of_range")
            sgpa = min(max(sgpa, 0.0), 4.0)

        history.append(round(sgpa, 2))

    if len(history) > SEMESTER_COUNT - 1:
        anomalies.append("semester_history_truncated")
        history = history[: SEMESTER_COUNT - 1]

    return history, sorted(set(anomalies))


def resolve_semester(
    student, requested: int | None, history: list[float]
) -> tuple[int, list[str]]:
    """Which semester-N model applies, and whether an override discards data."""
    warnings: list[str] = []
    natural = min(len(history) + 1, SEMESTER_COUNT)
    semester = requested or natural

    if not 1 <= semester <= SEMESTER_COUNT:
        raise InvalidSemester(f"semester must be between 1 and {SEMESTER_COUNT}")
    if semester - 1 > len(history):
        raise InvalidSemester(
            f"Semester {semester} needs {semester - 1} completed semesters, "
            f"but only {len(history)} are on record."
        )
    if semester < natural:
        discarded = len(history) - (semester - 1)
        warnings.append(
            f"semester_override_discards_history: forecasting semester {semester} "
            f"ignores {discarded} completed semester(s) already on record."
        )
    return semester, warnings


def admission_marks(student) -> dict:
    """Matric / FSc marks with the student's own stored totals.

    Totals come from the record, never from a module constant, because boards
    and tests use different maxima. A missing total falls back to the documented
    training default and is reported.
    """
    admission = getattr(student, "admission", None)
    if admission is None:
        return {
            "matric": None,
            "fsc": None,
            "matric_total": DEFAULT_MATRIC_TOTAL,
            "fsc_total": DEFAULT_FSC_TOTAL,
            "entry_test_score": None,
        }
    return {
        "matric": admission.matric_obtained,
        "fsc": admission.fsc_obtained,
        "matric_total": admission.matric_total or DEFAULT_MATRIC_TOTAL,
        "fsc_total": admission.fsc_total or DEFAULT_FSC_TOTAL,
        "entry_test_score": admission.entry_test_score,
    }


def _json_safe(features: dict) -> dict:
    """NaN is not valid JSON (browsers reject it) and not valid jsonb."""
    return {
        key: (None if not isinstance(value, (int, float)) or not math.isfinite(value)
              else round(float(value), 6))
        for key, value in features.items()
    }


def _top_drivers(pipeline, limit: int = 5) -> list[dict]:
    """The model's strongest weights, largest first.

    These are **weights, not causes**: the inputs are standardised, so the
    magnitude is comparable across features, but a weight says how the model
    uses a number, not what would change a student's outcome.
    """
    model = pipeline.named_steps.get("model")

    coefficients = getattr(model, "coef_", None)
    if coefficients is not None:
        coefficients = coefficients.ravel()
        ranked = sorted(
            zip(FEATURE_ORDER, coefficients), key=lambda p: abs(float(p[1])), reverse=True
        )
        total = sum(abs(float(coef)) for _, coef in ranked) or 1.0
        return [
            {
                "feature": name,
                "importance": round(abs(float(coef)) / total, 4),
                "direction": 1 if float(coef) >= 0 else -1,
            }
            for name, coef in ranked[:limit]
        ]

    importances = getattr(model, "feature_importances_", None)
    if importances is not None:
        ranked = sorted(
            zip(FEATURE_ORDER, importances), key=lambda p: abs(float(p[1])), reverse=True
        )
        total = sum(abs(float(score)) for _, score in ranked) or 1.0
        return [
            {
                "feature": name,
                "importance": round(abs(float(score)) / total, 4),
                "direction": 0,
            }
            for name, score in ranked[:limit]
        ]

    return []


DISCLAIMER = "Statistical estimate from a pre-trained model; not an official result."


def predict_student(student, semester: int | None = None, records=None) -> dict:
    """Full forecast for one student, scoped to their own tenant database."""
    started = time.perf_counter()

    history, anomalies = semester_history(student, records=records)
    semester, semester_warnings = resolve_semester(student, semester, history)
    used = history[: semester - 1]
    admission = admission_marks(student)

    features, feature_warnings = build_features_and_warnings(
        admission["matric"],
        admission["fsc"],
        used,
        matric_total=admission["matric_total"],
        fsc_total=admission["fsc_total"],
    )

    warnings = list(anomalies) + list(semester_warnings) + list(feature_warnings)

    admission_missing = math.isnan(features["matric_pct"]) and math.isnan(
        features["fsc_pct"]
    )

    # Semester 1 with no admission marks and no history has no informative
    # input at all. Returning the imputer's median as a confident-looking CGPA
    # would be the most misleading thing this service could do.
    meaningful = not (semester == 1 and admission_missing and not used)

    if admission_missing:
        _counters["admission_missing"] += 1
        if meaningful:
            warnings.append(
                "admission_marks_missing: matric and FSc marks are not recorded, so "
                "the admission side of this forecast comes from the training median."
            )

    manifest = load_manifest()
    meta = semester_meta(semester)

    if meaningful:
        pipeline = get_pipeline(semester)
        row = [[float(features[name]) for name in FEATURE_ORDER]]
        raw = float(pipeline.predict(row)[0])
    else:
        pipeline = None
        raw = float("nan")

    guard = policy.guardrail(
        raw,
        used,
        min_avg=settings.CGPA_GUARDRAIL_MIN_AVG,
        max_drop=settings.CGPA_GUARDRAIL_MAX_DROP,
        lo=settings.CGPA_MIN,
        hi=settings.CGPA_MAX,
    )

    display_value = guard["value"]
    band_source = display_value if display_value is not None else raw
    interval, _ = policy.interval_and_risk(
        band_source,
        meta.get("interval_90"),
        meta.get("residual_std"),
        threshold=settings.CGPA_AT_RISK_THRESHOLD,
        lo=settings.CGPA_MIN,
        hi=settings.CGPA_MAX,
    )
    # Risk is computed from the RAW output on purpose: a guardrail that lifts a
    # forecast must not also quiet the early-warning signal.
    _, at_risk = policy.interval_and_risk(
        raw,
        None,
        meta.get("residual_std"),
        threshold=settings.CGPA_AT_RISK_THRESHOLD,
        lo=settings.CGPA_MIN,
        hi=settings.CGPA_MAX,
    )

    if not meaningful:
        _counters["not_meaningful"] += 1
        warnings.append(
            "insufficient_inputs: no admission marks and no completed semesters, "
            "so there is nothing to base a forecast on yet."
        )
        display_value, interval, at_risk = None, None, None

    if guard["applied"]:
        _counters["guardrail_fired"] += 1

    _counters["predictions"] += 1
    elapsed_ms = (time.perf_counter() - started) * 1000
    logger.info(
        "cgpa_forecast student=%s semester=%s confident=%s guardrail=%s "
        "admission_missing=%s latency_ms=%.1f",
        getattr(student, "id", "?"),
        semester,
        meaningful,
        guard["applied"],
        admission_missing,
        elapsed_ms,
    )

    return {
        "student_id": str(student.id),
        "semester": semester,
        "completed_semesters": len(used),
        "semester_history": [round(float(g), 2) for g in used],
        "current_cgpa": round(float(getattr(student, "cgpa", 0) or 0), 2),
        "target": "final_cgpa",
        "meaningful": meaningful,
        "predicted_cgpa": display_value,
        "raw_prediction": None if not meaningful else round(raw, 4),
        "prediction_interval_90": interval,
        "at_risk_probability": at_risk,
        "guardrail_applied": bool(guard["applied"]),
        "guardrail_reasons": guard["reasons"],
        "model": _model_version(meta, manifest),
        "features": _json_safe(features),
        "drivers": _top_drivers(pipeline) if pipeline is not None else [],
        "warnings": warnings,
        "disclaimer": DISCLAIMER,
    }


# --------------------------------------------------------------------------
# Audit
# --------------------------------------------------------------------------


def _same_prediction(record, result: dict) -> bool:
    return (
        record.semester == result["semester"]
        and record.model_version == result["model"]["version"]
        and record.raw_prediction == result["raw_prediction"]
        and record.features == result["features"]
    )


def record_prediction(student, result: dict):
    """Persist an audit row, but not a duplicate of the previous one.

    A student refreshing the page, or the dashboard card mounting on every
    navigation, must not grow the table by one row per render. The row is
    written only when the semester, model version, raw output or features have
    changed since that student's last forecast for the same semester.

    Returns ``(record, created)``.
    """
    from apps.predictions.models import PredictionRecord

    latest = (
        PredictionRecord.objects.filter(student=student, semester=result["semester"])
        .order_by("-created_at")
        .first()
    )
    if latest is not None and _same_prediction(latest, result):
        return latest, False

    record = PredictionRecord.objects.create(
        student=student,
        student_registration_id=getattr(student, "registration_id", "") or "",
        semester=result["semester"],
        predicted_cgpa=result["predicted_cgpa"],
        raw_prediction=None if result["raw_prediction"] is None else result["raw_prediction"],
        guardrail_applied=result["guardrail_applied"],
        model_name=result["model"]["name"],
        model_version=result["model"]["version"],
        features=result["features"],
    )
    return record, True
