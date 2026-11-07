# CGPA Prediction — Implementation & Architecture

> Implemented feature. Companion to `00`–`08`. Training code: `ml/`. Serving code:
> `apps/predictions/`. For the runbook — endpoints, screens, commands and the
> verification record — see **`10_CGPA_FEATURE_INTEGRATION.md`** and
> **`VERIFICATION.md`**.

**Scope, before anything else.** All models were trained and evaluated on
**synthetic data only** (8 files, 10,000 rows per semester, generated as a linear
function of admission marks plus Gaussian noise). On that synthetic hold-out,
Ridge explains R² ≈ 0.893 of variance with MAE ≈ 0.142 CGPA points. R² is not
accuracy, and synthetic R² says nothing about accuracy on real student cohorts.

The deployment scope of this build is **demo / defence only**. The 2.0 at-risk
threshold is a demo triage line. No written approval for real-student use is
claimed or implied anywhere in this document or the code.

---

## 1. The decision this design encodes

**The models are the vendor's, not the university's.** Eight regressors — one per
current semester — are trained once from the eight synthetic datasets, hashed,
versioned like any other source artifact, and shipped inside the application. A
university has no interface to upload training data, choose an algorithm,
substitute a model, or trigger a retrain. It receives predictions only.

The isolation premise, stated precisely: this is safe **only because the training
data is synthetic vendor data**. There is no customer data in training to leak,
so "shared model" and "strong isolation" happen to coincide here. If training
ever moved to real university data, that premise would fail and the isolation
argument would have to be rebuilt from scratch — shared models are not, in
general, the stronger-isolation choice.

