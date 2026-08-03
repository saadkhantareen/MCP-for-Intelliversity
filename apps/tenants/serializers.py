from rest_framework import serializers

from apps.storage.utils import delete_cloudinary_asset, get_public_asset_url
from apps.tenants.models import PageAsset, PortalBranding


class UniversityPortalBrandingSerializer(serializers.ModelSerializer):
    logo_url = serializers.SerializerMethodField()
    logo_dark_url = serializers.SerializerMethodField()
    favicon_url = serializers.SerializerMethodField()
    page_asset = serializers.SerializerMethodField()
    theme_config = serializers.SerializerMethodField()

    university_name = serializers.CharField(
        source="university_portal.university.name", read_only=True
    )

    portal_name = serializers.CharField(
        source="university_portal.portal.name", read_only=True
    )

    class Meta:
        model = PortalBranding
        fields = [
            "theme_config",
            "logo_url",
            "logo_dark_url",
            "favicon_url",
            "page_asset",
            "university_name",
            "portal_name",
        ]

    def get_logo_url(self, obj) -> str | None:
        return get_public_asset_url(obj.logo_public_id)

    def get_logo_dark_url(self, obj) -> str | None:
        return get_public_asset_url(obj.logo_dark_public_id)

    def get_favicon_url(self, obj) -> str | None:
        return get_public_asset_url(obj.favicon_public_id)

    def get_page_asset(self, obj) -> dict | None:
        assets = getattr(obj.university_portal, "login_page_asset")
        if assets:
            page_asset = assets[0]
            return PageAssetSerializer(page_asset).data

        return None

    def get_theme_config(self, obj) -> dict:
        """Return a usable theme_config with sensible defaults so frontends
        always receive the `colors` key expected by tenantUtils.applyThemeToCSS.
        """
        cfg = obj.theme_config or {}

        # Ensure colors exist with sensible defaults
        colors = cfg.get("colors") or {}
        # provide minimal color palette if missing
        default_colors = {
            "primary": "#0057b8",
            "accent": "#ffd400",
            "background": "#ffffff",
            "text": "#111827",
        }

        # merge with defaults
        merged_colors = {**default_colors, **colors}

        # typography defaults
        typography = cfg.get("typography") or {}
        typography_defaults = {"font_family": "Inter, system-ui, sans-serif", "heading_family": "Inter, system-ui, sans-serif"}
        merged_typography = {**typography_defaults, **typography}

        result = {
            "colors": merged_colors,
            "typography": merged_typography,
            "border_radius_px": cfg.get("border_radius_px") or cfg.get("borderRadius") or 8,
            "darkMode": cfg.get("darkMode", False),
        }

        # include any other keys unchanged
        for k, v in cfg.items():
            if k not in result:
                result[k] = v

        return result


class PortalBrandingUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PortalBranding
        fields = [
            "theme_config",
            "logo_public_id",
            "logo_dark_public_id",
            "favicon_public_id",
        ]

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
        fields = ["page_type", "background_image_public_id", "metadata"]

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
