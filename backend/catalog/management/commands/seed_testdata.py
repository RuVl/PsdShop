"""Seed the catalog with test data for local/manual UI testing.

Builds countries x document types x years, with real (generated) images so the resize pipeline
runs, and a placeholder file per product so a checkout can be walked end to end. Covers the edge
cases the storefront has to survive: a very long name, the cheapest and the most expensive price,
a product with no year, an inactive product and a country with nothing in it.
"""

from decimal import Decimal
from io import BytesIO

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db.transaction import atomic

from catalog.models import Country, DocumentType, Product, ProductImage

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


class Command(BaseCommand):
    help = "Seed the catalog with countries, document types and products for manual testing."

    def add_arguments(self, parser):
        parser.add_argument("--flush", action="store_true", help="Wipe the catalog first.")
        parser.add_argument("--images", type=int, default=2, help="Images per product (0 skips them).")

    @atomic
    def handle(self, *args, **options):
        if options["flush"]:
            deleted = Product.objects.all().delete()
            Country.objects.all().delete()
            DocumentType.objects.all().delete()
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

        self.stdout.write(
            self.style.SUCCESS(f"Seeded {len(countries)} countries, {len(types)} document types, {products} products.")
        )

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

    def _add_images(self, product: Product, count: int):
        """Generate flat placeholder images so the card, the gallery and the resizer all have work."""

        if count <= 0:
            return

        from PIL import Image, ImageDraw

        palette = [(232, 240, 254), (255, 244, 229), (233, 247, 239)]
        for position in range(count):
            canvas = Image.new("RGB", (1400, 990), palette[position % len(palette)])
            draw = ImageDraw.Draw(canvas)
            draw.rectangle((40, 40, 1360, 950), outline=(120, 130, 150), width=6)
            draw.text((80, 90), f"{product.name_en}\npage {position + 1}", fill=(40, 50, 70))

            buffer = BytesIO()
            canvas.save(buffer, format="PNG")
            ProductImage.objects.create(
                product=product,
                position=position,
                image=ContentFile(buffer.getvalue(), name=f"{product.slug}-{position + 1}.png"),
            )
