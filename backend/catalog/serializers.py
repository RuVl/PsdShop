"""What the SPA reads: the same querysets the bot pages render, shaped as JSON.

Both languages ride along (`name_en` / `name_ru`): the SPA keeps the language in its route and
switches without a refetch, and the payload stays identical for every visitor - the same data the
server renders for a bot on the same URL.
"""

from rest_framework import serializers

from catalog.models import Country, DocumentType, Product, ProductImage


class CountrySerializer(serializers.ModelSerializer):
    products_count = serializers.IntegerField(read_only=True)
    flag = serializers.CharField(read_only=True)

    class Meta:
        model = Country
        fields = ["slug", "flag", "name_en", "name_ru", "is_popular", "products_count", "seo_text_en", "seo_text_ru"]


class DocumentTypeSerializer(serializers.ModelSerializer):
    products_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = DocumentType
        fields = ["slug", "name_en", "name_ru", "products_count", "seo_text_en", "seo_text_ru"]


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ["card", "card_webp", "page", "page_webp"]

    def to_representation(self, instance):
        # An empty ImageField serializes as null, not as a broken url.
        return {name: getattr(instance, name).url if getattr(instance, name) else None for name in self.Meta.fields}


class ProductListSerializer(serializers.ModelSerializer):
    """A grid card: what `storefront/_product_card.html` shows, by id."""

    url_slug = serializers.CharField(read_only=True)
    country = serializers.SlugRelatedField(slug_field="slug", read_only=True)
    document_type = serializers.SlugRelatedField(slug_field="slug", read_only=True)
    preview = ProductImageSerializer(read_only=True)

    class Meta:
        model = Product
        fields = ["id", "url_slug", "name_en", "name_ru", "price", "year", "country", "document_type", "preview"]


class ProductDetailSerializer(ProductListSerializer):
    """The product page: the card fields plus the description and the whole gallery."""

    images = ProductImageSerializer(many=True, read_only=True)

    class Meta(ProductListSerializer.Meta):
        fields = ProductListSerializer.Meta.fields + ["description_en", "description_ru", "images"]
