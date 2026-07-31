from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AssessmentPolicyViewSet,
    AssessmentTypeViewSet,
    FacultyAssessmentViewSet,
    FacultyStudentAssessmentViewSet,
    GradePolicyViewSet,
    GradeScaleViewSet,
    StudentResultViewSet,
)

router = DefaultRouter()

# Admin Endpoints
router.register(r"assessment-types", AssessmentTypeViewSet, basename="assessment-type")
router.register(
    r"assessment-policies", AssessmentPolicyViewSet, basename="assessment-policy"
)
router.register(r"grade-policies", GradePolicyViewSet, basename="grade-policy")
router.register(r"grade-scales", GradeScaleViewSet, basename="grade-scale")

# Faculty Endpoints
router.register(
    r"faculty/assessments", FacultyAssessmentViewSet, basename="faculty-assessment"
)
router.register(
    r"faculty/student-assessments",
    FacultyStudentAssessmentViewSet,
    basename="faculty-student-assessment",
)

# Results Endpoints
router.register(r"results", StudentResultViewSet, basename="student-results")

urlpatterns = [
    path("", include(router.urls)),
]
