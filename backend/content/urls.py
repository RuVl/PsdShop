from django.urls import path

from content.views import PageDetailView, PageListView, SiteSettingsView, SlideListView

urlpatterns = [
    path("content/pages/", PageListView.as_view(), name="content-pages"),
    path("content/pages/<slug:slug>/", PageDetailView.as_view(), name="content-page"),
    path("content/slides/", SlideListView.as_view(), name="content-slides"),
    path("content/settings/", SiteSettingsView.as_view(), name="content-settings"),
]
