from django.contrib import admin

from apps.tenants.models import Portal, University

# Register your models here.
admin.site.register(University)
admin.site.register(Portal)
