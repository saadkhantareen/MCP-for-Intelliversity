# VERIFICATION — CGPA prediction build

Everything below was run in this workspace on **2026-10-30 (Asia/Karachi)**
against a **local demo tenant**. No number here is estimated, and no check is
recorded that was not executed.

* Backend: `/mnt/data/FYP proposals/fyp 3 modules/Intelliversity-Backend`
* Frontend: `/mnt/data/FYP proposals/fyp 3 modules/Intelliversity-Frontend`
* Python: 3.12.3 via `uv run --no-project` (the project `.venv` has no
  `bin/python` on this NTFS mount, so a throwaway env is used for Django
  commands). Training uses `ml/requirements-train.txt`.
* Database: local `postgres:15` container on `127.0.0.1:5432`, main DB +
  `intelliversity_fast` tenant DB.

**Every API result in this file is a demo-tenant smoke test.** The tenant's
students and admission marks are synthetic (`seed_admissions --demo` and the
`is_demo=True` flag). They are not validation evidence and are not retained as
such.

---

## 1. Static / configuration checks

```
$ python manage.py check
System check identified no issues (0 silenced).

$ python manage.py makemigrations --check --dry-run
No changes detected
```

Migrations applied to the demo databases:

```
$ python manage.py migrate
  Applying profiles.0003_admissionrecord_is_demo_and_more... OK
  Applying predictions.0002_predictionrecord_student_registration_id_and_more... OK

$ python manage.py migrate_tenants
  ... FAST University migrated successfully
  All tenant migrations completed.
```

Dependency pin (corrected in this build):

```
$ grep -n "scikit-learn" pyproject.toml
26:    "scikit-learn==1.9.1",

$ uv lock          # exit 0
Added scikit-learn v1.9.1

$ python - <<'PY'   # read back from uv.lock
scikit-learn -> 1.9.1
numpy -> 2.5.4
pandas -> 3.1.0
joblib -> 1.6.0
PY
```

The previous `scikit-learn>=1.5,<2.0` range is gone. The serving loader still
enforces the installed major.minor against `manifest.library_versions` and fails
closed, so a mismatched environment cannot silently serve.

---

## 2. Training run (final, full zoo)

Command (from the backend root):

```
uv run --no-project --python 3.12 --with-requirements ml/requirements-train.txt \
    python ml/train.py
```

Runner-reported output (`ml/train.log`):

```
=== semester 8 (completed: 7) ==============================
hold-out  MAE=0.1421  RMSE=0.1773  R2=0.8927  (train-split model, never used for selection)
mode=full  elapsed=299.8s
```

`manifest.generated_at = 2026-10-30T15:46:34.890847+00:00`, `schema_version = 2`.
Zoo actually evaluated: Ridge, ElasticNet, KNN, RandomForest, ExtraTrees,
GradientBoosting, HistGradientBoosting (xgboost is not installed and is absent;
recorded in `training.zoo`). Selected model for all eight semesters: **Ridge**.

Artifact hashes recorded in the manifest and re-read from disk after the atomic
write:

| Semester | SHA-256 |
|---|---|
| 1 | `b7008cd80cc36e9984c445ae23268a424a7e750f7cdd0ef798e20035d510abfa` |
| 2 | `4868d0af2725a8cde35a0d0220786abcd453d004893e2c4c08c0de0b2a8d6e8b` |
| 3 | `d23e3e031e8dc4dbcae20b03023872182a0d2a87da5bb3281ea4a5143e1b5860` |
| 4 | `bf68797dccce227049e7968ed7103ea68bb64ff1e679479185a73435d333d888` |
| 5 | `2c351cd0b4019673572c94836785c048e1edd673aa7510fb4b39d74ee6cb7626` |
| 6 | `ec4a6eb0a4b44e46c5481de5e7d9b6e8ec74f61d6f1bd01251a18c393eadccdb` |
| 7 | `19dea0c23dfc70c4bff5e0fa21f635bc8e19471ec0443f91008dbde4512b8fa0` |
| 8 | `7f5755ed9380636880b3302b1930900da1c5ddc6e4a024674831056af5f0272b` |

---

## 3. Artifact verification

