"""Site-wide values every storefront template needs: footer texts, support link, menu pages."""

from content.models import Page, SiteSettings


def site_settings(request):
    """The settings row and the published pages, so the shared header/footer can render links."""

    return {
        "site_settings": SiteSettings.load(),
        # Lazy queryset: evaluated only by templates that actually draw the menu.
        "nav_pages": Page.objects.filter(is_published=True).exclude(slug=Page.HOME),
    }
