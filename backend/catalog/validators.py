"""Slug rules shared by the catalog models."""

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

# The storefront addresses the catalog as /<lang>/<country>/<type>/, so a country or type slug
# lands in the same position as a service path. A country called "cart" would shadow the cart page,
# and "all" is the wildcard the URLs are built on - both have to be refused at the source.
RESERVED_SLUGS = frozenset(
    {
        "all",
        "admin",
        "api",
        "cart",
        "contacts",
        "en",
        "info",
        "media",
        "purchases",
        "robots.txt",
        "ru",
        "sitemap.xml",
        "static",
        "unsubscribe",
    }
)


def validate_not_reserved(value: str):
    if value.lower() in RESERVED_SLUGS:
        raise ValidationError(
            _("'%(slug)s' is reserved by the site and cannot be used as a slug."),
            params={"slug": value},
        )
