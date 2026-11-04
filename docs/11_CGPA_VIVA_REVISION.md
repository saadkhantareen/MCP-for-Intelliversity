# CGPA Prediction: Viva Revision Notes

Companion to docs 09 and 10 and VERIFICATION.md. This is the short version.
If you only revise one thing before the viva, revise this file. Every number
here comes from `ml/evaluation/` or VERIFICATION.md, not from memory.

Scope first, always say it first: this is trained and evaluated on synthetic
data only, and it is demo and defence only. It is not validated on real
students, and it must never be presented as a real-student system.

## The system in 30 seconds

A student opens the forecast page in their own university portal. The browser
sends a request with a JWT token to the backend. The backend reads the
university from the host name, for example `student.fast.intelliversity.com`,
and opens that university's own database. It reads that student's admission
marks and completed semester SGPAs, turns them into 14 numbers, loads exactly
one pre-trained model file for that student's current semester, and returns a
predicted final CGPA, a band, a risk number, and a disclaimer. No university
ever uploads training data, and no model is trained at request time.

## Decision 1: Use shared vendor models, one per semester

Title: Use eight shared, pre-trained Ridge models, one per semester, with no
per-tenant training.

The Problem: A new university has no graduating cohort yet, so it cannot train
its own model, but it still needs a forecast on day one.

Options Considered: train one model per university; **use one shared vendor
model per semester for every university**; train one model on pooled university
data.

Rationale: A shared model works on day one because it does not need that
university's data. Pooling real university data would mix student data across
tenants. Per-university training would leave a new university with nothing
until its first cohort graduates.

Notes: This is safe only because the training data is synthetic vendor data.
If training ever used real university data, this argument would fail, and
shared models would not be the stronger isolation choice. That condition is
written in doc 09, section 1, and you must say it in the viva.

## Decision 2: Stay synthetic only, demo only

Title: Train and evaluate on synthetic data only, and scope the build to demo
and defence.

The Problem: No real student data was available, and the report must stay
honest about that.

Options Considered: wait for real data and build nothing; **build on synthetic
data with honest framing and a demo-only scope**; claim synthetic results as
real accuracy.

Rationale: The first option gives no working feature. The third option is
false. The middle option gives a working, testable system and a clear next
step: real-cohort backtesting.

Notes: Synthetic data here means 8 files, 10,000 rows per semester, where
Final CGPA was generated as a linear function of admission marks plus Gaussian
noise. That is why the results below look so clean. It is not a flaw you hid,
it is the reason the model behaves the way it does.

## Decision 3: Turn a variable list into a fixed 14-number summary

Title: Encode matric marks, FSc marks, and a variable-length SGPA list into a
fixed 14-feature vector, using the same function for training and serving.

The Problem: A sklearn model needs a fixed-length input in a fixed order, but
a student can have 0 to 7 completed semesters.

Options Considered: train a separate model shape per semester count; pad the
list with zeros; **summarise the list into level, trend, volatility, and
recency numbers**.

Rationale: Padding with zeros would pretend a missing semester is a 0.0 fail.
A summary keeps the shape fixed, keeps the raw admission percentages, and
keeps the most recent SGPA, the mean, the slope, the change, the spread, and
the count.

Notes: The 14 features are not 14 independent inputs. Matric percentage,
FSc percentage, admission average, admission gap, semester count, semester
mean, last, recency-weighted mean, trend, delta, standard deviation, minimum,
maximum, and semester mean minus admission average. Three of them are exact
linear combinations of the others, so driver bars in the UI are labelled
"model weights, not causes". The dataset files contain only matric marks,
FSc marks, semester SGPAs, and the target. Every average and mean is computed
at train time and at request time by the same file,
`apps/predictions/feature_engineering.py`. Only the first N minus 1 SGPAs are
used for a semester N model, so a future semester can never leak in.

## Decision 4: Guardrail as a drop cap, risk from the raw value

Title: Use a monotonic drop cap for the displayed forecast, and compute
at-risk risk from the raw model output, not from the guarded output.

The Problem: A forecast that drops far below a student's own semester average
looks wrong to a student and to an advisor, but hiding the risk signal would
be worse.

