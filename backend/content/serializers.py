"""Owner-written content as the SPA reads it. Both languages ride along, like the catalog API."""

from rest_framework import serializers

from content.models import Page, SiteSettings, Slide


class PageListSerializer(serializers.ModelSerializer):
    """Enough to draw a menu link."""

    class Meta:
        model = Page
        fields = ["slug", "title_en", "title_ru"]


class PageDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Page
        fields = ["slug", "title_en", "title_ru", "body_en", "body_ru"]


class SlideSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model = Slide
        fields = [
            "image", "title_en", "title_ru", "text_en", "text_ru",
            "button_label_en", "button_label_ru", "button_url",
        ]  # fmt: skip

    def get_image(self, obj: Slide) -> str | None:
        return obj.image.url if obj.image else None


class SiteSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = SiteSettings
        fields = ["support_url", "contact_email", "footer_note_en", "footer_note_ru"]
