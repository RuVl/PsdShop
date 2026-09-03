"""Seed the catalog with test data for local/manual UI testing.

Builds countries x document types x years, with real (generated) images so the resize pipeline
runs, and a placeholder file per product so a checkout can be walked end to end. Covers the edge
cases the storefront has to survive: a very long name, the cheapest and the most expensive price,
a product with no year, an inactive product and a country with nothing in it.
"""

from decimal import Decimal
from io import BytesIO

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db.models import ProtectedError
from django.db.transaction import atomic

from catalog.models import Country, DocumentType, Product, ProductImage
from content.models import Page, SiteSettings, Slide

# code, slug, (name_en, name_ru), is_popular
COUNTRIES = [
    ("us", "united-states", ("United States", "США"), True),
    ("gb", "united-kingdom", ("United Kingdom", "Великобритания"), True),
    ("de", "germany", ("Germany", "Германия"), True),
    ("fr", "france", ("France", "Франция"), False),
    ("es", "spain", ("Spain", "Испания"), False),
    ("it", "italy", ("Italy", "Италия"), False),
    ("pl", "poland", ("Poland", "Польша"), False),
    # Deliberately left without products: the sidebar must not show an empty country.
    ("pt", "portugal", ("Portugal", "Португалия"), False),
]

# slug, (name_en, name_ru), (issuer_en, issuer_ru) used to build product names
TYPES = [
    ("utility-bill", ("Utility bill", "Счёт за коммунальные услуги"), ("Electricity", "Электричество")),
    ("bank-statement", ("Bank statement", "Банковская выписка"), ("Bank", "Банк")),
    ("tax", ("Tax document", "Налоговый документ"), ("Tax office", "Налоговая")),
]

YEARS = [2026, 2025, 2024, 2023, 2022, 2021]

DESCRIPTION_EN = (
    "Editable {type} template for {country}, {year}. Layered source file, fonts included, "
    "all fields editable. Delivered as a download link right after payment."
)
DESCRIPTION_RU = (
    "Редактируемый шаблон: {type}, {country}, {year} год. Многослойный исходник, шрифты в "
    "комплекте, все поля редактируются. Ссылка на скачивание приходит сразу после оплаты."
)

PLACEHOLDER_FILE = b"PsdShop test file - not a real template.\n"

# Rough flags for the seed previews - enough to tell one card from another at a glance, drawn as
# bands (`h` across, `v` down) plus an optional canton. Not a flag library: a country the seed
# does not list gets its code on plain cloth. "gb" is not here - a striped band can't read as the
# Union Jack, so it gets its own drawing routine (`_draw_union_jack`).
FLAGS = {
    "us": ("h", [(178, 34, 52), (255, 255, 255)] * 3, (60, 59, 110)),
    "de": ("h", [(0, 0, 0), (221, 0, 0), (255, 206, 0)], None),
    "fr": ("v", [(0, 85, 164), (255, 255, 255), (239, 65, 53)], None),
    "es": ("h", [(198, 11, 30), (255, 196, 0), (198, 11, 30)], None),
    "it": ("v", [(0, 140, 69), (255, 255, 255), (205, 33, 42)], None),
    "pl": ("h", [(255, 255, 255), (220, 20, 60)], None),
    "pt": ("v", [(0, 102, 71), (218, 41, 28)], None),
}


