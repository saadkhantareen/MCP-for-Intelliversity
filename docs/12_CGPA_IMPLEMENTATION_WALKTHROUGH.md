# CGPA Prediction: How I Built It, Step by Step

This is the long version. It explains the whole workflow in baby steps, in
the order it actually happened, with file names, function names, and the
reason for each step. It is written so that a month from now you can read it
and rebuild the mental model without re-reading all of docs 09 and 10.

If you want the short version for the viva, read
`11_CGPA_VIVA_REVISION.md` first. This document is the evidence behind it.

## Step 0: What already existed before the ML work

Intelliversity already existed as a multitenant university system. That
word, multitenant, means one application serves many universities, and each
university gets its own database. The backend is Django REST Framework, the
frontend is React with Vite, and the database is PostgreSQL.

Three ideas from that existing system matter for everything that follows:

1. A university is resolved from the host name. A request to
   `student.fast.intelliversity.com` is not the same as a request to
   `admin.fast.intelliversity.com`, even though both belong to the same
   university, FAST University, whose database is called
   `intelliversity_fast`. The middleware that does this is
   `apps/tenants/middleware.py`, and the exact domain lookup is in
   `apps/tenants/utils/domain_utils.py`, function `resolve_university_portal`.
   It looks up a `UniversityDomain` row by exact domain name. If there is
   no such row, it returns 404 "Invalid domain". If the portal or university
   is inactive, it also returns 404.
2. A database router decides which database a model uses. The router is
   `apps/tenants/router.py`. Before this build it fell back to the default
   database when no tenant was in context. That is a fail-open bug: the
   wrong database is worse than no database. This build makes it fail
   closed, which means it raises `TenantNotResolved` instead.
3. Users log in through `/api/v1/accounts/login/`, get a JWT access token,
   and the frontend stores it in localStorage under `access_token`. Every
   later API call sends `Authorization: Bearer <token>`. That is how the
   backend knows who you are, separate from which university you belong to,
   which comes from the host name.

Nothing about ML existed yet in the product. The ML work had to fit inside
those three ideas, not replace them.

## Step 1: The starting material, 8 dataset files and one notebook

The starting material was simple, and that simplicity is important to
understand, because it explains almost every later result.

In the folder `model prediction` there were 8 Excel files:

- `dataset_semester_1.xlsx` up to `dataset_semester_8.xlsx`
- Each file had 10,000 rows.
- Each file was for students in that semester. A student in semester N had
  N minus 1 completed semesters in the file.

Each file had only these columns:

- `Matric_Marks`, `FSC_Marks`
- `Sem1_CGPA` up to `Sem(N-1)_CGPA`, only as many as that semester had
  completed
- `Final_CGPA`, the target, clipped to 1.5 to 4.0 in the data

There was also a notebook, `cgpa.ipynb`, which explored the data. The
important fact about the data, which was not obvious at first, is that
Final CGPA in these files was generated as a linear function of admission
marks plus Gaussian noise, with a standard deviation of about 0.177. In
plain words: the answer was mostly hidden in the admission marks, and the
semester SGPAs were mostly noise on top of that. You will see that fact
return in Step 3 and in Step 9.

Why 8 files, not 1 file? Because a semester 1 student has no SGPA history
and a semester 8 student has 7 SGPAs, and the model for each semester
should only see the history that student actually had at that point. If
you put all semesters in one file and computed a mean over all 7 SGPAs for
a semester 4 student, you would leak future semesters into an earlier
prediction. Keeping the files separate, and later slicing history to the
first N minus 1 SGPAs, prevents that leak by construction.

## Step 2: Training, file ml/train.py

Training is the step where the computer learns a formula from the data.
The file that does it is `Intelliversity-Backend/ml/train.py`. It does not
run in the web server. It runs once, on this machine, from the command
line:

```
uv run --no-project --python 3.12 --with-requirements ml/requirements-train.txt python ml/train.py
```

The `--fast` flag skips the boosting candidates and takes about 10 seconds.
The full run takes about 5 minutes. The training environment is pinned in
`ml/requirements-train.txt`: scikit-learn 1.9.1, pandas 3.1.0, numpy 2.5.4,
joblib 1.6.0, openpyxl 3.1.5. Pinning means exact versions, not ranges, so
a retrain later gives the same kind of artifact.

Inside train.py, the steps are in this order, and the order matters:

1. Split first, 80 percent train, 20 percent test, random_state 42, per
   semester. Split first means you cut the data before you choose a model.
   If you choose a model on all the data and then test on the same data,
   your test score is inflated, because the model has already seen the
   test rows. The old evaluation had that flaw. This build fixes it.
