"""Site-wide values every storefront template needs: footer texts, support link, menu pages."""

from django.utils.functional import SimpleLazyObject

from content.models import Page, SiteSettings


def site_settings(request):
    """The settings row and the published pages, so the shared header/footer can render links."""

    return {
        # Lazy for the same reason `nav_pages` is: this runs for every rendered template, and most
        # of them - the SPA shell, every admin page - use neither value. `load()` is a
        # get_or_create, so eager meant a write query on the first request of an empty database.
        "site_settings": SimpleLazyObject(SiteSettings.load),
        # Lazy queryset: evaluated only by templates that actually draw the menu.
        "nav_pages": Page.objects.menu(),
    }
