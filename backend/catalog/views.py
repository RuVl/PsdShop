"""The catalog API behind the SPA.

Filtering mirrors the bot pages: the same querysets, the same "unknown slug is a 404, `all` and
absence mean any" rule, the same page size - so a person and a bot walking the same URL see the
same set.
"""

from django.shortcuts import get_object_or_404
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.pagination import PageNumberPagination

from catalog.models import Country, DocumentType, Product
from catalog.serializers import (
    CountrySerializer,
    DocumentTypeSerializer,
    ProductDetailSerializer,
    ProductListSerializer,
)

# Cards per page, shared with the server-rendered listing (storefront.views).
PAGE_SIZE = 24


class CatalogPagination(PageNumberPagination):
    page_size = PAGE_SIZE


class CountryListView(ListAPIView):
    """Sidebar data: countries that have products, with counts. `is_popular` marks the top block."""

    serializer_class = CountrySerializer

    def get_queryset(self):
        return Country.objects.non_empty()


class DocumentTypeListView(ListAPIView):
    """Filter chips: document types that have products, with counts."""

    serializer_class = DocumentTypeSerializer

    def get_queryset(self):
        return DocumentType.objects.with_product_counts().filter(products_count__gt=0)


class ProductListView(ListAPIView):
    """The grid. `?country=` and `?type=` take slugs; `all` or absence means any; `?page=` pages."""

    serializer_class = ProductListSerializer
    pagination_class = CatalogPagination

    def get_queryset(self):
        products = Product.objects.active().for_listing()

        country = self.request.query_params.get("country")
        if country and country != "all":
            products = products.filter(country=get_object_or_404(Country, slug=country))

        doctype = self.request.query_params.get("type")
        if doctype and doctype != "all":
            products = products.filter(document_type=get_object_or_404(DocumentType, slug=doctype))

        return products


class ProductDetailView(RetrieveAPIView):
    """One product by id - the SPA takes the id off the `<id>-<slug>` URL segment."""

    serializer_class = ProductDetailSerializer

    def get_queryset(self):
        return Product.objects.active().for_listing()
