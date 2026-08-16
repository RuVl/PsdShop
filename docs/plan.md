# План переделки: Verdoc → PsdShop

Кодовая база унаследована от Verdoc (витрина паспортов, штучные файлы, два домена). Оплата,
доставка по почте, страница покупок, рассылки и админка со статистикой переиспользуются как есть.
Меняются каталог, модель выдачи, валюта, дизайн и SEO.

Решения зафиксированы в [ADR](./adr/): [0001](./adr/0001-unlimited-copies-no-reservation.md) —
безлимитный товар, [0006](./adr/0006-single-currency-usd.md) — одна валюта,
[0007](./adr/0007-seo-for-a-spa.md) — SEO, [0008](./adr/0008-catalog-country-type-year.md) — форма
каталога.

## 1. Что уже сделано (эта итерация)

- Удалено зеркало: `frontend/nginx/mirror.conf.template`, `MIRROR_DOMAIN`,
  `MIRROR_PLISIO_SECRET_KEY`, ветка выбора ключа в `OrderCreateView`, проверка callback по двум
  ключам.
- Переименования: `verdoc_*` → `psdshop_*` (volumes, сеть, контейнеры), `VerdocAdminSite` →
  `ShopAdminSite`, `pyproject.name`.
- Почтовый релей в `docker-compose.yaml` обезличен (`example.com` + путь к ключу DKIM).
- Доки: удалены `docs/db-refactoring/`, `docs/incidents/`, ADR про Allocation/сток/перенос данных.
  Оставшиеся перенумерованы, `CONTEXT.md` переписан.

## 2. Целевая схема

### catalog

```
Country          id, name (en/ru), code, is_popular, position
DocumentType     id, name (en/ru), slug (unique), position
Product          id, slug (unique), name (en/ru), description (en/ru),
                 country FK→Country (PROTECT), document_type FK→DocumentType (PROTECT),
                 year (null), price Decimal(10,2) USD, file FileField,
                 is_active bool, created_at, updated_at
ProductImage     id, product FK→Product (CASCADE), image ImageField, position
```

Что исчезает: `StockItem`, `ProductQuerySet.with_available()`, `StockItemQuerySet.available()`,
`catalog/forms.py` (формсет, защищавший удаление занятых единиц).

### sales

```
Order            без изменений, кроме total_price → Decimal USD
OrderItem        order FK, product FK→Product (PROTECT), product_name, unit_price Decimal,
                 token UUID unique null, token_expires_at, download_count,
                 first_downloaded_at, last_downloaded_at
                 UniqueConstraint(order, product)
Transaction      без изменений, source_price → Decimal USD
PaymentCallbackLog  без изменений
```

Что исчезает: `Allocation`, `protect_held_units`, `OrderItem.quantity`, `OrderItem.unit_price_usd`,
`OrderItem.reserve/release`, `_allocate`, команда `expire_transactions` и её строка в `cronjob`.

`Order.deliver()` становится «выдать токены всем строкам» и остаётся идемпотентной;
`Order.release()` не нужна — на EXPIRED/CANCELLED меняется только статус.

### customer, mailing

Без изменений.

## 3. API

| Метод | Путь | Изменение |
|---|---|---|
| GET | `/api/countries/` | плоский список стран с `products_count`, без вложенных товаров |
| GET | `/api/document-types/` | новый |
| GET | `/api/products/` | новый: фильтры `country`, `type`, `year`, `search`, `ordering`, пагинация |
| GET | `/api/products/<slug>/` | новый: описание, галерея, соседние товары |
| GET | `/api/years/` | новый (или `facets` в списке товаров) — годы, по которым есть товар |
| POST | `/api/order/` | без `quantity` в позициях |
| POST | `/api/order/status` | без 409 «оплачено, но нет стока» |
| POST | `/api/send-links/` | без изменений |
| GET | `/api/purchases/<token>/` | позиции вместо аллокаций |
| POST | `/api/purchases/<token>/refresh/<item_id>/` | `allocation_id` → `item_id` |
| POST | `/api/purchases/<token>/refresh-all/` | без изменений |
| GET | `/api/files/<uuid>/` | без изменений (токен на строке заказа) |
| GET | `/api/unsubscribe/<token>/`, POST | без изменений |
| — | `/api/exchange-rates/` | удаляется |

## 4. Фронт

