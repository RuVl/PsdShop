"""The machine-readable half of the storefront: sitemap.xml, robots.txt and the hreflang set.

These live apart from `tests.py` for the same reason `sales/tests_statistics.py` does: that file
holds the routing and the UA split, this one holds what crawlers read.
"""

from decimal import Decimal
from unittest.mock import patch
from xml.etree import ElementTree

from django.contrib.sites.models import Site
from django.core.files.base import ContentFile
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from backend.testing import TempUploadsMixin
from catalog.models import Country, DocumentType, Product
from content.models import Page
from storefront import sitemaps
from storefront.tests import BOT_UA

SITEMAP_NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9", "xhtml": "http://www.w3.org/1999/xhtml"}

# The links a crawler reads are built from the site row and SITE_SCHEME, never from the request,
# so the tests pin both instead of inheriting whatever the developer's dev.env says.
SITE = "https://testserver"


class SiteRowMixin:
    """Pins the django_site row - and unpins the module-level cache the sites app keeps."""

    def setUp(self):
        super().setUp()
        Site.objects.update_or_create(pk=1, defaults={"domain": "testserver", "name": "test"})
        Site.objects.clear_cache()
        self.addCleanup(Site.objects.clear_cache)


def sections(response) -> list[str]:
    """The section files an index points at."""

    root = ElementTree.fromstring(response.content)
    return [node.text for node in root.findall("s:sitemap/s:loc", SITEMAP_NS)]


def locations(response) -> list[str]:
    root = ElementTree.fromstring(response.content)
    return [node.text for node in root.findall("s:url/s:loc", SITEMAP_NS)]


def alternates(response, location: str) -> dict[str, str]:
    """hreflang -> href for the one <url> whose <loc> matches."""

    root = ElementTree.fromstring(response.content)
    for url in root.findall("s:url", SITEMAP_NS):
        if url.find("s:loc", SITEMAP_NS).text != location:
            continue
        return {link.get("hreflang"): link.get("href") for link in url.findall("xhtml:link", SITEMAP_NS)}
    raise AssertionError(f"{location} is not in this sitemap")