Options Considered: show the raw model output with no guardrail; use a floor
that pulls every low forecast up to the same value; **use a drop cap: the
displayed value never falls more than 0.2 below the past average, when that
average is 3.0 or above**.

Rationale: A drop cap is monotonic, a higher raw value never gives a lower
displayed value. Computing risk from the raw value keeps the early warning
honest: lifting the displayed number must not silence the warning.

Notes: The 3.0 and 0.2 numbers are arbitrary demo constants, not supervisor
policy. A student averaging 2.99 gets no cap, a student at 3.00 does. The
0 to 4 clamp also sets guardrail_applied, so a clamped value is never shown
as an unmodified model output. On this synthetic data the guardrail is a
measured negative result, see the table below. Say that, do not hide it.

## Decision 5: Fail closed on tenants, default deny on users

Title: Make the tenant router fail closed and make forecast access default
deny.

The Problem: A multitenant system must never serve one university's student
from another university's request, and must never let a student read another
student.

Options Considered: fall back to the default database when no tenant is
found; **raise TenantNotResolved when no tenant is in context**; let any
authenticated user read any student and filter in the UI.

Rationale: A fallback database is the wrong database by definition. A UI
filter is not security. The router must refuse, and the view must refuse.

Notes: A student can forecast only themselves. Admin and faculty can forecast
any student in their own tenant. Every other authenticated account gets 403.
Missing, corrupt, or version-mismatched artifacts give 503 on all three
endpoints, never a partial answer. Faculty cohort access is tenant-wide in
this demo, department and program scoping is deferred, say that if asked.

## Decision 6: Pin the model, hash the model, version the model

Title: Pin scikit-learn to 1.9.1, hash every artifact, and serve only through
a schema 2 manifest.

The Problem: A pickled sklearn pipeline can fail or change silently if it is
loaded with a different library version or a different file.

Options Considered: allow a version range such as 1.5 to below 2.0; **pin
exactly 1.9.1 in pyproject.toml and in ml/requirements-train.txt, check the
SHA-256 of each joblib file against the manifest, check feature order, and
fail closed on mismatch**.

Rationale: The old range contradicted the project's own rule against
cross-version serving. A hash check rejects a mixed or replaced artifact set.
A manifest lets a served number be traced to the exact files that produced
it: feature order, dataset hashes, policy, training config, and metrics.

Notes: Artifacts are written atomically, temp file plus rename, manifest
last. The serving loader checks the manifest basename allowlist, only
sem1 to sem8 joblib files, resolved inside ml/artifacts. The model version
shown in a response is the artifact hash plus its generated timestamp.

## Numbers to remember

All numbers are synthetic hold-out, 2,000 rows per semester, training-split
model. The shipped artifact is refit on all rows, the reported numbers come
from the training-split model. Both facts are in the manifest.

- Hold-out MAE: about 0.142 CGPA points, every semester.
- Hold-out R2: about 0.893, every semester. R2 is not accuracy.
- 90 percent band half width: about 0.29 CGPA points.
- Baselines at semester 8, MAE: mean 0.439, admission-only linear 0.142,
  last SGPA 0.835, current CGPA persistence 0.560, selected model 0.142.
- Ablation at semester 8: admission-only R2 0.892795, all 14 features R2
  0.892743, change minus 0.00005. Semester history adds no measurable signal
  on this data. The model is effectively an admission-marks mapping.
- At-risk at semester 8: threshold 2.0, observed positive rate 0.096,
  predicted probability mean 0.093, Brier score 0.029. Risk is P(final below
  2.0) under Gaussian residuals, conditional on graduation, dropout excluded.

Guardrail impact, before to after, per semester:

| Semester | Fire rate | MAE before to after | Coverage before to after |
|---|---|---|---|
| 1 | 0.0 percent | 0.142 to 0.142 | 90.1 to 90.5 percent |
| 3 | 17.7 percent | 0.142 to 0.150 | 90.0 to 88.5 percent |
| 5 | 56.2 percent | 0.142 to 0.216 | 90.0 to 71.8 percent |
| 8 | 69.3 percent | 0.142 to 0.328 | 89.8 to 48.1 percent |