Источник вёрстки — `design/` (`index.html`, `product.html`, `style.css`, `app.js`). Порядок:
CSS переносится целиком в `frontend/src/assets/`, разметка режется на компоненты Vue, jQuery-код
из `app.js` (фильтры, бургер, слайдер, лайтбокс) переписывается на реактивность.

Замены библиотек: `remodal` → существующий `ModalWindow.vue`; `swiper-bundle` → `swiper/element`
(без jQuery); `glightbox` — vanilla, подключается как есть или заменяется своим просмотрщиком;
`jquery` не тянем.

Маршруты:

| Путь | Вью | Состояние |
|---|---|---|
| `/` | `Home.vue` | переписывается: слайдер, поиск, сайдбар стран, фильтры, сетка карточек, пагинация |
| `/product/:slug` | `Product.vue` | новый: галерея, бейджи, описание, купить/в корзину |
| `/cart` | `Cart.vue` | переписывается: без счётчиков количества |
| `/purchases`, `/purchases/:token` | `MyPurchases.vue`, `Purchases.vue` | логика цела, вёрстка новая |
| `/unsubscribe/:token` | `Unsubscribe.vue` | логика цела, вёрстка новая |
| `/info`, `/contacts` | `Info.vue`, `Contacts.vue` | контент по дизайну |

Удаляются: `CurrencySwitch.vue`, `stores/currencies.js`, `CounterChanger.vue`, `CounterShow.vue`,
`CircleCounter.vue`, `ListView.vue`, старые ассеты (`banner_background.jpg`, `logo_icon.png`).
Корзина в `stores/cart.js` становится множеством `product_id` (без количеств), персист остаётся.

## 5. Этапы

**R1 — каталог (бэкенд).** Модели `Country`/`DocumentType`/`Product`/`ProductImage`, миграции
с нуля (старые удаляются, база пересоздаётся), админка с инлайном картинок, `seed_testdata`
переписывается под страны × типы × годы. Тесты `catalog/tests.py` — фильтры и видимость
неактивных.

**R2 — продажа без резервов.** `Allocation` и `StockItem` уходят, токены переезжают на
`OrderItem`, `sales/tests.py` переписываются: чекаут, дубль callback, поздняя оплата, повторная
выдача. Из `cronjob` уходит `expire_transactions`.

**R3 — одна валюта.** `djmoney` из зависимостей, `MoneyField` → `DecimalField`, `update-rates`
и `exchange-rates` удаляются, `sales/statistics.py` чистится от конвертации (комиссия Plisio
по-прежнему делится на `source_rate`), из статистики убирается прогноз стока.

**R4 — API витрины.** Эндпоинты из раздела 3, пагинация DRF, фасеты для фильтров.

**R5 — фронт.** Дизайн из `design/`, маршруты и компоненты из раздела 4, i18n-ключи под новые
тексты, адаптив по мокапам (`responsive-craft`).

**R6 — SEO.** По [ADR-0007](./adr/0007-seo-for-a-spa.md): мета из Django, `sitemap.xml`,
`robots.txt`. Делается после R5 и только если решение подтверждено.

**R7 — прод.** `django_site` под новый домен, сертификаты, DKIM-ключ нового домена, первый деплой.

Порядок R1 → R2 → R3 обязателен (каждый следующий опирается на схему предыдущего), R4 и R5 можно
вести параллельно, если зафиксировать контракт API.

## 6. Открытые вопросы

1. **Имя и домен.** Технические имена сейчас `psdshop` (директория проекта). Публичное название,
   домен, логотип и почта отправителя нужны к R7, но лучше знать раньше — они попадают в i18n,
   письма и `django_site`.
2. **SEO.** [ADR-0007](./adr/0007-seo-for-a-spa.md) в статусе `proposed`. Если SEO не нужен,
   R6 отменяется, а Django не попадает на путь HTML.
3. **Способы оплаты.** В подвале дизайна нарисованы карты, QIWI, WebMoney; реально работает
   только Plisio (крипта). Либо убираем чужие логотипы, либо добавляем шлюз — второе это отдельный
   объём работ.
4. **Файлы товара.** Один файл на товар или архив/несколько файлов (например, PSD + шрифты)?
   Сейчас в плане одно поле `file`.
5. **Копирайт и тексты.** «Правила», «Контакты», согласие на условия покупки — нужен реальный
   текст, в дизайне рыба.
