"""
URL configuration for backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("mailing.urls")),
    path("api/", include("sales.urls")),
]

# Product previews, development only - in production nginx serves them. Deliberately narrowed to
# `images/`: MEDIA_ROOT also holds the paid product files, and those must only ever be reached
# through DownloadFileView, behind a token.
if settings.DEBUG:
    urlpatterns += static(f"{settings.MEDIA_URL}images/", document_root=settings.MEDIA_ROOT / "images")
