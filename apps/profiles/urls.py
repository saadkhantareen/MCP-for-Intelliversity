from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.profiles.views import (
    AdminProfileViewSet,
    FacultyProfileViewSet,
    MyProfileView,
    StudentProfileViewSet,
    DocumentView,
    AdminDocumentView,
)
from apps.profiles.views_bulk import BulkUploadView, BulkUploadTemplateView

router = DefaultRouter()
# router.register(r"documents", DocumentViewSet, basename="document")
router.register(r"students", StudentProfileViewSet, basename="student-profile")
router.register(r"faculty", FacultyProfileViewSet, basename="faculty-profile")
router.register(r"admin", AdminProfileViewSet, basename="admin-profile")


urlpatterns = [
    path("bulk-upload/", BulkUploadView.as_view(), name="bulk-upload"),
    path(
        "bulk-upload/template/",
        BulkUploadTemplateView.as_view(),
        name="bulk-upload-template",
    ),
    # own profile
    path("me/", MyProfileView.as_view(), name="my-profile"),
    # documents — own
    path("documents/", DocumentView.as_view(), name="documents"),
    path("documents/<uuid:doc_id>/", DocumentView.as_view(), name="document-delete"),
    # documents — admin
    path(
        "documents/admin/<uuid:user_id>/",
        AdminDocumentView.as_view(),
        name="admin-documents",
    ),
]

urlpatterns += router.urls
