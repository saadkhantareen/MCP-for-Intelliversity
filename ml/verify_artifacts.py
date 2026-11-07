"""Verify that the shipped artifacts match the manifest and the serving contract.

Run after ``ml/train.py`` from the backend root, in a plain Python process (no
Django, no database):

    uv run --no-project --python 3.12 --with-requirements ml/requirements-train.txt \
        python ml/verify_artifacts.py

Checks, per semester:

* ``sem{N}.joblib`` exists and its sha256 equals ``manifest["semesters"][N]["sha256"]``;
* the file loads with ``joblib`` and is a fitted scikit-learn Pipeline;
* the pipeline's final estimator name matches ``manifest["semesters"][N]["model"]``;
* ``manifest["feature_order"]`` equals
  ``apps.predictions.feature_engineering.FEATURE_ORDER`` (the serving contract);
* ``manifest["policy"]`` equals ``apps.predictions.policy.DEFAULT_POLICY``;
* every dataset recorded in ``manifest["datasets"]`` hashes as recorded.

Also checks that the manifest declares ``schema_version == 2`` and documents the
shipped-refit vs reported-hold-out distinction. Exits non-zero on any failure.
"""

from __future__ import annotations

import hashlib
import json
import sys
import warnings
from pathlib import Path

import joblib
import numpy as np

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ML_DIR = Path(__file__).resolve().parent
ARTIFACT_DIR = ML_DIR / "artifacts"
DATASET_DIR = BACKEND_ROOT.parent / "model prediction"

sys.path.insert(0, str(BACKEND_ROOT))

from apps.predictions import policy  # noqa: E402
from apps.predictions.feature_engineering import FEATURE_ORDER  # noqa: E402

EXPECTED_SCHEMA_VERSION = 2


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    failures: list[str] = []

    def check(condition: bool, message: str) -> None:
        if condition:
            print(f"  PASS  {message}")
        else:
            print(f"  FAIL  {message}")
            failures.append(message)

    manifest_path = ARTIFACT_DIR / "manifest.json"
    if not manifest_path.exists():
        print(f"FAIL: no manifest at {manifest_path}; run ml/train.py first")
        return 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    print(f"manifest: {manifest_path}")
    print(f"generated_at: {manifest.get('generated_at')}")
    print(f"sha256(manifest): {sha256_file(manifest_path)}")
    print(f"mode: {manifest.get('training', {}).get('mode')}")

    print("\n-- top-level contract --")
    check(
        manifest.get("schema_version") == EXPECTED_SCHEMA_VERSION,
        f"schema_version == {EXPECTED_SCHEMA_VERSION}",
    )
    check(
        manifest.get("feature_order") == list(FEATURE_ORDER),
        "manifest feature_order == feature_engineering.FEATURE_ORDER",
    )
    check(
        manifest.get("policy") == dict(policy.DEFAULT_POLICY),
        "manifest policy == policy.DEFAULT_POLICY",
    )
    check(
        manifest.get("target") == "Final_CGPA",
        "target == Final_CGPA",
    )
    training = manifest.get("training", {})
    check(
        training.get("shipped_refit") == "all_rows",
        "training.shipped_refit documents the 100% refit",
    )
    check(
        training.get("selection") == "cv_r2_then_mae_on_train_split",
        "training.selection documents training-split CV",
    )

    print("\n-- datasets --")
    for semester, meta in sorted(manifest.get("datasets", {}).items(), key=lambda kv: int(kv[0])):
        path = DATASET_DIR / meta["file"]
        actual = sha256_file(path) if path.exists() else None
        check(actual == meta["sha256"], f"dataset {semester} sha256 matches {meta['file']}")

    print("\n-- per-semester artifacts --")
    for semester, meta in sorted(
        manifest["semesters"].items(), key=lambda kv: int(kv[0])
    ):
        label = f"sem{semester}"
        path = ARTIFACT_DIR / meta["artifact"]
        exists = path.exists()
        check(exists, f"{label}: artifact {meta['artifact']} exists")
        if not exists:
            continue
        check(
            sha256_file(path) == meta["sha256"],
            f"{label}: sha256 matches manifest",
        )
        try:
            pipeline = joblib.load(path)
        except Exception as exc:  # noqa: BLE001 - report and keep checking
            check(False, f"{label}: joblib.load failed ({exc})")
            continue
        check(True, f"{label}: joblib.load OK")
        model = getattr(pipeline, "named_steps", {}).get("model")
        model_name = type(model).__name__
        check(
            model_name == meta["model"],
            f"{label}: pipeline model is {model_name} == manifest model {meta['model']}",
        )
        try:
            single = np.zeros((1, len(FEATURE_ORDER)), dtype=float)
            prediction = pipeline.predict(single)
            check(
                bool(np.isfinite(np.asarray(prediction, dtype=float)).all()),
                f"{label}: pipeline.predict on a zero feature row returns finite values",
            )
        except Exception as exc:  # noqa: BLE001
            check(False, f"{label}: pipeline.predict failed ({exc})")

        # The serving path passes a plain Python list, so the pipeline must not
        # carry scikit-learn feature-name metadata (that would emit a
        # UserWarning on every request). The feature order contract is the
        # manifest, not the pickle.
        fitted_imputer = pipeline.named_steps.get("imputer")
        check(
            not hasattr(fitted_imputer, "feature_names_in_"),
            f"{label}: pipeline stores no sklearn feature names (serving passes a list)",
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            try:
                list_prediction = pipeline.predict([[0.0] * len(FEATURE_ORDER)])
            except Exception as exc:  # noqa: BLE001
                list_prediction = None
                check(False, f"{label}: pipeline.predict(list) failed ({exc})")
            if list_prediction is not None:
                feature_name_warnings = [
                    warning
                    for warning in caught
                    if "feature names" in str(warning.message)
                ]
                check(
                    len(feature_name_warnings) == 0,
                    f"{label}: pipeline.predict([[14 floats]]) emits no feature-name warning",
                )

    print("\n" + "=" * 60)
    if failures:
        print(f"FAILED: {len(failures)} check(s) failed")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
