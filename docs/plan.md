# План переделки: Verdoc → PsdShop

Кодовая база унаследована от Verdoc (витрина штучных файлов, SPA, два домена). Переиспользуются
оплата Plisio, доставка по почте, страница покупок, рассылки и админская статистика. Меняются
каталог, модель выдачи, валюта, дизайн и способ рендеринга витрины.

**Финиш текущего захода — локально работающий магазин** на dev-стенде с тестовыми данными.
Боевой запуск (домен, сертификаты, DKIM, крон, бэкапы) в этот заход не входит.

## 1. Принятые решения

| Решение | Где зафиксировано |
|---|---|
| Товар — шаблон, продаётся неограниченно; ни стока, ни резервов | [ADR-0001](./adr/0001-unlimited-copies-no-reservation.md) |
| Каталог: страна × тип документа × год, галерея картинок | [ADR-0008](./adr/0008-catalog-country-type-year.md) |
| Цены только в USD, `djmoney` уходит | [ADR-0006](./adr/0006-single-currency-usd.md) |
| Динамический рендеринг: SPA людям, Django-HTML ботам, один URL | [ADR-0010](./adr/0010-dynamic-rendering.md) |
| Язык в URL, обе версии в индексе, мета и sitemap с сервера | [ADR-0010](./adr/0010-dynamic-rendering.md) |
| Миграции пишутся с нуля, старая цепочка удаляется | этот файл, M1 |
| Товары заводятся руками в админке, без генерации текстов и импорта | этот файл, M1 |
| Картинки жмёт бэкенд (Pillow), отдаём webp + png | этот файл, M1 |
| Корзина остаётся в localStorage | [ADR-0010](./adr/0010-dynamic-rendering.md) |
| «Купить сейчас» — экспресс-чекаут одного товара, корзину не трогает | этот файл, M3 |
| Бесконечная прокрутка поверх настоящих страниц `?page=N` | этот файл, M2 |
| Тексты, мета, страницы, слайды — редактируются в админке | этот файл, M1 |
| CI, письмо владельцу и счётчики аналитики — **не** в этом заходе | решение владельца |

## 2. Архитектура витрины

### URL

Язык — префикс пути (`i18n_patterns`, `prefix_default_language=True`), корень отдаёт 302 на язык
браузера. Каталог адресуется двумя сегментами, где `all` означает «любой», поэтому у каждой
комбинации ровно одна форма записи и не бывает дублей от порядка параметров.

```
/                                   302 → /en/ или /ru/ (Accept-Language)
/en/                                главная = весь каталог
/en/all/all/                        301 → /en/
/en/germany/all/                    страна
/en/all/utility-bill/               тип документа
/en/germany/utility-bill/           страна + тип
/en/germany/utility-bill/142-vattenfall-2022/    товар
/en/cart/  /en/purchases/  /en/purchases/<token>/  /en/unsubscribe/<token>/
/en/info/  /en/contacts/            страницы из админки
/api/...                            без языкового префикса
/sitemap.xml  /robots.txt
```

Слаги — латиница из английских названий, транслита нет нигде. Слаг товара строится как
`<id>-<slug>`: id гарантирует уникальность и переживает любые правки названия.

Адресное пространство описано в одном месте — `backend/urlspace.py`. Слаги стран, типов и страниц
проверяются против служебных сегментов (`all`, `cart`, `purchases`, `unsubscribe`, `api`, `admin`),
языковых префиксов из `settings.LANGUAGES` и корней `STATIC_URL` / `MEDIA_URL`. `info` и `contacts`
в этом списке отсутствуют намеренно: это строки `content.Page`, и запрет на них означал бы запрет
завести те самые страницы. Их защищает вторая проверка — слаг страны и слаг страницы делят первый
сегмент, поэтому не могут совпадать (`validate_slug_is_free`). Слаг типа живёт на втором сегменте,
под страной, и с ними не пересекается. `sitemap.xml` и `robots.txt` в списке не нужны: точку
`SlugField` не принимает сам.

Обе проверки срабатывают в `full_clean()`, то есть в формах админки; запись слага из кода
(шелл, data-миграция, management-команда) их не вызывает.

`?year=` — фильтр, `canonical` ведёт на адрес без параметра. `?page=` — пагинация, `canonical` на
себя. Сортировки по году нет.

### Рендеринг

Динамический рендеринг ([ADR-0010](./adr/0010-dynamic-rendering.md)): все HTML-запросы приходят
в Django, вьюха решает по `User-Agent`. Бот получает полный серверный HTML
(`storefront/templates/`), человек — **shell**: собранный vite `index.html` с метой страницы,
подставленной в `<head>`; дальше работает Vue SPA (vue-router зеркалит URL-пространство, данные
из `/api/catalog/...`). Мета строится одной функцией на маршрут (`storefront/seo.py`) и попадает
в обе подачи — это страховка эквивалентности контента.

