"""sitemap.xml - every indexable storefront address, in both languages.

`django.contrib.sitemaps` already knows how to say a page twice: with `i18n` it walks the items
once per language and reverses each address with that language active, which is exactly what
`i18n_patterns` does to the URLs, and `alternates`/`x_default` print the hreflang set inside each
<url>. Writing that by hand would mean a second copy of the rules `storefront/seo.py` follows for
the <head>, and the two would drift.

What goes in is decided by the querysets the storefront itself lists from - `active()`,
`non_empty()`, `with_product_counts()`. A page nobody can reach from the site must not be
advertised here either, so the service pages (cart, purchases, unsubscribe) are absent: they are
`noindex`, see `seo.service_meta`.
"""

from django.conf import settings
from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from catalog.models import Country, DocumentType, Product
from content.models import Page


class StorefrontSitemap(Sitemap):
    """One language pass per address, hreflang included, on the site's own scheme."""

    i18n = True
    alternates = True
    x_default = True

    @property
    def protocol(self) -> str:
        # Absolute links are handed to a crawler, not built from its request - same rule as
        # backend/sites.py: absolute_url(). Read on access, so a settings override reaches it.
        return settings.SITE_SCHEME


class HomeSitemap(StorefrontSitemap):
    changefreq = "daily"
    priority = 1.0

    def items(self):
        return [""]

    def location(self, item):
        return reverse("storefront:home")


class ListingSitemap(StorefrontSitemap):
    """`/<country>/<type>/` and its two one-facet forms, for facets that hold products."""

    changefreq = "daily"
    priority = 0.8

    def items(self):
        sold = Product.objects.active().values_list("country__slug", "document_type__slug").distinct()
        countries = Country.objects.non_empty().values_list("slug", flat=True)
        types = DocumentType.objects.non_empty()

        # `all` is the wildcard the catalog URLs are built on; all/all is the home page and 301s.
        pairs = [(country, "all") for country in countries]
        pairs += [("all", doctype.slug) for doctype in types]
        return pairs + sorted(sold)

    def location(self, item):
        country, doctype = item
        return reverse("storefront:catalog", kwargs={"country": country, "doctype": doctype})


class ProductSitemap(StorefrontSitemap):
    changefreq = "weekly"
    priority = 0.6

    def items(self):
        # select_related, not for_listing(): the address needs the two slugs and nothing else,
        # and the card's image prefetch would be a query per page for nothing.
        return Product.objects.active().select_related("country", "document_type")

    def lastmod(self, item):
        return item.updated_at

    def location(self, item):
        return reverse(
            "storefront:product",
            kwargs={
                "country": item.country.slug,
                "doctype": item.document_type.slug,
                "product_slug": item.url_slug,
            },
        )


class PageSitemap(StorefrontSitemap):
    """Owner-written text pages. The `home` row is the front page's SEO block, not a page."""

    changefreq = "monthly"
    priority = 0.4

    def items(self):
        return Page.objects.menu()

    def lastmod(self, item):
        return item.updated_at

    def location(self, item):
        return reverse("storefront:page", kwargs={"page_slug": item.slug})


SITEMAPS = {
    "home": HomeSitemap,
    "listings": ListingSitemap,
    "products": ProductSitemap,
    "pages": PageSitemap,
}
