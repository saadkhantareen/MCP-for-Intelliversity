# 10 · CGPA Prediction — a working feature, end to end

Companion to `09_CGPA_PREDICTION_ARCHITECTURE.md` (*why* it is built this way).
This document is the runbook: every file, every endpoint, every screen, the
setup commands, the actual verified responses, and the limitations.

**Scope.** Trained and evaluated on synthetic data only; **demo / defence only**.
The 2.0 at-risk threshold is a demo triage line, not a validated cut-off. Every
forecast surface carries: *"Statistical estimate from a pre-trained model; not
an official result."* No written approval for real-student use is claimed or
implied.

---

## 1. What ships

### Trained artifacts (vendor-owned, never tenant-specific)

| Path | Purpose |
|---|---|
| `ml/train.py` | Split-first training + evaluation for 8 semester models; atomic, hashed artifacts |
| `ml/requirements-train.txt` | Exact pins (scikit-learn 1.9.1, pandas, numpy, joblib, openpyxl) |
| `ml/verify_artifacts.py` | Standalone check: hashes, feature order, loadability, no feature-name warning |
| `ml/artifacts/sem1..8.joblib` | One fitted pipeline per semester (imputer → scaler → Ridge) |
| `ml/artifacts/manifest.json` | Schema 2 contract: `feature_order`, `policy`, `training`, dataset/artifact SHA-256, metrics, residual quantiles |
| `ml/evaluation/*` | `baselines.csv`, `ablation.csv`, `coverage.csv`, `guardrail_impact.csv`, `at_risk_calibration.csv`, `eda.json`, `summary.json` |
| `ml/metrics.csv` | Leaderboard (7 candidates × 8 semesters) |

### Backend

| Path | Purpose |
|---|---|
| `apps/predictions/policy.py` | Guardrail + interval/risk maths, pure Python, shared with training evaluation |
| `apps/predictions/feature_engineering.py` | Raw record → the 14 features; NaN for missing; no numeric import at module level |
| `apps/predictions/services.py` | Artifact verification/caching, feature build, predict, guardrail, interval, risk, audit, health |
| `apps/predictions/views.py` | `cgpa/`, `cohort/`, `models/`; default-deny auth; 400/403/404 vs 503 |
| `apps/predictions/serializers.py` | Request validation; read-only audit serializer |
| `apps/predictions/models.py` | `PredictionRecord` (SET_NULL + retained registration id) |
| `apps/predictions/management/commands/predict_cgpa.py` | `--tenant` required, audited by default, `--unaudited` |
| `apps/predictions/management/commands/seed_admissions.py` | `--tenant` required; `--demo` (tagged `is_demo`) or validated `--csv` |
| `apps/predictions/management/commands/purge_predictions.py` | Retention window enforcement |
| `apps/tenants/router.py` | Fail-closed routing: raise `TenantNotResolved` instead of falling back to `default`; cross-DB relations refused |
| `apps/profiles/models.py` | `AdmissionRecord` (obtained + total, `is_demo`, entry score stored) |
| `apps/profiles/serializers.py` | Nested admission write with validation |
| `intelliversity/settings.py` | Artifact dir, guardrail/at-risk constants (documented as demo-only), cohort cap, retention, throttle rates |

### Frontend

| Path | Purpose |
|---|---|
| `src/features/predictions/api/prediction.service.js` | The three calls (`getForecast`, `getCohort`, `getModelInfo`) |
| `src/features/predictions/lib/risk.js` | **Single** risk definition: high ≥ 0.60, moderate ≥ 0.35, else low |
| `src/features/predictions/lib/forecast.js` | 2dp formatting, guardrail line, HTTP-status error branching, not-meaningful copy |
| `src/features/predictions/components/ForecastDetail.jsx` | Full forecast: number, band, trend, drivers, guardrail, warnings, disclaimer |
| `src/features/predictions/components/ForecastBand.jsx` | 0–4 scale, nominal 90% band, 2.00 line; dot coloured by probability |
| `src/features/predictions/components/SemesterTrend.jsx` | Completed SGPAs → dashed projection, with an `sr-only` data table |
| `src/features/predictions/components/CgpaForecastCard.jsx` | Student dashboard card — same number, band, risk, warnings, guardrail, disclaimer |
| `src/features/predictions/components/ForecastNotMeaningful.jsx` | Explicit "Forecast not meaningful yet" state |
| `src/features/predictions/components/RiskPill.jsx` | Pill driven only by `riskTone` |
| `src/features/predictions/pages/StudentForecastPage.jsx` | `/cgpa-forecast` |
| `src/features/predictions/pages/AdminCohortPage.jsx` | `/cgpa-cohort` (pagination, drawer, a11y) |
| `src/features/predictions/index.js` | Re-export barrel |
| `src/app/router/AppRouter.jsx` | Routes `/cgpa-forecast`, `/cgpa-cohort` |
| `src/app/layouts/navConfig.js` | Nav entries for student, admin, faculty |
| `src/features/dashboard/pages/StudentDashboardPage.jsx` | Renders `CgpaForecastCard` and passes the axios error through for status branching |
| `src/features/profile/pages/StudentForm.jsx` | Admission marks captured at registration |