2. Select on the training split only, with 5-fold cross-validation, over a
   zoo of candidates: Ridge, ElasticNet, KNN, RandomForest, ExtraTrees,
   GradientBoosting, HistGradientBoosting. XGBoost is optional and was
   absent in this run, and that fact is recorded in the manifest. Ranking
   is by cross-validated R2 first, then MAE. R2 here means how much of the
   variance in Final CGPA the model explains. MAE means mean absolute
   error, the average distance between predicted and actual CGPA in CGPA
   points.
3. Report on the untouched test split. The selected estimator is refit on
   the training split only, then scored on the test split. That gives the
   honest numbers quoted in the docs: MAE about 0.142, R2 about 0.893.
4. Baselines on the same test split. A baseline is the simplest thing you
   could do instead of the model, so you can tell whether the model is
   actually better than trivial. The baselines are: training mean, MAE
   0.439; admission-only linear model, MAE 0.142; last SGPA, MAE 0.835;
   current CGPA persistence, MAE 0.560. At semester 8 the selected model
   ties the admission-only baseline, which is already a clue.
5. Ablation, admission-only versus all 14 features, same split. Ablation
   means remove a part and see what breaks. Here removing the semester
   features changes R2 by minus 0.00005 at semester 8. In plain words,
   semester history adds nothing measurable on this data.
6. Uncertainty. The 90 percent band half width is the 90th percentile of
   absolute residuals from out-of-fold predictions on the training split
   only, about 0.29 CGPA points. Coverage is then measured on the test
   split, before and after the guardrail. That is why coverage before the
   guardrail is about 90 percent, and after it drops to 48 percent at
   semester 8.
7. Ship. The selected estimator is refit on all rows, 100 percent, and
   that refit is the shipped artifact. The reported hold-out numbers come
   from the training-split model, not from the shipped refit, and both
   facts are recorded in `manifest.training` as `shipped_refit: all_rows`
   and `reported_holdout_model: training_split_refit`. If you forget this
   distinction, you will claim the shipped model scored 0.142 on a test
   set it never saw in that form, which is not true. The docs state both
   facts on purpose.

The output of training is 8 files, `ml/artifacts/sem1.joblib` to
`ml/artifacts/sem8.joblib`, plus `ml/artifacts/manifest.json`, plus
evaluation files in `ml/evaluation/`: baselines.csv, ablation.csv,
coverage.csv, guardrail_impact.csv, at_risk_calibration.csv, eda.json,
summary.json, plus the older leaderboard `ml/metrics.csv`.

Each joblib file is a sklearn Pipeline with three steps in order: imputer,
scaler, Ridge. The imputer fills missing numbers with the training median.
The scaler standardises numbers so Ridge coefficients are comparable. Ridge
is a linear model with a penalty on large coefficients, which keeps it
stable when inputs are correlated, which they are here.

Artifacts are written atomically: write to a temp file, then rename with
os.replace, then write the manifest last. Atomic means a crash halfway
cannot leave a half-written model file that looks complete. After writing,
each artifact is hashed with SHA-256 and the hash is stored in the
manifest, along with dataset hashes, feature order, policy constants,
library versions, and metrics. That is what makes a served number
traceable: a response reports the artifact hash it used.

## Step 3: Why Ridge won, and why that tells you about the data

Ridge won all 8 semesters. That is not a coincidence, and it is not because
Ridge is "the best model in general". It won because the data was generated
by a linear formula. A linear model recovers a linear generator. Tree
models, RandomForest, ExtraTrees, GradientBoosting, try to split the data
into boxes, and on a smooth linear signal with Gaussian noise they add
variance without adding signal, so they score worse. ElasticNet, also
linear, came second, which fits the same story.

The flat leaderboard is the same story again. Cross-validated R2 is
0.89261 to 0.89278 across semesters, hold-out R2 is 0.89274 to 0.89290,
MAE is about 0.142 in every semester. If semester history really helped,
later semesters should score clearly better than semester 1, because they
have more history. They do not, because the history in these files carries
no extra signal about the final CGPA beyond what admission marks already
carry. That is why doc 09 says the shipped model is effectively an
admission-marks mapping, and why cohort ordering on this data relabels
admission rank. It is a measurement, not an opinion, and the ablation
table is the proof.

## Step 4: Feature engineering, file feature_engineering.py

This is the step most people get confused by, including the friend who
asked about it, so take it slowly.

The raw measured inputs are only three things: matric marks, FSc marks,
and a list of semester SGPAs. That list has a variable length: 0 for a
semester 1 student, 7 for a semester 8 student. A sklearn model cannot
take a variable-length list. It needs a fixed-length vector, always the
same length, always in the same order. That order is called FEATURE_ORDER,
and it has 14 entries.

So the file `apps/predictions/feature_engineering.py` does one job: it
takes the raw record and returns those 14 numbers, in that order, every
time, whether it is called from training or from the live API. That single
file is the reason training and serving cannot drift apart. If you had
one feature definition in the notebook and a different one in the API,
your served predictions would be nonsense even if training looked good.