Интерфейс целиком Vue: шапка, каталог, карточка, корзина, покупки, отписка. Плавающая корзина
из дизайна (`cartlequebutton`) — компонент с pinia-стором. `glightbox` остаётся библиотекой:
своих стилей лайтбокса в макете нет, перерисовывать вид смысла нет. jQuery, remodal и swiper
не переносятся; слайдер — свой (~60 строк, стили стрелок уже в макете).

Фильтры и пагинация — обычные SPA-переходы по настоящим URL (`/en/<country>/<type>/`,
`?page=N`); робот на тех же адресах получает серверные страницы со ссылками.

### Файлы

Загрузки лежат на одном томе `products`, но разделены по доступу:

```
backend/products/media/     превью товаров и картинки слайдов - MEDIA_ROOT, отдаёт nginx (/media/)
backend/products/private/   платные файлы - PRODUCT_FILES_ROOT, ни один location туда не смотрит
```

Платный файл уезжает в `private/` через `catalog/storages.py: ProductFilesStorage`: у хранилища
нет `base_url`, поэтому `product.file.url` кидает `ValueError`, а не отдаёт путь. Единственный
способ получить файл - `DownloadFileView` по токену. В разработке `MEDIA_URL` отдаёт сам Django
(`static()` в `backend/urls.py`), в проде - `location /media/` с томом, смонтированным в nginx
только на чтение.

### Статика

`design/style.css`, `img/`, `fonts/` живут в `backend/storefront/static/storefront/` — их делят
бот-шаблоны и SPA (в разработке vite dev server проксирует `/static` на бэкенд). Vite собирает
SPA с собственным хешированием имён в `static/storefront/spa/`, а `index.html` с Django-хуками
меты переносит в шаблоны как `shell.html` (`make spa`). Отдельного manifest-хранилища нет.

## 3. Целевая схема

### catalog

```
Country       name (en/ru), slug uniq, code (iso2 → флаг), is_popular, position,
              seo_text (en/ru), meta_title (en/ru), meta_description (en/ru)
DocumentType  name (en/ru), slug uniq, position, seo_text (en/ru), meta_* (en/ru)
Product       name (en/ru), slug, description (en/ru), country FK PROTECT,
              document_type FK PROTECT, year (null), price Decimal(10,2) USD,
              file FileField, is_active, created_at, updated_at, meta_* (en/ru)
ProductImage  product FK CASCADE, image, position
              (Pillow на сохранении делает варианты ~400px и ~1000px, png + webp)
```

Исчезают: `StockItem`, `ProductQuerySet.with_available()`, `StockItemQuerySet.available()`,
`catalog/forms.py`, весь блок «остатки» в `catalog/admin.py`.

### content (новое приложение)

```
Page          slug uniq, title (en/ru), body (en/ru, TinyMCE), meta_* (en/ru)   → /info, /contacts
Slide         image, title (en/ru), text (en/ru), button_label (en/ru), url, position, is_active
SiteSettings  синглтон: ссылка на поддержку, подпись в подвале, контакты
```

SEO-текст главной — строка `Page` со слагом `home`.

### sales

```
Order       без изменений, кроме total_price → Decimal
OrderItem   order, product FK PROTECT, product_name, unit_price Decimal,
            token UUID uniq null, token_expires_at, download_count,
            first_downloaded_at, last_downloaded_at
            UniqueConstraint(order, product);  поля quantity и unit_price_usd больше нет
Transaction source_price → source_amount Decimal + source_currency Char, остальное как было
PaymentCallbackLog  без изменений
```

Исчезают: `Allocation`, `protect_held_units`, `OrderItem.reserve/release/_allocate`,
`Order.release()`, команда `expire_transactions` и её строка в `backend/cronjob`, ветка 409
«оплачено, но нет стока» в callback. `Order.deliver()` остаётся идемпотентной и просто выдаёт
токены строкам заказа. `Order.objects.reusable()` упрощается: сравнение набора товаров и цен без
подсчёта резервов.

### customer, mailing

Без изменений.

## 4. API после переделки

Остаются: `POST /api/order/`, `POST /api/order/status`, `POST /api/send-links/`,
`GET /api/purchases/<token>/`, `POST /api/purchases/<token>/refresh/<item_id>/`,
`POST /api/purchases/<token>/refresh-all/`, `GET /api/files/<uuid>/`,
`GET|POST /api/unsubscribe/<token>/`.

