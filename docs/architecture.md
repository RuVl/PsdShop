# Architecture

The decisions the code rests on, and the shape they gave it. Vocabulary is in
[`CONTEXT.md`](../CONTEXT.md); how a particular problem got solved is in [`journal.md`](./journal.md).

PsdShop sells template documents (PSD/PDF). The customer picks files, pays a Plisio crypto invoice,
and gets one e-mailed link to a purchases page. Vue 3 SPA + Django REST Framework + PostgreSQL
behind nginx in Docker Compose, one domain. It grew out of **Verdoc**, a storefront for
one-of-a-kind files: payment, delivery, broadcasts and admin statistics were kept, everything about
the catalog was replaced.

## Domain decisions

**A product is a template sold any number of times.** No uniqueness means no scarcity: no
`StockItem`, no `Allocation` with `RESERVED/DELIVERED/RELEASED`, no reservation at checkout and no
expiry job, no "paid but out of stock" 409, no derived `available` counter. The download link lives
on `OrderItem` - token, TTL and download counter are fields of the order line. Consequences: there
are no quantities (`UniqueConstraint(order, product)`, the cart is a set); `OrderItem.product` is
`PROTECT` and taking a product off the shelf is `is_active=False`; replacing a file changes what
**earlier** buyers download, deliberately - a per-order snapshot would be `OrderItem.file` and no
other schema change.

**The catalog is country x document type x year.** Three separate things, not one category list:
`Country` (translated `name`, `code` for the flag, `is_popular`, `position` - the list is 80+ long
and needs a product count), `DocumentType` (translated `name`, `slug`, `position` - few of them, but
visible in the URL and the badge, and a new one must not need a migration), and `Product.year`
(`PositiveSmallIntegerField(null=True)` - a property of the file, and it has to stay a number).
Folding them into one polymorphic `Tag` was rejected: the per-country count, the year ordering and
the type badge would become three queries over one table, and the year would lose its type. Images
are `ProductImage` (`product`, `image`, `position`); the first by `position` is the list preview.
Ordering is fixed on the model (`ordering = ["-year", "name"]`); there is no `?ordering=`.
"Popular" is a flag on the country, not a sales calculation - the owner wants to control it.

**Prices are USD only.** Interface language and currency are different things: Plisio bills crypto
against a fiat amount, and that amount was always the dollar. So `djmoney` and its exchange app are
gone, `MoneyField` is `DecimalField(10, 2)`, and there is one price snapshot on `OrderItem`
(`unit_price`). A second currency later is a decision of this size, not "bring djmoney back": the
snapshot in the order and the amount handed to Plisio must stay in one currency or revenue will not
add up.

**A `Customer` is an entity, and access is by token.** There is no registration - the buyer types an
e-mail at checkout - but "everything this person bought" is needed by them (download again) and by
the shop (broadcasts, LTV, funnel), so the address is a row (unique e-mail, language, subscription)
that `Order` points at. Two independent tokens, both 24h: `Customer.access_token` opens the
purchases page and **rotates on every mail that carries it** (that is how old links are revoked),
`OrderItem.token` opens one file. The token is the whole authentication, so an unknown, malformed
and expired page token all answer the **same 404** - the API must not confirm that a token exists.
Sharing a link is the customer's right, so the mail says the page shows **all** purchases. The
`Customer` row is written at checkout, before payment, so abandoned checkouts stay as leads.

**A `Transaction` is one Plisio invoice, and an order can have several.** When the buyer switches
coin, Plisio mints a new invoice with a new `id` and marks the related ones `cancelled duplicate`;
`order_number` does not change. A `OneToOneField` therefore overwrote the previous invoice along
with its `amount` and `invoice_commission`. `Transaction` is a FK unique by `txn_id`, plus
`pending_amount` and `tx_urls` (Plisio aggregates multiple blockchain payments per invoice itself,
so they are not an entity here). `PaymentCallbackLog` stores the raw `jsonb` of every callback, so
investigating an incident does not depend on what we guessed to parse.

**Mail follows `Customer.language`.** The language cannot come from the request: the delivery mail
is sent from the Plisio webhook, where the buyer's browser is gone, `Accept-Language` belongs to
Plisio and there is no session. The storefront posts `language` with checkout and send-links, and
sending happens inside `translation.override(customer.language)`. Copy is gettext, not per-language
templates: one msgid holds both versions and a third language does not fork the files.

