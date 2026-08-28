"""Per-page meta, built once and rendered into both presentations of a page.

A storefront view builds one meta dict and hands it to whichever branch answers - the bot
template and the SPA shell render the same tags from it. That single source is what keeps the
two presentations equivalent, which dynamic rendering depends on: saying different things to
bots and people is cloaking.
"""

import json

from django.conf import settings
from django.http import HttpRequest
from django.template.loader import render_to_string
from django.urls import reverse, translate_url
from django.utils.safestring import mark_safe
from django.utils.text import Truncator
from django.utils.translation import gettext as _

from backend.sites import absolute_url


def site_name() -> str:
    return _("PDF document store")


def default_description() -> str:
    # The hero copy doubles as the fallback description, so the snippet matches the page.
    return _(
        "Editable proof-of-address documents, utility bills and bank statements in PDF. "
        "Delivered by a download link right after payment."
    )


def build_meta(
    request: HttpRequest,
    *,
    title: str,
    description: str = "",
    og_type: str = "website",
    og_image: str | None = None,
    ld: dict | None = None,
    noindex: bool = False,
) -> dict:
    path = request.path
    canonical = absolute_url(path, request)
    # Pagination canonicalizes to itself; every other query parameter (filters) drops off.
    page = request.GET.get("page")
    if page and page.isdigit() and int(page) > 1:
        canonical += f"?page={int(page)}"

    return {
        "title": title,
        "description": description or default_description(),
        "canonical": canonical,
        "alternates": [(code, absolute_url(translate_url(path, code), request)) for code, _name in settings.LANGUAGES],
        "og_type": og_type,
        "og_image": og_image,
        # Serialized here, with `<` escaped so a value can never close the <script> tag; the
        # template drops it in as-is (mark_safe would be defeated by a dict).
        "ld_json": mark_safe(json.dumps(ld, ensure_ascii=False).replace("<", "\\u003c")) if ld else None,  # noqa: S308
        "noindex": noindex,
    }


def catalog_meta(request: HttpRequest, country=None, doctype=None) -> dict:
    """Meta for the home page and the country/type listings."""

    selected = [obj for obj in (country, doctype) if obj is not None]
    if not selected:
        return build_meta(request, title=site_name())

    # A single-facet page may carry its own meta from the admin; combined pages are generated.
    title = selected[0].meta_title if len(selected) == 1 and selected[0].meta_title else ""
    title = title or f"{' — '.join(obj.name for obj in selected)} | {site_name()}"
    description = next((obj.meta_description for obj in selected if obj.meta_description), "")
    return build_meta(request, title=title, description=description)


def product_meta(request: HttpRequest, product) -> dict:
    """Meta for a product page, ld+json Product/Offer and BreadcrumbList included."""

    title = product.meta_title or f"{product.name} | {site_name()}"
    description = product.meta_description or Truncator(product.description).words(30) or ""

    images = [absolute_url(image.page.url, request) for image in product.images.all() if image.page]
    canonical_path = request.path
    ld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Product",
                "name": product.name,
                "description": description,
                "image": images,
                "offers": {
                    "@type": "Offer",
                    "price": str(product.price),
                    "priceCurrency": "USD",
                    "availability": "https://schema.org/InStock",
                    "url": absolute_url(canonical_path, request),
                },
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": 1,
                        "name": site_name(),
                        "item": absolute_url(reverse("storefront:home"), request),
                    },
                    {
                        "@type": "ListItem",
                        "position": 2,
                        "name": f"{product.country.name} — {product.document_type.name}",
                        "item": absolute_url(
                            reverse(
                                "storefront:catalog",
                                kwargs={"country": product.country.slug, "doctype": product.document_type.slug},
                            ),
                            request,
                        ),
                    },
                    {"@type": "ListItem", "position": 3, "name": product.name},
                ],
            },
        ],
    }

    return build_meta(
        request,
        title=title,
        description=description,
        og_type="product",
        og_image=images[0] if images else None,
        ld=ld,
    )


def service_meta(request: HttpRequest) -> dict:
    """Cart, purchases, unsubscribe - SPA-only pages that must stay out of the index."""

    return build_meta(request, title=site_name(), noindex=True)


def render_meta(meta: dict) -> str:
    return mark_safe(render_to_string("storefront/_meta.html", {"meta": meta}))  # noqa: S308
