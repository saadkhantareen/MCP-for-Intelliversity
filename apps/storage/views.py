from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.storage.serializers import (
    GlobalUploadSignatureSerializer,
    UploadSignatureSerializer,
)

"""
Flow
────
1. Client Get the UniversityPortal details (including ID) via UniversityPortalDetailView.
2. Client sends CloudinarySignatureRequestSerializer payload to CloudinarySignatureView.
3. View resolves the UniversityPortal, builds public_id + folder.
4. View calls cloudinary_utils.generate_upload_signature().
5. Response serialized by CloudinarySignatureResponseSerializer. == NOT NEEDED
6. Client POSTs file + signature bundle directly to Cloudinary.
7. On success, client sends CloudinaryAssetConfirmSerializer payload
    to CloudinaryAssetConfirmView to persist the resulting URL + public_id in the Django model
8. Client can later GET the branding/asset details via UniversityPortalBrandingSerializer or PageAssetSerializer.
"""


class GlobalUploadSignatureView(APIView):
    """
    GET  /uploads/global/signature/<str:asset_category>/
    Returns signed Cloudinary params for a global (cross-university) upload.
    """

    permission_classes = [AllowAny]

    def get(self, request: Request, asset_category: str) -> Response:
        serializer = GlobalUploadSignatureSerializer(
            data=request.data,
            context={"request": request, "asset_category": asset_category},
        )
        serializer.is_valid(raise_exception=True)
        return Response(serializer.get_upload_params())


class UploadSignatureView(APIView):
    """
    GET  /uploads/signature/<asset_category>/
    Returns signed Cloudinary params scoped to the current tenant + portal.
    Requires request.university and request.portal_name set by middleware.
    upload tenant-scoped assets
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, asset_category: str) -> Response:
        serializer = UploadSignatureSerializer(
            data=request.data,
            context={"request": request, "asset_category": asset_category},
        )
        serializer.is_valid(raise_exception=True)
        return Response(serializer.get_upload_params())