**Checkout is rate limited at the edge.** It no longer blocks the catalog, but it still costs us:
`POST /api/order/` calls Plisio (30s timeout, account limits), `POST /api/send-links/` mails any
address typed into it (sender reputation), and both write rows. `limit_req` in nginx on
`/api/order/` (10 r/m), `/api/send-links/` (5 r/m) and `/admin/login/`; `MAX_ORDER_ITEMS`; an MX
check on the mail domain (`customer/validators.py`, **fails open** - losing a sale to our own DNS is
worse than writing to a dead domain, switch with `VALIDATE_EMAIL_MX`); and
`Order.objects.reusable()` returns the live invoice on a double click (narrow conditions: `PENDING`,
not expired, same products, catalog price unchanged - which is why `Order.invoice_url` exists). The
limits are in nginx, not DRF: the zone at the edge is shared by every gunicorn worker and sees the
real client address, while DRF throttling on `LocMemCache` counts per worker and multiplies the
effective limit. **The Plisio callback is not limited** - it retries from several addresses, and a
request we drop is a payment we never hear about.

**Dynamic rendering: SPA for people, Django HTML for bots, one URL.** Indexing is required (Yandex
renders JS unreliably and the Russian listing is not optional), and full SSR would mean a second
runtime and a second translation system. Two earlier answers were tried and dropped: "meta from
Django on top of the SPA" left the crawler an empty `<div id="app">`, and "Django templates with Vue
islands" grew a manifest storage, storage switching by `sys.argv` and vanilla scripts where Vue was
wanted. So: every HTML request reaches Django, one view, one queryset, one meta context, two
presentations split by `User-Agent` (`storefront/bots.py`). A bot gets the server-rendered
templates; a person gets the **shell** - the vite-built `index.html` with this page's meta injected
into `<head>` - and the SPA takes over, reading `/api/catalog/...`.

This is not cloaking as long as the content is equivalent: same URLs, same querysets, shared meta
built by one function per route (`storefront/seo.py`). **Project rule: the bot template renders the
same data the API returns, never more and never less.** Google calls the approach legacy, which we
accept; the standing costs are the duplicated catalog markup (bot pages need no pixel accuracy - a
design change updates their content, not their look) and the bot-UA list (`BOT_UA_RE`), where a
forgotten crawler just gets the shell.

## URL space

The language is a path prefix (`i18n_patterns`, `prefix_default_language=True`). The catalog is two
segments where `all` means "any", so every combination has exactly one spelling.

```
/                                   302 → /en/ or /ru/ (Accept-Language)
/en/                                home = the whole catalog
/en/all/all/                        301 → /en/
/en/germany/all/                    country
/en/all/utility-bill/               document type
/en/germany/utility-bill/           country + type
/en/germany/utility-bill/142-vattenfall-2022/    product
/en/cart/  /en/purchases/  /en/purchases/<token>/  /en/unsubscribe/<token>/
/en/info/  /en/contacts/            content.Page rows
/api/...                            no language prefix
/sitemap.xml  /robots.txt
```

Slugs are latin, built from the English name; there is no transliteration. A product slug is
`<id>-<slug>`: the id guarantees uniqueness and survives renames. The space is described in one
place, `backend/backend/urlspace.py`, and slugs are validated against the service segments, the
language prefixes and the `STATIC_URL`/`MEDIA_URL` roots. `info` and `contacts` are deliberately
absent from the reserved list - they are `content.Page` rows, and banning them would ban creating
those very pages; what protects them is the second check, that a country slug and a page slug share
the first segment and therefore cannot collide (`validate_slug_is_free`). Both checks run in
`full_clean()`, i.e. in admin forms - writing a slug from code does not trigger them.

`?year=` is a filter (canonical without it), `?page=` is pagination (canonical to itself), `?q=` is
search. Page 1 carries no parameter.

## Order / fulfillment flow

Apps: `catalog` (products), `content` (pages, slides, settings), `customer` (buyers and access),
`sales` (checkout, payment, delivery), `mailing` (broadcasts), `storefront` (both presentations).

