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
from django.conf.urls.i18n import i18n_patterns
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

# No language prefix: the admin, the API and the Plisio callback are not part of the storefront.
urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("catalog.urls")),
    path("api/", include("content.urls")),
    path("api/", include("mailing.urls")),
    path("api/", include("sales.urls")),
]

# The storefront is server-rendered and bilingual: the language lives in the path (/en/, /ru/), and
# the bare root 302-redirects to the visitor's language (LocaleMiddleware + prefix_default_language).
urlpatterns += i18n_patterns(
    path("", include("storefront.urls")),
    prefix_default_language=True,
)

# Product previews and slide images, development only - in production nginx serves them off the
# volume. MEDIA_ROOT holds nothing else: the paid files sit in PRODUCT_FILES_ROOT, outside it, and
# are only ever reached through DownloadFileView, behind a token.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