The 14 features are:

- `matric_pct`: matric obtained divided by the student's own stored total.
- `fsc_pct`: FSc obtained divided by the student's own stored total.
- `admission_avg`: mean of the two percentages.
- `admission_gap`: FSc percentage minus matric percentage.
- `sem_count`: how many completed semesters, 0 to 7.
- `sem_mean`: mean of completed SGPAs.
- `sem_last`: most recent SGPA.
- `sem_weighted`: recency-weighted mean, recent semesters count more.
- `sem_trend`: least-squares slope across semesters, rising or falling.
- `sem_delta`: last SGPA minus first SGPA.
- `sem_std`: standard deviation, how spread out the SGPAs are.
- `sem_min`, `sem_max`: lowest and highest SGPA.
- `sem_vs_admission`: semester mean on a 0 to 4 scale minus admission
  average on a 0 to 4 scale, so a positive number means the student is
  doing better than their admission profile, negative means worse.

Why summaries, not the raw list? Take two students with the same mean,
3.5. Student A has 3.0, 3.5, 4.0, rising. Student B has 4.0, 3.5, 3.0,
falling. Their mean is identical, but their last, trend, and delta are
opposite, and an advisor would treat them differently. A summary captures
level, trend, volatility, and recency in a fixed shape, without needing a
different model for each history length.

Why not precompute these summaries in the Excel files? Because a
semester 4 model may use only the first 3 SGPAs. If the file already
contained a mean over all 7 SGPAs, that mean would leak future semesters
into an earlier prediction. Computing at request time, from completed
semesters only, avoids leakage, and keeps one source of truth.

Three details that were bugs before this build, and are now fixed:

1. Missing admission marks become NaN, not 0.0. NaN is "not a number",
   a placeholder that tells the imputer to fill the training median.
   Coding missing as 0.0 would pretend the student scored zero, which is
   a completely different student. A partial record, matric present and
   FSc absent, leaves admission average and gap as NaN too, rather than
   fabricating a gap.
2. Percentages use the student's own stored totals. A student with
   950 out of 1050 is 90.5 percent, not 950 out of 1150, which is 82.6
   percent. The constants 1150 and 1100 are only a fallback where no
   total exists, such as the training data, and they are the same
   constants used by the seed command, so the two paths cannot drift.
3. Semester history is status-aware, not "SGPA greater than zero means
   completed". The function `semester_history` in services.py decides
   completion from the term record status: ENROLLED with SGPA 0 is in
   progress and skipped, COMPLETED, FAILED, and DROPPED_OUT are finalised,
   and a finalised 0.0 is a genuine fail and is kept as 0.0, not dropped.
   ENROLLED with SGPA above 0 is kept, because some tenants never finalise
   the status flag and would otherwise lose their whole history. The
   known limitation is documented: there is no separate finalised boolean
   on StudentTermRecord, so a deferred term still marked ENROLLED is
   indistinguishable from a term in progress and is treated as absent,
   and the gap itself is not represented in the feature vector.

Why are driver bars labelled "model weights, not causes"? Because
admission average, admission gap, and semester versus admission are exact
linear combinations of the other features. For a Ridge model, the share
of a coefficient among correlated inputs is not identifiable as a cause.
Permutation importance would be the causal-ish alternative, but this
build labels the bars honestly instead. In the frontend the bar width is
the weight share, not weight times 1.6, which was an old bug.

## Step 5: Policy, file policy.py

The file `apps/predictions/policy.py` is pure Python, no Django, no
numpy at module level, so it can be imported by training evaluation and
by serving without dragging the whole web stack in. It holds three pieces
of maths: guardrail, interval, and risk.

Guardrail, function `guardrail`, in plain words:

- Input: raw model prediction, history list, and the constants.
- If there is no history, or the past average is below 3.0, return the
  raw value unchanged, guardrail_applied false.
- If the past average is at or above 3.0, compute the cap as past average
  minus 0.20. If raw is below the cap, lift it to the cap and set
  guardrail_applied true, reason history_drop_cap. If raw is at or above
  the cap, leave it unchanged.
- Then clamp to 0 to 4. If clamping changed the value, guardrail_applied
  is also true, so a clamped value is never presented as unmodified.
- The rule is monotonic: a larger raw never gives a smaller displayed
  value. The old rule used past average minus max drop divided by 2, and
  the old docs showed a flagship example that did not reproduce from the
  code. Both are fixed, and the new flagship example is pasted from the
  running service.

Why a drop cap and not a floor? A floor would pull every low forecast up
to the same past average, erasing all differences between students. A
drop cap only limits how far below the past average the display can fall,
and preserves differences above the cap. Whether that is a good product
decision on real data is a separate question, and on synthetic data the
answer is no, it hurts accuracy, see Step 9.