@override_settings(SITE_SCHEME="https")
class SitemapTests(SiteRowMixin, TempUploadsMixin, TestCase):
    @classmethod
    def _product(cls, country, doctype, *, slug, year=2022, active=True):
        return Product.objects.create(
            country=country,
            document_type=doctype,
            year=year,
            price=Decimal("10.00"),
            slug=slug,
            name_en=f"{slug} en",
            name_ru=f"{slug} ru",
            is_active=active,
            file=ContentFile(b"x", name=f"{slug}.psd"),
        )

    def setUp(self):
        super().setUp()
        self.germany = Country.objects.create(slug="germany", code="de", name_en="Germany", name_ru="Германия")
        self.france = Country.objects.create(slug="france", code="fr", name_en="France", name_ru="Франция")
        # Nothing on sale here - it must not reach the sitemap at all.
        Country.objects.create(slug="portugal", code="pt", name_en="Portugal", name_ru="Португалия")

        self.utility = DocumentType.objects.create(slug="utility-bill", name_en="Utility bill", name_ru="Счёт")
        self.bank = DocumentType.objects.create(slug="bank-statement", name_en="Bank statement", name_ru="Выписка")

        self.product = self._product(self.germany, self.utility, slug="germany-utility")
        self._product(self.france, self.utility, slug="france-utility")
        # Only an inactive product, so germany x bank-statement is an empty facet.
        self.hidden = self._product(self.germany, self.bank, slug="hidden", active=False)

        Page.objects.create(slug="info", title_en="Rules", title_ru="Правила", body_en="<p>x</p>")
        Page.objects.create(slug="draft", title="Draft", is_published=False)
        Page.objects.create(slug=Page.HOME, title="Home", body_en="<p>home</p>")

    def get(self, section="products", query=""):
        return self.client.get(f"/sitemap-{section}.xml{query}")

    def all_locations(self) -> list[str]:
        """Every address in the map, walked the way a crawler walks it: index, then sections."""

        index = self.client.get("/sitemap.xml")
        found = []
        for url in sections(index):
            found += locations(self.client.get(url.replace(SITE, "")))
        return found

    def test_it_is_xml_and_lists_both_languages_of_a_product(self):
        response = self.get()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/xml")
        for lang in ("en", "ru"):
            self.assertIn(
                f"{SITE}/{lang}/germany/utility-bill/{self.product.url_slug}/",
                locations(response),
            )

    def test_the_index_points_at_every_section(self):
        response = self.client.get("/sitemap.xml")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            sections(response),
            [f"{SITE}/sitemap-{name}.xml" for name in ("home", "listings", "products", "pages")],
        )

    def test_every_url_carries_its_alternates_and_an_x_default(self):
        response = self.get("home")

        links = alternates(response, f"{SITE}/en/")
        self.assertEqual(
            links,
            {
                "en": f"{SITE}/en/",
                "ru": f"{SITE}/ru/",
                # x-default is the bare root: Django 302s it by Accept-Language.
                "x-default": f"{SITE}/",
            },
        )

    def test_the_owner_written_pages_are_listed_but_the_home_row_is_not(self):
        urls = locations(self.get("pages"))

        self.assertIn(f"{SITE}/en/info/", urls)
        # The `home` row is the front page's SEO block, not a page of its own.
        self.assertNotIn(f"{SITE}/en/home/", urls)
        self.assertNotIn(f"{SITE}/en/draft/", urls)

    def test_nothing_hidden_or_service_reaches_the_sitemap(self):
        urls = self.all_locations()

        self.assertNotIn(f"{SITE}/en/germany/bank-statement/{self.hidden.url_slug}/", urls)
        for path in ("/en/cart/", "/en/purchases/", "/en/unsubscribe/token-x/", "/en/all/all/"):
            self.assertNotIn(f"{SITE}{path}", urls)

    def test_only_facets_with_products_are_listed(self):
        urls = set(locations(self.get("listings")))

        self.assertIn(f"{SITE}/en/germany/utility-bill/", urls)
        self.assertIn(f"{SITE}/en/germany/all/", urls)
        self.assertIn(f"{SITE}/en/all/utility-bill/", urls)
        # An inactive product leaves the facet empty, and an empty country has no page at all.
        self.assertNotIn(f"{SITE}/en/germany/bank-statement/", urls)
        self.assertNotIn(f"{SITE}/en/all/bank-statement/", urls)
        self.assertNotIn(f"{SITE}/en/portugal/all/", urls)

    def test_a_product_is_listed_at_the_address_the_view_calls_canonical(self):
        # No year and no slug: the URL is the bare id, and the product view must not 301 it.
        bare = Product.objects.create(
            country=self.germany,
            document_type=self.utility,
            year=None,
            price=Decimal("10.00"),
            slug="",
            name_en="Bare",
            name_ru="Без слага",
            file=ContentFile(b"x", name="bare.psd"),
        )
        location = f"{SITE}/en/germany/utility-bill/{bare.url_slug}/"

        self.assertIn(location, locations(self.get()))
        self.assertEqual(self.client.get(location.replace(f"{SITE}", "")).status_code, 200)

    def test_an_empty_catalog_still_answers_with_a_valid_sitemap(self):
        Product.objects.all().delete()

        # No products, so no listing and no product pages - the home page and the text page remain.
        self.assertEqual(
            set(self.all_locations()),
            {
                f"{SITE}/en/",
                f"{SITE}/ru/",
                f"{SITE}/en/info/",
                f"{SITE}/ru/info/",
            },
        )

    def test_a_flooded_sitemap_paginates_instead_of_growing(self):
        for index in range(20):
            self._product(self.france, self.bank, slug=f"flood-{index}")

        # The limit is per section, which is why the map is an index over section files.
        with patch.object(sitemaps.StorefrontSitemap, "limit", 10):
            first, second = self.get("products"), self.get("products", "?p=2")

            self.assertEqual(len(locations(first)), 10)
            self.assertTrue(locations(second))
            # The index advertises the overflow page, or nothing would ever fetch it.
            self.assertIn(f"{SITE}/sitemap-products.xml?p=2", sections(self.client.get("/sitemap.xml")))
            # Past the end and not a number are both "no such page", never a 500.
            self.assertEqual(self.get("products", "?p=999").status_code, 404)
            self.assertEqual(self.get("products", "?p=nope").status_code, 404)

    def test_an_unknown_section_is_a_404(self):
        self.assertEqual(self.client.get("/sitemap-nope.xml").status_code, 404)

    def test_the_query_count_does_not_grow_with_the_catalog(self):
        # The first request of a process pays for the site row and the settings singleton, which
        # are then cached - measure past that, or the warm-up looks like the growth.
        self.all_locations()

        with CaptureQueriesContext(connection) as small:
            self.all_locations()

        for index in range(50):
            self._product(self.france, self.bank, slug=f"more-{index}")

        with CaptureQueriesContext(connection) as large:
            self.all_locations()

        self.assertEqual(len(large), len(small))

    @override_settings(SITE_SCHEME="http")
    def test_the_scheme_follows_the_setting_not_the_request(self):
        # Links are handed out for another host to open, so the scheme is ours, not the crawler's.
        urls = sections(self.client.get("/sitemap.xml")) + self.all_locations()
        self.assertTrue(all(url.startswith("http://") for url in urls))


