from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.enrollments.views import CourseOfferingViewSet

router = DefaultRouter()
router.register(r"course-offerings", CourseOfferingViewSet, basename="course-offering")

urlpatterns = [
    path("", include(router.urls)),
]
