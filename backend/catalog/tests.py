from decimal import Decimal
from io import BytesIO

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db.models import ProtectedError
from django.test import TestCase

from backend.testing import TempUploadsMixin
from backend.urlspace import reserved_slugs
from catalog.models import IMAGE_FIELDS, IMAGE_VARIANTS, Country, DocumentType, Product, ProductImage
from content.models import Page
from customer.models import Customer
from sales.models import Order, OrderItem


def png_bytes(width: int = 1600, height: int = 1200) -> bytes:
    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (width, height), (200, 210, 220)).save(buffer, format="PNG")
    return buffer.getvalue()


class CatalogFactoryMixin(TempUploadsMixin):
    def setUp(self):
        super().setUp()
        self.country = Country.objects.create(name="Germany", slug="germany", code="de")
        self.document_type = DocumentType.objects.create(name="Utility bill", slug="utility-bill")

    def make_product(self, name: str = "Germany utility bill 2022", **overrides) -> Product:
        fields = {
            "name": name,
            "slug": overrides.pop("slug", "germany-utility-bill-2022"),
            "country": self.country,
            "document_type": self.document_type,
            "year": 2022,
            "price": Decimal("25.00"),
            "file": ContentFile(b"template", name="template.psd"),
        }
        fields.update(overrides)
        return Product.objects.create(**fields)


class SlugTests(CatalogFactoryMixin, TestCase):
    """A country slug sits in the same URL position as a service path (/cart) and as a page."""

    def test_a_reserved_slug_is_refused(self):
        country = Country(name="Cart", slug="cart", code="xx")

        with self.assertRaises(ValidationError):
            country.full_clean()

    def test_the_wildcard_segment_is_reserved(self):
        self.assertIn("all", reserved_slugs())

        with self.assertRaises(ValidationError):
            DocumentType(name="Everything", slug="all").full_clean()

    def test_a_document_type_cannot_shadow_a_service_path(self):
        with self.assertRaises(ValidationError):
            DocumentType(name="Purchases", slug="purchases").full_clean()

    def test_a_language_prefix_is_reserved(self):
        """The codes come from settings.LANGUAGES, not from a second list to keep in step."""

        with self.assertRaises(ValidationError):
            Country(name="English", slug="en", code="gb").full_clean()

    def test_the_media_root_is_reserved(self):
        """Derived from MEDIA_URL - nginx answers there, so a country cannot."""

        with self.assertRaises(ValidationError):
            Country(name="Media", slug="media", code="xx").full_clean()

    def test_a_country_cannot_shadow_a_page(self):
        Page.objects.create(slug="contacts", title="Contacts")

        with self.assertRaises(ValidationError):
            Country(name="Contacts", slug="contacts", code="xx").full_clean()

    def test_a_document_type_may_repeat_a_country_slug(self):
        """A type is addressed under a country, so the two never share a position."""

        DocumentType(name="Germany", slug=self.country.slug).full_clean()

    def test_an_ordinary_slug_passes(self):
        Country(name="Poland", slug="poland", code="pl").full_clean()

    def test_the_url_segment_carries_the_id(self):
        product = self.make_product()

        self.assertEqual(product.url_slug, f"{product.pk}-germany-utility-bill-2022")


class CountingTests(CatalogFactoryMixin, TestCase):
    """The sidebar counts what a visitor can actually buy."""

    def test_inactive_products_are_not_counted(self):
        self.make_product(slug="live-one")
        self.make_product(name="Draft", slug="draft-one", is_active=False)

        country = Country.objects.with_product_counts().get(pk=self.country.pk)

        self.assertEqual(country.products_count, 1)

    def test_an_empty_country_is_left_out_of_the_sidebar(self):
        Country.objects.create(name="Portugal", slug="portugal", code="pt")
        self.make_product()

        slugs = [country.slug for country in Country.objects.non_empty()]

        self.assertEqual(slugs, ["germany"])

    def test_active_filters_the_storefront_queryset(self):
        self.make_product(slug="live-one")
        self.make_product(name="Draft", slug="draft-one", is_active=False)

        self.assertEqual(Product.objects.active().count(), 1)