All prediction routes sit inside `ProtectedRoute` → `PortalRouter`, so tenant
resolution and the portal shell are inherited, not reimplemented.

---

## 2. How one request flows

```
browser (student.fast.intelliversity.com)
  │  GET /api/v1/predictions/cgpa/          Authorization: Bearer <jwt>
  ▼
TenantMiddleware        resolves University from the host, set_current_tenant
  ▼
UniversityDatabaseRouter  StudentProfile / term records / PredictionRecord
                          → intelliversity_fast   (raises if no tenant)
  ▼
services.predict_student
    semester_history       finalised terms, ordered deterministically, [0,4] validated
    resolve_semester       completed + 1, capped at 8; lower override warns
    build_features         own totals; NaN for missing marks
    get_pipeline(N)        allowlist → path → sha256 → feature_order → sklearn version → joblib
    raw                    pipeline.predict([[14 floats]])
    policy.guardrail       max(raw, past_avg − 0.20) when past_avg ≥ 3.0; 0–4 clamp
    policy.interval_and_risk  band on guarded value; risk from RAW value
  ▼
record_prediction          audit row only when inputs/model changed
  ▼
JSON                       number · band · risk · drivers (weights) · guardrail · provenance
```

Isolation holds here because the artifact contains **no tenant rows** (it is a
set of coefficients) and every feature comes from the requesting student's own
tenant database. That sentence is only true while training data stays synthetic
vendor data.

---

## 3. Backend API

Four method–path combinations:

| Method | Path | Who | What |
|---|---|---|---|
| `GET` | `/api/v1/predictions/cgpa/` | any authenticated user | Self forecast (students scoped to themselves) |
| `GET` | `/api/v1/predictions/cgpa/?student_id=<uuid>&semester=<1-8>` | admin / faculty | One named student, optional semester override |
| `POST` | `/api/v1/predictions/cgpa/` | same | Same inputs, JSON body |
| `GET` | `/api/v1/predictions/cohort/` | admin / faculty | Cohort, worst-first, paginated |
| `GET` | `/api/v1/predictions/models/` | any authenticated user | Provenance + per-artifact health |

(The forecast pair shares one path; the four combinations are `GET cgpa`,
`POST cgpa`, `GET cohort`, `GET models`.)

Cohort parameters: `search` (≤ 100 chars), `at_risk=1`, `threshold` (finite,
0–1), `page`, `page_size` (≤ 1000). Filtering and sorting happen **before**
pagination, so `total_count` is the number that matched, not the page size.

Forecast response (real output, see §9):

```json
{
  "student_id": "…", "semester": 6, "completed_semesters": 5,
  "semester_history": [3.62, 3.71, 3.79, 3.88, 3.97],
  "current_cgpa": 3.79, "target": "final_cgpa", "meaningful": true,
  "predicted_cgpa": 3.59,
  "raw_prediction": 3.5457,
  "prediction_interval_90": [3.3, 3.88],
  "at_risk_probability": 0.0,
  "guardrail_applied": true,
  "guardrail_reasons": ["history_drop_cap"],
  "model": {"name": "Ridge", "version": "ec4a6eb0a4b4+2026-10-30T15:46:34.890847+00:00",
            "version_hash": "ec4a6eb0a4b4…", "trained_at": "2026-10-30T15:46:34.890847+00:00"},
  "drivers": [{"feature": "admission_avg", "importance": 0.2042, "direction": 1}, "…"],
  "warnings": [],
  "disclaimer": "Statistical estimate from a pre-trained model; not an official result."
}
```