```
$ uv run --no-project --python 3.12 --with-requirements ml/requirements-train.txt \
      ml/verify_artifacts.py
  PASS  sem8: joblib.load OK
  PASS  sem8: pipeline model is Ridge == manifest model Ridge
  PASS  sem8: pipeline.predict on a zero feature row returns finite values
  PASS  sem8: pipeline stores no sklearn feature names (serving passes a list)
  PASS  sem8: pipeline.predict([[14 floats]]) emits no feature-name warning

ALL CHECKS PASSED
```

The script also checks, for sem1..8: artifact exists, SHA-256 matches the
manifest, `manifest.feature_order == FEATURE_ORDER`,
`manifest.policy == policy.DEFAULT_POLICY`, `schema_version == 2`, all eight
dataset hashes match, and `training.shipped_refit == "all_rows"`.

The numpy-fit change matters for serving: training now fits on plain float
arrays, so `pipeline.predict([[14 floats]])` (what Django sends) produces no
`UserWarning: X does not have valid feature names`. A DataFrame-fit and
numpy-fit model were compared on the same split — max prediction difference
1.1e-15, identical MAE.

---

## 4. Evaluation artefacts (from `ml/train.py`, saved to `ml/evaluation/`)

Reproduced by the run above; files are the source of the numbers quoted in
docs 09/10.

`coverage.csv` (2,000 hold-out rows per semester):

```
semester,stage,n_test_rows,covered_rows,empirical_coverage,target_coverage,half_width_90
1,before_guardrail,2000,1802,0.901,0.9,0.2910
1,after_guardrail,2000,1809,0.9045,0.9,0.2910
3,before_guardrail,2000,1800,0.900,0.9,0.2905
3,after_guardrail,2000,1770,0.885,0.9,0.2905
8,before_guardrail,2000,1797,0.8985,0.9,0.2904
8,after_guardrail,2000,963,0.4815,0.9,0.2904
```

`guardrail_impact.csv` (semester 8):

```
semester,subset,n_rows,share_of_test_rows,mae_before,mae_after,fire_rate
8,all_test_rows,2000,1.0,0.14209,0.328415,0.6935
8,guardrail_fired,1387,0.6935,0.14109,0.40982,1.0
8,guardrail_not_fired,613,0.3065,0.14436,0.14421,0.0
```

`ablation.csv` (semester 8): admission-only MAE 0.142043 / R² 0.892795 vs
all-14-features MAE 0.142090 / R² 0.892743 → ΔR² = **−0.00005**, ΔMAE
+4.65e−5.

`baselines.csv` (semester 8, n=2000): mean 0.4393, admission-only linear 0.1420,
last-SGPA 0.8350, current-CGPA persistence 0.5601, selected model 0.1421.

`summary.json` (semester 8): `at_risk = {threshold: 2.0, observed_positive_rate:
0.096, predicted_prob_mean: 0.0933, brier_score: 0.0289}`.

`eda.json` (semester 8, training-split OOF residuals): mean −8.94e−5,
σ 0.176343, skew 0.0078, excess kurtosis −0.1113,
`corr(|residual|, prediction)` 0.004 (labelled a diagnostic, not proof of
homoscedasticity), `corr(residual, last SGPA)` ≈ 0.

**The guardrail is a measured negative result on this data** — MAE 0.1421 →
0.3284 and coverage 89.9% → 48.1% at semester 8. This is reported as-is; see
docs/09 §5.

---

## 5. API verification (demo tenant, 18/18 checks)

Run in one process via Django's test client with real JWT-less
`force_authenticate` users (permissions still evaluated against role groups),
host header `student.fast.intelliversity.com` / `admin.fast.intelliversity.com`.

```
PASS  student self-forecast = 200
PASS  student -> other student = 403
PASS  role-less -> other student = 403
PASS  admin -> named student = 200
PASS  impossible semester = 400 with message
      -> "Semester 8 needs 7 completed semesters, but only 5 are on record."
PASS  cohort pagination fields present
      -> count, has_next, has_previous, page, page_size, total_count, total_pages
PASS  cohort worst-first across pages  -> 14 rows, total_count=14
PASS  at_risk filter before limit      -> total_count=3 count=2
PASS  GET /models/ = 200 with 8 healthy artifacts
PASS  semester-1 + no admission + no history -> not meaningful
PASS  guardrail caps at past_avg - 0.20 (history mean 3.794)
      -> raw=3.5457 -> guarded=3.59
PASS  at-risk computed from raw, not guarded  -> risk=0.0
PASS  audit dedupe: refresh does not append   -> 14 -> 14
PASS  unauthenticated = 401
PASS  no tenant = 503 tenant_unresolved
PASS  policy.guardrail(3.32, mean 3.79) == 3.59
PASS  policy guardrail is monotonic (high raw not lowered) -> 2.90 -> 3.59, 3.70 -> 3.70
PASS  student just below 3.0 averaging-2.99 gets no drop cap -> applied=False

18/18 checks passed
```

