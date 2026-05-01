from apps.storage.choices import AssetAccess, AssetCategory, GlobalAssetCategory

CATEGORY_ACCESS_MAP = {
    AssetCategory.PROFILE: AssetAccess.PUBLIC,
    AssetCategory.ASSIGNMENT: AssetAccess.PRIVATE,
    AssetCategory.DOCUMENT:   AssetAccess.PRIVATE,
}

GLOBAL_CATEGORY_ACCESS_MAP = {
    GlobalAssetCategory.BRANDING: AssetAccess.PUBLIC,
    GlobalAssetCategory.PAGE_BG: AssetAccess.PUBLIC,
}