Status codes:

| Code | Meaning | UI behaviour |
|---|---|---|
| 200 | forecast produced | number + band |
| 400 | impossible semester / bad threshold / field error | backend detail shown **verbatim** |
| 401 | unauthenticated | login flow |
| 403 | student asking for another student; role-less account | permission message |
| 404 | unknown student | not-found message |
| 503 | tenant unresolved, or artifact missing/corrupt/mismatched | "Prediction service unavailable." |

A 503 never includes a stack trace or a filesystem path in the body; the detail
goes to the server log with an error code (`artifact_unavailable`,
`tenant_unresolved`).

---

## 4. Frontend — what it actually does

| Route | Portal | Behaviour |
|---|---|---|
| `/cgpa-forecast` | student | Predicted CGPA (2dp), nominal band, S1→Final trend, driver weights, guardrail raw→adjusted line, warnings, model quality, "not meaningful yet" state, disclaimer |
| `/cgpa-cohort` | admin, faculty | KPI row computed **among shown students**, pagination with "Showing N of M", strict missing-admission count, keyboard-accessible rows, drawer with the full forecast, guardrail marker per row |
| `/dashboard` | student | `CgpaForecastCard`: same number, band, risk, warnings, guardrail, disclaimer, link to the full page |

Rules the UI follows, stated without embellishment:

* **One risk definition.** `lib/risk.js` is imported by the pill, the band dot and
  the recommendation card. High ≥ 0.60, moderate ≥ 0.35.
* **`raw_prediction` is never a headline.** It appears only when
  `guardrail_applied` is true, as `Raw model output 3.55 → adjusted 3.59
  (history drop cap)`, rounded to 2dp.
* **Drivers are labelled "Model weights, not causes"** and the bar width equals
  the weight share.
* **Cohort ordering is server-side** (worst first by raw-derived risk); the page
  does not re-sort it.
* **Not-meaningful rows show "—"**, are excluded from the at-risk and mean
  tiles, and are counted in `skipped`.
* **The band is described as nominal**, and the model-quality card says
  "Synthetic hold-out; not evidence of real-cohort accuracy."

---

## 5. Turning it on for a university

```bash
cd Intelliversity-Backend

python manage.py migrate                 # main DB (tenants, portals, domains)
python manage.py migrate_tenants         # every tenant DB (academics, predictions, …)
python manage.py seed_roles              # role groups + permissions

python manage.py seed_admissions --tenant fast --csv admissions.csv   # real marks
python manage.py seed_admissions --tenant fast --demo                 # demo tenant only

./run_backend.sh                         # or your production server
```

`admissions.csv` header:
`registration_id,matric_obtained,matric_total,fsc_obtained,fsc_total`
(`registration_id`, `matric_obtained`, `fsc_obtained` required; totals default to
1150/1100). Rows are validated (`obtained ≤ total`, `total > 0`); unknown
registration ids and invalid rows are reported, not silently dropped. Demo rows
are tagged `is_demo=True`.

Frontend: `pnpm install && pnpm dev` (or build `dist/`). No extra service, no
external ML host, no GPU.

Nothing in that list trains a model. Training is:

```bash
uv run --no-project --python 3.12 --with-requirements ml/requirements-train.txt \
    python ml/train.py --fast      # ~10 s, skip boosting candidates
uv run --no-project --python 3.12 --with-requirements ml/requirements-train.txt \
    python ml/train.py             # ~5 min, full leaderboard
uv run --no-project --python 3.12 --with-requirements ml/requirements-train.txt \
    ml/verify_artifacts.py
```

---

## 6. Where the inputs come from

| Feature group | Source | Who writes it |
|---|---|---|
| `matric_pct`, `fsc_pct` | `AdmissionRecord` (obtained **and** total) | Admin (StudentForm), CSV import, `seed_admissions` |
| `sem_*` | `StudentTermRecord.sgpa` for terms the status marks as finalised | Existing examination flow |

`AdmissionRecord` is written through the student endpoint:

```json
PATCH /api/v1/profiles/students/<id>/
{ "admission": { "matric_obtained": 950, "matric_total": 1050,
                 "fsc_obtained": 980, "fsc_total": 1100 } }
```