Interval: the band is the guarded value plus or minus the 90 percent half
width from the manifest, about 0.29. It is nominal, not calibrated, which
means it covers about 90 percent of synthetic hold-out rows before the
guardrail, and much less after it, and its coverage on real cohorts is
unknown.

Risk: at-risk probability is P(final CGPA below 2.0) under a Gaussian
residual model, computed from the raw prediction, not from the guarded
one. If the guardrail lifts a forecast from 3.54 to 3.59, the risk must
still be computed from 3.54, otherwise lifting the display would also
silence the warning. Risk excludes dropout, it assumes the student
graduates, and 2.0 is a demo triage threshold, not a validated cut-off.

## Step 6: Backend wiring, folder apps/predictions

Now the backend, file by file, in the order a request actually touches
them. All of these live under `Intelliversity-Backend/apps/predictions/`,
except the two files that were changed to support them.

1. `models.py`: `PredictionRecord`. One row per forecast, but only when
   something changed. Fields include student, with on_delete SET_NULL and
   a retained registration id, so the audit row survives student deletion;
   semester, predicted CGPA nullable, raw prediction, guardrail applied,
   model name, model version, and a JSON snapshot of the features. The
   nullable predicted CGPA matters: a not-meaningful forecast has no
   number to store. The cohort list writes no audit rows. Opening a drawer
   in the UI calls the single-student endpoint, which does write, and
   the CLI is audited unless you pass --unaudited.
2. `feature_engineering.py`: Step 4 above. It imports no numeric library
   at module level, so importing it in the web process is cheap and
   cannot fail because pandas is missing.
3. `policy.py`: Step 5 above.
4. `services.py`: the workhorse. Functions you should know by name:
   - `semester_history`: Step 4, status-aware, deterministic ordering,
     SGPA validated in 0 to 4, anomalies reported in warnings, lower
     semester override emits `semester_override_discards_history`.
   - `resolve_semester`: natural semester is completed plus 1, capped at
     8. A requested semester is rejected with 400 if semester minus 1
     exceeds completed history. History is sliced to the first
     semester minus 1 SGPAs only.
   - `get_pipeline(N)`: allowlist check, only sem1 to sem8 joblib, path
     resolved inside ml/artifacts, SHA-256 checked against the manifest,
     feature order checked against FEATURE_ORDER, sklearn major.minor
     checked against the manifest, then joblib load, cached behind an
     RLock so two requests cannot load the same pipeline twice at once.
   - `predict_student`: builds features, calls the pipeline, applies the
     guardrail, computes interval and risk, writes the audit row only if
     inputs or model changed, and returns the finished JSON.
   - `get_counters`: counts predictions, guardrail firings, missing
     admission rate, load failures, and latency, with no student PII
     beyond ids, for logging.
5. `views.py`: three endpoints, all under `/api/v1/predictions/`.
   - GET and POST `cgpa/`: single-student forecast. GET without a
     student id means "myself" for a student. GET or POST with a student
     id and optional semester means admin or faculty asking for a named
     student.
   - GET `cohort/`: admin or faculty only, worst-first, paginated, with
     filtering and sorting done before pagination, so total_count is
     the number that matched, not the page size. Parameters include
     search up to 100 characters, at_risk equals 1, threshold finite
     between 0 and 1, page, page_size up to 1000.
   - GET `models/`: provenance and per-artifact health. It returns 200
     only after verifying all 8 artifacts, existence, hash, and
     loadability. Otherwise 503 with per-semester status.
   Auth is default deny. A student may forecast themselves, admin and
   faculty may forecast any student in their tenant, every other
   authenticated account is 403. There is no staff-by-elimination path,
   which was a bug before: any authenticated non-student used to fall
   through to the staff branch.
   Status mapping is deliberate: bad request, bad threshold, or
   impossible semester is 400 with a human message; unauthenticated is
   401; forbidden is 403; unknown student is 404; tenant unresolved or
   artifact missing, corrupt, or mismatched is 503 with a code such as
   artifact_unavailable or tenant_unresolved, and no stack trace or
   filesystem path in the body.
6. `serializers.py`: request validation for the forecast and cohort
   parameters, and a read-only audit serializer. Validation rejects NaN
   and infinite thresholds, which would otherwise pass silently.
7. `urls.py`: maps `cgpa/`, `cohort/`, and `models/` under the predictions
   prefix. That is four method-path combinations in total: GET cgpa,
   POST cgpa, GET cohort, GET models. The old docs said five endpoints,
   which was wrong, and this build corrects it.
