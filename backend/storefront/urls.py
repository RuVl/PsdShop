"""Storefront routes. Mounted under `i18n_patterns`, so every path here gains a `/<lang>/` prefix."""

import re

from django.urls import path, register_converter
from django.urls.converters import SlugConverter

from backend.urlspace import reserved_slugs
from storefront import views


class CountrySegmentConverter(SlugConverter):
    """
    A country slug that never captures one of the site's own reserved roots.

    The `/<country>/<type>/` pattern is a greedy two-segment catch-all: without this it also
    matches `api/send-links`, so `LocaleMiddleware` sees `/en/api/...` as a valid path and turns a
    real `/api/` 404 into a 302 into the storefront. Blocking the reserved roots (from
    `backend/urlspace.py`) keeps those 404s intact. `all` - the "any country" wildcard - stays
    allowed.
    """

    _blocked = "|".join(re.escape(slug) for slug in sorted(reserved_slugs() - {"all"}))
    regex = rf"(?!(?:{_blocked})/)[-a-zA-Z0-9_]+"


register_converter(CountrySegmentConverter, "country")

app_name = "storefront"

urlpatterns = [
    path("", views.catalog, name="home"),
    # SPA-only pages: Django serves the shell on them so the URLs answer 200 for everyone;
    # the parameters are consumed by the SPA router. Slugs are reserved in backend/urlspace.py.
    path("cart/", views.spa, name="cart"),
    path("purchases/", views.spa, name="purchases"),
    path("purchases/<uuid:token>/", views.spa, name="purchases-token"),
    path("unsubscribe/<str:token>/", views.spa, name="unsubscribe"),
    path("<country:country>/<slug:doctype>/", views.catalog, name="catalog"),
]