That student's matric percentage is `950/1050 = 0.9048` (90.5%), **not**
`950/1150 = 0.826`. Stored totals are authoritative; the 1150/1100 constants are
only a fallback for records with no total and are the same constants
`seed_admissions` uses, so the two paths cannot drift.

`entry_test_score` is stored but **not fed to the model** in this build.

Missing admission marks are NaN → the imputer uses the training median, and the
response carries `admission_marks_missing` in `warnings`. A semester-1 student
with no marks and no history is not forecast at all: `meaningful: false`, null
numbers, `insufficient_inputs` warning, and the UI shows "Forecast not meaningful
yet".

`current_semester` on the student profile counts **completed** semesters
(`sgpa > 0`), so the portal cannot say "semester 6" while the predictor served
the semester-4 model.

---

## 7. Why the university never trains

* **Contract.** Models are shipped artifacts. No upload endpoint, no training
  trigger, no per-program model, no "use my data" toggle.
* **Isolation.** The artifact holds weights and imputer/scaler statistics — no
  student rows. Features are read per request from the tenant database resolved
  by subdomain. `PredictionRecord` is written to the same tenant database.
  Cross-database relations are refused by the router.
* **Consistency.** Every university gets the same model for the same semester, so
  a result is explainable and supportable.
* **Upgrade path.** Retraining is a release: new artifacts, new hashes, new
  `generated_at`. Every response reports the artifact hash it used, and
  `PredictionRecord` keeps the features and version needed to reproduce it.

---

## 8. Operating it

| Task | How |
|---|---|
| Upgrade models | Retrain → `verify_artifacts.py` → deploy `ml/artifacts/` → restart workers |
| Roll back | Restore the previous `ml/artifacts/` (hash check rejects a mixed set) |
| Health | `GET /api/v1/predictions/models/` — 200 only when all 8 artifacts verify |
| Inspect one student | `python manage.py predict_cgpa --tenant <sub> --student <uuid> [--json]` |
| Purge audit rows | `python manage.py purge_predictions --tenant <sub> [--days N] [--dry-run]` |
| Throttling | `CGPA_THROTTLE_PREDICTIONS` (default `120/min`), `CGPA_THROTTLE_COHORT` (`30/min`) |
| Counters | `services.get_counters()` — predictions, guardrail fired, admission missing, load failures, not-meaningful |

**Audit semantics.** Only the single-student endpoint (`cgpa/` GET/POST) writes a
`PredictionRecord`, and only when the semester, model version, raw output or
features changed since the previous row for that student/semester. The cohort
list writes **no** audit rows; opening the drawer in the UI calls the
single-student endpoint, which does. CLI forecasts are audited unless
`--unaudited` is passed, and the CLI output says which it was.

**Warm workers.** Once a pipeline is loaded it stays in process memory. Deleting
an artifact at runtime makes `/models/` return 503 but does not evict a warm
copy. Cache invalidation is deferred (see §10).

---

## 9. Verified in this environment

Local Postgres (`postgres:15` container), tenant `intelliversity_fast`, 15 demo
students (12 original + a flagship case + a no-admission case + a zero-SGPA
case), one admin. **Demo-tenant smoke test — data is synthetic and is not
retained as validation evidence.**

| Check | Result |
|---|---|
| Student self-forecast | `200` |
| Student → another student | `403` — "Students can only request their own forecast." |
| Role-less account → another student | `403` — "This account has no role that may request a CGPA forecast." |
| Admin → named student | `200` |
| Impossible semester (8 with 5 completed) | `400` — "Semester 8 needs 7 completed semesters, but only 5 are on record." |
| Cohort pagination | `count=5, total_count=14, page=1, page_size=5, total_pages=3, has_next=true` |
| Worst-first across pages | monotonic in `at_risk_probability` over the concatenated pages |
| `at_risk=1&threshold=0.6` | `total_count=3`, page returns 2, all ≥ 0.6 |
| `GET /models/` | `200`, `health.ok=true`, 8/8 artifacts verified |
| Artifact removed (cold process) | `503 artifact_unavailable` on `cgpa/`, `cohort/`, `models/` |
| Semester-1, no admission, no history | `200` with `meaningful=false`, all numbers `null`, `insufficient_inputs` warning |
| Guardrail flagship (history mean 3.794) | raw `3.5457` → guarded `3.59`, `guardrail_applied=true`, risk from raw `0.0` |
| Audit dedupe | two identical refreshes: row count unchanged (14 → 14) |
| Unauthenticated | `401` |
| Authenticated, no tenant | `503 tenant_unresolved` |
| Admission totals | `950/1050` → `matric_pct = 0.904762` |
| `manage.py check` / `makemigrations --check` | no issues / no changes |
| Frontend `eslint` + `npm run build` | clean / built |