Добавляются: `GET /api/cart/items/?ids=1,2,3` — карточный payload каталога для корзины, которая
живёт в localStorage (тот же сериализатор, что у сетки: снятый с продажи товар просто отсутствует
в ответе, изменившаяся цена приезжает исправленной); каталожный API для SPA — `GET /api/catalog/countries/`,
`GET /api/catalog/document-types/`, `GET /api/catalog/products/?country=&type=&page=`,
`GET /api/catalog/products/<id>/` (оба языка в каждом ответе, страница = 24 карточки — та же
константа, что у серверной пагинации); контентный API — `GET /api/content/pages/`,
`GET /api/content/pages/<slug>/` (в том числе `home` — SEO-блок главной),
`GET /api/content/slides/`, `GET /api/content/settings/`.

Удалены: `GET /api/exchange-rates/` и валютные ручки — цены только в USD.

В `sales/serializers.py` количеств и конвертации валют больше нет: чекаут принимает
`{email, language, products: [id]}`, выдачу описывает плоский `PurchaseItemSerializer` с полями
токена (ни `allocations`, ни валюты в строке нет).

## 5. Этапы

**M1 — схема и админка.** Модели catalog и content, Pillow в зависимостях, миграции пишутся с нуля
(все существующие файлы миграций удаляются, база пересоздаётся), админка с инлайном картинок и
фильтрами, `seed_testdata` под страны × типы × годы. Тесты каталога.
_Готово, когда:_ в админке заводится товар с файлом и картинками, варианты картинок создаются,
`make dev-test` зелёный.

**M2 — витрина.** Приложение `storefront` (бот-страницы + shell, UA-развилка, `seo.py`),
каталожный и контентный API, SPA по `design/index.html` и `design/product.html`: роутер с
префиксом языка, каталог, карточка товара, плавающая корзина, страницы `Page` в меню, слайдер
из админки, бесконечная прокрутка поверх `?page=N`.
_Готово, когда:_ обе языковые версии открываются, фильтры работают без перезагрузки, бот
получает полный HTML на тех же URL, вёрстка совпадает с макетом на ширинах от 320 до 1920
(`responsive-craft`), **и сценарий пройден руками в браузере** (каталог, фильтр, карточка,
добавление в корзину, корзина, смена языка).

**M3 — покупка.** Корзина и модалка оплаты на дизайне, экспресс-покупка одного товара («Купить
сейчас» с карточки и со страницы товара, корзину не трогает), страница покупок и форма
восстановления ссылок на плоской выдаче `OrderItem`, отписка. Ссылки из писем строятся `reverse()`
с языковым префиксом; `?lang=` уходит из последней ручки API (`/api/cart/items/`, теперь отдаёт
карточный payload каталога, по которому корзина сверяется с магазином при открытии). Verdoc-набор
компонентов удаляется целиком.
_Готово, когда:_ сквозной сценарий проходит локально — товар в корзину, оплата, поддельный callback
Plisio, письмо в консоли, скачивание файла по ссылке, обновление истёкшей ссылки.

Схема `sales` и её тесты переписаны ещё на M1, поэтому серверная часть чекаута
(`POST /api/order/` без количеств, токены на `OrderItem`, `sales/statistics.py`) в M3 не менялась.

**M4 — SEO-обвязка.** Мета из моделей с автоподстановкой, `ld+json` (Product + Offer,
BreadcrumbList), canonical, 301 с `all/all` и `noindex` на корзину, покупки и отписку сделаны ещё
на M2 вместе с `storefront/seo.py`; этап добавляет `sitemap.xml` (индекс над секциями, обе
языковые версии и hreflang внутри), `robots.txt` и `x-default` в `<head>` — той же формулой, что
у карты, чтобы обе подачи говорили одно.
_Готово, когда:_ `curl` показывает текст страницы без JS, у каждой страницы уникальные title и
description, карта сайта валидна и содержит обе языковые версии.

**M5 — подчистка, обвязка и аудит.** Валютный код и `djmoney` удалены ещё на M1/M2b,
Verdoc-компоненты — на M3, поэтому этап взял оставшееся: неиспользуемые зависимости фронта
(`lodash`, `vue-country-flag-next`), второй источник шрифтов, осиротевшие i18n-ключи, формулировки
про резерв в конфигах nginx и в образе. Плюс актуализация обвязки по просьбе заказчика:
`make nginx-check`, отслеживаемые `package-lock.json` и `frontend/nginx/ssl/`, честные пути в
`clean`/`db-dump`, вычищенные env-шаблоны. Плюс аудит безопасности перед запуском (отчёт —
в [журнале](./journal.md)): constant-time сравнение подписи колбэка, ключ Plisio вон из логов,
лимит на форму входа в админку, JSON-only API.
_Готово, когда:_ `make lint` и тесты зелёные, в коде нет упоминаний стока и валютных курсов,
сквозной сценарий пройден руками на чистой базе.

