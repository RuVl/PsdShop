from django.contrib import admin, messages
from django.db.models import ProtectedError
from django.utils.html import format_html
from modeltranslation.admin import TranslationAdmin

from backend.seo import SeoFieldsetMixin
from catalog.models import Country, DocumentType, Product, ProductImage


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    fields = ["image", "thumbnail", "position"]
    readonly_fields = ["thumbnail"]
    extra = 1

    @admin.display(description="Preview")
    def thumbnail(self, obj: ProductImage):
        # The generated card variant, not the original: the original can be a 4000px scan.
        if not obj.pk or not obj.card:
            return "-"

        return format_html('<img src="{}" style="max-height: 90px">', obj.card.url)


@admin.register(Country)
class CountryAdmin(SeoFieldsetMixin, TranslationAdmin):
    list_display = ["flag", "name", "slug", "code", "products_count", "is_popular", "position"]
    list_editable = ["is_popular", "position"]
    list_filter = ["is_popular"]
    search_fields = ["name_en", "name_ru", "slug", "code"]
    prepopulated_fields = {"slug": ("name_en",)}

    def get_queryset(self, request):
        return super().get_queryset(request).with_product_counts()

    @admin.display(description="Products", ordering="products_count")
    def products_count(self, obj: Country):
        return obj.products_count


@admin.register(DocumentType)
class DocumentTypeAdmin(SeoFieldsetMixin, TranslationAdmin):
    list_display = ["name", "slug", "products_count", "position"]
    list_editable = ["position"]
    search_fields = ["name_en", "name_ru", "slug"]
    prepopulated_fields = {"slug": ("name_en",)}

    def get_queryset(self, request):
        return super().get_queryset(request).with_product_counts()

    @admin.display(description="Products", ordering="products_count")
    def products_count(self, obj: DocumentType):
        return obj.products_count


@admin.register(Product)
class ProductAdmin(SeoFieldsetMixin, TranslationAdmin):
    list_display = ["name", "country", "document_type", "year", "price", "images_count", "is_active"]
    list_editable = ["price", "is_active"]
    list_filter = ["is_active", "country", "document_type", "year"]
    search_fields = ["name_en", "name_ru", "slug"]
    list_select_related = ["country", "document_type"]
    autocomplete_fields = ["country", "document_type"]
    prepopulated_fields = {"slug": ("name_en",)}
    inlines = [ProductImageInline]
    readonly_fields = ["created_at", "updated_at"]

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("images")

    @admin.display(description="Images")
    def images_count(self, obj: Product):
        return len(obj.images.all())

    def delete_model(self, request, obj):
        """
        A bought product cannot be deleted - its file is what the customer downloads (ADR-0001).

        Both delete flows already stop before this: the confirmation page collects the related
        rows, finds the PROTECTed `OrderItem`s and refuses to offer the button. This is the net
        under the race where the first order for a product lands between the two requests, and it
        turns the resulting 500 into a message that says what to do instead.

        `delete_queryset` is deliberately not overridden: walking the queryset object by object
        would swallow one error per sold product while `delete_selected` still reported every
        selected row as deleted.
        """

        try:
            super().delete_model(request, obj)
        except ProtectedError:
            self.message_user(request, self.SOLD_PRODUCT_MESSAGE % obj, messages.ERROR)

    SOLD_PRODUCT_MESSAGE = (
        '"%s" has been bought at least once and cannot be deleted - its file has to stay '
        "downloadable. Untick 'is active' to take it off the storefront instead."
    )
