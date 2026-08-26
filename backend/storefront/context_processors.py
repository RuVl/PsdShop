"""Site-wide values every storefront template needs: the footer texts and support link."""

from content.models import SiteSettings


def site_settings(request):
    """The one settings row, so the shared header/footer can read it without a per-view query."""

    return {"site_settings": SiteSettings.load()}
