from rest_framework.routers import DefaultRouter

from apps.academics.views import (
    AcademicYearViewSet,
    BatchViewSet,
    CourseViewSet,
    CurriculumViewSet,
    DepartmentViewSet,
    ProgramViewSet,
)

router = DefaultRouter()
router.register(r"departments", DepartmentViewSet, basename="department")
router.register(r"programs", ProgramViewSet, basename="program")
router.register(r"courses", CourseViewSet, basename="course")
router.register(r"curriculums", CurriculumViewSet, basename="curriculum")
router.register(r"academic-years", AcademicYearViewSet, basename="academic-year")
router.register(r"batches", BatchViewSet, basename="batch")

urlpatterns = []

urlpatterns += router.urls
