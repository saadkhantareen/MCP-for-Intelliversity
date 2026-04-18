from apps.storage.choices import AssetCategory, GlobalAssetCategory


def validate_asset_category(asset_category):
    if asset_category not in AssetCategory.values:
        raise ValueError(f"Invalid asset category: {asset_category}")


def validate_global_asset_category(asset_category):
    if asset_category not in GlobalAssetCategory.values:
        raise ValueError(f"Invalid global asset category: {asset_category}")
