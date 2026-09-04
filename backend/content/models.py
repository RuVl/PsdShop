"""Everything on the storefront the owner writes: pages, the welcome slider and site-wide texts."""

from django.db import models
from django.utils.translation import gettext_lazy as _

from backend.seo import MetaTagsMixin
from backend.urlspace import validate_not_reserved, validate_slug_is_free


class PageQuerySet(models.QuerySet):
    def published(self) -> "PageQuerySet":
        return self.filter(is_published=True)

    def menu(self) -> "PageQuerySet":
        """
        The pages that have an address of their own: everything published bar the home block.

        One definition, because four places need the same answer - the API, the bot pages' nav,
        the sitemap and the page view itself - and a menu that lists a page the view 404s on, or a
        sitemap that advertises one, is the kind of drift nothing fails loudly about.
        """

        return self.published().exclude(slug=Page.HOME)


class Page(MetaTagsMixin):
    """
    A text page written in the admin: the rules, the contacts, the SEO block of the home page.

    The home page block is the row with slug `home` - it has no URL of its own and is rendered
    into the storefront's front page.

    :param slug: Last URL segment, e.g. "info"; `home` is the front-page block.
    :param title: Page heading (translated).
    :param body: Page text, HTML from the editor (translated).
    :param is_published: Hidden pages answer 404.
    """

    HOME = "home"

    slug = models.SlugField(max_length=255, unique=True, validators=[validate_not_reserved])
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True, default="")

    is_published = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = PageQuerySet.as_manager()

    class Meta:
        verbose_name = _("Page")
        verbose_name_plural = _("Pages")
        ordering = ["slug"]

    def __str__(self):
        return self.title or self.slug

    def clean(self):
        super().clean()
        # A page and a country answer on the same URL segment - see backend/urlspace.py.
        validate_slug_is_free(self)


class SlideQuerySet(models.QuerySet):
    def visible(self) -> "SlideQuerySet":
        return self.filter(is_active=True)


class Slide(models.Model):
    """
    One slide of the welcome slider on the front page.

    :param image: Illustration shown next to the text.
    :param title: Slide heading (translated).
    :param text: Slide body (translated).
    :param button_label: Text of the button; empty hides the button (translated).
    :param button_url: Where the button leads.
    :param position: Order in the slider.
    :param is_active: Whether the slide is shown.
    """

    image = models.ImageField(upload_to="slides/", blank=True)
    title = models.CharField(max_length=255)
    text = models.TextField(blank=True, default="")

    button_label = models.CharField(max_length=255, blank=True, default="")
    button_url = models.CharField(max_length=500, blank=True, default="")

    position = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    objects = SlideQuerySet.as_manager()

    class Meta:
        verbose_name = _("Slide")
        verbose_name_plural = _("Slides")
        ordering = ["position", "pk"]

    def __str__(self):
        return self.title


class SiteSettings(models.Model):
    """
    The one row of site-wide settings, edited in the admin.

    A singleton: `load()` is the only way anything reads it, and saving always writes row 1, so a
    second row cannot appear and quietly win. Deletion is closed off in the admin
    (`has_delete_permission`) rather than on the model - a `delete()` override reads as a promise
    it cannot keep, because a queryset delete never calls it. Losing the row costs nothing anyway:
    `load()` writes an empty one back.

    :param support_url: Where "write to support" goes (a Telegram link, usually).
    :param contact_email: Address shown on the contacts page.
    :param footer_note: Small print under the logo in the footer (translated).
    """

    support_url = models.CharField(max_length=500, blank=True, default="")
    contact_email = models.EmailField(blank=True, default="")
    footer_note = models.TextField(blank=True, default="")

    class Meta:
        verbose_name = _("Site settings")
        verbose_name_plural = _("Site settings")

    def __str__(self):
        return str(_("Site settings"))

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "SiteSettings":
        """The settings row, created empty on first use so a fresh install has something to read."""

        instance, _created = cls.objects.get_or_create(pk=1)
        return instance