1. **Checkout** - `POST /api/order/` (`OrderCreateView` + `OrderSerializer`), payload
   `{email, language, products: [id]}`. Gets or creates the `Customer`, computes `total_price`
   **from the catalog** (never from the client), writes `Order` + `OrderItem`s **with a price
   snapshot** (`product_name`, `unit_price`), then asks Plisio for an invoice and stores
   `Order.invoice_url`. If that call fails the order is deleted and the endpoint answers **502**
   with `{detail, code: "invoice_failed", provider_code}`, passing Plisio's own message on.
2. **Payment callback** - `POST /api/order/status` (`PlisioCallbackView`). The invoice request sends
   its own `callback_url` ending in **`?json=true`** (`sales/views.py: callback_url()`); see the
   journal for why that parameter decides whether any payment is accepted at all. The view verifies
   `verify_hash` (HMAC-SHA1 over the body, both as received and key-sorted) against
   `PLISIO_SECRET_KEY` with `hmac.compare_digest`, writes the raw payload to `PaymentCallbackLog`
   **before** the atomic block, then upserts the `Transaction` **by `txn_id`**. On PAID/OVERPAID
   `order.mark_paid()` stamps `paid_at` once - only that first call sends the mail - and
   `order.deliver()` hands the files over. On EXPIRED/CANCELLED there is nothing to undo. A repeat
   callback is a 200 no-op.
3. **Delivery** - the purchases page is `GET /api/purchases/<customer_token>/`, with
   `POST .../refresh/<id>/` and `POST .../refresh-all/` re-issuing file tokens; one file is
   `GET /api/files/<uuid>/`. `POST /api/send-links/` is the recovery path: it tops up anything
   undelivered, **rotates** `access_token` and mails the new link, while leaving file tokens alone
   so links the customer already shared keep working.
   - **Every link a mail carries is built with `reverse()` under
     `translation.override(customer.language)`** (`Customer.get_purchases_url`,
     `mailing.services.make_unsubscribe_url`), then absolutised through `backend/sites.py`. The
     storefront routes live under `i18n_patterns`, so a hand-glued path loses the language prefix
     and 404s - and the browser that opens the link is not the one the mail was sent from.
   - `serve_order_item()` in `sales/views.py` is the single place a file is streamed from and the
     only place a download writes to the DB. It records the download **after** the file is open, so
     a refused link never counts, and it is an `UPDATE` with `F()`, not a `save()`, so two parallel
     downloads add up to two. The counter answers "did the **customer** take the file", so
     `DownloadFileView` skips it for a staff session - the carve-out is on the session, not the link.
   - A dead SMTP never costs the customer their order: the callback logs and still answers 200
     (a Plisio retry would send nothing, `paid_at` is already stamped), while `send-links` answers
     502 so the form can say to try again.
4. **Plisio only tells us about an invoice once, in the callback.** Its `operations/<id>` endpoint
   answers with nine fields without White Label, and none of `amount`, `source_rate` or `commission`
   - there is nothing to reconcile money against. `sales/plisio.py` therefore holds only
   `callback_to_fields()` (the one place a payload field becomes a `Transaction` column; a key the
   payload omits is left out entirely, so a repeat cannot blank what an earlier message filled) and
   `apply_order_status()` (the one place a status becomes an order state change).

**State transitions live on the models** (`Order.mark_paid/deliver/release/refresh_download_tokens`),
each `@atomic`. Change those instead of touching row state in a view; they raise `ValueError` on a
violation, which views turn into 400/409.

**Who counts as a buyer is defined once**: `CustomerQuerySet.buyers()` / `leads()` /
`subscribed_buyers()`, keyed off `paid_at__isnull=False` through `Exists()` rather than a join, so
it never disturbs counts a caller annotates. The admin filter and the broadcast recipient list both
go through it. `OrderQuerySet.paid()` is the same rule from the order side, and is what the
purchases page and `send-links` filter on. **Never filter by `status` instead**: `STATUS_MAP` turns
`cancelled duplicate` back into `PENDING`, so a status filter hides orders that were paid and
delivered.

## Statistics (`/admin/stats/`)

One admin page: how much did I make, what sells, what does Plisio keep. USD, **UTC** days
(`TIME_ZONE = "UTC"`), and the page says so.

The numbers are plain functions over a half-open period in `sales/statistics.py` - no HTTP, no
templates, held by `sales/tests_statistics.py`; `sales/admin_views.py` only parses the period and
renders. Two definitions are fixed there and nowhere else: money is the **`OrderItem` snapshot**
(editing a catalogue price cannot rewrite last month), and a sale is **`Order.paid_at`**.

