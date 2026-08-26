"""Server-rendered catalog: the home page and the country/type/year listing.

The URL carries the filter (`/<lang>/<country>/<type>/`, `all` meaning "any"), the query string
carries the year and the page. Everything a card shows comes off the models directly - there is no
JSON API for the listing (ADR-0009).
"""

from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from catalog.models import Country, DocumentType, Product

# Cards per page. The infinite scroll (M2b) requests the same `?page=N` behind the scenes.
PAGE_SIZE = 24


def catalog(request, country=None, doctype=None):
    """The home page (no segments) and every filtered listing share this view."""

    # `all/all/` is the same set as the bare language root - keep one canonical address for it.
    if country == "all" and doctype == "all":
        return redirect("storefront:home", permanent=True)

    selected_country = get_object_or_404(Country, slug=country) if country and country != "all" else None
    selected_type = get_object_or_404(DocumentType, slug=doctype) if doctype and doctype != "all" else None

    products = Product.objects.active().for_listing()
    if selected_country:
        products = products.filter(country=selected_country)
    if selected_type:
        products = products.filter(document_type=selected_type)

    # Years offered in the current country/type selection, before the year filter narrows it -
    # so picking a year never empties the year dropdown.
    years = list(products.exclude(year__isnull=True).values_list("year", flat=True).distinct().order_by("-year"))

    selected_year = request.GET.get("year") or ""
    if selected_year:
        if selected_year.isdigit():
            products = products.filter(year=int(selected_year))
        else:
            selected_year = ""

    page = Paginator(products, PAGE_SIZE).get_page(request.GET.get("page"))

    context = {
        "products": page,
        "page_obj": page,
        "countries": Country.objects.non_empty(),
        "popular_countries": Country.objects.non_empty().filter(is_popular=True),
        "document_types": DocumentType.objects.with_product_counts().filter(products_count__gt=0),
        "years": years,
        "selected_country": selected_country,
        "selected_type": selected_type,
        "selected_year": selected_year,
    }
    return render(request, "storefront/catalog.html", context)