8. `management/commands/`: three commands, all requiring --tenant.
   - `predict_cgpa --tenant <sub> --student <uuid>`: CLI forecast,
     audited by default, with a --json flag and --unaudited flag.
   - `seed_admissions --tenant <sub> --csv file.csv` or `--demo`: CSV
     import with validation, obtained cannot exceed total, total must
     be above zero, unknown registration ids reported, not silently
     dropped. Demo rows are tagged is_demo True.
   - `purge_predictions --tenant <sub> --days N --dry-run`: retention
     window enforcement, default 365 days.
9. Migrations: `apps/predictions/migrations/0002_...` and
   `apps/profiles/migrations/0003_...`. The profiles migration adds
   is_demo and the matric total default to AdmissionRecord. The
   predictions migration changes the student foreign key to SET_NULL,
   adds the retained registration id, and makes predicted CGPA nullable.
   `manage.py check` must show no issues, and `makemigrations --check`
   must show no changes, otherwise the code and the database schema have
   drifted.

The supporting changes outside predictions are:

- `apps/tenants/router.py`: fail closed. For a tenant app with no tenant,
  db_for_read and db_for_write raise instead of returning "default".
  allow_relation returns False for cross-tenant pairs, except the one
  deliberate allowance for shared apps, documented in doc 09: auth,
  contenttypes, and accounts exist in both databases, and Django admin's
  LogEntry references a tenant user, so that pair is allowed on purpose.
- `apps/profiles/models.py`: AdmissionRecord, with obtained and total for
  matric and FSc, entry_test_score stored but not fed to the model, and
  is_demo flag. Seed demo rows are excluded from validation, and doc 10
  section 9 labels them "demo-tenant smoke test, data not retained".
- `apps/profiles/serializers.py`: nested admission write, so a PATCH to
  a student can include an admission object with obtained and total,
  validated, for example 950 out of 1050 gives 0.904762, not 0.826.
- `intelliversity/settings.py`: artifact directory, guardrail constants
  CGPA_GUARDRAIL_MIN_AVG 3.0 and CGPA_GUARDRAIL_MAX_DROP 0.2, at-risk
  threshold 2.0, CGPA min 0.0 and max 4.0, cohort cap, retention, and
  throttle rates, 120 per minute for predictions and 30 per minute for
  cohort. Throttles are configured but were not load tested, say that
  if asked.

A full request, end to end, in order:

1. Browser at `student.fast.intelliversity.com:5173` calls
   `student.fast.intelliversity.com:8000/api/v1/predictions/cgpa/` with a
   Bearer token. Note the frontend API base is
   `${window.location.origin}:8000`, so the host, and therefore the
   tenant, follows the page you are on.
2. TenantMiddleware resolves FAST University from the host, sets the
   current tenant, and configures the tenant database connection.
3. The router routes StudentProfile, term records, and PredictionRecord
   to `intelliversity_fast`. If no tenant were in context, it would
   raise, not fall back.
4. The view checks auth: is this a student asking for themselves, or
   admin or faculty asking for a named student, or anyone else? Anyone
   else gets 403.
5. services.semester_history reads finalised terms, ordered, validated.
6. services.resolve_semester picks the natural semester, or validates
   the requested one, and slices history.
7. feature_engineering builds the 14 numbers, with NaN for missing
   admission.
8. services.get_pipeline loads, or reuses from cache, the one model file
   for that semester, after hash, feature order, and version checks.
9. The pipeline predicts a raw number from a plain list of 14 floats.
   Training now fits on plain float arrays, not DataFrames, so serving
   produces no "X does not have valid feature names" warning. A
   DataFrame-fit and a numpy-fit model were compared on the same split:
   maximum prediction difference 1.1e-15, identical MAE.
10. policy.guardrail lifts the raw number to the cap if needed, policy
    interval and risk compute the band from the guarded value and risk
    from the raw value.
11. record_prediction writes an audit row only if inputs or model
    changed.
12. The view returns JSON with number, band, risk, drivers, guardrail,
    provenance, warnings, and disclaimer. No model file, no training
    data, and no other tenant's data ever leaves the server in that
    response.

## Step 7: Frontend wiring, folder src/features/predictions

The frontend does not contain any ML. It never sees a model file, and it
cannot alter a model. It only displays finished numbers from the backend,
and that separation is deliberate, because it keeps the feature identical
for every tenant.

Files, in the order a user touches them:

- `api/prediction.service.js`: three calls, getForecast, getCohort,
  getModelInfo, all under `/api/v1/predictions`, using the shared axios
  client in `src/shared/api/client.js`, which attaches the access_token
  from localStorage to every request.
- `lib/risk.js`: the single risk definition for the whole UI. High at or
  above 0.60, moderate at or above 0.35, else low. The pill, the band dot,
  and the recommendation card all import this file, so they cannot
  disagree. Before this build, the student page used 0.50 and the risk
  tone used 0.60 and 0.35, which was a bug.