- **Plisio's commission divides, it does not multiply.** It arrives in the invoice's cryptocurrency
  and `source_rate` says how much of that currency one dollar buys, so the fiat value is
  `commission / source_rate`. On a stablecoin the rate is 1 and both readings agree; on BTC it is
  ~1e-5 and the multiplied figure collapses to zero. An invoice missing either number, or carrying a
  zero rate, is left out rather than counted as free. `completed` and `mismatch` count, a
  `cancelled duplicate` does not.
- **Time to pay is split by the callbacks, not by the transaction.** `time_to_pay` is the whole wait
  (`paid_at - created_at`, median and average); `payment_stages` cuts it into new → pending and
  pending → completed. The middle stamp is the earliest `PaymentCallbackLog` with a
  `pending`/`pending internal` status, because `Transaction` has a single `updated_at` that the paid
  callback overwrites. An order with no pending callback is left out of both legs instead of reading
  as instant, and the page prints the coverage.
- **"All time" starts at the first sale** (`first_sale_at()`); an empty shop falls back to 30 days.
- **A chart point opens the orders paid that day** on the ordinary changelist with
  `paid_at__gte`/`paid_at__lt`. Those lookups are only allowed because `paid_at` is in
  `OrderAdmin.list_filter`, and they are passed as aware datetimes in the shape Django's own date
  filter builds - a bare date arrives naive and warns on every click.
- **`admin.site` is ours.** `INSTALLED_APPS` names `backend.apps.ShopAdminConfig` instead of
  `django.contrib.admin`, and `admin.site` is a lazy proxy onto its `default_site`, so every
  `@admin.register` keeps working. `ShopAdminSite` overrides `get_urls` **and** `get_app_list` -
  without the second the page would only be reachable by typing the URL.
- **Chart.js 4.5.1 is vendored** in `sales/static/sales/` (MIT, one UMD file) - the admin must not
  call a CDN. Its palette comes from the admin's CSS variables (`--link-fg`, `--body-fg`), so the
  theme toggle carries the chart; update it by replacing the file. Data rides in via `json_script`;
  there is no API endpoint. Days with no sales draw no point, and `moving_average` (7-day trailing)
  rides alongside.
- **The CSV is not what the page shows**: the screen is cut to the top ten, the export carries every
  product sold in the period. It starts with a BOM or Excel mangles non-ASCII names.

## Uploads: two roots, one volume

`MEDIA_ROOT` is `backend/products/media/` - previews and slide images, public; nginx serves it from
`location /media/` off the `products` volume (read-only there), and under `DEBUG` Django serves the
same tree.

Paid files live in `PRODUCT_FILES_ROOT` (`backend/products/private/`), **outside MEDIA_ROOT**, on
`catalog/storages.py: ProductFilesStorage`. It has no `base_url`, so `product.file.url` raises
instead of handing out a path, and no nginx location maps onto that directory: the only way to a
product file is `DownloadFileView`, behind a token. Both roots are read from settings on access, so
`TempUploadsMixin` (`backend/testing.py`) can redirect them and a test never writes into the tree.
Replacing an upload deletes the file it replaced (`Product.save`, `ProductImage.save`) and deleting
a row deletes its files (`post_delete`), including on a queryset delete.

## nginx

One domain. `frontend/nginx/site.conf.template` is rendered by nginx's `envsubst` (filter `DOMAIN`)
and holds only `listen` / `server_name` / certificate paths, including **`site-body.conf`** from
inside its `server` block - headers, locations, compression, timeouts. Two plain files beside it:
`00-limits.conf` with the `limit_req` zones, which belong to the `http` context and must be declared
exactly once, and `proxy-backend.conf` with the `proxy_pass` block every backend location includes.
Validate a change with `make nginx-check`. `frontend/nginx/ssl/` is a tracked empty directory -
`frontend/Dockerfile` copies it, and a fresh checkout cannot build the image without it.

## Broadcasts (`mailing`)

A `Broadcast` is written in the admin (TinyMCE, one editor per language), saved as a **draft**,
test-mailed to `test_email` (one message per language), then **queued**; cron runs `broadcast` every
15 minutes over `Customer.objects.subscribed_buyers()`.

