from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.academics.views import (
    AcademicPolicyView,
    AcademicYearViewSet,
    BatchViewSet,
    CourseViewSet,
    CurriculumViewSet,
    DepartmentViewSet,
    FacultyCourseViewSet,
    ProgramViewSet,
    SectionViewSet,
    TermViewSet,
)

router = DefaultRouter()
router.register(r"departments", DepartmentViewSet, basename="department")
router.register(r"programs", ProgramViewSet, basename="program")
router.register(r"courses", CourseViewSet, basename="course")
router.register(r"curriculums", CurriculumViewSet, basename="curriculum")
router.register(r"academic-years", AcademicYearViewSet, basename="academic-year")
router.register(r"terms", TermViewSet, basename="term")
router.register(r"batches", BatchViewSet, basename="batch")
router.register(r"sections", SectionViewSet, basename="section")
router.register(r"faculty-courses", FacultyCourseViewSet, basename="faculty-course")

urlpatterns = [
    path("academic-policy/", AcademicPolicyView.as_view(), name="academic-policy"),
]

urlpatterns += router.urls
