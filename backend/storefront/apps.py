from django.apps import AppConfig
from django.conf import settings
from django.core.checks import Tags, Warning, register

PLACEHOLDER_DOMAIN = "example.com"

SITE_DOMAIN_WARNING = (
    "The django_site row still points at the placeholder domain. Every absolute URL - the links "
    "in delivery e-mails, the canonical tags, the sitemap - is built from it (backend/sites.py), "
    "so they all lead to example.com. Fix it in the admin: Sites -> the single row -> domain."
)


@register(Tags.database)
def placeholder_site_domain(app_configs, databases=None, **kwargs):
    """
    Warn when a production deploy still carries the domain the sites app seeded.

    Tagged `database` so it runs where it is useful - `migrate`, which is the deploy step right
    before the site goes up - instead of on every management command, where a warning nobody can
    act on just teaches people to scroll past warnings.
    """

    if settings.DEBUG or not databases:
        return []

    from django.contrib.sites.models import Site

    try:
        site = Site.objects.get(pk=settings.SITE_ID)
    except Exception:
        # No table yet (the first `migrate`), or no row - `migrate` is what fixes both, and a
        # check that raises there would block it.
        return []

    if site.domain != PLACEHOLDER_DOMAIN:
        return []

    return [Warning(SITE_DOMAIN_WARNING, id="storefront.W001")]


class StorefrontConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "storefront"
