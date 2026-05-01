from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.enrollments.views import (
    FacultyCourseEnrollementViewSet,
    GetCoursesForFacultyEnrollementView,
    GetCoursesForStudentEnrollmentView,
    StudentCourseEnrollmentDeleteAPIView,
    StudentCourseEnrollmentListCreateAPIView,
)

router = DefaultRouter()
router.register(
    r"faculty/courses", FacultyCourseEnrollementViewSet, basename="faculty-enrollment"
)

urlpatterns = [
    path(
        "faculty/courses-for-enrollment/",
        GetCoursesForFacultyEnrollementView.as_view(),
        name="get-courses-for-faculty-enrollment",
    ),
    path(
        "student/courses-for-enrollment/",
        GetCoursesForStudentEnrollmentView.as_view(),
        name="get-courses-for-student-enrollment",
    ),
    path(
        "student/enrollments/",
        StudentCourseEnrollmentListCreateAPIView.as_view(),
        name="student-course-enrollment",
    ),
    path(
        "student/enrollments/<int:pk>/",
        StudentCourseEnrollmentDeleteAPIView.as_view(),
        name="student-enrollment-detail",
    ),
]

urlpatterns += router.urls
