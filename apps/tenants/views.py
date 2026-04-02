import logging

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
from apps.tenants.utils.domain_utils import resolve_university_portal

logger = logging.getLogger(__name__)


class UniversityPortalDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, subdomain, portal_name):
        try:
            university_portal = UniversityPortal.objects.select_related(
                "university", "portal"
            ).get(
                university__subdomain=subdomain,
                portal__name=portal_name,
                is_active=True,
            )
        except UniversityPortal.DoesNotExist:
            return Response(
                {"detail": "No active UniversityPortal found for this subdomain."},
                status=status.HTTP_404_NOT_FOUND,
            )

        data = {
            "university_portal_id": university_portal.id,
            "university": university_portal.university.name,
            "portal": university_portal.portal.name,
        }
        return Response(data, status=status.HTTP_200_OK)


# apply cache in future after setting up redis or memcached
class PortalBrandingDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        university_portal, error = resolve_university_portal(request.get_host())
        if error:
            return error

        try:
            portal_branding = PortalBranding.objects.get(
                university_portal=university_portal
            )
        except PortalBranding.DoesNotExist:
            return Response(
                {
                    "detail": "No active PortalBranding found for this university portal."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = UniversityPortalBrandingSerializer(portal_branding)
        return Response(serializer.data, status=status.HTTP_200_OK)


class PageAssetDetailView(APIView):

    permission_classes = [AllowAny]

    def get(self, request, university_portal_id, page_type):
        try:
            page_asset = PageAsset.objects.select_related("university_portal").get(
                university_portal__id=university_portal_id,
                page_type=page_type,
            )

        except PageAsset.DoesNotExist:
            return Response(
                {
                    "detail": "No active PageAsset found for this university portal and page type."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = PageAssetSerializer(page_asset)
        return Response(serializer.data, status=status.HTTP_200_OK)


# also delete the cache key in the update view after updating the asset
class PortalBrandingUpdateView(APIView):

    def patch(self, request: Request) -> Response:
        university_portal, error = resolve_university_portal(request.get_host())
        if error:
            return error

        instance, _ = PortalBranding.objects.get_or_create(
            university_portal=university_portal
        )

        serializer = PortalBrandingUpdateSerializer(
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

    def patch(self, request: Request, page_type: str) -> Response:
        university_portal, error = resolve_university_portal(request.get_host())
        if error:
            return error

        instance, _ = PageAsset.objects.get_or_create(
            university_portal=university_portal,
            page_type=page_type,
        )

        serializer = PageAssetUpdateSerializer(
            instance,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {"detail": "Page asset updated successfully."}, status=status.HTTP_200_OK
        )
