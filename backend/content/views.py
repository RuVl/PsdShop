"""The content API behind the SPA: pages, the welcome slider and the site-wide settings.

Mirrors what the bot pages render - same rows, same "unpublished is a 404" rule.
"""

from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from content.models import Page, SiteSettings, Slide
from content.serializers import PageDetailSerializer, PageListSerializer, SiteSettingsSerializer, SlideSerializer


class PageListView(ListAPIView):
    """Menu links: published pages, without the `home` block (it has no URL of its own)."""

    serializer_class = PageListSerializer

    def get_queryset(self):
        return Page.objects.menu()


class PageDetailView(RetrieveAPIView):
    """One page by slug. `home` is reachable here - the front page reads its SEO block this way."""

    serializer_class = PageDetailSerializer
    lookup_field = "slug"

    def get_queryset(self):
        return Page.objects.published()


class SlideListView(ListAPIView):
    serializer_class = SlideSerializer

    def get_queryset(self):
        return Slide.objects.visible()


class SiteSettingsView(APIView):
    def get(self, request):
        return Response(SiteSettingsSerializer(SiteSettings.load()).data)