- `lib/forecast.js`: 2 decimal place formatting, guardrail line text,
  HTTP status error branching, and not-meaningful copy.
- `components/ForecastDetail.jsx`: full forecast, number, band, trend,
  drivers, guardrail, warnings, disclaimer.
- `components/ForecastBand.jsx`: 0 to 4 scale, nominal 90 percent band,
  2.00 line, dot coloured by probability via riskTone, not by value
  below 2, which was an old bug.
- `components/SemesterTrend.jsx`: completed SGPAs to dashed projection,
  with a screen-reader-only data table, so the chart is not the only
  source of the numbers.
- `components/CgpaForecastCard.jsx`: student dashboard card, same number,
  band, risk, warnings, guardrail, and disclaimer as the full page, so
  the card and the page cannot disagree.
- `components/ForecastNotMeaningful.jsx`: explicit "Forecast not
  meaningful yet" state, with dashes for numbers, excluded from at-risk
  and mean tiles, counted in skipped.
- `components/RiskPill.jsx`: pill driven only by riskTone.
- `pages/StudentForecastPage.jsx`: route `/cgpa-forecast`, student portal.
- `pages/AdminCohortPage.jsx`: route `/cgpa-cohort`, admin and faculty
  portals, pagination with "Showing N of M", KPI row computed among shown
  students, strict missing-admission count, keyboard-accessible rows,
  drawer with the full forecast, guardrail marker per row.
- `index.js`: re-export barrel, so other parts of the app import from
  the feature folder, not from deep file paths.
- `src/app/router/AppRouter.jsx`: routes `/cgpa-forecast` and
  `/cgpa-cohort`, inside ProtectedRoute and PortalRouter, so tenant
  resolution and the portal shell are inherited, not reimplemented.
- `src/app/layouts/navConfig.js`: nav entries for student, admin, and
  faculty, three entries in total.
- `src/features/dashboard/pages/StudentDashboardPage.jsx`: renders the
  forecast card and passes the axios error through for status branching,
  instead of swallowing it.
- `src/features/profile/pages/StudentForm.jsx`: admission marks captured
  at registration, with obtained and total, not just obtained.

Status branching in the UI, which you should be able to recite:

- 200: show number and band.
- 400: show the backend detail verbatim, for example the impossible
  semester message.
- 401: login flow.
- 403: permission message.
- 503: "Prediction service unavailable.", never a stack trace.

Raw prediction is never a headline. It appears only when guardrail_applied
is true, as "Raw model output 3.55, adjusted 3.59, history drop cap",
rounded to 2 decimal places. Drivers are labelled "Model weights, not
causes" and the bar width equals the weight share. The band is described
as nominal, and the model quality card says "Synthetic hold-out; not
evidence of real-cohort accuracy."

## Step 8: How I tested it, and how I know it is right

Testing happened in layers, cheapest first, and each layer catches a
different kind of mistake. This order is worth remembering for the viva,
because "we tested it" is not an answer, "we tested it in these layers"
is.

Layer 1, static checks. `python manage.py check` must show no issues.
`python manage.py makemigrations --check` must show no changes. If either
fails, the code and the schema have drifted, and nothing else matters.

Layer 2, artifact verification. `ml/verify_artifacts.py` checks, for all
8 semesters: artifact exists, SHA-256 matches the manifest, feature order
in the manifest equals FEATURE_ORDER, policy in the manifest equals
policy.DEFAULT_POLICY, schema version is 2, all 8 dataset hashes match,
and the shipped refit is all rows. It also loads each pipeline and
predicts on a zero row and on a list of 14 floats, with no feature-name
warning. Output in this build: ALL CHECKS PASSED.

Layer 3, API matrix, 18 checks, via Django test client with
force_authenticate users, permissions still evaluated, host headers
student.fast and admin.fast. The 18 checks are: student self 200,
student to other student 403, role-less account to other student 403,
admin to named student 200, impossible semester 400 with the human
message, cohort pagination fields present, cohort worst-first across
pages with 14 rows and total_count 14, at-risk filter before limit with
total_count 3 and page count 2, models 200 with 8 healthy artifacts,
semester 1 with no admission and no history not meaningful, guardrail
cap at past average minus 0.20 with raw 3.5457 to guarded 3.59, at-risk
from raw with risk 0.0, audit dedupe with row count staying 14 to 14,
unauthenticated 401, no tenant 503 tenant_unresolved, policy guardrail
on 3.32 with mean 3.79 equals 3.59, guardrail monotonic with 2.90 to 3.59
and 3.70 to 3.70, and a student averaging 2.99 getting no drop cap.

