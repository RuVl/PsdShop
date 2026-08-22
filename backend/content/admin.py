from django import forms
from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import reverse
from modeltranslation.admin import TranslationAdmin
from tinymce.widgets import TinyMCE

from backend.seo import SeoFieldsetMixin
from content.models import Page, SiteSettings, Slide


class PageAdminForm(forms.ModelForm):
    class Meta:
        model = Page
        fields = "__all__"
        # Keyed by the untranslated name: TranslationAdmin copies the widget onto body_en / body_ru,
        # which is the only reason both languages get an editor.
        widgets = {"body": TinyMCE(attrs={"cols": 80, "rows": 20})}


@admin.register(Page)
class PageAdmin(SeoFieldsetMixin, TranslationAdmin):
    form = PageAdminForm
    list_display = ["slug", "title", "is_published", "updated_at"]
    list_filter = ["is_published"]
    search_fields = ["slug", "title_en", "title_ru"]
    prepopulated_fields = {"slug": ("title_en",)}


@admin.register(Slide)
class SlideAdmin(TranslationAdmin):
    list_display = ["title", "position", "is_active"]
    list_editable = ["position", "is_active"]
    list_filter = ["is_active"]


@admin.register(SiteSettings)
class SiteSettingsAdmin(TranslationAdmin):
    """One row, so the changelist is pointless: the sidebar link lands straight on the edit form."""

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        row = SiteSettings.load()
        return HttpResponseRedirect(reverse("admin:content_sitesettings_change", args=[row.pk]))
