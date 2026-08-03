# apps/attendance/urls.py
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AttendancePolicyViewSet,
    AttendanceRecordViewSet,
    ClassSessionViewSet,
    ComplianceView,
    CourseOfferingSummaryView,
    DefaultersExportView,
    DefaultersView,
    MyCourseHistoryView,
    MySummaryView,
)

app_name = "attendance"

router = DefaultRouter()
router.register("sessions", ClassSessionViewSet, basename="class-session")
router.register("records", AttendanceRecordViewSet, basename="attendance-record")
router.register("policies", AttendancePolicyViewSet, basename="attendance-policy")

urlpatterns = [
    # Explicit paths FIRST. Not strictly required here (no prefix collides with
    # the router's), but it is the habit that saves you when one eventually does.
    path("summary/me/", MySummaryView.as_view(), name="summary-me"),
    path("summary/me/<uuid:course_offering_id>/",
         MyCourseHistoryView.as_view(), name="summary-me-course"),
    path("summary/course-offering/<uuid:course_offering_id>/",
         CourseOfferingSummaryView.as_view(), name="summary-course-offering"),

    path("reports/defaulters/", DefaultersView.as_view(), name="report-defaulters"),
    path("reports/defaulters/export/",
         DefaultersExportView.as_view(), name="report-defaulters-export"),
    path("reports/compliance/", ComplianceView.as_view(), name="report-compliance"),

    path("", include(router.urls)),
]