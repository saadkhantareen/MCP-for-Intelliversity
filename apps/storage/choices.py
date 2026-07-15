from django.db import models


class AssetCategory(models.TextChoices):
    PROFILE = "profile", "Profile"
    ASSIGNMENT = "assignment", "Assignment"
    DOCUMENT = "document", "Document"


class GlobalAssetCategory(models.TextChoices):
    BRANDING = "branding", "Branding"
    PAGE_BG = "page_bg", "Page Background"


class AssetAccess(models.TextChoices):
    PUBLIC = "public", "Public"
    PRIVATE = "private", "Private"
