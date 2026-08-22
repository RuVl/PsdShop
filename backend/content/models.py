"""Everything on the storefront the owner writes: pages, the welcome slider and site-wide texts."""

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from backend.seo import MetaTagsMixin


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

    slug = models.SlugField(max_length=255, unique=True)
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True, default="")

    is_published = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Page")
        verbose_name_plural = _("Pages")
        ordering = ["slug"]

    def __str__(self):
        return self.title or self.slug


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
    second row cannot appear and quietly win.

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

    def delete(self, *args, **kwargs):
        raise ValidationError(_("The site settings row cannot be deleted."))

    @classmethod
    def load(cls) -> "SiteSettings":
        """The settings row, created empty on first use so a fresh install has something to read."""

        instance, _created = cls.objects.get_or_create(pk=1)
        return instance
