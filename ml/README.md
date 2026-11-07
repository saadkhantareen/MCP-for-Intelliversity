# Bundled CGPA models

Eight pre-trained regressors — one per *current semester* — shipped with the
application. A university never trains, tunes, or replaces them: the artifacts
in `artifacts/` are the product's, and the API only feeds them a student's
record from that university's own database.

## Files

| Path | Purpose |
|---|---|
| `train.py` | Trains the eight models from `model prediction/dataset_semester_*.xlsx`; writes the artifacts, manifest and evaluation |
| `requirements-train.txt` | Exact `==` pins for the training environment (scikit-learn 1.9.1, pandas, numpy, joblib, openpyxl) |
| `verify_artifacts.py` | Post-run check: artifact hashes vs manifest, `feature_order` vs serving contract, no sklearn feature-name metadata |
| `artifacts/sem{1..8}.joblib` | Fitted scikit-learn `Pipeline` (imputer → scaler → model), refit on 100% of rows |
| `artifacts/manifest.json` | `schema_version` 2 contract: feature order, policy, training metadata, dataset/artifact hashes, per-semester evaluation |
| `evaluation/baselines.csv` | Selected model + four naive baselines on the held-out split, per semester |
| `evaluation/ablation.csv` | Admission-only Ridge vs all-14-feature Ridge, same split |
| `evaluation/guardrail_impact.csv` | Guardrail MAE before/after, fire rate, split by rule reason |
| `evaluation/coverage.csv` | Empirical coverage of the nominal 90% band, before/after guardrail |
| `evaluation/at_risk_calibration.csv` | Predicted `P(final CGPA < 2.0)` vs observed rate, in risk deciles |
| `evaluation/eda.json` | Residual skewness, excess kurtosis, heteroscedasticity diagnostic, residual-vs-last-SGPA correlation, quantiles used |
| `evaluation/summary.json` | Headline numbers per semester |
| `metrics.csv` | CV leaderboard (on the training split) per semester, for the report |
| `train.log` | Output of the last training run |

`artifacts/manifest.json` is the contract between training and serving:
`apps/predictions/services.py` reads it to know which model serves semester N,
how wide the 90% interval is, and which library version produced the artifact.
The pipeline is fitted on plain float arrays (not a pandas frame) because the
serving path calls `pipeline.predict([[f0, ..., f13]])`; the feature order is
the manifest's `feature_order`, not sklearn feature-name metadata.

## Retrain (vendor side, not per tenant)

```bash
cd Intelliversity-Backend

uv run --no-project --python 3.12 \
  --with-requirements ml/requirements-train.txt \
  python ml/train.py

# debug pass: Ridge/ElasticNet/KNN only, skips the tree ensembles
uv run --no-project --python 3.12 \
  --with-requirements ml/requirements-train.txt \
  python ml/train.py --fast

# after training, verify the shipped artifacts against the manifest
uv run --no-project --python 3.12 \
  --with-requirements ml/requirements-train.txt \
  python ml/verify_artifacts.py
```

The script needs the eight datasets in `../model prediction/`. It writes new
artifacts in place; commit them together with `manifest.json` so the deployed
code and the shipped models stay in lockstep. xgboost is optional and is never
installed by the pinned requirements; if it is present the full run includes
it in the leaderboard, otherwise it is skipped and recorded as absent.

## Evaluation protocol (schema 2)

1. **Split first.** Each semester is split 80/20 with
   `train_test_split(test_size=0.2, random_state=42)`.
2. **Selection on the training split only.** A 5-fold CV leaderboard on the
   training partition picks the estimator (`cv_r2_then_mae_on_train_split`).
3. **Hold-out touched once.** The selected estimator is refit on the training
   split and scored on the test split (`holdout`); `cv` stays separate.
4. **Baselines** on the same test split: training mean, admission-only Ridge,
   last SGPA (training mean when no semester exists), current-CGPA persistence.
5. **Ablation:** admission-only Ridge vs all 14 features.
6. **Guardrail impact:** `policy.guardrail` applied row-wise with the row's
   historical SGPAs; MAE before/after and fire rate recorded.
7. **Band coverage:** the 90% half-width is the 90th percentile of
   `|out-of-fold training residual|`; coverage on the test split is measured
   before and after the guardrail, clipped to 0–4.
8. **At-risk calibration:** `policy.interval_and_risk` at `2.0` from the raw
   prediction; predicted vs observed rate per risk decile.
9. **Shipped model:** refit on **all** rows. Reported `holdout` numbers describe
   the training-split model, not the shipped 100% refit.

## Results (full run, `random_state=42`)

All eight semesters select **Ridge**. Hold-out MAE ≈ 0.142, R² ≈ 0.893, nominal
90% band half-width ≈ 0.29 (q90 of training OOF absolute residual).

The interesting honest findings:

* **The ceiling is the data.** `Final_CGPA` is essentially a linear function of
  admission marks plus Gaussian noise (σ ≈ 0.176). The admission-only Ridge
  **matches the 14-feature model** — the ablation ΔMAE is within ±8e-5 across
  all eight semesters — so the ten semester-summary features add no measurable
  signal. Tree ensembles are consistently worse out-of-fold.
* **The model is a real improvement over naive baselines.** The test-split
  MAE of ~0.142 compares with ~0.44 for the training mean, ~0.30–0.84 for
  last-SGPA (semesters 2–8), and ~0.21–0.56 for persistence.
* **The demo guardrail is harmful for semesters ≥ 3.** It fires on 18–69% of
  test rows and raises MAE from ~0.142 to 0.150–0.328 while collapsing 90%
  band coverage from ~90% to 48–89%. Semester GPAs saturate at 4.0, so
  `max(raw, past_avg − 0.2)` lifts genuinely low forecasts. This is recorded,
  not hidden: see `evaluation/guardrail_impact.csv` and `coverage.csv`.
  (Semester 2 barely fires at 1.8%; semester 1 has no history so it cannot fire
  its drop cap at all.)
* **At-risk calibration is reasonable at the extremes.** The top risk decile
  has predicted mean ≈ 0.72–0.73 and observed rate ≈ 0.77; the bottom half is
  predicted ≈ 0 with zero observed positives (base rate 9.6%, Brier ≈ 0.029).

Residual diagnostics are in `evaluation/eda.json`: skewness ≈ 0.007,
excess kurtosis ≈ −0.11, `corr(|residual|, prediction)` ≈ 0.004 (a diagnostic,
not proof of homoscedasticity), and `corr(residual, last_semester_sgpa)` ≈ 0.000
for semesters 2–8. The numbers in the report should be quoted from these files,
not from this README.
