from django.contrib import admin

from apps.tenants.models import (
    PageAsset,
    Portal,
    PortalBranding,
    University,
    UniversityDomain,
    UniversityPortal,
)

admin.site.register(University)
admin.site.register(Portal)
admin.site.register(UniversityPortal)
admin.site.register(UniversityDomain)
admin.site.register(PortalBranding)
admin.site.register(PageAsset)
