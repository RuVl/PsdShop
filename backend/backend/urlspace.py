"""
What the site answers on itself, and what a slug is therefore not allowed to be.

The catalog is addressed as `/<lang>/<country>/<type>/`, so a country slug lands in the same
position as a service path and as a text page written in the admin. This module is the one place
that knows which names are taken.

Both checks run in `full_clean()`, which the admin calls and the ORM does not: `Country.objects
.create(slug="cart")` from a shell, a data migration or a management command goes through
untouched. That is deliberate - slugs are typed by the owner in the admin, and the guarantee costs
either a schema-level constraint that freezes the list into migrations or a `full_clean()` inside
`save()`. Anything writing slugs from code has to call `full_clean()` itself.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

# Segments the site answers on by itself, from the URL map in docs/architecture.md. The pages the owner
# writes - `info`, `contacts` - are deliberately absent: those are `content.Page` rows, not fixed
# routes, and reserving them here would forbid creating the very pages they stand for.
SERVICE_SLUGS = frozenset(
    {
        # The wildcard the catalog URLs are built on.
        "all",
        "admin",
        "api",
        "cart",
        "purchases",
        "unsubscribe",
    }
)

# Models whose slug occupies the first catalog segment, `/<lang>/<slug>/`. A document type is
# addressed one level deeper, under a country, so it shares that position with nothing.
TOP_LEVEL_SLUG_MODELS = ("catalog.Country", "content.Page")


def reserved_slugs() -> frozenset[str]:
    """Every name the site itself answers on: service paths, language prefixes, asset roots."""

    prefixes = {_url_prefix(settings.STATIC_URL), _url_prefix(settings.MEDIA_URL)}
    return SERVICE_SLUGS | {code for code, _name in settings.LANGUAGES} | (prefixes - {""})


def validate_not_reserved(value: str) -> None:
    """Field validator: refuse a slug that would shadow a page the site serves itself."""

    if value.lower() in reserved_slugs():
        raise ValidationError(
            _("'%(slug)s' is reserved by the site and cannot be used as a slug."),
            params={"slug": value},
        )


def validate_slug_is_free(instance) -> None:
    """
    Refuse a slug another model already answers on at the top level.

    A country and a text page share the first segment, so `/en/contacts/` cannot be both. Their own
    tables are covered by `unique=True`; this is the check across them.
    """

    from django.apps import apps

    if not instance.slug:
        return

    for label in TOP_LEVEL_SLUG_MODELS:
        model = apps.get_model(label)
        if model is type(instance):
            continue

        if model.objects.filter(slug=instance.slug).exists():
            raise ValidationError(
                {
                    "slug": ValidationError(
                        _("'%(slug)s' is already used by another %(model)s."),
                        params={"slug": instance.slug, "model": model._meta.verbose_name},
                    )
                }
            )


def _url_prefix(url: str) -> str:
    """First segment of a settings URL: '/static/' -> 'static'. A URL on another host owns nothing here."""

    return "" if "://" in url else url.strip("/").split("/")[0]
