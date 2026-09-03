# Глубина модулей и швы

Разбор дерева по словарю deep modules: **интерфейс** - всё, что вызыватель обязан знать (сигнатура,
инварианты, порядок вызовов, режимы отказа); **глубина** - сколько поведения он получает на единицу
выученного интерфейса; **шов** - место, где поведение подменяется без правки в этом месте.

Два инструмента, которыми меряно ниже:

- **Тест на удаление.** Убрать модуль мысленно. Сложность исчезла - это был pass-through. Сложность
  всплыла в N местах - модуль окупался.
- **Один адаптер = гипотетический шов, два = настоящий.** Тестовый дубль считается вторым адаптером:
  если тест лезет *за* интерфейс (патчит `requests.get`), шов стоит не там.

Документ описывает состояние на 2026-08-31 и ничего в коде не меняет.

## Сводка

| модуль | интерфейс сейчас | глубина | шов | что делать |
|---|---|---|---|---|
| листинг каталога (`catalog/views.py:59`, `storefront/views.py:64`) | правило «неизвестный slug - 404, `all`/пусто - любой» написано дважды | мелкий, дублированный | нет | `catalog/selectors.py: listing()` |
| Plisio (`sales/plisio.py` + `sales/views.py:72,130`) | перевод payload в одном файле, выпуск инвойса и `validate_hash` - в другом | реализация глубокая, интерфейс размазан | есть, но течёт | собрать весь Plisio за `plisio.py` |
| dual-render (`storefront/views.py:57,95,114`) | `if not is_bot(...) and _shell_available()` трижды | мелкий, уже разъехался | нет | `storefront/rendering.py: respond()` |
| `views/Catalog.vue:51-182` | 110 строк URL-машины внутри вьюхи-разметки | глубокая логика без интерфейса | нет | `composables/useCatalogListing.js` |
| `ProductImage.build_variants` (`catalog/models.py:283`) | PIL внутри модели, мутирует `self` | глубокая, отдельно не тестируется | внутренний | `catalog/images.py`, чистая функция |
| доставка + письмо (`sales/views.py:189`, `sales/views.py:292`) | «оплачено - deliver - письмо, письмо не валит продажу» дважды, с разной политикой | мелкий | нет | `sales/fulfillment.py` |
| `api/order.js: fetchPurchases` | отдаёт сырой JSON - единственный такой в `api/` | - | нарушает собственный контракт | модель `Purchase` либо явная оговорка |
| `customer_by_token` (`sales/views.py:321`) | резолв + одинаковый 404 в трёх вьюхах | тонкий | - | mixin/декоратор; выигрыш маленький |
| `stores/order.js` | два экшена, единственный вызыватель - `CheckoutModal.vue` | pass-through со скрытым `window.location` | ложный | тест на удаление проваливает |
| `stores/content.js` | нет `failed`, ошибки глотаются | - | - | добавить `failed`, как в `stores/catalog.js` |

**Уже глубокое, не трогать:** `storefront/seo.py` (`build_meta` + четыре обёртки), `sales/statistics.py`
(чистые функции над полуинтервалом), `customer/validators.py`, токены `Customer`,
`models/Localized.js`, `api/errors.js`, `backend/urlspace.py`, `sales/utils.send_purchases_link`.

## По файлам

### `backend/catalog/views.py:59` и `backend/storefront/views.py:64`

Одно правило выбора карточек записано в двух местах. ADR-0010 (теперь `docs/architecture.md`)
держится на том, что бот и SPA видят один набор, но гарантирует это комментарий
«mirrors the bot pages», а не код.

Тест на удаление: убрать общий модуль - правило воскресает в двух местах, то есть ровно сегодняшнее
состояние. Шов настоящий: два адаптера уже существуют, `ProductListView` и `storefront.catalog`.

```python
# catalog/selectors.py
def listing(country=None, doctype=None, q=None) -> tuple[ProductQuerySet, Country | None, DocumentType | None]:
    """Один набор карточек для обеих подач. Неизвестный slug -> Http404, `all`/None -> любой."""
```

Возвращать вместе с queryset выбранные объекты: они нужны обеим сторонам - мете и сайдбару.
`PAGE_SIZE` уже общий (`catalog/views.py`), это последний скопированный руками кусок.

### `backend/sales/plisio.py` и `backend/sales/views.py:72,130`

Модуль объявляет себя «Plisio, в словах наших моделей», но за его пределами остались: выпуск
инвойса (`views.py:72-124`), `validate_hash` (`views.py:130-159`), `callback_url()` и `redact()`.
Вызыватель обязан знать `PLISIO_LANGUAGES`, форму params, форму ответа (`status == "success"`,
`data.invoice_url`, `data.message`, `data.code`) - большой интерфейс поверх одного HTTP-вызова.

Второй адаптер уже есть - тесты; сегодня они лезут за интерфейс и патчат `requests.get`, зная
параметры Plisio. Это и есть признак того, что шов стоит не там.

```python
# sales/plisio.py
def create_invoice(order, callback_url) -> Invoice | InvoiceError   # url  |  (message, code)
def verify_callback(data: dict) -> bool                             # переезд validate_hash
# callback_to_fields / apply_order_status - уже здесь
```

`?json=true` остаётся частью `callback_url()` и не превращается в параметр вызова: это не настройка,
а условие, при котором подпись вообще сходится (см. `docs/journal.md`).

