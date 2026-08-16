from modeltranslation.translator import TranslationOptions, register

from content.models import Page, SiteSettings, Slide


@register(Page)
class PageTranslationOptions(TranslationOptions):
    fields = ("title", "body", "meta_title", "meta_description")


@register(Slide)
class SlideTranslationOptions(TranslationOptions):
    fields = ("title", "text", "button_label")


@register(SiteSettings)
class SiteSettingsTranslationOptions(TranslationOptions):
    fields = ("footer_note",)