- **The sender is resumable, not restartable.** `BroadcastDelivery` is one row per
  `(broadcast, customer)` with a `UniqueConstraint`. The command first writes `PENDING` rows for
  everyone (`bulk_create(ignore_conflicts=True)`), then walks `PENDING` + `FAILED`, closing each row
  as its message goes out. A crash costs the one message in flight, a repeated run cannot mail
  anyone twice, and re-queueing retries only failures. `Broadcast` has **no counters** - they are
  annotations in `BroadcastAdmin.get_queryset`.
- **Bilingual from one row.** `mailing/translation.py` puts `subject` and `body` through
  modeltranslation and `build_broadcast_email` reads them inside `translation.override(...)`; an
  empty language falls back to the site default. `BroadcastAdminForm.widgets` is keyed by the plain
  `body` - `TranslationAdmin` copies that widget onto `body_en` / `body_ru`, which is the only
  reason both get an editor.
- **Opting out is `Customer.is_subscribed`**, not a suppression table. The footer link goes to the
  SPA route `/unsubscribe/:token` (`django.core.signing`, salt `broadcast-unsubscribe`, language in
  `?lang=`). The page **asks first**: `GET /api/unsubscribe/<token>/` only reads the token and
  answers `{email, is_subscribed}`, and `POST` on the same URL is the only thing that unsubscribes.
  Keep that split - Gmail and Outlook pre-fetch every URL in a message.

## Email delivery

Mail goes wherever `EMAIL_URL` points (SMTP in production). A **backup** DKIM-signing relay is the
`mail` service in `docker-compose.yaml` (`boky/postfix`), behind a compose **profile** so it does
not start by default: `docker compose --profile mail up -d mail`, then `EMAIL_URL=smtp://mail:587`
and restart the backend. boky listens on **587**; delivery to recipients' MX on 25 is Postfix's own
job. DKIM: the selector is `mail` (boky default) and must match the published
`mail._domainkey.<domain>` record; the private key is mounted read-only at
`/etc/opendkim/keys/<domain>.private` from `secrets/opendkim/` (gitignored). The compose file
carries `example.com` placeholders. **Never regenerate a key that is already published** (do not set
`DKIM_AUTOGENERATE`), and never commit or print it.

## i18n

Both ends are bilingual (en/ru). Model content uses **django-modeltranslation**
(`catalog/translation.py`, `mailing/translation.py`). The catalog API has no `?lang=`: every payload
carries both languages (`name_en` / `name_ru`), so the SPA switches without a refetch and every
visitor gets an identical payload. **The interface language lives in the URL path prefix**
(`i18n_patterns` on the server, the `/:lang` route param in vue-router) - there is no `?lang=`
anywhere anymore. The frontend uses vue-i18n (`src/i18n/locales/`) and the router guard sets the
locale from the path.

E-mail copy is gettext in `backend/locale/ru/LC_MESSAGES/django.po`; msgids are the English text, so
there is no `en` catalogue. `makemessages` also picks up model verbose names and choice labels -
leave those empty, they are admin-only. `.mo` files are untracked build output: `startup.sh` and the
test targets compile them, both with `--ignore=.venv`, because the venv lives inside the project
directory here.

## Frontend

Vue 3 + Pinia (with `pinia-plugin-persistedstate` for the cart), Vue Router, axios and `glightbox`
for the product gallery - the whole dependency list, installed by `npm ci` from the tracked
`package-lock.json`. Pinia is registered **before** the router in `src/main.js`: vue-router starts
its first navigation from `install()`, and the `/` redirect reads the language store. Stores:
`cart`, `catalog`, `content`, `order`, `settings` (language only). Requests go through `src/api/`
(`catalog.js`, `content.js`, `order.js`) - a view never reaches for the axios client itself.

**The shell.** `make spa` builds `frontend/index.html` into `storefront/shell.html`: vite injects
the `{{ storefront_meta }}` / `{{ LANGUAGE_CODE }}` hooks at build time and moves the file into the
backend templates, with hashed assets under `static/storefront/spa/`. vue-router mirrors
`backend/backend/urlspace.py` - keep the two in sync when a route is added, and land a change in the
bot template and the Vue view together. If `shell.html` is missing, the catalog views serve a person
the bot page and log a warning: the site degrades but lives.

