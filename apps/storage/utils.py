import uuid

import cloudinary.uploader
from cloudinary.utils import cloudinary_url, now

_SIGNED_URL_TTL = 3600  # 1 hour


def build_folder_path(subdomain, portal_name, asset_category, access, is_global=False):
    """
    Generate a folder path for Cloudinary uploads, e.g. "universities/oxford/portals/student/public/branding"
    """
    start = "universities"

    if is_global:
        start = "global"

    folder = f"{start}/{subdomain}/{portal_name}/{access}/{asset_category}"
    return folder


def build_public_id(subdomain, portal_name, asset_category, access, is_global=False):
    """
    Generate a unique public_id for Cloudinary uploads, e.g. "universities/oxford/portals/student/public/branding/logo-3f7a2c..."
    """

    folder = build_folder_path(
        subdomain, portal_name, asset_category, access, is_global
    )
    public_id = f"{folder}/{uuid.uuid4().hex}"
    return public_id


def get_public_asset_url(
    public_id: str | None, *, resource_type: str = "image", **options
) -> str | None:
    """Plain unsigned URL for publicly accessible assets (delivery_type='upload')."""
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
    """
    Signed, time-limited URL for restricted assets.
    delivery_type: "authenticated" | "private"
    """
    if not public_id:
        return None

    url, _ = cloudinary_url(
        public_id,
        resource_type=resource_type,
        type=delivery_type,
        sign_url=True,
        secure=True,
        expires_at=now() + ttl,
        **options,
    )
    return url


def delete_cloudinary_asset(
    public_id: str | None, *, resource_type: str = "image"
) -> None:
    """Deletes an asset from Cloudinary. Silently skips if public_id is falsy."""
    if not public_id:
        return
    cloudinary.uploader.destroy(public_id, resource_type=resource_type)