Microsoft's multitenant guidance describes three patterns — tenant-specific,
shared, and tuned-shared models — and calls one of them "shared models"; it does
not call shared models the stronger-isolation option
([Azure Architecture Center](https://learn.microsoft.com/en-us/azure/architecture/guide/multitenant/approaches/ai-ml)).
This build implements the *shared* pattern.

| Risk | Control actually enforced in this build |
|---|---|
| A student of university B resolved through university A's request | `StudentProfile` lookup only after a tenant is in context; the router raises `TenantNotResolved` when it is missing |
| Prediction history leaking between tenants | `PredictionRecord` is a tenant app → routed to the tenant DB |
| One tenant's data in the model | Impossible: training reads the eight `.xlsx` files only, never a live database |
| An arbitrary file being loaded as a model | Manifest basename allowlist (`sem[1-8].joblib`), path resolved inside `ml/artifacts`, SHA-256 checked against the manifest |
| A stale or mismatched pipeline serving predictions | Manifest `feature_order` must equal the code's `FEATURE_ORDER`; scikit-learn major.minor must match the recorded training version; any mismatch → 503 |
| Fallback to the wrong database | `db_for_read`/`db_for_write` raise instead of returning `"default"` for a tenant app with no tenant |

Known limitation, recorded rather than papered over: `auth`, `contenttypes` and
`accounts` are shared apps (present in *both* databases), and their primary keys
can diverge between the global and tenant databases. The relation guard allows
those app pairs deliberately (Django admin's `LogEntry` references a tenant
user); any product feature that resolves a shared-app object across databases
must be treated with care. There is no such feature today.

---

## 2. What ships

| Path | Contents |
|---|---|
| `ml/train.py` | Trains and evaluates the eight models (split-first; see §5) |
| `ml/requirements-train.txt` | Exact pins for the training environment |
| `ml/verify_artifacts.py` | Standalone post-training verification (hashes, feature order, loadability) |
| `ml/artifacts/sem{1..8}.joblib` | `Pipeline(imputer → scaler → Ridge)` per semester |
| `ml/artifacts/manifest.json` | Schema 2: feature order, dataset/artifact SHA-256, policy, training config, metrics, residual quantiles |
| `ml/evaluation/` | Baselines, ablation, coverage, guardrail impact, at-risk calibration, EDA — saved as files, not prose |
| `ml/metrics.csv` | Leaderboard (7 candidates × 8 semesters) |
| `apps/predictions/feature_engineering.py` | The single feature definition, imported by training **and** serving; imports no numeric library at module level |
| `apps/predictions/policy.py` | Guardrail and uncertainty maths — pure Python, shared by training evaluation and serving |
| `apps/predictions/services.py` | Verify/load artifacts, build features, predict, guardrail, interval, risk, audit |
| `apps/predictions/views.py` | `cgpa/`, `cohort/`, `models/` |

The manifest is the contract: serving never hard-codes which model serves which
semester, how wide the interval is, or what the guardrail thresholds are.

---

## 3. Data and target

| | |
|---|---|
| Measured inputs | `Matric_Marks`, `FSC_Marks`, `Sem1..Sem(N-1)_CGPA` |
| Target | `Final_CGPA` (clipped to 1.5–4.0 in the data) |
| Rows | 10,000 per semester, no nulls, no duplicates |
| Semester files | `dataset_semester_N.xlsx` = a student in semester N, N−1 semesters completed |

The datasets contain only those columns. Every percentage, average, slope and
standard deviation used by the models is computed at train and serve time by
`feature_engineering.py`; nothing derived is baked into the files. For semester
N only the first N−1 SGPA columns are read, so a later semester cannot leak into
an earlier prediction.

### What the evaluation actually supports

Saved to `ml/evaluation/` (files, reproduced by `ml/train.py`; see
`VERIFICATION.md` for the run record):

* **The ceiling is linear.** Admission-only Ridge matches the 14-feature model:
  ΔMAE between −7.8e−5 and +4.7e−5 across semesters. At semester 8 the all-feature
  model's R² is 0.892743 versus 0.892795 for admission-only — a change of
  **−0.00005**.
* **Semester history adds no measurable signal on this data.** The shipped model
  is therefore effectively an admission-marks mapping. It does not track
  learning progress, and its cohort/at-risk ordering on this data relabels
  admission rank.
* **Residual diagnostics** (`ml/evaluation/eda.json`, semester 8): mean
  −8.9e−5, σ 0.17634, skew 0.0078, excess kurtosis −0.111,
  `corr(|residual|, prediction)` 0.004. That last number is reported as a
  *diagnostic*, not as proof of homoscedasticity; marginal quantiles matching a
  Gaussian do not establish it either.
* **Correlation of residual with the last semester SGPA** is ≈ 0 for semesters
  2–8 (null for semester 1, which has no semester). This is why "the model
  ignores progress" is a measurement, not an opinion.

The older claim that adding raw semester columns moved R² from 0.89278 to
0.89273 came from a different comparison and is superseded by the ablation
table above; use −0.00005.

---

## 4. Feature contract

The dataset has **three** measured inputs per student: matric marks, FSc marks,
and a variable-length list of semester SGPAs. A fixed-shape model cannot take a
variable-length list, so the list is summarised into a fixed 14-number
description of level, trend, volatility and recency:

| Feature | Meaning |
|---|---|
| `matric_pct`, `fsc_pct` | Admission marks as fractions of the student's **own stored totals** |
| `admission_avg`, `admission_gap` | Mean and FSc−Matric difference |
| `sem_count` | Completed semesters (0..7) |
| `sem_mean`, `sem_last`, `sem_weighted` | Level, most recent, recency-weighted mean |
| `sem_trend`, `sem_delta` | Least-squares slope; last − first |
| `sem_std`, `sem_min`, `sem_max` | Volatility and range |
| `sem_vs_admission` | Semester mean (×4 scale) − admission average |

These are not 14 independent inputs. `admission_avg`, `admission_gap` and
`sem_vs_admission` are linear combinations of the others; for Ridge they are
redundant. That is exactly why the driver shares shown in the UI are **model
weights, not causes**, and why the UI labels them that way.

Missing admission marks become **NaN**, not 0.0, so the pipeline's median
imputer fires with the training distribution. A partial record (matric present,
FSc absent) leaves `admission_avg` and `admission_gap` as NaN rather than
fabricating a gap. Percentages are clamped to [0, 1] and an out-of-range ratio is
reported in `warnings`. Totals come from `AdmissionRecord.matric_total` /
`fsc_total`; the constants `DEFAULT_MATRIC_TOTAL = 1150` and
`DEFAULT_FSC_TOTAL = 1100` are used only where no total exists (the training
data, which has no totals) and are the single source of truth for
`seed_admissions` defaults as well.

Consequence worth stating: a missing-admission forecast is *less* reliable, not
"gracefully degrading to semester history" — on this data the imputer supplies
the training median admission level, and the UI says so.

---

## 5. Training

```bash
cd Intelliversity-Backend
uv run --no-project --python 3.12 --with-requirements ml/requirements-train.txt \
    python ml/train.py            # add --fast to skip the boosting candidates
```

Methodology (this replaced the earlier, inflated "hold-out"):

1. **Split first** — 80/20, `random_state=42`, per semester.
2. **Select on the training split only** — 5-fold CV over the candidate zoo
   (Ridge, ElasticNet, KNN, RandomForest, ExtraTrees, GradientBoosting,
   HistGradientBoosting; xgboost is optional and absent here), ranked by CV R²
   then MAE.
3. **Report on the untouched test split** — refit the selected estimator on the
   training split, score MAE/RMSE/R² on the test split.
4. **Baselines on the same test split** — training mean, admission-only Ridge,
   last-SGPA, current-CGPA persistence.
5. **Ablation** — admission-only vs all 14 features, same split.
6. **Uncertainty** — the 90% half-width is the out-of-fold 90th percentile of
   absolute residuals *computed on the training split only*; coverage is then
   measured on the test split, before and after the guardrail.
7. **Ship** — refit the selected estimator on **all** rows. The shipped artifact
   is the 100% refit; the reported hold-out numbers come from the training-split
   model. Both facts are recorded in `manifest.training`.

Dependencies are pinned, not ranged: `pyproject.toml` requires
`scikit-learn==1.9.1`, `uv.lock` resolves it (verified: `scikit-learn -> 1.9.1`,
`numpy -> 2.5.4`, `pandas -> 3.1.0`, `joblib -> 1.6.0`), and
`ml/requirements-train.txt` pins the one-shot training environment. The earlier
`scikit-learn>=1.5,<2.0` range is gone.

Artifacts are written atomically (temp file + `os.replace`) and hashed after
writing; `manifest.json` is written last. The manifest records dataset hashes,
training config, library versions and the policy constants, so a served number
can be traced to the exact files that produced it.

Training is one-shot on this machine. Nothing runs on Kaggle, Colab or any
external service, at training or serving time; PyPI downloads during environment
setup are the only external step.

### Results (synthetic hold-out, 2,000 rows per semester)

| Semester | Hold-out MAE | Hold-out R² | 90% half-width | Guardrail fire rate | MAE before → after | Coverage before → after |
|---|---|---|---|---|---|---|
| 1 | 0.1420 | 0.8928 | 0.291 | 0.0% | 0.1420 → 0.1420 | 90.1% → 90.5% |
| 2 | 0.1420 | 0.8929 | 0.2907 | 1.9% | 0.1420 → 0.1423 | 90.0% → 90.2% |
| 3 | 0.1420 | 0.8929 | 0.2905 | 17.7% | 0.1420 → 0.1500 | 90.0% → 88.5% |
| 4 | 0.1421 | 0.8928 | 0.2905 | 43.7% | 0.1421 → 0.1773 | 89.9% → 81.6% |
| 5 | 0.1420 | 0.8929 | 0.2903 | 56.2% | 0.1420 → 0.2161 | 90.0% → 71.8% |
| 6 | 0.1420 | 0.8929 | 0.2902 | 62.0% | 0.1420 → 0.2566 | 89.8% → 62.2% |
| 7 | 0.1420 | 0.8929 | 0.2905 | 66.5% | 0.1420 → 0.2944 | 90.0% → 54.0% |
| 8 | 0.1421 | 0.8927 | 0.2904 | 69.3% | 0.1421 → 0.3284 | 89.8% → 48.1% |

Baselines at semester 8 (MAE): training mean 0.4393, admission-only Ridge 0.1420,
last-SGPA 0.8350, current-CGPA persistence 0.5601, shipped model 0.1421.

**The guardrail is a measured negative result on this data.** It fires for 69% of
semester-8 test rows (it lifts anyone whose admission-driven raw falls more than
0.2 below their semester average) and raises MAE from 0.1421 to 0.3284 while
collapsing 90% band coverage from 90% to 48%. It is kept because the product
decision is a monotonic drop-cap rather than a floor, and because it is now
reported instead of hidden — but it must not be described as a calibration aid,
and on real data it must be re-evaluated before use. The raw prediction is shown
alongside the guarded one wherever they differ.

---

## 6. Serving

One request, one model. `resolve_semester` derives the natural semester as
completed semesters + 1 (capped at 8); a requested semester is rejected with 400
if `semester - 1` exceeds the completed history, and history is sliced to the
first `semester - 1` SGPAs only. A lower override emits
`semester_override_discards_history` so a discarded semester is never silent.

```
subdomain → TenantMiddleware → set_current_tenant
          → router raises TenantNotResolved if a tenant model is touched without one
          → StudentProfile (tenant DB)
          → admission marks (own totals) + completed SGPAs (status-aware)
          → build_features → NaN for missing admission
          → get_pipeline(N): allowlist → path → sha256 → feature order → sklearn version → joblib
          → raw prediction
          → guardrail: value = max(raw, past_avg - 0.20) when past_avg >= 3.0
          → interval: guarded ± interval_90 (nominal)
          → risk: P(raw < 2.0) under Gaussian residuals — from the RAW value
          → audit row (only if inputs/model changed)
```

Design decisions worth defending:

* **Risk comes from the raw output.** A guardrail that lifts a forecast must not
  also silence the early-warning signal.
* **The band is nominal, not "calibrated".** Its 90th-percentile residual width
  covers ~90% of the synthetic hold-out *before* the guardrail (0.898–0.901) and
  much less after it. Empirical coverage on real cohorts is unknown; that
  measurement is the stated next step.
* **Drivers are weights.** Standardised Ridge coefficients, labelled "model
  weights, not causes" in the UI.
* **`meaningful` exists for a reason.** Semester 1 with no admission marks and no
  history has no informative input; the API returns `null` numbers and the UI
  shows "Forecast not meaningful yet" rather than the imputer's median dressed up
  as a prediction.

Guardrail constants (`CGPA_GUARDRAIL_MIN_AVG = 3.0`,
`CGPA_GUARDRAIL_MAX_DROP = 0.2`) are **arbitrary demo constants**, not policy.
The boundary is intentionally documented: a student averaging 2.99 receives no
guardrail; one at 3.00 does. The 0–4 clamp also sets `guardrail_applied`, so a
clamped value is never presented as an unmodified model output.

Fault mapping: a bad request is 400/403/404; a broken deployment — missing,
corrupt, unhashed or version-mismatched artifact, unreadable manifest — is 503
on all three endpoints. `GET /models/` returns 200 only after verifying all eight
artifacts (existence, hash, loadability); otherwise 503 with per-semester status.

Authentication: default-deny. A student may forecast themselves; admin/faculty
may forecast any student in their tenant; every other authenticated account is
403. There is no staff-by-elimination path.

---

## 7. Schema additions

```python
# apps/profiles/models.py — AdmissionRecord
student = OneToOneField(StudentProfile, related_name="admission")
matric_obtained / fsc_obtained = PositiveIntegerField(null=True)
matric_total = PositiveIntegerField(default=1150)   # served totals are authoritative
fsc_total    = PositiveIntegerField(default=1100)
entry_test_score = DecimalField(...)                # stored, NOT fed to the model
is_demo = BooleanField(default=False)               # seed-demo rows, excluded from validation

# apps/predictions/models.py — PredictionRecord
student = ForeignKey(StudentProfile, on_delete=SET_NULL, null=True)  # audit survives deletion
student_registration_id = CharField(...)            # retained identifier
semester, predicted_cgpa (nullable), raw_prediction, guardrail_applied,
model_name, model_version, features (JSON snapshot)
```

Two migrations accompany this build: `profiles.0003` (is_demo, matric_total
default) and `predictions.0002` (SET_NULL + retained registration id + nullable
predicted value). `PredictionRecord` is written only when the semester, model
version, raw output or features changed since the previous forecast for that
student and semester, so a refresh does not append a duplicate.
`purge_predictions --tenant <sub> --days N` enforces the retention window
(default 365 days).

---

## 8. Limitations — plain language

1. **Synthetic only.** No real cohort has ever seen these models. R² 0.893 on
   generated data is not evidence of accuracy on students.
2. **Admission-dominant.** The model mostly restates admission marks. A student
   who outperforms their admission profile is still projected near their
   admission band; a student who underperforms it may be projected high.
3. **The guardrail is harmful on this data** (§5): up to +0.19 MAE and 48%
   coverage at semester 8. Its thresholds are arbitrary demo constants.
4. **Intervals are nominal.** Coverage is measured only on synthetic data, and
   only before the guardrail is it ≈90%.
5. **Risk is conditional on graduation.** `P(final < 2.0)` excludes dropout and
   is a Gaussian-residual approximation.
6. **Demo scope.** 2.0 is a demo triage threshold. Cohort ordering is advisor
   triage for the demo only and must never be the sole basis for probation,
   scholarship or progression decisions.
7. **Faculty cohort access is tenant-wide** in this demo; department/program
   scoping is deferred.
8. **Warm workers keep serving loaded pipelines** if an artifact is deleted at
   runtime; the health endpoint reports 503 but in-process caches do not
   invalidate. Cache invalidation/staleness signalling is deferred.
9. **Shared-app PK divergence** (`auth`/`contenttypes`/`accounts` exist in both
   databases) is a known structural risk, mitigated only by not using those
   objects across databases.

---

## 9. Operational notes

| Task | How |
|---|---|
| Retrain / upgrade | `uv run … --with-requirements ml/requirements-train.txt python ml/train.py`, then verify with `ml/verify_artifacts.py`, deploy `ml/artifacts/`, restart workers |
| Roll back | Restore the previous `ml/artifacts/` directory (hash check protects against a mixed set) |
| Health | `GET /api/v1/predictions/models/` — 200 only if all eight verify |
| Inspect one student | `python manage.py predict_cgpa --tenant <sub> --student <uuid> [--json]` |
| Import admission marks | `python manage.py seed_admissions --tenant <sub> --csv file.csv` (validated) |
| Purge audit rows | `python manage.py purge_predictions --tenant <sub> [--days N] [--dry-run]` |
| Demo tenant data | `seed_admissions --tenant <sub> --demo` tags rows `is_demo=True` |

`ml/train.py --fast` skips the boosting candidates for a ~10 s retrain loop;
the full leaderboard run takes ~5 minutes on this machine.

---

## 10. Deliberate non-goals

* No per-tenant training, no upload endpoint, no training trigger, no per-program
  model, no pooling of university data.
* No external ML service: serving is local files plus the tenant database.
* No real-student deployment, no dropout prediction, no progression decision.
* No new feature set in this build — the 14-feature contract is unchanged, and
  changing it would require a separate, explicit decision and a retrain.
