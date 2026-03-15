from django.db import models

from apps.base_models import BaseModel
from apps.tenants.choices import PortalType


class University(BaseModel):

    name = models.CharField(max_length=255)
    subdomain = models.SlugField(max_length=100, unique=True)

    db_name = models.CharField(max_length=255)
    db_host = models.CharField(max_length=255)
    db_port = models.CharField(max_length=10, default="5432")

    is_active = models.BooleanField(default=True)

    portals = models.ManyToManyField("Portal", related_name="universities")

    class Meta:
        app_label = "tenants"

    def __str__(self):
        return self.name

    @property
    def db_alias(self):
        return f"intelliversity_{self.subdomain}"


class Portal(BaseModel):
    name = models.CharField(choices=PortalType.choices, max_length=50, unique=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name