Read that table out loud in the viva. It proves you measured the guardrail
instead of assuming it helps.

## The flagship example, step by step

History: 3.62, 3.71, 3.79, 3.88, 3.97. Mean: 3.794. Completed: 5 semesters,
so the natural model is semester 6.

1. Raw model output: 3.5457.
2. Past average 3.794 is at or above 3.0, so the cap is 3.794 minus 0.20,
   which is 3.594, shown as 3.59.
3. Raw 3.5457 is below the cap, so the displayed forecast is 3.59,
   guardrail_applied is true, reason is history_drop_cap.
4. At-risk probability is computed from 3.5457, not from 3.59, and at these
   values it rounds to 0.0.
5. Interval: guarded value plus or minus the nominal 90 percent half width,
   about 0.29, giving 3.30 to 3.88 in the verified response.
6. Disclaimer on every surface: "Statistical estimate from a pre-trained
   model; not an official result."

If the panel asks why the old docs showed 3.32 with guardrail false for this
same history, answer: that was the old floor logic and it did not reproduce
from the code. The new example above is pasted from the running service in
doc 10, section 9.

## Limitations to say out loud, before they ask

1. Synthetic only. No real cohort has ever seen these models.
2. Admission dominant. A student who beats their admission profile is still
   projected near it. Cohort order on this data relabels admission rank.
3. Guardrail harmful on this data. See the table above. Re-derive or disable
   it on real data.
4. Intervals are nominal, not calibrated. Coverage is about 90 percent
   before the guardrail on synthetic data, much less after it, unknown on
   real data.
5. Risk excludes dropout, assumes graduation, and uses a Gaussian
   approximation. The 2.0 line is a demo triage line, never a sole basis for
   probation, scholarship, or progression.
6. Faculty cohort is tenant-wide in the demo. No department scoping yet.
7. Warm workers keep serving a loaded pipeline if an artifact file is deleted
   at runtime. The health endpoint then reports 503, but the warm copy does
   not evict itself. Cache invalidation is deferred.
8. Shared apps auth, contenttypes, and accounts exist in both databases and
   their primary keys can diverge. No feature today resolves those objects
   across databases, and any future feature must treat that with care.

## Viva questions, one line each

- Why eight models, not one? Because the input history length and the
  natural semester change, and one model per semester keeps routing simple:
  exactly one model per request, never an average.
- Why Ridge, not a tree? Because the synthetic generator is linear in
  admission marks, so a linear model recovers it and trees do worse. On real
  data that choice must be re-tested.
- Why is R2 flat across semesters? Because semester GPAs add no signal in
  the generated data, so semester 1 and semester 8 score the same.
- Why keep 14 features if admission-only ties? Because the contract was
  fixed for this build, the ablation proves the point, and changing the
  feature set would need a separate decision and a retrain.
- What happens if a model file is missing? 503 artifact_unavailable on
  forecast, cohort, and models, in a cold process. Warm workers are the
  exception, see limitation 7.
- What happens if a student asks for another student? 403.
- What happens with no admission marks and no history? Meaningful is false,
  numbers are null, UI says "Forecast not meaningful yet", the imputer
  median is not dressed up as a prediction.
- What happens with a semester 8 request and only 5 completed semesters?
  400, with the message "Semester 8 needs 7 completed semesters, but only 5
  are on record."
- How do you know the docs match the code? The flagship response, the
  guardrail table, and the API matrix in VERIFICATION.md were pasted from
  runs on 2026-10-30, and the evaluation files are saved under ml/evaluation.
- What is next, in one sentence? Real-cohort backtesting with forward-in-time
  splits, persistence baselines, coverage by band and programme, and
  dropout-inclusive outcomes, with kill criteria such as time-split MAE above
  0.24, coverage outside 85 to 95 percent, or at-risk AUC below 0.70, which
  would reject the model.

## What I did not do, and why that is a strength

No Kaggle, no Colab, no external ML service at train or serve time. Training
is one-shot on this machine, serving is local files plus the tenant database.
No upload endpoint, no training trigger, no per-program model, no pooling of
university data, no dropout prediction, no progression decision. Each "no"
is a scope decision that keeps the demo defensible.
