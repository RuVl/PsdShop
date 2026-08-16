import tempfile
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db.models import ProtectedError
from django.test import TestCase, override_settings

from catalog.models import IMAGE_FIELDS, IMAGE_VARIANTS, Country, DocumentType, Product, ProductImage
from catalog.validators import RESERVED_SLUGS
from customer.models import Customer
from sales.models import Order, OrderItem


def png_bytes(width: int = 1600, height: int = 1200) -> bytes:
    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (width, height), (200, 210, 220)).save(buffer, format="PNG")
    return buffer.getvalue()


class CatalogFactoryMixin:
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
    """A country slug sits in the same URL position as a service path (/cart, /info)."""

    def test_a_reserved_slug_is_refused(self):
        country = Country(name="Cart", slug="cart", code="xx")

        with self.assertRaises(ValidationError):
            country.full_clean()

    def test_the_wildcard_segment_is_reserved(self):
        self.assertIn("all", RESERVED_SLUGS)

        with self.assertRaises(ValidationError):
            DocumentType(name="Everything", slug="all").full_clean()

    def test_a_document_type_cannot_shadow_a_service_path(self):
        with self.assertRaises(ValidationError):
            DocumentType(name="Purchases", slug="purchases").full_clean()

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


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ProductImageTests(CatalogFactoryMixin, TestCase):
    """The owner uploads one file; the storefront must never serve that original."""

    def setUp(self):
        super().setUp()
        media = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(override_settings(MEDIA_ROOT=media))
        self.media = Path(media)
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
