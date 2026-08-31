from django.core.exceptions import ValidationError
from django.test import TestCase

from catalog.models import Country
from content.models import Page, SiteSettings, Slide


class PageSlugTests(TestCase):
    """A page slug is a top-level URL segment, so it answers to the same rules as a country."""

    def test_a_page_can_be_called_after_the_route_it_serves(self):
        """`/en/contacts/` is this row and nothing else - the name must not be reserved from it."""

        Page(slug="contacts", title="Contacts").full_clean()
        Page(slug="info", title="Info").full_clean()

    def test_a_page_cannot_shadow_a_service_path(self):
        with self.assertRaises(ValidationError):
            Page(slug="cart", title="Cart").full_clean()

    def test_a_page_cannot_shadow_a_country(self):
        Country.objects.create(name="Germany", slug="germany", code="de")

        with self.assertRaises(ValidationError):
            Page(slug="germany", title="About Germany").full_clean()

    def test_the_front_page_block_is_allowed(self):
        """`home` has no URL of its own, so nothing can collide with it."""

        Page(slug=Page.HOME, title="Home").full_clean()


class ContentApiTests(TestCase):
    """The JSON the SPA reads mirrors the bot pages: published rows only, both languages."""

    def setUp(self):
        Page.objects.create(slug="info", title_en="Rules", title_ru="Правила", body_en="<p>x</p>", body_ru="<p>у</p>")
        Page.objects.create(slug="hidden", title="Hidden", is_published=False)
        Page.objects.create(slug=Page.HOME, title="Home", body_en="<p>seo</p>")
        Slide.objects.create(title_en="Hi", title_ru="Привет", position=0)
        Slide.objects.create(title="Off", is_active=False, position=1)

    def test_page_list_is_menu_material(self):
        rows = self.client.get("/api/content/pages/").json()
        self.assertEqual([row["slug"] for row in rows], ["info"])
        self.assertEqual(rows[0]["title_ru"], "Правила")

    def test_page_detail_carries_both_bodies(self):
        row = self.client.get("/api/content/pages/info/").json()
        self.assertEqual(row["body_en"], "<p>x</p>")
        self.assertIn("body_ru", row)

    def test_home_block_is_reachable_by_slug_only(self):
        self.assertEqual(self.client.get("/api/content/pages/home/").json()["body_en"], "<p>seo</p>")

    def test_unpublished_page_is_404(self):
        self.assertEqual(self.client.get("/api/content/pages/hidden/").status_code, 404)

    def test_slides_skip_inactive(self):
        rows = self.client.get("/api/content/slides/").json()
        self.assertEqual([row["title_en"] for row in rows], ["Hi"])

    def test_settings_row(self):
        SiteSettings.load()
        row = self.client.get("/api/content/settings/").json()
        self.assertIn("support_url", row)
        self.assertIn("footer_note_ru", row)
