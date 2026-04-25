import time
import uuid

import cloudinary.uploader
from cloudinary.utils import cloudinary_url

_SIGNED_URL_TTL = 3600  # 1 hour


def build_folder_path(subdomain, portal_name, asset_category, access, is_global=False):
    start = "universities"
    if is_global:
        start = "global"
    return f"{start}/{subdomain}/{portal_name}/{access}/{asset_category}"


def build_public_id(subdomain, portal_name, asset_category, access, is_global=False):
    folder = build_folder_path(subdomain, portal_name, asset_category, access, is_global)
    return f"{folder}/{uuid.uuid4().hex}"


def get_public_asset_url(
    public_id: str | None, *, resource_type: str = "image", **options
) -> str | None:
    if not public_id:
        return None
    url, _ = cloudinary_url(
        public_id,
        resource_type=resource_type,
        type="upload",
        secure=True,
        **options,
    )
    return url


def get_private_asset_url(
    public_id: str | None,
    *,
    resource_type: str = "image",
    delivery_type: str = "authenticated",
    ttl: int = _SIGNED_URL_TTL,
    **options,
) -> str | None:
    if not public_id:
        return None
    url, _ = cloudinary_url(
        public_id,
        resource_type=resource_type,
        type=delivery_type,
        sign_url=True,
        secure=True,
        expires_at=int(time.time()) + ttl,  # ← fix: was now() which returns a str
        **options,
    )
    return url


def delete_cloudinary_asset(
    public_id: str | None, *, resource_type: str = "image"
) -> None:
    if not public_id:
        return
    cloudinary.uploader.destroy(public_id, resource_type=resource_type)