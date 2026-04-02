from django.urls import path

from apps.tenants.views import (
    PageAssetDetailView,
    PageAssetUpdateView,
    PortalBrandingDetailView,
    PortalBrandingUpdateView,
    UniversityPortalDetailView,
)

urlpatterns = [
    path(
        "<str:subdomain>/<str:portal_name>/",
        UniversityPortalDetailView.as_view(),
        name="university-portal-detail",
    ),
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
        "<uuid:university_portal_id>/<str:page_type>/background/",
        PageAssetDetailView.as_view(),
        name="page-asset-detail",
    ),
    path(
        "<str:page_type>/background/update/",
        PageAssetUpdateView.as_view(),
        name="page-asset-update",
    ),
]
