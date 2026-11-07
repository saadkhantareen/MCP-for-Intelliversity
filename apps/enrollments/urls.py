from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.enrollments.views import CourseOfferingViewSet, EnrolledStudentAPIView, FacultyAssignmentViewSet, EnrollmentViewSet

router = DefaultRouter()
router.register(r"course-offerings", CourseOfferingViewSet, basename="course-offering")
router.register(r"faculty-assignments", FacultyAssignmentViewSet, basename="faculty-assignment")
router.register(r"student-enrollments", EnrollmentViewSet, basename="student-enrollment")

urlpatterns = [
    path("students/", EnrolledStudentAPIView.as_view(), name="enrolled-students"),
    path("", include(router.urls)),
]
