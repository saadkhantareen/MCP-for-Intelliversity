from rest_framework import serializers

from apps.storage.utils import delete_cloudinary_asset, get_public_asset_url
from apps.tenants.models import PageAsset, PortalBranding


class UniversityPortalBrandingSerializer(serializers.ModelSerializer):
    logo_url = serializers.SerializerMethodField()
    logo_dark_url = serializers.SerializerMethodField()
    favicon_url = serializers.SerializerMethodField()
    page_asset = serializers.SerializerMethodField()

    class Meta:
        model = PortalBranding
        fields = [
            "theme_config",
            "logo_url",
            "logo_dark_url",
            "favicon_url",
            "page_asset",
        ]

    def get_logo_url(self, obj) -> str | None:
        return get_public_asset_url(obj.logo_public_id)

    def get_logo_dark_url(self, obj) -> str | None:
        return get_public_asset_url(obj.logo_dark_public_id)

    def get_favicon_url(self, obj) -> str | None:
        return get_public_asset_url(obj.favicon_public_id)

    def get_page_asset(self, obj) -> dict | None:
        page_type = self.context.get("page_type")
        if not page_type:
            return None

        try:
            page_asset = PageAsset.objects.get(
                university_portal=obj.university_portal,
                page_type=page_type,
            )
        except PageAsset.DoesNotExist:
            return None

        return PageAssetSerializer(page_asset).data


class PortalBrandingUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PortalBranding
        fields = ["logo_public_id", "logo_dark_public_id", "favicon_public_id"]

    def update(self, instance, validated_data):
        public_id_fields = [
            "logo_public_id",
            "logo_dark_public_id",
            "favicon_public_id",
        ]

        for field in public_id_fields:
            if field in validated_data:
                old_public_id = getattr(instance, field, None)
                if old_public_id:
                    delete_cloudinary_asset(old_public_id)

        return super().update(instance, validated_data)


class PageAssetUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PageAsset
        fields = ["background_image_public_id"]

    def update(self, instance, validated_data):
        if "background_image_public_id" in validated_data:
            old_public_id = getattr(instance, "background_image_public_id", None)
            if old_public_id:
                delete_cloudinary_asset(old_public_id)

        return super().update(instance, validated_data)


class PageAssetSerializer(serializers.ModelSerializer):
    background_image_url = serializers.SerializerMethodField()

    class Meta:
        model = PageAsset
        fields = ["page_type", "background_image_url", "metadata"]

    def get_background_image_url(self, obj) -> str | None:
        return get_public_asset_url(obj.background_image_public_id)
