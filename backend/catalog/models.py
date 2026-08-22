from io import BytesIO
from typing import TYPE_CHECKING

from django.core.files.base import ContentFile
from django.db import models
from django.db.models import Count, Q
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _

from backend.seo import MetaTagsMixin
from backend.urlspace import validate_not_reserved, validate_slug_is_free
from catalog.storages import ProductFilesStorage

if TYPE_CHECKING:
    from sales.models import OrderItem


class CountryQuerySet(models.QuerySet):
    def with_product_counts(self) -> "CountryQuerySet":
        """Annotate `products_count` - active products only, which is what the sidebar shows."""

        return self.annotate(products_count=Count("products", filter=Q(products__is_active=True)))

    def non_empty(self) -> "CountryQuerySet":
        return self.with_product_counts().filter(products_count__gt=0)


class Country(MetaTagsMixin):
    """
    Country of the document. Drives the sidebar, the flag on a card and one level of the URL.

    :param name: Country name (translated).
    :param slug: Latin slug used in the URL, e.g. "germany".
    :param code: ISO 3166-1 alpha-2 code, used for the flag.
    :param is_popular: Shown in the "popular" block of the sidebar - set by hand, not computed.
    :param position: Manual ordering; ties fall back to the name.
    :param seo_text: Text block under the listing (translated).
    """

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, validators=[validate_not_reserved])
    code = models.CharField(max_length=2, blank=True, default="")

    is_popular = models.BooleanField(default=False)
    position = models.PositiveSmallIntegerField(default=0)

    seo_text = models.TextField(blank=True, default="")

    objects = CountryQuerySet.as_manager()

    if TYPE_CHECKING:
        products: "ProductQuerySet"

    class Meta:
        verbose_name = _("Country")
        verbose_name_plural = _("Countries")
        ordering = ["position", "name"]

    def __str__(self):
        return f"{self.flag} {self.name}".strip()

    def clean(self):
        super().clean()
        # A country and a text page answer on the same URL segment - see backend/urlspace.py.
        validate_slug_is_free(self)

    @property
    def flag(self) -> str:
        return self.code2flag(self.code)

    @staticmethod
    def code2flag(code: str | None) -> str:
        """Emoji flag from an ISO code ('de' -> '🇩🇪'). Empty code gives an empty string."""

        return "".join(chr(0x1F1E6 + (ord(c.upper()) - ord("A"))) for c in code) if code else ""


class DocumentTypeQuerySet(models.QuerySet):
    def with_product_counts(self) -> "DocumentTypeQuerySet":
        return self.annotate(products_count=Count("products", filter=Q(products__is_active=True)))


class DocumentType(MetaTagsMixin):
    """
    Kind of document: utility bill, bank statement, tax. A badge on the card and a filter.

    A model rather than choices: the owner adds a kind without a migration, and the slug is part
    of the URL.

    :param name: Type name (translated).
    :param slug: Latin slug used in the URL, e.g. "utility-bill".
    :param position: Manual ordering; ties fall back to the name.
    :param seo_text: Text block under the listing (translated).
    """

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, validators=[validate_not_reserved])
    position = models.PositiveSmallIntegerField(default=0)

    seo_text = models.TextField(blank=True, default="")

    objects = DocumentTypeQuerySet.as_manager()

    if TYPE_CHECKING:
        products: "ProductQuerySet"

    class Meta:
        verbose_name = _("Document type")
        verbose_name_plural = _("Document types")
        ordering = ["position", "name"]

    def __str__(self):
        return self.name


def product_file_storage() -> ProductFilesStorage:
    """
    Where a paid file is written: `PRODUCT_FILES_ROOT`, outside MEDIA_ROOT and outside any URL.

    A callable, so the migration records this name rather than a storage with a frozen path baked
    into it.
    """

    return ProductFilesStorage()


class ProductQuerySet(models.QuerySet):
    def active(self) -> "ProductQuerySet":
        return self.filter(is_active=True)

    def for_listing(self) -> "ProductQuerySet":
        """Everything a card needs, without a query per row."""

        return self.select_related("country", "document_type").prefetch_related("images")