Additional checks run separately:

```
# CSV import validation + unknown registration id reporting
$ python manage.py seed_admissions --tenant fast --csv /tmp/admissions.csv
skipped line 3 (FA24-BSE-014): matric_obtained cannot exceed matric_total
1 row(s) skipped as invalid.
1 registration id(s) not found, e.g. ['NOT-A-REG']
Admission records written: 1.

# stored totals drive the percentage (950 / 1050, not 950 / 1150)
matric_pct: 0.904762 fsc_pct: 0.890909

# CLI path
$ python manage.py predict_cgpa --tenant fast --student cc15aa7d-…
semester 6: projected final CGPA 3.59 [guardrail history_drop_cap: raw 3.55]
(model Ridge ec4a6eb0a4b4, audited)
  Statistical estimate from a pre-trained model; not an official result.

# retention
$ python manage.py purge_predictions --tenant fast --dry-run
[dry-run] 0 row(s) older than 365 day(s) in fast.
```

### Cold-process artifact fault (separate process, `sem3.joblib` moved aside)

```
cold process, sem3 removed: forecast -> 503 artifact_unavailable
cold process, sem3 removed: cohort   -> 503 artifact_unavailable
cold process, sem3 removed: models   -> 503 artifact_unavailable
artifact restored: True
```

Warm-process nuance, recorded honestly: an already-loaded pipeline is served
from the in-process cache even if the file is removed, so `/models/` reports 503
while warm endpoints keep answering. Cache invalidation is deferred.

### No-tenant and unauthenticated behaviour

```
unauthenticated forecast            -> 401 {"detail": "Authentication credentials were not provided."}
authenticated, root domain (no tenant) -> 503 {"code": "tenant_unresolved"}
```

---

## 6. Frontend checks

```
$ npx eslint src/features/predictions src/features/dashboard/pages/StudentDashboardPage.jsx
eslint exit: 0

$ npm run build
dist/assets/index-DvxNgioT.js   331.57 kB │ gzip: 107.96 kB
✓ built in 9.63s
[build exit: 0]
```

No new npm dependencies were added. The prediction pages are code-split and
appear in the build output (`StudentForecastPage`, `AdminCohortPage`,
`ForecastDetail`).

---

## 7. What was NOT verified (state it plainly)

1. **No real student data.** Nothing here validates accuracy on real cohorts.
2. **No browser-level UI test.** The frontend was verified by lint + build and by
   contract review; no automated screenshot/interaction run exists.
3. **No multi-tenant isolation test with two live tenants.** Isolation is
   enforced by the router (fail-closed) and was exercised as "no tenant → 503",
   not as "tenant A cannot read tenant B" with two populated databases.
4. **No load test.** Throttles are configured (`120/min`, `30/min`) but not
   exercised to their limits.
5. **Warm-cache invalidation** on artifact replacement is not implemented
   (deferred).
6. **Coverage on real data** is unknown; the 90% band is nominal, measured only
   on synthetic hold-out and degraded by the guardrail.

---

## 8. Reproduce the demo

```bash
# backend
cd "/mnt/data/FYP proposals/fyp 3 modules/Intelliversity-Backend"
python manage.py migrate && python manage.py migrate_tenants
python manage.py seed_roles
python manage.py seed_admissions --tenant fast --demo     # demo rows, is_demo=True
./run_backend.sh

# frontend
cd "../Intelliversity-Frontend" && pnpm install && pnpm dev
```

Demo tenant: `intelliversity_fast` (host `fast.intelliversity.com`), admin
`admin@fast.edu.pk` / `Test@12345`, students `fa24-bse-001…014`. **Demo only.**