class ProductImageTests(CatalogFactoryMixin, TestCase):
    """The owner uploads one file; the storefront must never serve that original."""

    def setUp(self):
        super().setUp()
        self.product = self.make_product()

    def add_image(self, **overrides) -> ProductImage:
        return ProductImage.objects.create(
            product=self.product,
            image=ContentFile(png_bytes(), name="scan.png"),
            **overrides,
        )

    def test_every_variant_is_generated(self):
        image = self.add_image()

        for field in IMAGE_FIELDS:
            self.assertTrue(getattr(image, field), f"{field} was not generated")

    def test_variants_are_resized_and_keep_the_aspect_ratio(self):
        image = self.add_image()

        self.assertEqual(image.card.width, IMAGE_VARIANTS["card"])
        self.assertEqual(image.page.width, IMAGE_VARIANTS["page"])
        # 1600x1200 is 4:3, and thumbnail() keeps it.
        self.assertEqual(image.card.height, round(IMAGE_VARIANTS["card"] * 3 / 4))

    def test_replacing_the_upload_rebuilds_the_variants(self):
        image = self.add_image()
        first_card = image.card.name

        image.image = ContentFile(png_bytes(800, 800), name="other.png")
        image.save()

        self.assertNotEqual(image.card.name, first_card)
        self.assertFalse((self.media / first_card).exists(), "the previous variant was left on disk")

    def test_replacing_the_upload_drops_the_previous_original(self):
        image = ProductImage.objects.get(pk=self.add_image().pk)
        first_original = image.image.name

        image.image = ContentFile(png_bytes(800, 800), name="other.png")
        image.save()

        self.assertNotEqual(image.image.name, first_original)
        self.assertFalse((self.media / first_original).exists(), "the previous original was left on disk")

    def test_deleting_the_row_takes_every_file_with_it(self):
        image = self.add_image()
        paths = [self.media / getattr(image, field).name for field in ("image", *IMAGE_FIELDS)]
        self.assertTrue(all(path.exists() for path in paths))

        image.delete()

        self.assertEqual([path for path in paths if path.exists()], [])

    def test_a_queryset_delete_also_cleans_up(self):
        """The signal, not `delete()`, is what makes this true - the admin deletes in bulk."""

        image = self.add_image()
        card = self.media / image.card.name

        ProductImage.objects.all().delete()

        self.assertFalse(card.exists())

    def test_the_card_preview_is_the_first_image(self):
        second = self.add_image(position=2)
        first = self.add_image(position=1)

        self.assertEqual(self.product.preview.pk, first.pk)
        self.assertNotEqual(self.product.preview.pk, second.pk)

    def test_a_product_without_images_has_no_preview(self):
        self.assertIsNone(self.product.preview)


class ProductFileTests(CatalogFactoryMixin, TestCase):
    """The paid file is the product; it must be nowhere near what the site serves openly."""

    def test_the_file_is_written_outside_media_root(self):
        product = self.make_product()

        self.assertTrue((self.private / product.file.name).exists())
        self.assertEqual(list(self.media.iterdir()), [])

    def test_the_file_has_no_url(self):
        """`base_url` is unset on purpose - nothing may build a link to a paid file by accident."""

        product = self.make_product()

        with self.assertRaises(ValueError):
            product.file.url  # noqa: B018

    def test_deleting_the_product_takes_its_file(self):
        product = self.make_product()
        path = self.private / product.file.name

        product.delete()

        self.assertFalse(path.exists())

    def test_replacing_the_file_drops_the_previous_one(self):
        product = Product.objects.get(pk=self.make_product().pk)
        first = self.private / product.file.name

        product.file = ContentFile(b"newer", name="replacement.psd")
        product.save()

        self.assertFalse(first.exists())
        self.assertTrue((self.private / product.file.name).exists())


