# Enrollment, Attendance, and Examinations

This document explains the newer academic-adjacent backend modules that now exist in code but need to be understood carefully because some of them are not yet wired into the root URLConf.

## 1. Module purpose

### Enrollments

The enrollments module manages:

- course offerings generated from curriculum courses, terms, and sections
- faculty assignment to offerings
- student enrollment records
- student/faculty offering lookup actions

### Attendance

The attendance module manages:

- attendance policies
- class sessions
- attendance records
- attendance logs
- student summaries and course summaries
- defaulters and compliance reports

### Examinations

The examinations module manages:

- assessment types
- assessment policies
- assessments created by faculty
- student assessment submissions / results
- grade policies
- grade scales

All three modules are tenant-scoped like the rest of the academic system.

## 2. Enrollment app structure

### Models

The enrollments app contains these core models:

- `CourseOffering`
- `FacultyAssignment`
- `Enrollment`

### URL surface

The enrollments URLConf exposes:

- `course-offerings/`

### View responsibilities

The enrollments views are organized around:

- generating course offerings for a term/section
- listing offerings for admin, faculty, and student users
- faculty assignment management
- student enrollment management

### Key flow

1. an academic curriculum course is paired with a term and section to create a course offering
2. faculty are assigned to the offering
3. students are enrolled in the offering
4. attendance and assessment data later reference the same offering

## 3. Attendance app structure

### Models

The attendance app contains these core models:

- `AttendancePolicy`
- `ClassSession`
- `AttendanceRecord`
- `AttendanceLog`

### URL surface

The attendance URLConf exposes:

- `sessions/`
- `records/`
- `policies/`
- `summary/me/`
- `summary/me/<course_offering_id>/`
- `summary/course-offering/<course_offering_id>/`
- `reports/defaulters/`
- `reports/defaulters/export/`
- `reports/compliance/`

### View responsibilities

The attendance views are organized around:

- class session management
- per-student attendance history
- course offering summary reporting
- defaulter reporting
- compliance reporting
- export endpoints for reporting workflows

## 4. Examinations app structure

### Models

The examinations app contains these core models:

- `AssessmentType`
- `AssessmentPolicy`
- `Assessment`
- `StudentAssessment`
- `GradePolicy`
- `GradeScale`

### URL surface

The examinations URLConf exposes:

- `assessment-types/`
- `assessment-policies/`
- `grade-policies/`
- `grade-scales/`
- `faculty/assessments/`
- `faculty/student-assessments/`
- `results/`

### View responsibilities

The examinations views are organized around:

- admin maintenance of assessment and grading policy
- faculty assessment creation and grading
- student result retrieval
- grade calculation and presentation

## 5. Root URL wiring status

Important implementation note:

- `apps.enrollments.urls` exists and is already wired in the root URLConf
- both `apps.attendance.urls` and `apps.examinations.urls` exist
- both have functional routers and viewsets
- neither is currently included in `intelliversity/urls.py`

Correction note:

- `apps.enrollments.urls` is already mounted at `/api/v1/enrollments/`
- `apps.attendance.urls` and `apps.examinations.urls` are still not mounted at the root

That means enrollments APIs are reachable now, while attendance and examinations APIs are implemented in the app layer but are not yet reachable from the project root until the root URLConf includes them.

## 6. How these modules fit the academic flow

A realistic academic lifecycle is:

1. an admin defines departments, programs, courses, terms, batches, and sections
2. the enrollment module creates course offerings for a term/section
3. faculty are assigned to offerings
4. attendance sessions are created for teaching activities
5. attendance records are stored per student
6. assessment policies and assessment types are configured
7. faculty enter scores or results
8. grade policy converts scores into grades / SGPA / CGPA outputs

## 7. Key relationships

### Enrollments

- `CourseOffering` ties together curriculum course, term, section, and capacity.
- `FacultyAssignment` links faculty to a course offering and tracks assignment status.
- `Enrollment` links a student to a course offering and tracks enrollment status.

### Attendance

- A `ClassSession` is linked to a course offering and represents a teaching session.
- `AttendanceRecord` stores the attendance status of a student for a session.
- `AttendanceLog` keeps more detailed audit/history style information.
- `AttendancePolicy` controls allowed rules and thresholds.

### Examinations

- `AssessmentType` defines the type of exam or evaluation.
- `AssessmentPolicy` defines how grading is governed.
- `Assessment` belongs to an offering and assessment type.
- `StudentAssessment` stores the student-specific score/result.
- `GradePolicy` and `GradeScale` support score-to-grade interpretation.

## 8. Documentation and maintenance notes

When updating docs or code around academics, these two modules should be treated as first-class tenants of the academic ecosystem, not as afterthoughts.

The most important maintenance point is wiring:

- if the APIs should be exposed immediately, add them to the root URLConf
- if they are intentionally held back, the docs should clearly say that they exist but are not globally mounted yet

## 9. LLM handoff summary

If another LLM needs to understand the backend quickly, it should know:

- enrollments, attendance, and examinations are real modules with models, URLs, and views
- enrollments is already public through the root URLConf
- attendance and examinations still need root URL inclusion before the APIs are publicly reachable
- both modules depend on the tenant-scoped academic/enrollment data model
