"""Template helpers for the server-rendered storefront."""

from django import template
from django.urls import translate_url

register = template.Library()


@register.simple_tag(takes_context=True)
def switch_language_url(context, lang_code):
    """The current page's URL under another language prefix - powers the language switcher."""

    return translate_url(context["request"].get_full_path(), lang_code)
