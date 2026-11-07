"""
Seed the two tenants (COMSATS, FAST) with portals, branding and login page assets.

Usage:
    python manage.py seed_tenants

Safe to re-run: every record is created with update_or_create, so running the
command again updates existing rows instead of duplicating them.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.tenants.choices import PageType, PortalType
from apps.tenants.models import (
    PageAsset,
    Portal,
    PortalBranding,
    University,
    UniversityPortal,
)

# Configuration
DB_HOST = settings.ENV("MAIN_POSTGRES_HOST", default="localhost")
DB_PORT = settings.ENV("MAIN_POSTGRES_PORT", default="5432")

UNIVERSITIES = [
    {
        "key": "comsats",
        "name": "COMSATS University",
        "subdomain": "comsats",
        "db_name": "intelliversity_comsats",
        "db_host": DB_HOST,
        "db_port": DB_PORT,
    },
    {
        "key": "fast",
        "name": "FAST University",
        "subdomain": "fast",
        "db_name": "intelliversity_fast",
        "db_host": DB_HOST,
        "db_port": DB_PORT,
    },
]

PORTALS = [
    PortalType.STUDENT,
    PortalType.FACULTY,
    PortalType.ADMIN,
]

LOGIN_PAGE_TYPE = PageType.LOGIN

BRANDING = {
    "comsats": {
        "logo": "global/comsats/student/public/branding/4d31473eb74c4a37bb9d28919e509107",
        "logo_dark": "global/comsats/student/public/branding/4d31473eb74c4a37bb9d28919e509107",
        "favicon": "global/comsats/student/public/branding/2c1940ee92b84e40b16a45a1f544b244",
        "theme": {
            "colors": {
                "text": "#352A25",
                "accent": "#B68C68",
                "primary": "#8C654B",
                "surface": "#FFFCF7",
                "secondary": "#624735",
                "background": "#F5EDE3",
                "text_muted": "#89796C",
            },
            "danger": "#B4534B",
            "page_bg": "#F7F1E9",
            "topbar_bg": "#624735",
            "sidebar_bg": "#352A25",
            "typography": {
                "font_family": "Lato, sans-serif",
                "base_size_px": 15,
                "heading_family": "Playfair Display, serif",
            },
            "border_radius_px": 12,
        },
    },
    "fast": {
        "logo": "global/fast/student/public/branding/95ac0cfea8054db9bcf7059c97371fe7",
        "logo_dark": "global/fast/student/public/branding/95ac0cfea8054db9bcf7059c97371fe7",
        "favicon": "global/fast/student/public/branding/95ac0cfea8054db9bcf7059c97371fe7",
        "theme": {
            "colors": {
                "text": "#292D27",
                "accent": "#A58B55",
                "primary": "#626B4F",
                "surface": "#FFFEFA",
                "secondary": "#414936",
                "background": "#F1F0E8",
                "text_muted": "#77796C",
            },
            "danger": "#A94442",
            "page_bg": "#F5F4ED",
            "topbar_bg": "#414936",
            "sidebar_bg": "#292D27",
            "typography": {
                "font_family": "Inter, sans-serif",
                "base_size_px": 15,
                "heading_family": "Cormorant Garamond, serif",
            },
            "border_radius_px": 12,
        },
    },
}

LOGIN_BG = {
    "comsats": "global/comsats/student/public/page_bg/cf84b51220434075a982f0fe59ab74aa",
    "fast": "global/fast/student/public/page_bg/85d16ba19d3d467e9e78e08a42f5126a",
}


class Command(BaseCommand):
    help = "Seed universities, portals, university-portal pairs, branding and login page assets for the COMSATS and FAST tenants (DEBUG only)."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "seed_tenants can only be run when DEBUG=True. Aborting."
            )

        with transaction.atomic():
            universities = self._seed_universities()
            portals = self._seed_portals()
            pairs = self._seed_university_portals(universities, portals)
            self._seed_branding(pairs)
            self._seed_page_assets(pairs)

        self.stdout.write(self.style.SUCCESS("Tenant seeding completed."))

    def _seed_universities(self):
        self.stdout.write("Seeding universities...")
        result = {}
        for uni_config in UNIVERSITIES:
            university, created = University.objects.update_or_create(
                subdomain=uni_config["subdomain"],
                defaults={
                    "name": uni_config["name"],
                    "db_name": uni_config["db_name"],
                    "db_host": uni_config["db_host"],
                    "db_port": uni_config["db_port"],
                    "is_active": True,
                },
            )
            result[uni_config["key"]] = university
            action = "created" if created else "updated"
            self.stdout.write(f"  University {action}")

        return result

    def _seed_portals(self):
        self.stdout.write("Seeding portals...")
        result = {}
        for name in PORTALS:
            portal, created = Portal.objects.update_or_create(
                name=name, defaults={"is_active": True}
            )
            result[name] = portal
            action = "created" if created else "updated"
            self.stdout.write(f"  Portal {action}")

        return result

    def _seed_university_portals(self, universities, portals):
        self.stdout.write("Seeding university portals...")
        pairs = []  # list of (university_key, UniversityPortal)
        for uni_key, university in universities.items():
            for portal in portals.values():
                pair, created = UniversityPortal.objects.update_or_create(
                    university=university,
                    portal=portal,
                    defaults={"is_active": True},
                )
                pairs.append((uni_key, pair))
                action = "created" if created else "updated"
                self.stdout.write(f"  UniversityPortal {action}")

        return pairs

    def _seed_branding(self, pairs):
        self.stdout.write("Seeding portal branding...")
        for uni_key, pair in pairs:
            branding_config = BRANDING[uni_key]
            branding, created = PortalBranding.objects.update_or_create(
                university_portal=pair,
                defaults={
                    "logo_public_id": branding_config["logo"],
                    "logo_dark_public_id": branding_config["logo_dark"],
                    "favicon_public_id": branding_config["favicon"],
                    "theme_config": branding_config["theme"],
                },
            )
            action = "created" if created else "updated"
            self.stdout.write(f"  PortalBranding {action}")

    def _seed_page_assets(self, pairs):
        self.stdout.write("Seeding page assets...")
        for uni_key, pair in pairs:
            asset, created = PageAsset.objects.update_or_create(
                university_portal=pair,
                page_type=LOGIN_PAGE_TYPE,
                defaults={"background_image_public_id": LOGIN_BG[uni_key]},
            )
            action = "created" if created else "updated"
            self.stdout.write(f"  PageAsset {action}")
