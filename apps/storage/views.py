# apps/storage/views.py
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.storage.serializers import (
    GlobalUploadSignatureSerializer,
    PrivateAssetUrlSerializer,
    UploadSignatureSerializer,
)

"""
Upload Flow
───────────
1. Client calls GET /uploads/signature/<asset_category>/        → gets signed Cloudinary params
2. Client POSTs file directly to Cloudinary                     → file uploaded (public or private)
3. Client saves returned public_id to Django model via profiles API

View Private Asset Flow
───────────────────────
1. Client calls POST /uploads/private-url/  { public_id, resource_type }
2. Server returns a signed URL valid for 1 hour
3. Client opens/downloads file from that URL
"""


class GlobalUploadSignatureView(APIView):
    """
    GET /uploads/global/signature/<asset_category>/?domain=...
    Returns signed Cloudinary params for global uploads (branding, page backgrounds).
    No auth required.
    """

    permission_classes = [AllowAny]

    def get(self, request: Request, asset_category: str, **kwargs) -> Response:
        serializer = GlobalUploadSignatureSerializer(
            data=request.data,
            context={
                "request": request,
                "asset_category": asset_category,
                "domain": request.query_params.get("domain"),
            },
        )
        serializer.is_valid(raise_exception=True)
        return Response(serializer.get_upload_params())


class UploadSignatureView(APIView):
    """
    GET /uploads/signature/<asset_category>/
    Returns signed Cloudinary params scoped to the current tenant + portal.

    - profile  → public upload  (profile pictures)
    - document → private upload (user documents)

    Requires auth + middleware to set request.university and request.portal_name.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, asset_category: str) -> Response:
        serializer = UploadSignatureSerializer(
            data=request.data,
            context={"request": request, "asset_category": asset_category},
        )
        serializer.is_valid(raise_exception=True)
        return Response(serializer.get_upload_params())

    # class PrivateAssetUrlView(APIView):
    """
    POST /uploads/private-url/

    Body:
        {
            "public_id":     "universities/fast/admin/private/document/abc123",
            "resource_type": "raw"
        }

    Response:
        {
            "url": "https://res.cloudinary.com/...?signature=...&expires_at=..."
        }

    Returns a signed time-limited URL (1 hour) for viewing a private Cloudinary asset.
    Only authenticated users can access this.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = PrivateAssetUrlSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response({"url": serializer.get_signed_url()})
