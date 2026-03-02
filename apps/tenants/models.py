from django.db import models

from apps.base_models import BaseModel


class University(BaseModel):

    name = models.CharField(max_length=255)
    subdomain = models.SlugField(max_length=100, unique=True)

    db_name = models.CharField(max_length=255)
    db_host = models.CharField(max_length=255)
    db_port = models.CharField(max_length=10, default="5432")

    is_active = models.BooleanField(default=True)

    class Meta:
        app_label = "tenants"

    def __str__(self):
        return self.name

    @property
    def db_alias(self):
        return f"tenant_{self.subdomain}"
