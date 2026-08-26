"""Storefront catalog: routing, language prefix, filtering and the sidebar."""

from decimal import Decimal
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.test import TestCase

from backend.testing import TempUploadsMixin
from catalog.models import Country, DocumentType, Product


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

    def test_year_filter(self):
        response = self.client.get("/en/germany/utility-bill/?year=2023")
        self.assertEqual(len(response.context["products"]), 1)

    def test_year_list_ignores_year_selection(self):
        # Picking a year must not shrink the year dropdown itself.
        response = self.client.get("/en/germany/utility-bill/?year=2022")
        self.assertEqual(response.context["years"], [2023, 2022])

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
