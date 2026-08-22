from django.core.exceptions import ValidationError
from django.test import TestCase

from catalog.models import Country
from content.models import Page


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