class Product(MetaTagsMixin):
    """
    One template on sale: a file plus everything the storefront shows about it.

    Sold any number of times, so it carries no stock (ADR-0001). It cannot be deleted once bought -
    `OrderItem.product` is PROTECT, and taking it off the shelf is `is_active=False`.

    :param name: Product name (translated).
    :param slug: Latin part of the URL; the id in front of it keeps the address unique.
    :param description: Product description (translated).
    :param country: Country of the document.
    :param document_type: Kind of document.
    :param year: Year printed on the document, if any.
    :param price: Price in USD.
    :param file: The file the customer downloads after paying.
    :param is_active: Whether the product is on the storefront.
    """

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255)
    description = models.TextField(blank=True, default="")

    country = models.ForeignKey(Country, related_name="products", on_delete=models.PROTECT)
    document_type = models.ForeignKey(DocumentType, related_name="products", on_delete=models.PROTECT)
    year = models.PositiveSmallIntegerField(null=True, blank=True)

    price = models.DecimalField(max_digits=10, decimal_places=2)
    file = models.FileField(upload_to="", storage=product_file_storage)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ProductQuerySet.as_manager()

    if TYPE_CHECKING:
        images: models.QuerySet["ProductImage"]
        order_items: models.QuerySet["OrderItem"]

    class Meta:
        verbose_name = _("Product")
        verbose_name_plural = _("Products")
        ordering = ["-year", "name"]
        indexes = [
            models.Index(fields=["is_active", "country", "document_type"]),
            models.Index(fields=["year"]),
        ]

    # What the row held when it was read. Empty on a new instance, so a first save never mistakes
    # its own upload for a replacement - the name a colliding upload gets belongs to someone else.
    _stored_file = ""

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        instance._stored_file = instance.file.name
        return instance

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        replaced = self._stored_file and self.file.name != self._stored_file

        super().save(*args, **kwargs)

        # A replaced file is unreachable the moment the row points elsewhere, and it is the one
        # upload here that is measured in megabytes.
        if replaced:
            self.file.storage.delete(self._stored_file)

        self._stored_file = self.file.name if self.file else ""

    @property
    def url_slug(self) -> str:
        """The last URL segment: the id makes it unique, the slug makes it readable."""

        return f"{self.pk}-{self.slug}" if self.slug else str(self.pk)

    @property
    def preview(self) -> "ProductImage | None":
        """First image by position - the one the card shows. Uses the prefetch when there is one."""

        images = self.images.all()
        return images[0] if images else None


# Longest side of each generated variant, in pixels.
IMAGE_VARIANTS = {"card": 500, "page": 1200}
# Both are written for every variant: webp for browsers that take it, jpeg as the fallback.
IMAGE_FIELDS = ("card", "card_webp", "page", "page_webp")


class ProductImage(models.Model):
    """
    One preview image of a product, plus the variants the storefront actually serves.

    The owner uploads a single file of any size; the resized jpeg/webp pairs are generated here,
    so a 5 MB scan never reaches a phone.

    :param product: Product this image belongs to.
    :param image: The uploaded original.
    :param position: Order in the gallery; the first one is the card preview.
    """

    product = models.ForeignKey(Product, related_name="images", on_delete=models.CASCADE)
    image = models.ImageField(upload_to="images/")

    card = models.ImageField(upload_to="images/", editable=False, blank=True)
    card_webp = models.ImageField(upload_to="images/", editable=False, blank=True)
    page = models.ImageField(upload_to="images/", editable=False, blank=True)
    page_webp = models.ImageField(upload_to="images/", editable=False, blank=True)

    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = _("Product image")
        verbose_name_plural = _("Product images")
        ordering = ["position", "pk"]

    # The original this row was read with; see the note on Product._stored_file.
    _source_name = ""

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        instance._source_name = instance.image.name
        return instance

    def __str__(self):
        return f"{self.product_id} - {self.image.name}"

    def save(self, *args, **kwargs):
        replaced = self._source_name and self.image.name != self._source_name

        super().save(*args, **kwargs)

        if self.image and (replaced or not self.card):
            # The previous original is nobody's now - the variants are rebuilt from the new one.
            if replaced:
                self.image.storage.delete(self._source_name)

            self.build_variants()

        self._source_name = self.image.name if self.image else ""

    def build_variants(self):
        """(Re)generate every variant from the original. Old files are dropped first."""

        # Imported here so the module keeps importing on a machine without Pillow's binaries.
        from PIL import Image

        for field in IMAGE_FIELDS:
            stored = getattr(self, field)
            if stored:
                stored.delete(save=False)

        stem = self.image.name.rsplit("/", 1)[-1].rsplit(".", 1)[0]

        with Image.open(self.image) as source:
            source.load()
            # Flattened onto white: the fallback is jpeg, which has no alpha channel to keep.
            if source.mode in ("RGBA", "LA", "P"):
                flat = Image.new("RGB", source.size, (255, 255, 255))
                flat.paste(source.convert("RGBA"), mask=source.convert("RGBA").split()[-1])
                source = flat
            else:
                source = source.convert("RGB")

            for variant, size in IMAGE_VARIANTS.items():
                frame = source.copy()
                frame.thumbnail((size, size * 4))

                for suffix, fmt, options in (("", "JPEG", {"quality": 85}), ("_webp", "WEBP", {"quality": 82})):
                    buffer = BytesIO()
                    frame.save(buffer, format=fmt, **options)
                    extension = "webp" if suffix else "jpg"
                    getattr(self, f"{variant}{suffix}").save(
                        f"{stem}_{variant}.{extension}",
                        ContentFile(buffer.getvalue()),
                        save=False,
                    )

        super().save(update_fields=list(IMAGE_FIELDS))


@receiver(post_delete, sender=Product)
def drop_product_file(sender, instance: Product, **kwargs):
    """A deleted product must not leave its file behind - a product is only ever deleted unsold."""

    if instance.file:
        instance.file.delete(save=False)


@receiver(post_delete, sender=ProductImage)
def drop_image_files(sender, instance: ProductImage, **kwargs):
    """A deleted row must not leave five files behind - including when a queryset deletes it."""

    for field in ("image", *IMAGE_FIELDS):
        stored = getattr(instance, field)
        if stored:
            stored.delete(save=False)