Two pieces of markup are literally shared: `storefront/_bgs_decor.html` and
`components/storefront/PageDecor.vue` carry the same decor/wave block, and **the dark strip must
stay on every page** - the header is `position: fixed`, so without it the content slides underneath.
`App.vue` draws it once and puts the route's **named `hero` view** inside it: a listing route
declares `components: {default: Catalog, hero: HomeHero}` and every other route declares none - the
same split as `storefront/base.html` holding the strip and `storefront/catalog.html` filling its
`hero` block.

**What crawlers read** sits beside the storefront views and outside `i18n_patterns`:
`storefront/sitemaps.py` (`/sitemap.xml`, an index over `/sitemap-<section>.xml`) and
`storefront/templates/storefront/robots.txt`. The map is `django.contrib.sitemaps` with
`i18n`/`alternates`/`x_default`, so one entry carries both languages and its hreflang set; sections
list only what the storefront lists (`active()`, `non_empty()`, `with_product_counts()`), so the
`noindex` service pages are absent by construction. `x-default` is the address without a language
prefix - the same string `seo.x_default` puts in `<head>`. robots.txt is rendered by Django so its
`Sitemap:` line is built from `django_site` + `SITE_SCHEME` like every other absolute link.

**Pagination.** `Catalog.vue` reads `?page=` and asks the API for exactly that page; **the number of
pages comes from the server** (`total_pages`, `catalog.views.CatalogPagination`), so the SPA keeps no
copy of the page size to divide by. `components/storefront/Pagination.vue` is a port of Django's
`Paginator.get_elided_page_range(on_each_side=1, on_ends=1)`, the same window `storefront/views.py`
asks for, so both presentations print the same numbers at the same addresses. Anything that is not a
whole number above 1 (`?page=abc`, `-3`, `2.5`) means page 1; a `?page=` past the end lands on the
last real page (the API answers 404 both for an overshoot and for an unknown slug, so asking for
page 1 tells the two apart). Changing page - and only that, so a search does not pull the field it
is typed in under the header - scrolls the first card under the fixed header with
`behavior: "instant"`, because `style.css` sets `scroll-behavior: smooth` on `<html>` and an
animated scroll lands late and dies on the reader's first wheel. Picture boxes reserve their height
(`.banner__media`, the `width`/`height` on the hero image).

**The banner is ours, not the mockup's slider.** `components/storefront/Banner.vue` and the
`.banner--static` block in `storefront/catalog.html` render the same box, dressed by `.banner` in
`shop.css`: one purple panel with a real `border-radius`, slides stacked in one grid cell so the
height is the tallest slide's, a crossfade, arrows, dots, swipe and the arrow keys. Autoplay stops
on hover, on focus, on a hidden tab and under `prefers-reduced-motion`; the hidden slide is `inert`.

**Search is the server's** (`?q=` on `/api/catalog/products/`, `ProductQuerySet.search` over
`name_en`/`name_ru`, capped at `MAX_SEARCH_LENGTH`). It lives in `?q=` in the storefront URL too, so
a reload or a shared link keeps it, and every facet link carries it over. A new query starts at page 1.

**Everything the API hands over is a model, not a payload** (`src/models/`). `Localized` turns the
`name_en`/`name_ru` pairs into one property read against the active locale with an English fallback
- the rule modeltranslation applies on the server - and `Product`, `Country`, `DocumentType`,
`Page`, `Slide`, `SiteSettings` extend it. `Product` also owns `priceLabel` (USD, two decimals) and
`route(lang)`. The api modules construct them, so a view never sees raw JSON. One catch:
`localStorage` holds JSON, so `stores/cart.js` rebuilds its lines with `new Product(...)` in the
persist plugin's `afterHydrate` - without it `item.name` is undefined until the first `refresh()`.

**The cart is a set of products.** `Cart.vue` calls `cart.refresh()` on open, which asks
`GET /api/cart/items/?ids=` what those ids are now: localStorage may be months old and the invoice
is written from the catalog, so a product off the shelf leaves the cart here rather than failing at
checkout, and a moved price is corrected before the customer sees the total.

