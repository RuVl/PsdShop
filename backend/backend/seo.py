"""Meta tags, handled the same way everywhere."""

from django.db import models


class MetaTagsMixin(models.Model):
    """
    Meta tags a page can override.

    Every page the storefront serves carries them - a product, a country, a document type, a text
    page - so they live here rather than in one app's models. Left empty they are built from the
    name, so the owner only fills them in where the generated text is not good enough.

    The listing pages also carry a `seo_text` block under the grid; that one is theirs alone and is
    declared on the models that have it.
    """

    meta_title = models.CharField(max_length=255, blank=True, default="")
    meta_description = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        abstract = True


class SeoFieldsetMixin:
    """
    Moves the meta tags into a collapsed block at the bottom of the change form.

    Every one of them is optional, so they must not sit among the fields that are not - an owner
    filling in a product should reach the end of the form without meeting them. Mix it in before
    the admin class it applies to.

    Field names are matched by prefix: by the time this runs modeltranslation has expanded
    `meta_title` into `meta_title_en` / `meta_title_ru`.
    """

    SEO_FIELD_PREFIXES = ("meta_title", "meta_description", "seo_text")
    SEO_FIELDSET_NAME = "SEO - optional"
    SEO_FIELDSET_DESCRIPTION = "Optional. Leave empty unless this page needs meta tags of its own."

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)

        # A named fieldset means the admin class laid the form out by hand - leave it alone.
        if any(name for name, _options in fieldsets):
            return fieldsets

        fields = [field for _name, options in fieldsets for field in options["fields"]]
        seo = [field for field in fields if self._is_seo_field(field)]
        if not seo:
            return fieldsets

        return [
            (None, {"fields": [field for field in fields if not self._is_seo_field(field)]}),
            (
                self.SEO_FIELDSET_NAME,
                {
                    "fields": seo,
                    "classes": ["collapse"],
                    "description": self.SEO_FIELDSET_DESCRIPTION,
                },
            ),
        ]

    def _is_seo_field(self, field) -> bool:
        # A non-string is a row of fields grouped by hand; those are never ours.
        if not isinstance(field, str):
            return False

        return any(field == prefix or field.startswith(f"{prefix}_") for prefix in self.SEO_FIELD_PREFIXES)
