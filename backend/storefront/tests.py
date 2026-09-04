"""Storefront catalog: routing, language prefix, filtering, the sidebar and the UA split."""

import tempfile
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings

from backend.testing import TempUploadsMixin
from catalog.models import Country, DocumentType, Product
from content.models import Page, Slide

BOT_UA = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"

# What `make spa` would leave in the templates dir, cut down to the contract the view fills.
SHELL_HTML = '<!DOCTYPE html><html lang="{{ LANGUAGE_CODE }}"><head>{{ storefront_meta }}</head><body><div id="app"></div></body></html>'  # noqa: E501


def shell_on_disk():
    """A TEMPLATES override whose DIRS hold a shell.html, standing in for the vite build."""

    tmp = tempfile.mkdtemp()
    Path(tmp, "storefront").mkdir()
    Path(tmp, "storefront", "shell.html").write_text(SHELL_HTML)
    templates = deepcopy(settings.TEMPLATES)
    templates[0]["DIRS"] = [tmp]
    return override_settings(TEMPLATES=templates)


class CatalogViewTests(TempUploadsMixin, TestCase):
    @classmethod
    def _product(cls, country, doctype, *, year, price="10.00", slug=None, active=True):
        slug = slug or f"{country.slug}-{doctype.slug}-{year or 'x'}"
        return Product.objects.create(
            country=country,
            document_type=doctype,
            year=year,
            price=Decimal(price),
            slug=slug,
            name_en=f"{country.slug} {doctype.slug} {year}",
            name_ru=f"{country.slug} {doctype.slug} {year}",
            is_active=active,
            file=ContentFile(b"x", name=f"{slug}.psd"),
        )

    def setUp(self):
        super().setUp()
        # The catalog assertions are about the server-rendered page, so ask as a bot; without the
        # header the view would answer with the SPA shell (or its fallback) instead.
        self.client.defaults["HTTP_USER_AGENT"] = BOT_UA
        self.germany = Country.objects.create(
            slug="germany", code="de", name_en="Germany", name_ru="Германия", is_popular=True
        )
        self.france = Country.objects.create(slug="france", code="fr", name_en="France", name_ru="Франция")
        # No products - must never show up in the sidebar.
        self.empty = Country.objects.create(slug="portugal", code="pt", name_en="Portugal", name_ru="Португалия")

        self.utility = DocumentType.objects.create(slug="utility-bill", name_en="Utility bill", name_ru="Счёт")
        self.bank = DocumentType.objects.create(slug="bank-statement", name_en="Bank statement", name_ru="Выписка")

        self._product(self.germany, self.utility, year=2022)
        self._product(self.germany, self.utility, year=2023)
        self._product(self.germany, self.bank, year=2023)
        self._product(self.france, self.utility, year=2021)
        self.hidden = self._product(self.germany, self.utility, year=2019, slug="hidden", active=False)

    def test_root_redirects_to_language(self):
        self.assertRedirects(self.client.get("/", HTTP_ACCEPT_LANGUAGE="ru"), "/ru/", fetch_redirect_response=False)
        self.assertRedirects(self.client.get("/", HTTP_ACCEPT_LANGUAGE="en"), "/en/", fetch_redirect_response=False)

    def test_home_lists_active_products_only(self):
        response = self.client.get("/en/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "germany utility-bill 2022")
        self.assertNotContains(response, "hidden utility-bill 2019")

    def test_all_all_redirects_to_home(self):
        response = self.client.get("/en/all/all/")
        self.assertRedirects(response, "/en/", status_code=301, fetch_redirect_response=False)

    def test_country_filter(self):
        response = self.client.get("/en/france/all/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["products"]), 1)

    def test_type_filter(self):
        response = self.client.get("/en/germany/bank-statement/")
        self.assertEqual(len(response.context["products"]), 1)

    def test_unknown_country_404(self):
        self.assertEqual(self.client.get("/en/atlantis/all/").status_code, 404)

    def test_sidebar_hides_empty_country(self):
        slugs = {c.slug for c in self.client.get("/en/").context["countries"]}
        self.assertIn("germany", slugs)
        self.assertNotIn("portugal", slugs)

    def test_country_product_counts(self):
        germany = next(c for c in self.client.get("/en/").context["countries"] if c.slug == "germany")
        self.assertEqual(germany.products_count, 3)

    def test_pagination(self):
        # Three active germany utility-bill products (2022, 2023 + this) split into two pages of 2.
        self._product(self.germany, self.utility, year=2024, slug="extra")
        with patch("storefront.views.PAGE_SIZE", 2):
            page1 = self.client.get("/en/germany/utility-bill/")
            self.assertEqual(len(page1.context["products"]), 2)
            page2 = self.client.get("/en/germany/utility-bill/?page=2")
            self.assertEqual(page2.context["page_obj"].number, 2)

    def test_every_page_is_linked_by_number(self):
        """The crawler must reach page 5 from page 1, not only page 2 (mirrors Pagination.vue)."""

        for index in range(20):
            self._product(self.germany, self.utility, year=2024, slug=f"extra-{index}")

        with patch("storefront.views.PAGE_SIZE", 2):
            page1 = self.client.get("/en/germany/utility-bill/")
            self.assertContains(page1, 'href="?page=2"')
            self.assertContains(page1, f'href="?page={page1.context["page_obj"].paginator.num_pages}"')
            # A long listing is elided rather than printed page by page.
            self.assertIn(page1.context["page_obj"].paginator.ELLIPSIS, page1.context["page_range"])

    def test_a_page_past_the_end_lands_on_the_last_one(self):
        with patch("storefront.views.PAGE_SIZE", 2):
            response = self.client.get("/en/germany/utility-bill/?page=999")
        self.assertEqual(response.context["page_obj"].number, response.context["page_obj"].paginator.num_pages)


class DynamicRenderingTests(TempUploadsMixin, TestCase):
    """The UA split: bots get the rendered page, people get the SPA shell, both with one meta."""

    def setUp(self):
        super().setUp()
        country = Country.objects.create(slug="germany", code="de", name_en="Germany", name_ru="Германия")
        doctype = DocumentType.objects.create(slug="utility-bill", name_en="Utility bill", name_ru="Счёт")
        Product.objects.create(
            country=country,
            document_type=doctype,
            year=2022,
            price=Decimal("10.00"),
            slug="one",
            name_en="Germany utility bill 2022",
            name_ru="Германия счёт 2022",
            is_active=True,
            file=ContentFile(b"x", name="one.psd"),
        )

    def test_bot_gets_rendered_catalog(self):
        with shell_on_disk():
            response = self.client.get("/en/germany/all/", HTTP_USER_AGENT=BOT_UA)
        self.assertContains(response, "products-list")
        self.assertContains(response, "Germany utility bill 2022")

    def test_person_gets_shell_with_page_meta(self):
        with shell_on_disk():
            response = self.client.get("/en/germany/all/", HTTP_USER_AGENT="Mozilla/5.0 (X11; Linux x86_64)")
        self.assertContains(response, '<div id="app">')
        self.assertNotContains(response, "products-list")
        # The shell still carries this page's meta - same title the bot page renders.
        self.assertContains(response, "Germany |")
        self.assertContains(response, 'hreflang="ru"')

    def test_person_without_build_falls_back_to_rendered_page(self):
        # No shell.html on disk (no `make spa` yet): the site must degrade, not 500.
        with patch("storefront.views.SHELL_TEMPLATE", "storefront/missing-shell.html"):
            response = self.client.get("/en/", HTTP_USER_AGENT="Mozilla/5.0 (X11; Linux x86_64)")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "products-list")

    def test_service_pages_serve_noindex_shell_to_everyone(self):
        with shell_on_disk():
            for ua in (BOT_UA, "Mozilla/5.0 (X11; Linux x86_64)"):
                for url in ("/en/cart/", "/en/purchases/", "/en/unsubscribe/token-x/"):
                    response = self.client.get(url, HTTP_USER_AGENT=ua)
                    self.assertContains(response, '<div id="app">', msg_prefix=f"{ua} {url}")
                    self.assertContains(response, 'name="robots" content="noindex"', msg_prefix=f"{ua} {url}")

    def _second_product(self):
        Product.objects.create(
            country=Country.objects.get(slug="germany"),
            document_type=DocumentType.objects.get(slug="utility-bill"),
            year=2023,
            price=Decimal("10.00"),
            slug="two",
            name_en="Germany utility bill 2023",
            name_ru="Германия счёт 2023",
            is_active=True,
            file=ContentFile(b"x", name="two.psd"),
        )

    def test_canonical_keeps_pagination_drops_filters(self):
        self._second_product()
        with shell_on_disk(), patch("storefront.views.PAGE_SIZE", 1):
            response = self.client.get("/en/germany/all/?page=2&utm_source=x", HTTP_USER_AGENT=BOT_UA)
        self.assertContains(response, 'rel="canonical" href="http://example.com/en/germany/all/?page=2"')

    def test_canonical_clamps_a_page_past_the_end(self):
        """`?page=999` renders the last page, so it must not canonicalize to itself."""

        self._second_product()
        with shell_on_disk(), patch("storefront.views.PAGE_SIZE", 1):
            response = self.client.get("/en/germany/all/?page=999", HTTP_USER_AGENT=BOT_UA)
        self.assertContains(response, 'rel="canonical" href="http://example.com/en/germany/all/?page=2"')

    def test_canonical_of_a_page_past_the_end_of_a_single_page_listing_is_bare(self):
        with shell_on_disk():
            response = self.client.get("/en/germany/all/?page=999", HTTP_USER_AGENT=BOT_UA)
        self.assertContains(response, 'rel="canonical" href="http://example.com/en/germany/all/"')

    def test_the_shell_carries_the_same_clamped_canonical(self):
        """The clamp lives in build_meta, so the SPA branch cannot drift from the bot one."""

        with shell_on_disk():
            response = self.client.get("/en/germany/all/?page=999", HTTP_USER_AGENT="Mozilla/5.0 (X11; Linux x86_64)")
        self.assertContains(response, 'rel="canonical" href="http://example.com/en/germany/all/"')

    def test_the_bot_listing_applies_the_search(self):
        """A crawler on `?q=` must see the filtered set the API returns, not the whole facet."""

        self._second_product()
        with shell_on_disk():
            response = self.client.get("/en/germany/all/?q=2023", HTTP_USER_AGENT=BOT_UA)
        self.assertContains(response, "Germany utility bill 2023")
        self.assertNotContains(response, "Germany utility bill 2022")

    def test_the_bot_pagination_carries_the_search(self):
        self._second_product()
        with shell_on_disk(), patch("storefront.views.PAGE_SIZE", 1):
            response = self.client.get("/en/germany/all/?q=utility", HTTP_USER_AGENT=BOT_UA)
        self.assertContains(response, 'href="?q=utility&amp;page=2"')

    def test_the_all_all_redirect_keeps_the_search(self):
        response = self.client.get("/en/all/all/?q=utility", HTTP_USER_AGENT=BOT_UA)
        self.assertRedirects(response, "/en/?q=utility", status_code=301, fetch_redirect_response=False)


class ProductPageTests(TempUploadsMixin, TestCase):
    """The product page: canonical address, both presentations, ld+json."""

    def setUp(self):
        super().setUp()
        country = Country.objects.create(slug="germany", code="de", name_en="Germany", name_ru="Германия")
        doctype = DocumentType.objects.create(slug="utility-bill", name_en="Utility bill", name_ru="Счёт")
        self.product = Product.objects.create(
            country=country,
            document_type=doctype,
            year=2022,
            price=Decimal("25.00"),
            slug="vattenfall-2022",
            name_en="Vattenfall 2022",
            name_ru="Vattenfall 2022",
            is_active=True,
            file=ContentFile(b"x", name="one.psd"),
        )
        self.url = f"/en/germany/utility-bill/{self.product.pk}-vattenfall-2022/"

    def test_bot_gets_rendered_product_page(self):
        response = self.client.get(self.url, HTTP_USER_AGENT=BOT_UA)
        self.assertContains(response, "Vattenfall 2022")
        self.assertContains(response, "application/ld+json")
        self.assertContains(response, '"@type": "Product"')
        self.assertContains(response, '"priceCurrency": "USD"')

    def test_person_gets_shell_with_product_meta(self):
        with shell_on_disk():
            response = self.client.get(self.url, HTTP_USER_AGENT="Mozilla/5.0 (X11; Linux x86_64)")
        self.assertContains(response, '<div id="app">')
        self.assertContains(response, 'og:type" content="product"')
        self.assertContains(response, "Vattenfall 2022")

    def test_stale_slug_redirects_to_canonical(self):
        response = self.client.get(f"/en/germany/utility-bill/{self.product.pk}-old-name/", HTTP_USER_AGENT=BOT_UA)
        self.assertRedirects(response, self.url, status_code=301, fetch_redirect_response=False)

    def test_wrong_facet_redirects_to_canonical(self):
        Country.objects.create(slug="france", code="fr", name_en="France", name_ru="Франция")
        url = f"/en/france/utility-bill/{self.product.pk}-vattenfall-2022/"
        response = self.client.get(url, HTTP_USER_AGENT=BOT_UA)
        self.assertRedirects(response, self.url, status_code=301, fetch_redirect_response=False)

    def test_a_slug_without_a_hyphen_after_the_id_is_a_404(self):
        """`12abc` used to reach the view and hand `int()` a word - a 500 on a crawlable address."""

        self.assertEqual(self.client.get("/en/germany/utility-bill/12abc/", HTTP_USER_AGENT=BOT_UA).status_code, 404)

    def test_the_bare_id_still_resolves(self):
        response = self.client.get(f"/en/germany/utility-bill/{self.product.pk}/", HTTP_USER_AGENT=BOT_UA)
        self.assertRedirects(response, self.url, status_code=301, fetch_redirect_response=False)

    def test_unknown_or_inactive_product_is_404(self):
        self.assertEqual(self.client.get("/en/germany/utility-bill/999999-x/", HTTP_USER_AGENT=BOT_UA).status_code, 404)
        self.product.is_active = False
        self.product.save(update_fields=["is_active"])
        self.assertEqual(self.client.get(self.url, HTTP_USER_AGENT=BOT_UA).status_code, 404)


class PageViewTests(TempUploadsMixin, TestCase):
    """Owner-written pages on /<lang>/<slug>/: both presentations, unpublished is a 404."""

    def setUp(self):
        super().setUp()
        Page.objects.create(slug="info", title_en="Rules", title_ru="Правила", body_en="<p>Store rules text</p>")
        Page.objects.create(slug="hidden", title="Hidden", is_published=False)
        Page.objects.create(slug=Page.HOME, title="Home", body_en="<p>home seo block</p>")

    def test_bot_gets_rendered_page(self):
        response = self.client.get("/en/info/", HTTP_USER_AGENT=BOT_UA)
        self.assertContains(response, "Store rules text")
        self.assertContains(response, "<title>Rules |")

    def test_person_gets_shell_with_page_meta(self):
        with shell_on_disk():
            response = self.client.get("/en/info/", HTTP_USER_AGENT="Mozilla/5.0 (X11; Linux x86_64)")
        self.assertContains(response, '<div id="app">')
        self.assertContains(response, "<title>Rules |")

    def test_unpublished_and_home_slugs_are_404(self):
        self.assertEqual(self.client.get("/en/hidden/", HTTP_USER_AGENT=BOT_UA).status_code, 404)
        self.assertEqual(self.client.get("/en/home/", HTTP_USER_AGENT=BOT_UA).status_code, 404)

    def test_menu_links_point_at_pages(self):
        response = self.client.get("/en/", HTTP_USER_AGENT=BOT_UA)
        self.assertContains(response, 'href="/en/info/"')
        self.assertNotContains(response, 'href="/en/hidden/"')

    def test_home_renders_slides_and_seo_block(self):
        Slide.objects.create(title_en="Welcome!", title_ru="Привет!", position=0)
        response = self.client.get("/en/", HTTP_USER_AGENT=BOT_UA)
        self.assertContains(response, "Welcome!")
        self.assertContains(response, "home seo block")
        # A filtered listing carries neither.
        Country.objects.create(slug="germany", code="de", name_en="Germany", name_ru="Германия")
        filtered = self.client.get("/en/germany/all/", HTTP_USER_AGENT=BOT_UA)
        self.assertNotContains(filtered, "Welcome!")
        self.assertNotContains(filtered, "home seo block")
