from modeltranslation.translator import TranslationOptions, register

from catalog.models import Country, DocumentType, Product


@register(Country)
class CountryTranslationOptions(TranslationOptions):
    fields = ("name", "seo_text", "meta_title", "meta_description")


@register(DocumentType)
class DocumentTypeTranslationOptions(TranslationOptions):
    fields = ("name", "seo_text", "meta_title", "meta_description")


@register(Product)
class ProductTranslationOptions(TranslationOptions):
    fields = ("name", "description", "meta_title", "meta_description")
