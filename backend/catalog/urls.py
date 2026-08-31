from django.urls import path

from catalog.views import CountryListView, DocumentTypeListView, ProductDetailView, ProductListView

urlpatterns = [
    path("catalog/countries/", CountryListView.as_view(), name="catalog-countries"),
    path("catalog/document-types/", DocumentTypeListView.as_view(), name="catalog-document-types"),
    path("catalog/products/", ProductListView.as_view(), name="catalog-products"),
    path("catalog/products/<int:pk>/", ProductDetailView.as_view(), name="catalog-product"),
]
