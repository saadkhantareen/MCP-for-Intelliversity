from django.urls import path

from apps.storage.views import (
    GlobalUploadSignatureView,
    UploadSignatureView,
)

urlpatterns = [
    path(
        "uploads/global/signature/<str:asset_category>/",
        GlobalUploadSignatureView.as_view(),
        name="global-upload",
    ),
    path(
        "uploads/signature/<str:asset_category>/",
        UploadSignatureView.as_view(),
        name="upload",
    ),
    # path(
    #     "uploads/private-url/",
    #     PrivateAssetUrlView.as_view(),
    #     name="private-asset-url",
    # ),
]
