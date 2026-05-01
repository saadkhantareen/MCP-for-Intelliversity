from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.profiles.views import (
    AdminProfileViewSet,
    DocumentViewSet,
    FacultyProfileViewSet,
    MyProfileView,
    StudentProfileViewSet,
)

router = DefaultRouter()
router.register(r"documents", DocumentViewSet, basename="document")
router.register(r"students", StudentProfileViewSet, basename="student-profile")
router.register(r"faculty", FacultyProfileViewSet, basename="faculty-profile")
router.register(r"admin", AdminProfileViewSet, basename="admin-profile")


urlpatterns = [
    path("me/", MyProfileView.as_view(), name="my-profile"),
]

urlpatterns += router.urls