@override_settings(SITE_SCHEME="https")
class RobotsTests(SiteRowMixin, TestCase):
    def test_it_is_plain_text_and_points_at_the_sitemap(self):
        response = self.client.get("/robots.txt")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/plain")
        self.assertIn(f"Sitemap: {SITE}/sitemap.xml", response.content.decode())

    @override_settings(SITE_SCHEME="http")
    def test_the_sitemap_line_follows_the_site_row(self):
        site = Site.objects.get_current()
        site.domain = "localhost:8000"
        site.save()
        Site.objects.clear_cache()

        response = self.client.get("/robots.txt")

        self.assertIn("Sitemap: http://localhost:8000/sitemap.xml", response.content.decode())

    def test_the_pages_that_must_not_be_crawled_are_disallowed(self):
        body = self.client.get("/robots.txt").content.decode()

        for path in ("/admin/", "/api/", "*/cart/", "*/purchases/", "*/unsubscribe/"):
            self.assertIn(f"Disallow: {path}", body)

    def test_filters_and_pagination_stay_crawlable(self):
        # canonical already collapses them; blocking the crawl would just hide the products.
        body = self.client.get("/robots.txt").content.decode()

        self.assertNotIn("?page=", body)
        self.assertNotIn("?year=", body)


@override_settings(SITE_SCHEME="https")
class MetaAlternatesTests(SiteRowMixin, TestCase):
    """The <head> half of the same statement the sitemap makes."""

    def setUp(self):
        super().setUp()
        Page.objects.create(slug="info", title_en="Rules", title_ru="Правила", body_en="<p>x</p>")

    def test_a_page_advertises_every_language_and_an_x_default(self):
        response = self.client.get("/en/info/", HTTP_USER_AGENT=BOT_UA)
        body = response.content.decode()

        self.assertIn(f'hreflang="en" href="{SITE}/en/info/"', body)
        self.assertIn(f'hreflang="ru" href="{SITE}/ru/info/"', body)
        # The prefix-less address, the one the root redirector answers by Accept-Language.
        self.assertIn(f'hreflang="x-default" href="{SITE}/info/"', body)

    def test_the_head_and_the_sitemap_advertise_the_same_x_default(self):
        head = self.client.get("/en/", HTTP_USER_AGENT=BOT_UA).content.decode()
        sitemap = self.client.get("/sitemap-home.xml")

        self.assertIn(f'hreflang="x-default" href="{SITE}/"', head)
        self.assertEqual(alternates(sitemap, f"{SITE}/en/")["x-default"], f"{SITE}/")