### `backend/storefront/views.py:57,95,114`

Решение «бот - серверная страница, человек - shell» записано трижды и уже разъехалось: `catalog()`
пишет warning при отсутствующем `shell.html` (`views.py:59-62`), `page()` и `product()` молча отдают
человеку бот-страницу.

Второй, незакреплённый инвариант: контекст бот-ветки строится только *после* проверки shell, иначе
SPA-ответ платил бы за запросы, которые не рендерит. Сейчас это держится порядком строк.

```python
# storefront/rendering.py
def respond(request, meta, template, build_context):  # build_context - callable, ленивый
```

Ленивый контекст делает порядок структурным: SPA-ветка физически не может выполнить запросы бот-ветки.

### `frontend/src/views/Catalog.vue:51-182`

Вьюха разметки, внутри которой живёт машина состояния URL: `page`, `?q=` с debounce, `gridKey`,
разбор двух смыслов 404 (`landOnLastPage`), скролл-якорь. Ничего из этого не тестируется без
монтирования дизайнерской вёрстки.

Интерфейс composable - ровно то, что и так нужно шаблону (`products`, `state`, `notFound`, `page`,
`totalPages`, `pageRoute`, `catalogTarget`, `queryInput`, `onSearchIcon`); реализация - 110 строк.
Дублирования тут нет, аргумент - тестируемость и читаемость самой вьюхи.

Рядом: `Catalog.vue:264` читает `selectedCountry?.seo_text_en` мимо геттера `Localized` - дырка в
интерфейсе модели, лечится свойством `hasSeoText`.

### `backend/catalog/models.py:283-320`

`build_variants` - единственное место, импортирующее PIL, и единственное, что мутирует `self` и
пишет файлы одновременно. Правило testability «возвращай результат, а не побочный эффект»:

```python
# catalog/images.py
def build_variants(source) -> dict[str, ContentFile]:  # чистая, тестируется без модели и без хранилища
```

`ProductImage.save` после этого только раскладывает готовое по полям.

Рядом, `catalog/models.py:207-217` и `269-281`: «запомнить прежний файл, после super().save() удалить,
если заменился» скопировано в двух моделях. Помощник `delete_replaced_file(instance, field)` убирает
копию, но это мелочь по сравнению с вынесением PIL.

### `backend/sales/views.py:189-201` и `292-311`

Последовательность «платёж подтверждён - выдать файлы - отправить письмо, отказ почты не валит
продажу» записана дважды и с разной политикой: в callback письмо глотается и отдаётся 200 (иначе
Plisio будет ретраить впустую, `paid_at` уже стоит), в `send-links` - 502, чтобы форма могла
попросить повторить. Обе политики правильные, но общая часть - `ensure_access_token` +
`send_purchases_link` + логирование - живёт в двух местах.

`apply_order_status` уже владеет половиной истории (статус + `deliver`) и сознательно возвращает
`(first_payment, items)`, отдавая решение о письме вызывателю. Собрать вторую половину в
`sales/fulfillment.py: notify_purchases(request, customer) -> bool`, политику отказа оставить
вызывателям.

### `frontend/src/api/order.js`

Модуль объявляет: «граница между HTTP и приложением; наружу выходит модель, а не сырой payload».
`fetchPurchases`, `refreshPurchaseItem`, `refreshAllPurchaseItems` возвращают `data` как есть, и
`views/Purchases.vue` работает с полями payload напрямую (`item.download_url`, `item.unit_price`,
`order.paid_at`). Либо модели `Purchase`/`PurchaseItem` (там же нашлось бы место форматированию цены,
которое у `Product` уже есть - `priceLabel`), либо оговорка в комментарии, что страница покупок
сознательно читает снимок заказа сырым.

### `backend/sales/views.py:321-374`

`customer_by_token` + одинаковый ответ `PURCHASES_GONE` повторяются в трёх вьюхах. Интерфейс уже
маленький, выигрыш от mixin'а - три строки на вьюху; делать вместе с чем-то другим в этом файле, ради
себя одного не стоит.

### `frontend/src/stores/order.js`

Тест на удаление: убрать store - `CheckoutModal.vue` вызовет `createOrder`, `cart.clearCart()` и
присвоит `window.location.href` сам. Сложность не всплывает в N местах: вызыватель один. Плюс store
прячет переход по адресу - побочный эффект, которого не видно в имени `buyCart`. Либо свернуть в
компонент, либо признать шов ложным и оставить как есть осознанно.

### `frontend/src/stores/content.js`

`catalog.js` держит `failed` и вьюха умеет сказать «не загрузилось»; `content.js` глотает ошибку
молча. Правило проекта - «loading, failed и empty никогда не выглядят одинаково» - здесь нарушено для
меню и настроек. Для слайдов молчание законно (нет слайдера - валидное состояние), для `pages` и
`settings` - нет.

## Порядок работ

1. `catalog/selectors.py` и `storefront/rendering.py` - оба про равенство двух подач, один заход,
   тесты `storefront/` уже есть.
2. Plisio за один модуль - развяжет тесты `sales/`.
3. `catalog/images.py` - дёшево, чистая функция.
4. `useCatalogListing()`.
5. `sales/fulfillment.py`.

Остальное - попутно, когда файл открыт по другому поводу.