**One component takes money: `components/storefront/CheckoutModal.vue`** - the cart's pay button and
the "buy now" of every card and product page (the express path buys one template without touching
the cart). The markup is the design's, but remodal is not carried over, so Escape, the backdrop, the
scroll lock and the focus are the component's own. It closes **only after the invoice exists**; a
failure prints inside the modal, and the cart is cleared only on success.

Two routes share the "my purchases" name and are not the same page: `/purchases`
(`views/MyPurchases.vue`) is the e-mail form you land on when the link is lost, `/purchases/:token`
(`views/Purchases.vue`) is the page the mail links to, where prices come from the order snapshot.
The token in the URL is the whole authentication, so a 404 from any of its calls means "the link is
spent" and the page says so instead of retrying. `/unsubscribe/:token` is the third token page.

**Anything that fetches shows which of "loading", "failed" and "empty" it is in** - an empty result
and a dead backend must never look alike. **A form that posts must show the failure**:
`src/api/errors.js: errorMessageKey(error, overrides)` maps a status onto an i18n key once and a
form passes in what a status means in its own context (`404` on send-links is "no purchases on this
address", `502` at checkout is "the gateway refused"). Never `console.error` and move on, and never
close the payment modal before the request comes back. Plisio's `detail` stays out of the interface
(English-only and technical); its `provider_code` goes to the console.

## Design

The design is a static build in **`design/`** (`index.html`, `product.html`, `style.css`, `app.js`,
`img/`, `fonts/`) - the source of truth for the look. Its `style.css` lives at
`backend/storefront/static/storefront/css/` and dresses both presentations, so a Vue component
reuses the design's class names rather than inventing its own, and **`style.css` stays a copy of the
mockup** - our own additions go to `storefront/css/shop.css`, which both presentations link:
`.btn-ghost` / `.btn-solid` on top of the design's `.btn` (plus `.btn-ghost--light` for the purple
slide), the `.pagination` block and `.banner`. The design's only filled button is the pink-blue
gradient (`.btn-grade` / `.button`), which stays where the designer put it - the hero and the
product cards.

The jQuery plugins the mockup ships with (`remodal`, `swiper-bundle`, jQuery) are **not** carried
over: the modal is our component, the banner is ours, and the filters/burger/search from `app.js`
are reactive state. `glightbox` stays, as an npm package, for the product gallery. The header is
`position: fixed` over a light page, so `composables/useHeaderScroll.js` ports the design's scroll
handler: `header-scrolled` paints it black past the first pixel and `out` slides it away while the
reader moves down (never while the mobile menu is open).
`design/Инструкция по обновлению.txt` documents the year badge and the filter block the designer
added last - follow it when the markup differs from an older screenshot.

## Open items

1. **Domain** - `psd-shop.com` or `psd-templates.store`. Needed for the launch.
2. **Copy** is placeholder text until the owner signs off on the design.
3. **The payment-system logos** are out of the footer; what fills the gap is a design question.
4. **The owner's list of design corrections** is a separate pass.
5. **The `?year=` filter is not implemented.** The mockup has a year dropdown
   (`design/index.html`, `filter-products`); the code has no `?year=` in `catalog/views.py`, no
   dropdown in `Catalog.vue` and nothing on the bot pages. Year *ordering* was rejected on purpose,
   the filter was not - it has to land in both presentations plus a canonical without the parameter.
6. **Tokens appear in access logs** (`/purchases/<token>/`, `/api/files/<uuid>/`): strip them from
   `access_log_format` or restrict access to the logs - the owner's call, see the journal.
7. **No 2FA on the admin**, only a rate limit. Acceptable for a single owner; a second staff member
   means `django-otp`.
8. **Slide images are not recompressed** on upload, unlike product previews (which go through
   Pillow). Only staff can upload, but the policy is worth remembering.

## Production launch

In order, on the server: domain and certificates into `frontend/nginx/ssl/` → filled `.env`
(`DOMAIN`, `ALLOWED_HOSTS`, `CORS`/`CSRF`, `PLISIO_SECRET_KEY`, `EMAIL_URL`) → `make up` →
`make migrate` → `make superuser` → point the `django_site` row at the real domain → Plisio webhook
(optional in the dashboard, since `callback_url` with `?json=true` ships with every invoice; if you
do set it: `https://<domain>/api/order/status?json=true`) → DKIM (the `mail` profile, key in
`secrets/`) → check `make nginx-check`, `/sitemap.xml`, `/robots.txt` and the backups.