class ProductDeletionTests(CatalogFactoryMixin, TestCase):
    """A sold template has to stay downloadable, so the catalogue cannot drop it (ADR-0001)."""

    def test_a_bought_product_cannot_be_deleted(self):
        product = self.make_product()
        customer = Customer.objects.create(email="buyer@example.com")
        order = Order.objects.create(customer=customer, total_price=product.price)
        OrderItem.objects.create(
            order=order,
            product=product,
            product_name=product.name,
            unit_price=product.price,
        )

        with self.assertRaises(ProtectedError):
            product.delete()

        self.assertTrue(Product.objects.filter(pk=product.pk).exists())

    def test_an_unsold_product_can_be_deleted(self):
        product = self.make_product()

        product.delete()

        self.assertFalse(Product.objects.filter(pk=product.pk).exists())

    def test_taking_a_product_off_the_shelf_is_a_flag(self):
        product = self.make_product()

        product.is_active = False
        product.save(update_fields=["is_active"])

        self.assertNotIn(product, Product.objects.active())
        self.assertTrue(Product.objects.filter(pk=product.pk).exists())


class FlagTests(TestCase):
    def test_a_code_becomes_an_emoji_flag(self):
        self.assertEqual(Country(code="de").flag, "🇩🇪")

    def test_no_code_means_no_flag(self):
        self.assertEqual(Country(code="").flag, "")


class CatalogApiTests(CatalogFactoryMixin, TestCase):
    """The JSON the SPA reads mirrors the bot listing: same sets, same 404s, both languages."""

    def setUp(self):
        super().setUp()
        self.product = self.make_product(name_en="Germany utility bill 2022", name_ru="Германия счёт 2022")
        # A country with nothing on the shelf must not reach the sidebar payload.
        Country.objects.create(name="Portugal", slug="portugal", code="pt")

    def test_countries_carry_both_languages_and_counts(self):
        (row,) = self.client.get("/api/catalog/countries/").json()
        self.assertEqual(row["slug"], "germany")
        self.assertEqual(row["flag"], "🇩🇪")
        self.assertEqual(row["products_count"], 1)
        self.assertIn("name_en", row)
        self.assertIn("name_ru", row)

    def test_document_types_skip_empty(self):
        DocumentType.objects.create(name="Tax", slug="tax")
        slugs = [row["slug"] for row in self.client.get("/api/catalog/document-types/").json()]
        self.assertEqual(slugs, ["utility-bill"])

    def test_products_filter_by_slugs(self):
        response = self.client.get("/api/catalog/products/", {"country": "germany", "type": "utility-bill"})
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        (row,) = payload["results"]
        self.assertEqual(row["url_slug"], self.product.url_slug)
        self.assertEqual(row["country"], "germany")
        self.assertEqual(row["name_ru"], "Германия счёт 2022")

    def test_unknown_filter_slug_is_404_like_the_bot_page(self):
        self.assertEqual(self.client.get("/api/catalog/products/", {"country": "atlantis"}).status_code, 404)

    def test_all_means_any(self):
        payload = self.client.get("/api/catalog/products/", {"country": "all", "type": "all"}).json()
        self.assertEqual(payload["count"], 1)

    def test_inactive_products_stay_out(self):
        self.make_product(slug="hidden", is_active=False)
        self.assertEqual(self.client.get("/api/catalog/products/").json()["count"], 1)

    def test_detail_carries_description_and_gallery(self):
        row = self.client.get(f"/api/catalog/products/{self.product.pk}/").json()
        self.assertIn("description_en", row)
        self.assertEqual(row["images"], [])
        self.assertIsNone(row["preview"])

    def test_detail_of_inactive_product_is_404(self):
        hidden = self.make_product(slug="hidden", is_active=False)
        self.assertEqual(self.client.get(f"/api/catalog/products/{hidden.pk}/").status_code, 404)
