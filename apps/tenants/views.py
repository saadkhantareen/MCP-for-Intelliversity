import logging

from django.db.models import Prefetch
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tenants.models import PageAsset, PortalBranding, UniversityPortal
from apps.tenants.serializers import (
    PageAssetSerializer,
    PageAssetUpdateSerializer,
    PortalBrandingUpdateSerializer,
    UniversityPortalBrandingSerializer,
)

logger = logging.getLogger(__name__)


# apply cache in future after setting up redis or memcached
class PortalBrandingDetailView(APIView):
    permission_classes = [AllowAny]
    serializer_class = UniversityPortalBrandingSerializer

    def get(self, request: Request, **kwargs: dict) -> Response:
        domain = request.query_params.get("domain")

        try:
            portal_branding = (
                PortalBranding.objects.select_related(
                    "university_portal",
                    "university_portal__university",
                    "university_portal__portal",
                )
                .prefetch_related(
                    "university_portal__domains",
                    Prefetch(
                        "university_portal__page_assets",
                        # as branding is called once on the login page, so we return the login page asset here to save an extra call from the client
                        queryset=PageAsset.objects.filter(page_type="login"),
                        to_attr="login_page_asset",
                    ),
                )
                .filter(
                    university_portal__domains__domain=domain,
                    university_portal__is_active=True,
                )
                .first()
            )
        except PortalBranding.DoesNotExist:
            return Response(
                {
                    "detail": "No active PortalBranding found for this university portal."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.serializer_class(portal_branding)
        return Response(serializer.data, status=status.HTTP_200_OK)


class PageAssetDetailView(APIView):

    permission_classes = [AllowAny]
    serializer_class = PageAssetSerializer

    def get(self, request: Request, page_type: str, **kwargs: dict) -> Response:
        domain = request.query_params.get("domain")
        try:
            page_asset = PageAsset.objects.select_related("university_portal").get(
                university_portal__domains__domain=domain,
                university_portal__is_active=True,
                page_type=page_type,
            )

        except PageAsset.DoesNotExist:
            return Response(
                {
                    "detail": "No active PageAsset found for this university portal and page type."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.serializer_class(page_asset)
        return Response(serializer.data, status=status.HTTP_200_OK)


# also delete the cache key in the update view after updating the asset
class PortalBrandingUpdateView(APIView):
    permission_classes = [AllowAny]
    serializer_class = PortalBrandingUpdateSerializer

    def patch(self, request: Request, **kwargs: dict) -> Response:
        domain = request.query_params.get("domain")
        try:
            university_portal = UniversityPortal.objects.get(
                domains__domain=domain, is_active=True
            )
        except UniversityPortal.DoesNotExist:
            return Response(
                {"detail": "No active UniversityPortal found for this domain."},
                status=status.HTTP_404_NOT_FOUND,
            )

        instance, _ = PortalBranding.objects.get_or_create(
            university_portal=university_portal
        )

        serializer = self.serializer_class(
            instance,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {"detail": "Branding updated successfully."}, status=status.HTTP_200_OK
        )


class PageAssetUpdateView(APIView):
    permission_classes = [AllowAny]
    serializer_class = PageAssetUpdateSerializer

    def patch(self, request: Request, page_type: str, **kwargs: dict) -> Response:

        domain = request.query_params.get("domain")
        try:
            university_portal = UniversityPortal.objects.get(
                domains__domain=domain, is_active=True
            )
        except UniversityPortal.DoesNotExist:
            return Response(
                {"detail": "No active UniversityPortal found for this domain."},
                status=status.HTTP_404_NOT_FOUND,
            )

        instance, _ = PageAsset.objects.get_or_create(
            university_portal=university_portal,
            page_type=page_type,
        )

        serializer = self.serializer_class(
            instance,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {"detail": "Page asset updated successfully."}, status=status.HTTP_200_OK
        )
