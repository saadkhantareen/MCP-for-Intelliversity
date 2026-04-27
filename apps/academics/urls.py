from rest_framework.routers import DefaultRouter
from apps.academics.views import CourseViewSet, DepartmentViewSet, ProgramViewSet

router = DefaultRouter()
router.register(r"departments", DepartmentViewSet, basename="department")
router.register(r"programs", ProgramViewSet, basename="program")
router.register(r"courses", CourseViewSet, basename="course")

urlpatterns = []

urlpatterns += router.urls