Flagship response, pasted from the running service:

```json
{
  "student_id": "cc15aa7d-28c4-478c-990d-d01b7e79b55d",
  "semester": 6, "completed_semesters": 5,
  "semester_history": [3.62, 3.71, 3.79, 3.88, 3.97],
  "current_cgpa": 3.79, "meaningful": true,
  "predicted_cgpa": 3.59, "raw_prediction": 3.5457,
  "prediction_interval_90": [3.3, 3.88],
  "at_risk_probability": 0.0,
  "guardrail_applied": true, "guardrail_reasons": ["history_drop_cap"],
  "model": {"name": "Ridge", "version": "ec4a6eb0a4b4+2026-10-30T15:46:34.890847+00:00"},
  "warnings": [],
  "disclaimer": "Statistical estimate from a pre-trained model; not an official result."
}
```

Guardrail arithmetic: past average 3.794 ≥ 3.0, so the cap is
`3.794 − 0.20 = 3.594 → 3.59`; the raw 3.5457 was below it and was lifted. The
at-risk figure is computed from `3.5457`, not from `3.59` — at these values both
round to `0.0`.

The full command/output record, with timestamps, is in `VERIFICATION.md`.

---

## 10. Known limitations

1. **Synthetic only.** No real cohort has ever seen these models. R² 0.893 on
   generated data says nothing about students.
2. **Admission-dominant.** Semester history adds no measurable signal
   (ΔR² = −0.00005 at semester 8; admission-only MAE equals the 14-feature
   model's). The model does not track learning progress, and cohort ordering on
   this data relabels admission rank.
3. **The guardrail is a measured negative result.** At semester 8 it fires for
   69% of rows and raises MAE from 0.1421 to 0.3284 while band coverage drops
   from ~90% to 48%. It is kept because the product decision is a monotonic
   drop-cap and because it is now reported; it is not a calibration aid and must
   be re-evaluated on real data.
4. **The guardrail thresholds are arbitrary demo constants.** 3.0 / 0.2 are not
   supervisor policy. A student averaging 2.99 gets no cap; 3.00 does.
5. **Intervals are nominal.** Coverage ≈ 90% is measured on synthetic hold-out
   data *before* the guardrail; real-cohort coverage is unknown.
6. **Risk excludes dropout.** `P(final < 2.0)` assumes graduation and Gaussian
   residuals; the 2.0 line is a demo triage threshold.
7. **Faculty cohort access is tenant-wide** in this demo; department/program
   scoping is deferred.
8. **No prediction snapshot over ~1,000 students.** The cohort endpoint computes
   on demand and has a cap (`CGPA_COHORT_MAX_STUDENTS`, default 5000,
   `truncated` flag). A nightly snapshot is the next step at scale.
9. **Warm workers do not invalidate caches** when artifacts change on disk.
10. **Django admin's `LogEntry`** relies on the one deliberate cross-database
    relation allowance (global ↔ shared app). It is documented in the router.

Deferred, with reasons: nightly `PredictionSnapshot`; department-scoped faculty
cohort access; per-artifact versioned directory + symlink swap; cache staleness
signal for warm workers; skops/ONNX artifact format migration.

---

## 11. Next steps

* Real-cohort backtesting with forward-in-time splits, persistence baselines,
  interval coverage by band/programme, and dropout-inclusive outcomes.
* Pre-registered kill criteria for the shipped model, for example: time-split
  MAE > 0.24, coverage outside 85–95%, or at-risk AUC < 0.70 ⇒ reject.
* Re-derive (or disable) the guardrail once real data exists — the synthetic
  evaluation says it costs accuracy.
* Nightly per-student snapshot so advisors see trend, not one number.
* Notify a student when their projection crosses 2.00 (reuse the notification
  plumbing).
