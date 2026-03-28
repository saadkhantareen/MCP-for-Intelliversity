from django.urls import path
from apps.profiles.views import (
    MyProfileView,
    UserProfileView,
    DocumentView,
    AdminDocumentView,
)

from apps.profiles.views_bulk import BulkUploadView, BulkUploadTemplateView
urlpatterns = [
    path('bulk-upload/', BulkUploadView.as_view(), name='bulk-upload'),
    path('bulk-upload/template/', BulkUploadTemplateView.as_view(), name='bulk-upload-template'),
    # own profile
    path("me/", MyProfileView.as_view(), name="my-profile"),

    # admin — manage any user profile
    path("users/", UserProfileView.as_view(), name="user-profile-list"),
    path("users/<uuid:user_id>/", UserProfileView.as_view(), name="user-profile-detail"),

    # documents — own
    path("documents/", DocumentView.as_view(), name="documents"),
    path("documents/<uuid:doc_id>/", DocumentView.as_view(), name="document-delete"),

    # documents — admin
    path("documents/admin/<uuid:user_id>/", AdminDocumentView.as_view(), name="admin-documents"),
]