class Command(BaseCommand):
    help = "Seed the catalog with countries, document types and products for manual testing."

    def add_arguments(self, parser):
        parser.add_argument("--flush", action="store_true", help="Wipe the catalog first.")
        parser.add_argument(
            "--force",
            action="store_true",
            help="Allow --flush outside DEBUG. `make manage` runs in the production container.",
        )
        parser.add_argument("--images", type=int, default=2, help="Images per product (0 skips them).")

    @atomic
    def handle(self, *args, **options):
        if options["flush"]:
            # --flush drops the countries, document types, pages and slides the owner writes, not
            # just the generated ones. `make manage` reaches the production container, so outside
            # DEBUG it takes a second, explicit word. The test runner forces DEBUG=False, which is
            # why the gate is a flag and not DEBUG alone.
            if not settings.DEBUG and not options["force"]:
                raise CommandError(
                    "--flush deletes every country, document type, page and slide, and DEBUG is "
                    "off - this looks like a production database. Add --force if you mean it."
                )

            try:
                deleted = Product.objects.all().delete()
            except ProtectedError as error:
                # A sold product cannot be deleted - `OrderItem.product` is PROTECT, so the file
                # outlives the sale (docs/architecture.md). Say that instead of dumping the traceback.
                sold = {item.order_id for item in error.protected_objects}
                raise CommandError(
                    f"Some products have been sold and cannot be deleted (orders: {sorted(sold)}). "
                    f"Wipe the whole dev database with `make dev-nuke` if that is what you want."
                ) from error

            Country.objects.all().delete()
            DocumentType.objects.all().delete()
            Page.objects.all().delete()
            Slide.objects.all().delete()
            self.stdout.write(f"Flushed existing catalog: {deleted}")

        countries = {
            slug: Country.objects.create(
                code=code,
                slug=slug,
                name_en=names[0],
                name_ru=names[1],
                is_popular=popular,
                position=index,
                seo_text_en=f"Document templates for {names[0]}: utility bills, bank statements and tax papers.",
                seo_text_ru=f"Шаблоны документов: {names[1]}. Коммунальные счета, выписки и налоговые справки.",
            )
            for index, (code, slug, names, popular) in enumerate(COUNTRIES)
        }

        types = {
            slug: DocumentType.objects.create(
                slug=slug,
                name_en=names[0],
                name_ru=names[1],
                position=index,
            )
            for index, (slug, names, _issuer) in enumerate(TYPES)
        }

        products = 0
        for country_index, (_code, country_slug, country_names, _popular) in enumerate(COUNTRIES):
            if country_slug == "portugal":
                continue

            for type_index, (type_slug, type_names, issuer) in enumerate(TYPES):
                for year_index, year in enumerate(YEARS):
                    price = Decimal("15.00") + Decimal(country_index * 7 + type_index * 5 + year_index)
                    product = self._create_product(
                        country=countries[country_slug],
                        document_type=types[type_slug],
                        country_names=country_names,
                        type_names=type_names,
                        issuer=issuer,
                        year=year,
                        price=price,
                    )
                    self._add_images(product, options["images"])
                    products += 1

        products += self._create_edge_cases(countries, types, options["images"])

        # A hand-filled meta pair, so the meta builder's override path has data to show.
        germany = countries["germany"]
        germany.meta_title_en = "Germany document templates - utility bills & statements"
        germany.meta_title_ru = "Шаблоны документов Германии - счета и выписки"
        germany.meta_description_en = "Editable German utility bills, bank statements and tax papers in PDF."
        germany.meta_description_ru = "Редактируемые немецкие счета, выписки и налоговые документы в PDF."
        germany.save()

        pages, slides = self._create_content()

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {len(countries)} countries, {len(types)} document types, {products} products, "
                f"{pages} pages, {slides} slides."
            )
        )

    def _create_content(self) -> tuple[int, int]:
        """Pages for the menu, the home SEO block, welcome slides and the settings row."""

        pages = [
            {
                "slug": Page.HOME,
                "title_en": "Welcome",
                "title_ru": "Добро пожаловать",
                "body_en": (
                    "<p>Editable document templates for address and income verification: utility bills, "
                    "bank statements and tax papers for dozens of countries. Every file is a layered "
                    "source with fonts included.</p>"
                ),
                "body_ru": (
                    "<p>Редактируемые шаблоны документов для подтверждения адреса и дохода: коммунальные "
                    "счета, банковские выписки и налоговые справки для десятков стран. Каждый файл - "
                    "многослойный исходник со шрифтами.</p>"
                ),
            },
            {
                "slug": "info",
                "title_en": "Rules",
                "title_ru": "Правила",
                "body_en": "<h2>Store rules</h2><p>Test copy: every sale is final, links live for 24 hours.</p>",
                "body_ru": "<h2>Правила магазина</h2><p>Тестовый текст: продажи финальны, ссылки живут 24 часа.</p>",
            },
            {
                "slug": "contacts",
                "title_en": "Contacts",
                "title_ru": "Контакты",
                "body_en": "<p>Support: <a href='https://t.me/example'>@example</a>, e-mail below.</p>",
                "body_ru": "<p>Поддержка: <a href='https://t.me/example'>@example</a>, почта ниже.</p>",
            },
        ]
        for page in pages:
            Page.objects.update_or_create(slug=page["slug"], defaults=page)

        slides = [
            {
                "title_en": "Welcome to the store!",
                "title_ru": "Добро пожаловать в магазин!",
                "text_en": "New documents and weekly deals arrive in our Telegram channel.",
                "text_ru": "Новые документы и акции недели - в нашем Telegram-канале.",
                "button_label_en": "Open Telegram",
                "button_label_ru": "Открыть Telegram",
                "button_url": "https://t.me/example",
            },
            {
                "title_en": "Fresh 2026 templates",
                "title_ru": "Свежие шаблоны 2026 года",
                "text_en": "Utility bills and bank statements updated for the new year.",
                "text_ru": "Коммунальные счета и банковские выписки, обновлённые под новый год.",
            },
        ]
        for position, slide in enumerate(slides):
            Slide.objects.create(position=position, image=self._slide_image(position), **slide)

        settings_row = SiteSettings.load()
        settings_row.support_url = "https://t.me/example"
        settings_row.contact_email = "support@example.com"
        settings_row.footer_note_en = "Test shop - seeded data, nothing here is for sale."
        settings_row.footer_note_ru = "Тестовый магазин - данные из seed, ничего не продаётся."
        settings_row.save()

        return len(pages), len(slides)

    def _slide_image(self, position: int) -> ContentFile:
        from PIL import Image, ImageDraw

        palette = [(33, 54, 255), (217, 15, 43)]
        # Two shapes on purpose: a slide holds whatever the owner uploads, and the block must not
        # depend on it being wide.
        sizes = [(640, 420), (900, 500)]
        width, height = sizes[position % len(sizes)]
        canvas = Image.new("RGB", (width, height), palette[position % len(palette)])
        ImageDraw.Draw(canvas).ellipse((width * 0.2, height * 0.15, width * 0.8, height * 0.85), fill=(255, 255, 255))
        buffer = BytesIO()
        canvas.save(buffer, format="PNG")
        return ContentFile(buffer.getvalue(), name=f"slide-{position + 1}.png")

    def _create_product(self, *, country, document_type, country_names, type_names, issuer, year, price, **overrides):
        name_en = overrides.pop("name_en", f"{country_names[0]} {issuer[0]} {type_names[0]} {year}")
        name_ru = overrides.pop("name_ru", f"{country_names[1]}: {type_names[1]} ({issuer[1]}) {year}")
        slug = overrides.pop("slug", f"{country.slug}-{document_type.slug}-{year}")

        return Product.objects.create(
            country=country,
            document_type=document_type,
            year=year,
            price=price,
            slug=slug,
            name_en=name_en,
            name_ru=name_ru,
            description_en=DESCRIPTION_EN.format(type=type_names[0].lower(), country=country_names[0], year=year),
            description_ru=DESCRIPTION_RU.format(type=type_names[1].lower(), country=country_names[1], year=year),
            file=ContentFile(PLACEHOLDER_FILE, name=f"{slug}.psd"),
            **overrides,
        )

    def _create_edge_cases(self, countries, types, images: int) -> int:
        """The rows that break layouts: a very long name, extreme prices, no year, hidden."""

        germany, utility = countries["germany"], types["utility-bill"]
        cases = [
            {
                "slug": "germany-utility-bill-bundle",
                "name_en": (
                    "Germany Stadtwerke utility bill + Kontoauszug + Meldebescheinigung + "
                    "Steuerbescheid combo pack with editable layers and matching fonts"
                ),
                "name_ru": (
                    "Германия: счёт Stadtwerke + выписка Kontoauszug + прописка Meldebescheinigung + "
                    "налоговое уведомление Steuerbescheid, комплект с редактируемыми слоями"
                ),
                "price": Decimal("499.99"),
                "year": 2024,
            },
            {
                "slug": "germany-utility-bill-cheap",
                "name_en": "Germany utility bill (single page)",
                "name_ru": "Германия: счёт за коммуналку (одна страница)",
                "price": Decimal("0.99"),
                "year": 2020,
            },
            {
                "slug": "germany-utility-bill-undated",
                "name_en": "Germany utility bill (blank year)",
                "name_ru": "Германия: счёт за коммуналку (без года)",
                "price": Decimal("29.00"),
                "year": None,
            },
            {
                "slug": "germany-utility-bill-hidden",
                "name_en": "Germany utility bill (draft, hidden)",
                "name_ru": "Германия: счёт за коммуналку (черновик, скрыт)",
                "price": Decimal("31.00"),
                "year": 2019,
                "is_active": False,
            },
        ]

        for case in cases:
            product = Product.objects.create(
                country=germany,
                document_type=utility,
                description_en="Edge case for manual testing.",
                description_ru="Крайний случай для ручного тестирования.",
                file=ContentFile(PLACEHOLDER_FILE, name=f"{case['slug']}.psd"),
                **case,
            )
            self._add_images(product, images)

        return len(cases)

    def _draw_stamp(self, canvas, draw, product: Product):
        """A big flag and a big red number in the middle of the placeholder."""

        from PIL import ImageFont

        width, height = canvas.size
        flag_w = int(min(width, height) * 0.42)
        flag_h = int(flag_w * 2 / 3)
        left = (width - flag_w) // 2
        top = (height - flag_h) // 2 - int(flag_h * 0.25)

        code = product.country.code.lower()
        if code == "gb":
            self._draw_union_jack(draw, left, top, flag_w, flag_h)
        else:
            direction, bands, canton = FLAGS.get(code, ("h", [(220, 224, 232)], None))
            for index, colour in enumerate(bands):
                if direction == "h":
                    y0 = top + flag_h * index // len(bands)
                    y1 = top + flag_h * (index + 1) // len(bands)
                    draw.rectangle((left, y0, left + flag_w, y1), fill=colour)
                else:
                    x0 = left + flag_w * index // len(bands)
                    x1 = left + flag_w * (index + 1) // len(bands)
                    draw.rectangle((x0, top, x1, top + flag_h), fill=colour)

            if canton:
                draw.rectangle((left, top, left + flag_w * 2 // 5, top + flag_h * 7 // 13), fill=canton)

        draw.rectangle((left, top, left + flag_w, top + flag_h), outline=(60, 70, 90), width=max(1, flag_w // 80))

        # The number is the product id: two cards of the same country and year still differ.
        label = str(product.pk)
        font = ImageFont.load_default(size=max(24, int(flag_h * 0.7)))
        box = draw.textbbox((0, 0), label, font=font)
        draw.text(
            ((width - (box[2] - box[0])) // 2 - box[0], top + flag_h + int(flag_h * 0.12) - box[1]),
            label,
            font=font,
            fill=(214, 32, 48),
        )

    def _draw_union_jack(self, draw, left: int, top: int, width: int, height: int):
        """Navy field, a white diagonal cross, a white+red centre cross - reads as the Union Jack
        at thumbnail size, which a plain band never could (see the flag comment above `FLAGS`)."""

        navy, white, red = (1, 33, 105), (255, 255, 255), (200, 16, 46)
        right, bottom = left + width, top + height
        center_x, center_y = left + width / 2, top + height / 2

        draw.rectangle((left, top, right, bottom), fill=navy)

        diagonal_white = max(2, int(min(width, height) * 0.22))
        draw.line((left, top, right, bottom), fill=white, width=diagonal_white)
        draw.line((right, top, left, bottom), fill=white, width=diagonal_white)

        diagonal_red = max(1, int(min(width, height) * 0.10))
        draw.line((left, top, right, bottom), fill=red, width=diagonal_red)
        draw.line((right, top, left, bottom), fill=red, width=diagonal_red)

        cross_white_h = max(3, int(height * 0.34))
        draw.rectangle((left, center_y - cross_white_h / 2, right, center_y + cross_white_h / 2), fill=white)
        cross_white_v = max(3, int(width * 0.22))
        draw.rectangle((center_x - cross_white_v / 2, top, center_x + cross_white_v / 2, bottom), fill=white)

        cross_red_h = max(2, int(height * 0.14))
        draw.rectangle((left, center_y - cross_red_h / 2, right, center_y + cross_red_h / 2), fill=red)
        cross_red_v = max(2, int(width * 0.09))
        draw.rectangle((center_x - cross_red_v / 2, top, center_x + cross_red_v / 2, bottom), fill=red)

    def _add_images(self, product: Product, count: int):
        """Generate flat placeholder images so the card, the gallery and the resizer all have work."""

        if count <= 0:
            return

        from PIL import Image, ImageDraw

        palette = [(232, 240, 254), (255, 244, 229), (233, 247, 239)]
        # Real uploads are not one shape: a scan is a portrait A4, a photo is landscape, and
        # somebody always uploads a square or something tiny. The card crops with object-fit, so
        # the seed has to hand it every one of those to be worth testing against.
        shapes = [
            ("landscape", 1400, 990),
            ("a4-portrait", 900, 1273),
            ("square", 1000, 1000),
            ("panorama", 1600, 640),
            ("small", 300, 200),
        ]
        # Offset by the product id, so neighbouring cards in the grid differ.
        offset = product.pk or 0
        for position in range(count):
            shape, width, height = shapes[(offset + position) % len(shapes)]
            canvas = Image.new("RGB", (width, height), palette[position % len(palette)])
            draw = ImageDraw.Draw(canvas)
            inset = max(4, min(width, height) // 30)
            border = (inset, inset, width - inset, height - inset)
            draw.rectangle(border, outline=(120, 130, 150), width=inset // 4 or 1)
            draw.text((inset * 2, inset * 2), f"{product.name_en}\n{shape} {width}x{height}", fill=(40, 50, 70))
            # A frame and a caption look the same from across the grid. The flag and the number in
            # the middle are what make one card tell itself apart from the next.
            self._draw_stamp(canvas, draw, product)

            buffer = BytesIO()
            canvas.save(buffer, format="PNG")
            ProductImage.objects.create(
                product=product,
                position=position,
                image=ContentFile(buffer.getvalue(), name=f"{product.slug}-{position + 1}.png"),
            )
