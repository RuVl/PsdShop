"""
Guarantee the site row `SITE_ID` points at.

`django.contrib.sites` seeds `example.com` at pk=1 through a `post_migrate` hook, so on a fresh
database this is a no-op. It earns its keep on a database where the row was edited away or the id
moved: without it `SITE_ID = 1` resolves to nothing and every page 500s, including the admin login
the owner needs to fix the domain from.
"""

from django.conf import settings
from django.db import migrations

PLACEHOLDER_DOMAIN = "example.com"


def ensure_site(apps, schema_editor):
    Site = apps.get_model("sites", "Site")
    site_id = getattr(settings, "SITE_ID", 1)

    Site.objects.get_or_create(
        pk=site_id,
        defaults={"domain": PLACEHOLDER_DOMAIN, "name": PLACEHOLDER_DOMAIN},
    )


def noop(apps, schema_editor):
    """The row belongs to `sites`, not to us - dropping it on a reverse would break that app."""


class Migration(migrations.Migration):
    dependencies = [
        ("sites", "0002_alter_domain_unique"),
    ]

    operations = [
        migrations.RunPython(ensure_site, noop),
    ]
