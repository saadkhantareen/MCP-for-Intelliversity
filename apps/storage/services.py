import time

import cloudinary
import cloudinary.utils

from apps.storage.utils import build_folder_path, build_public_id


class CloudinaryService:
    """One instance per request. Auto-detects global vs university context."""

    def __init__(self, request):
        self._university = getattr(request, "university", None)
        self._user = getattr(request, "user", None)

        self._api_key = cloudinary.config().api_key
        self._api_secret = cloudinary.config().api_secret
        self._cloud_name = cloudinary.config().cloud_name

    def upload_signature(
        self,
        portal_name: str,
        asset_category: str,
        access: str,
        university_subdomain: str,
        is_global: bool,
    ) -> dict:
        """
        Returns signed params for a React → Cloudinary direct upload.

        PUBLIC  assets → Cloudinary type "upload"        (publicly accessible)
        PRIVATE assets → Cloudinary type "authenticated" (signed URL required)
        """

        public_id = build_public_id(
            university_subdomain, portal_name, asset_category, access, is_global
        )
        asset_folder = build_folder_path(
            university_subdomain, portal_name, asset_category, access, is_global
        )
        upload_type = "authenticated" if access == "private" else "upload"
        context = self._build_context(university_subdomain, portal_name, is_global)
        timestamp = int(time.time())

        params_to_sign = {
            "public_id": public_id,
            "timestamp": timestamp,
            "asset_folder": asset_folder,
            "type": upload_type,
            "context": context,
        }

        # SDK signs the params
        signature = cloudinary.utils.api_sign_request(params_to_sign, self._api_secret)

        return {
            "cloud_name": self._cloud_name,
            "api_key": self._api_key,
            "timestamp": timestamp,
            "signature": signature,
            "public_id": public_id,
            "type": upload_type,
            "context": context,
            "asset_folder": asset_folder,
        }

    # Private helper
    def _build_context(
        self,
        university_subdomain: str,
        portal_name: str,
        is_global: bool,
    ) -> str:
        """Cloudinary context metadata string: key=value|key=value"""

        context = {"university": university_subdomain, "portal": portal_name}

        if not is_global and self._user and self._user.is_authenticated:
            try:
                context["user_id"] = str(self._user.id)
            except AttributeError:
                raise ValueError(
                    "Authenticated user must have an ID for Cloudinary context metadata."
                )

        return "|".join(f"{k}={v}" for k, v in context.items() if v)