Layer 4, cold-process fault injection. Move sem3.joblib aside in a test
copy, start a cold process, and check forecast, cohort, and models all
return 503 artifact_unavailable, then restore the file. This proves the
health check is real, not just parsing the manifest. The old health check
parsed only the manifest and returned 200 even with all joblibs missing.
That is fixed, with one honest nuance: an already-loaded pipeline in a
warm worker keeps serving from memory, so models reports 503 while warm
endpoints keep answering. Cache invalidation is deferred, and you must
say that if the panel probes it.

Layer 5, CSV and CLI checks. Seed admissions from CSV with an invalid row
and an unknown registration id, and check both are reported, not silently
dropped. Check stored totals drive the percentage, 950 out of 1050 gives
0.904762. Run `predict_cgpa` from the CLI for the flagship student and
check the output matches the API. Run `purge_predictions --dry-run` and
check it reports 0 rows older than 365 days for the demo tenant.

Layer 6, frontend checks. `npx eslint` on the predictions folder and the
dashboard page, exit 0. `npm run build`, exit 0, built in 9.63 seconds,
dist file about 332 kilobytes, gzip about 108 kilobytes. No new npm
dependencies were added. Prediction pages are code-split and appear in
the build output. This layer does not prove the UI works in a browser,
it only proves it compiles and lints, and the docs say that plainly.

Layer 7, live demo rehearsal, 2026-10-30 evening, after the test-client
verification. This layer found a real bug that the test client did not
catch, and that bug is part of the authentic story. The live backend,
started with `./run_backend.sh`, returned 503 artifact_unavailable on
forecast, cohort, and models, with the log detail "scikit-learn is not
installed in this deployment". The serving virtualenv on the home drive,
`$HOME/.venvs/intelliversity`, had Django but no sklearn, because the
verification runs had used `uv run --no-project` with the training
requirements, not the serving venv. The fix was to install the exact
manifest versions into that venv with uv pip: scikit-learn 1.9.1,
pandas 3.1.0, numpy 2.5.4, joblib 1.6.0, then restart the backend. After
that restart, the live API returned flagship forecast 200 with 3.59,
raw 3.5457, guardrail true; cohort 200 with total_count 14; models 200
with 8 out of 8 artifacts ok and hashes matching VERIFICATION.md. The
lesson for the viva is: a test-client pass is not a live-server pass,
because the test client and the live server can run in different Python
environments. Always rehearse the demo in the exact environment you will
present from, using run_backend.sh, not a throwaway training environment.

What was not verified, stated plainly in VERIFICATION.md section 7:
no real student data, no browser-level UI test at the time of writing,
no multi-tenant isolation test with two live tenants at the time of
writing, no load test, warm-cache invalidation not implemented, and
real-cohort coverage unknown. A live rehearsal and a two-tenant test were
ordered after that section was written, and their results belong in an
addendum to VERIFICATION.md, not as a silent edit to the original run
record.

## Step 9: How I know it fits the architecture

Fit is not a feeling, it is a checklist. Each item below maps to a file
or a test, so you can point to it in the viva.

- Shared model, no tenant data in training: training reads only the 8
  Excel files, never a live database. Check ml/train.py imports and the
  manifest dataset hashes.
- Tenant isolation at request time: middleware resolves the university
  from the host, router routes tenant models to that tenant's database
  and raises without a tenant, views scope students to their tenant.
  Check middleware.py, router.py, and views.py auth.
- One model per request, no ensemble: resolve_semester picks one N,
  get_pipeline loads one file, services predicts once. Check services.py.
- No future leakage: history sliced to first N minus 1 SGPAs, features
  computed at request time from completed terms only. Check
  feature_engineering.py and services.semester_history.
- Honest numbers: split-first evaluation, baselines, ablation, coverage
  before and after guardrail, all saved as files in ml/evaluation, not
  as prose. Check summary.json and the CSVs.
- Traceability: every response reports model name, version hash, and
  generated timestamp, and every audit row stores features and version.
  Check the flagship response in doc 10, section 9.
- No external ML: training is local, serving is local files plus the
  tenant database, PyPI downloads during environment setup are the only
  external step. Check docs 09, section 5, and the runbook in doc 10,
  section 5.
- Failure behaviour is safe: 400 for bad input, 403 for forbidden, 401
  for unauthenticated, 503 for broken deployment, never a partial
  answer, never a stack trace in the body. Check views.py and the API
  matrix in VERIFICATION.md section 5.

If any of those checks failed, the build would not fit, even if the
forecast number looked good. A good number with a leak, a fallback to
the wrong database, or a silent fallback to the imputer median dressed
up as a prediction, is not a good system.

## Step 10: What is deferred, and what comes next

