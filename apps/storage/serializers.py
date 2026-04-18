from rest_framework import serializers

from apps.storage.constants import CATEGORY_ACCESS_MAP, GLOBAL_CATEGORY_ACCESS_MAP
from apps.storage.services import CloudinaryService
from apps.storage.validators import (
    validate_asset_category,
    validate_global_asset_category,
)
from apps.tenants.models import UniversityDomain


class GlobalUploadSignatureSerializer(serializers.Serializer):

    def validate(self, attrs: dict) -> dict:
        asset_category = self.context["asset_category"]
        validate_global_asset_category(asset_category)

        domain = self.context["domain"]

        try:
            university_domain = UniversityDomain.objects.select_related(
                "university_portal__university",
                "university_portal__portal",
            ).get(domain=domain)
        except UniversityDomain.DoesNotExist:
            raise serializers.ValidationError({"non_field_errors": "Invalid domain."})

        university_portal = university_domain.university_portal

        access = GLOBAL_CATEGORY_ACCESS_MAP.get(asset_category)
        if access is None:
            raise serializers.ValidationError(
                {"asset_category": f"No access mapping defined for '{asset_category}'."}
            )

        attrs["asset_category"] = asset_category
        attrs["university_subdomain"] = university_portal.university.subdomain
        attrs["portal_name"] = university_portal.portal.name
        attrs["access"] = access

        return attrs

    def get_upload_params(self) -> dict:
        service = CloudinaryService(self.context["request"])
        vd = self.validated_data

        return service.upload_signature(
            portal_name=vd["portal_name"],
            asset_category=vd["asset_category"],
            access=vd["access"],
            university_subdomain=vd["university_subdomain"],
            is_global=True,
        )


class UploadSignatureSerializer(serializers.Serializer):

    def validate(self, attrs: dict) -> dict:
        asset_category = self.context["asset_category"]
        validate_asset_category(asset_category)

        request = self.context["request"]

        access = CATEGORY_ACCESS_MAP.get(asset_category)
        if access is None:
            raise serializers.ValidationError(
                {"asset_category": f"No access mapping defined for '{asset_category}'."}
            )

        attrs["asset_category"] = asset_category
        attrs["university_subdomain"] = request.university.subdomain
        attrs["portal_name"] = request.portal_name
        attrs["access"] = access

        return attrs

    def get_upload_params(self) -> dict:
        service = CloudinaryService(self.context["request"])
        vd = self.validated_data

        return service.upload_signature(
            portal_name=vd["portal_name"],
            asset_category=vd["asset_category"],
            access=vd["access"],
            university_subdomain=vd["university_subdomain"],
            is_global=False,
        )
