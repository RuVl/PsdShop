"""The storefront's HTML, served two ways off the same URLs (dynamic rendering).

A search bot gets the full server-rendered page; a person gets the SPA shell - the vite-built
index.html with this page's meta rendered into <head> (`make spa` produces it). Both branches of
a view share one queryset and one meta dict, which is what keeps them equivalent.
"""

import logging

from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.template import TemplateDoesNotExist
from django.template.loader import get_template
from django.urls import reverse

from backend.sites import absolute_url
from catalog.models import Country, DocumentType, Product
from catalog.views import PAGE_SIZE
from content.models import Page, Slide
from storefront import seo
from storefront.bots import is_bot

logger = logging.getLogger(__name__)

SHELL_TEMPLATE = "storefront/shell.html"


def _shell_available() -> bool:
    try:
        get_template(SHELL_TEMPLATE)
    except TemplateDoesNotExist:
        return False
    return True


def render_shell(request, meta):
    return render(request, SHELL_TEMPLATE, {"storefront_meta": seo.render_meta(meta)})


def catalog(request, country=None, doctype=None):
    """The home page (no segments) and every filtered listing share this view."""

    # `all/all/` is the same set as the bare language root - keep one canonical address for it.
    if country == "all" and doctype == "all":
        return redirect("storefront:home", permanent=True)

    selected_country = get_object_or_404(Country, slug=country) if country and country != "all" else None
    selected_type = get_object_or_404(DocumentType, slug=doctype) if doctype and doctype != "all" else None

    # The front page alone carries the welcome slider and the owner-written SEO block.
    home_page = None
    if not selected_country and not selected_type:
        home_page = Page.objects.filter(is_published=True, slug=Page.HOME).first()

    meta = seo.catalog_meta(request, selected_country, selected_type, home_page)

    if not is_bot(request) and _shell_available():
        return render_shell(request, meta)
    if not is_bot(request):
        # No SPA build on disk: serve the bot page rather than a 500, but say so - in production
        # this means the deploy skipped `make spa`.
        logger.warning("SPA shell template missing; serving the server-rendered page to a person")

    products = Product.objects.active().for_listing()
    if selected_country:
        products = products.filter(country=selected_country)
    if selected_type:
        products = products.filter(document_type=selected_type)

    page = Paginator(products, PAGE_SIZE).get_page(request.GET.get("page"))

    context = {
        "storefront_meta": seo.render_meta(meta),
        "products": page,
        "page_obj": page,
        # The window the template draws: first, last and the neighbours of the current page, with
        # `Paginator.ELLIPSIS` standing in for the gaps - the same shape Pagination.vue builds.
        # A list, not the generator the paginator hands back: a template that walks it twice would
        # find it empty the second time.
        "page_range": list(page.paginator.get_elided_page_range(page.number, on_each_side=1, on_ends=1)),
        "countries": Country.objects.non_empty(),
        "popular_countries": Country.objects.non_empty().filter(is_popular=True),
        "document_types": DocumentType.objects.with_product_counts().filter(products_count__gt=0),
        "selected_country": selected_country,
        "selected_type": selected_type,
        "home_page": home_page,
        "slides": Slide.objects.visible() if home_page or (not selected_country and not selected_type) else None,
    }
    return render(request, "storefront/catalog.html", context)


def page(request, page_slug=""):
    """An owner-written text page (content.Page): /en/<slug>/."""

    item = get_object_or_404(Page.objects.filter(is_published=True).exclude(slug=Page.HOME), slug=page_slug)

    meta = seo.page_meta(request, item)
    if not is_bot(request) and _shell_available():
        return render_shell(request, meta)

    return render(request, "storefront/page.html", {"storefront_meta": seo.render_meta(meta), "page": item})


def product(request, country=None, doctype=None, product_slug=""):
    """One product. The id in `<id>-<slug>` resolves it; every other segment is decoration."""

    pk = int(product_slug.split("-", 1)[0])
    item = get_object_or_404(Product.objects.active().for_listing(), pk=pk)

    # One canonical address per product: a stale slug or a wrong facet 301s to the current one.
    expected = reverse(
        "storefront:product",
        kwargs={"country": item.country.slug, "doctype": item.document_type.slug, "product_slug": item.url_slug},
    )
    if request.path != expected:
        return redirect(expected, permanent=True)

    meta = seo.product_meta(request, item)

    if not is_bot(request) and _shell_available():
        return render_shell(request, meta)

    context = {
        "storefront_meta": seo.render_meta(meta),
        "product": item,
        "countries": Country.objects.non_empty(),
        "popular_countries": Country.objects.non_empty().filter(is_popular=True),
        "selected_country": item.country,
        "selected_type": item.document_type,
    }
    return render(request, "storefront/product.html", context)


def robots(request):
    """robots.txt: the paths a crawler has no business in, and where the map is.

    Rendered by Django rather than served as a file so the Sitemap line carries the real host -
    the `django_site` row and SITE_SCHEME, the same pair every other absolute link is built from.
    Filters and pagination stay crawlable on purpose: `canonical` already collapses them, and
    blocking the crawl would only hide the products behind them.
    """

    return render(
        request,
        "storefront/robots.txt",
        {"sitemap_url": absolute_url(reverse("sitemap"), request)},
        content_type="text/plain",
    )


def spa(request, **kwargs):
    """Cart, purchases, unsubscribe - pages that exist only in the SPA.

    Bots get the same shell: these are service pages, marked noindex, with nothing to rank.
    The URL parameters belong to the SPA router; the view ignores them.
    """

    return render_shell(request, seo.service_meta(request))