**Правки дизайна вынесены за рамки этапов** — заказчик собирает список отдельно, они заходят
своей итерацией после M5.

Порядок строгий: M1 → M2 → M3 → M4 → M5, все пять закрыты. Каждый этап — своя ветка `feature/...`
с PR в `dev`.

Миграции M1 переписаны с нуля, поэтому уже смигрированная dev-БД на них падает
(`InconsistentMigrationHistory`). Обновляться нужно через `make dev-nuke` — цель удаляет том
`psdshop_postgres` вместе с данными, в отличие от `dev-reset`, который пересоздаёт только
контейнер. После неё: `make dev-migrate` и `make dev-manage c="seed_testdata --flush"`.

## 6. Как проверять

```bash
make dev-infra && make dev-migrate            # база
make dev-manage c="seed_testdata --flush"     # каталог
make dev-backend                              # :8000
make dev-frontend                             # vite dev server: http://localhost:5173/ (проксирует /static и /media на :8000)
make spa                                      # прод-сборка: shell.html + ассеты в backend-дерево

make dev-test                                 # тесты
make lint                                     # ruff
make nginx-check                              # envsubst + nginx -t в стоковом контейнере
curl -s -A Googlebot localhost:8000/en/germany/all/ | grep -c "products-item"  # бот: HTML без JS
curl -s localhost:8000/en/germany/all/ | grep "og:title"                       # человек: shell с метой
curl -sI localhost:8000/ | grep -i location                                    # редирект по языку
```

Сквозной сценарий оплаты гоняется тестом с поддельным callback (как в текущем `sales/tests.py`),
письма печатаются в консоль (`EMAIL_URL=consolemail://` в `backend/dev.env`).

## 7. Риски и узкие места

- **Слаги против служебных путей.** Страна со слагом `cart` сломает роутинг — валидатор на модели
  и тест на список зарезервированных слов.
- **Статика отдаётся без манифеста** (`StaticFilesStorage`): хеширует имена сам vite, а
  дизайнерский `style.css` и админка обходятся без cache-busting. Значит и ломающихся `url()`
  внутри CSS при `collectstatic` быть не может — но и кэш у `style.css` сбрасывается только
  заголовками nginx.
- **Варианты картинок.** Удаление `ProductImage` должно уносить все производные файлы, иначе диск
  копит мусор.
- **Товар нельзя удалить**, если он куплен (`PROTECT`) — админка обязана объяснять это по-человечески,
  а не 500-й ошибкой.
- **Двойной источник языка.** Язык страницы теперь в URL, а язык писем — в `Customer.language`.
  Форма чекаута должна слать текущий язык страницы, иначе покупатель получит письмо не на том языке.

## 8. Осталось открытым

1. **Домен** — `psd-shop.com` или `psd-templates.store`. Нужен к боевому запуску, не раньше.
2. **Тексты** — рыба до согласования дизайна с заказчиком.
3. **Логотипы платёжек** в подвале убираем; чем заменить пустое место — вопрос дизайна.
4. **Список правок дизайна** от заказчика — отдельная итерация после M5.
5. **Фильтр по году не реализован.** В макете (`design/index.html`, блок `filter-products`) есть
   выпадающий список годов и кнопка «Сортировать по году»; в коде нет ни `?year=` в
   `catalog/views.py`, ни выпадающего списка в `Catalog.vue`, ни на бот-страницах. Сортировку по
   году план отверг сознательно (каталог и так `ordering = ["-year", "name"]`), а фильтр — нет:
   это невыполненный пункт, а не косметика. Делать его нужно сразу в обеих подачах плюс canonical
   без параметра, поэтому он идёт отдельной задачей.
6. **Токены в логах доступа** (`/purchases/<token>/`, `/api/files/<uuid>/`): вырезать их из
   `access_log_format` или ограничиться доступом к логам — решение владельца, см. журнал.

## 9. Боевой запуск (за рамками этого захода)

Порядок, в котором это делается на сервере: домен и сертификаты в `frontend/nginx/ssl/` →
заполненные `.env` (`DOMAIN`, `ALLOWED_HOSTS`, `CORS`/`CSRF`, `PLISIO_SECRET_KEY`, `EMAIL_URL`) →
`make up` → `make migrate` → `make superuser` → строка `django_site` под реальный домен →
webhook Plisio на `https://<домен>/api/order/status` → DKIM (профиль `mail`, ключ в `secrets/`) →
проверка `make nginx-check`, `/sitemap.xml`, `/robots.txt` и бэкапов (крон в контейнере postgres).
