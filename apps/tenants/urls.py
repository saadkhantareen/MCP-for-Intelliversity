from django.urls import path

from apps.tenants.views import (
    PageAssetDetailView,
    PageAssetUpdateView,
    PortalBrandingDetailView,
    PortalBrandingUpdateView,
)

urlpatterns = [
    path(
        "branding/",
        PortalBrandingDetailView.as_view(),
        name="portal-branding-detail",
    ),
    path(
        "branding/update/",
        PortalBrandingUpdateView.as_view(),
        name="portal-branding-update",
    ),
    path(
        "<str:page_type>/background/",
        PageAssetDetailView.as_view(),
        name="page-asset-detail",
    ),
    path(
        "<str:page_type>/background/update/",
        PageAssetUpdateView.as_view(),
        name="page-asset-update",
    ),
]
