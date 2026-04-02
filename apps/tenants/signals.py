from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.tenants.models import (
    DomainSSLStatus,
    PortalBranding,
    UniversityDomain,
    UniversityPortal,
)


@receiver(post_save, sender=UniversityPortal)
def create_default_domain(sender, instance, created, **kwargs):
    if not created:
        return

    university = instance.university
    portal = instance.portal

    domain_name = f"{portal.name}.{university.subdomain}.intelliversity.com"

    # Ensure no existing primary domain
    UniversityDomain.objects.filter(university_portal=instance, is_primary=True).update(
        is_primary=False
    )

    UniversityDomain.objects.get_or_create(
        domain=domain_name,
        defaults={
            "university_portal": instance,
            "is_primary": True,
            "is_custom": False,
            "ssl_status": DomainSSLStatus.ACTIVE,
        },
    )


@receiver(post_save, sender=UniversityPortal)
def create_portal_branding(sender, instance, created, **kwargs):
    if created:
        PortalBranding.objects.create(university_portal=instance)
