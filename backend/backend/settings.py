from datetime import timedelta
from pathlib import Path

import environ

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(DEBUG=(bool, False))

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS")
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS")

# Development settings
if DEBUG:
    SITE_ID = 1

# Production settings
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

    SECURE_SSL_REDIRECT = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")  # from reverse proxy

    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True  # Remember to add site to https://hstspreload.org/

# Application definition
INSTALLED_APPS = [
    "modeltranslation",
    # Stands in for "django.contrib.admin": same app, our AdminSite (see backend/admin.py).
    "backend.apps.ShopAdminConfig",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    # Ships the sitemap.xml template the storefront map is rendered with.
    "django.contrib.sitemaps",
    "rest_framework",
    "corsheaders",
    "tinymce",
    "storefront",
    "catalog",
    "content",
    "customer",
    "mailing",
    "sales",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # Picks the language off the URL prefix (/en/, /ru/) and falls back to Accept-Language. The
    # storefront is server-rendered, so the page language has to be active during the response.
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "backend.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.template.context_processors.i18n",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "storefront.context_processors.site_settings",
            ],
        },
    },
]

WSGI_APPLICATION = "backend.wsgi.application"

# Site settings
# Used to build absolute URLs (download links, the purchases page link in e-mails).
# Overridable so a local run can hand out http:// links that actually open.
SITE_SCHEME = env("SITE_SCHEME", default="https")

# Customer access lifetimes
PURCHASES_PAGE_TTL = timedelta(hours=24)  # Customer.access_token
DOWNLOAD_TTL = timedelta(hours=24)  # OrderItem.token

# Checkout limit. Nothing is reserved (ADR-0001), but every checkout costs a Plisio invoice, so a
# single request must not be able to ask for the whole catalogue.
MAX_ORDER_ITEMS = 25

# Look up the MX record of the e-mail domain at checkout. Fails open on any DNS trouble, see
# customer/validators.py - turn it off only if outbound DNS is blocked.
VALIDATE_EMAIL_MX = env.bool("VALIDATE_EMAIL_MX", default=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
        },
        "file": {
            "level": "DEBUG",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": BASE_DIR / "logs" / "django.log",
            "maxBytes": 1024 * 1024 * 10,  # 10 MB
            "backupCount": 5,
            "formatter": "standard",
        },
        "null": {
            "class": "logging.NullHandler",
        },
    },
    "root": {
        "handlers": ["console", "file"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
        "django.security.DisallowedHost": {
            "handlers": ["null"],
            "level": "ERROR",
            "propagate": False,
        },
    },
}

DATABASES = {
    "default": env.db(),
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Internationalization
USE_I18N = True
LANGUAGE_CODE = "en"
LANGUAGES = (
    ("en", "English"),
    ("ru", "Russian"),
)
MODELTRANSLATION_DEFAULT_LANGUAGE = "en"

# gettext catalogues for the e-mail copy. msgids are the English text, so only `ru` has a
# catalogue here. `.mo` files are compiled by startup.sh and are not tracked.
LOCALE_PATHS = [BASE_DIR / "locale"]

# Timezone
USE_TZ = True
TIME_ZONE = "UTC"

# Static files (CSS, JavaScript, Images)
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "static"

# Plain static storage: the SPA assets are hashed by vite itself, and the remaining Django-served
# static (bot-page CSS, admin) needs no cache-busting manifest.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# Uploads live on the `products` volume, split by who is allowed to read them.
#
# `media/` is public: product previews and slide images, served by nginx straight off the volume
# (`location /media/` in frontend/nginx/site-body.conf) and by Django itself under DEBUG.
#
# `private/` holds the paid files and is deliberately outside MEDIA_ROOT, so no URL maps onto it -
# a product file is only ever reached through DownloadFileView, behind a token. The storage below
# has no `base_url` either, so `product.file.url` raises instead of quietly handing out a path
# (see catalog/storages.py).
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "products" / "media"
PRODUCT_FILES_ROOT = BASE_DIR / "products" / "private"

# Plisio token
PLISIO_SECRET_KEY = env("PLISIO_SECRET_KEY")

# Email config
# The backend follows the scheme of EMAIL_URL (smtp:// in production, consolemail:// in dev).
# Passing `backend=` here would pin it to SMTP and silently ignore the scheme.
EMAIL_CONFIG = env.email("EMAIL_URL")

EMAIL_HOST_USER = EMAIL_CONFIG.get("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = EMAIL_CONFIG.get("EMAIL_HOST_PASSWORD")

EMAIL_HOST = EMAIL_CONFIG.get("EMAIL_HOST")
EMAIL_PORT = EMAIL_CONFIG.get("EMAIL_PORT")

DEFAULT_FROM_EMAIL = env.get_value("DEFAULT_FROM_EMAIL", default=EMAIL_HOST_USER)

EMAIL_BACKEND = EMAIL_CONFIG.get("EMAIL_BACKEND")
EMAIL_USE_TLS = EMAIL_CONFIG.get("EMAIL_USE_TLS", False)
EMAIL_USE_SSL = EMAIL_CONFIG.get("EMAIL_USE_SSL", False)

# TinyMCE (self-hosted GPL build, no API key) - WYSIWYG editor for Broadcast.body in admin.
# promotion/branding False strip the "Upgrade" button and "Powered by Tiny" ads.
# skin/content_css default to light; a capture-phase script in the broadcast change_form
# swaps them to the dark variants when the admin theme is dark (see change_form.html).
TINYMCE_DEFAULT_CONFIG = {
    "height": 500,
    "menubar": "edit insert format table",
    "promotion": False,
    "branding": False,
    "skin": "oxide",
    "content_css": "default",
    "plugins": "advlist autolink lists link image charmap preview anchor "
    "searchreplace visualblocks code fullscreen insertdatetime table help wordcount",
    "toolbar": "undo redo | blocks | bold italic forecolor | "
    "alignleft aligncenter alignright | bullist numlist | "
    "link image table | removeformat | preview code fullscreen | help",
}