Deferred, with reasons, from doc 10, section 10: nightly
PredictionSnapshot, because the cohort endpoint computes on demand and
has a cap of 5000 with a truncated flag, and a snapshot is only needed
above about 1,000 students; department and program faculty scoping,
because the demo is tenant-wide and labelled as such; per-artifact
versioned directory with symlink swap, because atomic file writes plus
hash checks already protect a single release; cache staleness signal
for warm workers, because it needs a worker restart or invalidation
protocol, not a one-line fix; skops or ONNX artifact format migration,
because joblib with pinned versions and hashes is sufficient for a
demo, and a format migration would need its own verification run.

Next steps, from doc 10, section 11, in order: real-cohort backtesting
with forward-in-time splits, persistence baselines, interval coverage by
band and programme, and dropout-inclusive outcomes; pre-registered kill
criteria, for example time-split MAE above 0.24, coverage outside 85 to
95 percent, or at-risk AUC below 0.70, any of which rejects the model;
re-derive or disable the guardrail once real data exists, because the
synthetic evaluation says it costs accuracy; nightly per-student
snapshot so advisors see a trend, not one number; notify a student when
their projection crosses 2.00, reusing the existing notification
plumbing.

## Appendix A: File map, one line each

Backend, Intelliversity-Backend:
- ml/train.py: split-first training, evaluation, artifact writing.
- ml/verify_artifacts.py: standalone hash, order, and load checks.
- ml/requirements-train.txt: exact training pins.
- ml/artifacts/sem1 to sem8.joblib: one Ridge pipeline per semester.
- ml/artifacts/manifest.json: schema 2 contract for serving.
- ml/evaluation/: baselines, ablation, coverage, guardrail impact,
  at-risk calibration, EDA, summary, all as files.
- apps/predictions/feature_engineering.py: raw record to 14 features.
- apps/predictions/policy.py: guardrail, interval, risk, pure Python.
- apps/predictions/services.py: history, semester resolution, pipeline
  loading, prediction, audit, counters.
- apps/predictions/views.py: cgpa, cohort, models, default-deny auth.
- apps/predictions/serializers.py: request validation, audit read.
- apps/predictions/models.py: PredictionRecord, SET_NULL, retained id.
- apps/predictions/urls.py: cgpa, cohort, models routing.
- apps/predictions/management/commands/predict_cgpa.py: CLI forecast.
- apps/predictions/management/commands/seed_admissions.py: CSV and demo
  import, validated, demo tagged.
- apps/predictions/management/commands/purge_predictions.py: retention.
- apps/tenants/router.py: fail-closed routing.
- apps/tenants/middleware.py: host to university resolution.
- apps/profiles/models.py: AdmissionRecord, obtained, total, is_demo.
- apps/profiles/serializers.py: nested admission write.
- intelliversity/settings.py: artifact dir, guardrail, at-risk, cohort
  cap, retention, throttles.
- VERIFICATION.md: actual command and output record, 2026-10-30.
- docs/09_CGPA_PREDICTION_ARCHITECTURE.md: why it is built this way.
- docs/10_CGPA_FEATURE_INTEGRATION.md: runbook, endpoints, screens.
- docs/11_CGPA_VIVA_REVISION.md: short viva notes, this series.
- docs/12_CGPA_IMPLEMENTATION_WALKTHROUGH.md: this document.

Frontend, Intelliversity-Frontend, src/features/predictions:
- api/prediction.service.js: getForecast, getCohort, getModelInfo.
- lib/risk.js: single risk definition, high 0.60, moderate 0.35.
- lib/forecast.js: formatting, guardrail line, status branching.
- components/ForecastDetail.jsx, ForecastBand.jsx, SemesterTrend.jsx,
  CgpaForecastCard.jsx, ForecastNotMeaningful.jsx, RiskPill.jsx.
- pages/StudentForecastPage.jsx, AdminCohortPage.jsx.
- index.js: barrel export.
- src/app/router/AppRouter.jsx: forecast and cohort routes.
- src/app/layouts/navConfig.js: student, admin, faculty nav.
- src/features/dashboard/pages/StudentDashboardPage.jsx: card on
  dashboard.
- src/features/profile/pages/StudentForm.jsx: admission capture.

## Appendix B: Commands to reproduce the demo

Backend, from Intelliversity-Backend:
```
python manage.py migrate
python manage.py migrate_tenants
python manage.py seed_roles
python manage.py seed_admissions --tenant fast --demo
./run_backend.sh
```

Frontend, from Intelliversity-Frontend:
```
pnpm install
pnpm dev
```

Then open, in a browser on the same machine, with the hosts file entries
already present for fast.intelliversity.com:
- Student: http://student.fast.intelliversity.com:5173/login, then
  /cgpa-forecast
- Admin: http://admin.fast.intelliversity.com:5173/login, then
  /cgpa-cohort

Demo tenant is intelliversity_fast, host fast.intelliversity.com, and
its students are synthetic and tagged is_demo True. Treat it as a smoke
test only, never as validation evidence, and never present its students
as real students.
