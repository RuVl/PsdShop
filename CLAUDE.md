# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

PsdShop is a digital-goods storefront: customers buy template documents (PSD/PDF), pay via
**Plisio** (crypto invoices), and receive a time-limited e-mailed link to a purchases page they
download the files from. Vue 3 SPA frontend + Django REST Framework backend + PostgreSQL, all
orchestrated with Docker Compose behind nginx, on a single domain.

Domain vocabulary is in [`CONTEXT.md`](./CONTEXT.md), decisions in [`docs/adr/`](./docs/adr/), and
the running log of smaller ones - what was solved, how, and what it costs - is
[`docs/journal.md`](./docs/journal.md); add an entry in the same commit that closes a fork.

### Status: the rework is done, the shop is not launched

The tree started as a fork of **Verdoc**, a storefront for one-of-a-kind files: the infrastructure,
payment, delivery, broadcasts and admin statistics were kept, while the catalog, the fulfillment
model, the currency and the whole design were replaced. All five stages of
[`docs/plan.md`](./docs/plan.md) are shipped - read it before changing models, it still holds the
target schema and the open questions.

What that leaves: the design corrections the owner is collecting (a separate pass, by their list),
and the production launch itself - domain, certificates, the `django_site` row, DKIM, cron and
backups - which was never part of this rework.

The decisions the code rests on:

| Decision | ADR |
|---|---|
| A product is a template sold any number of times - no `StockItem`, no `Allocation`, no reservation | [0001](./docs/adr/0001-unlimited-copies-no-reservation.md) |
| Catalog is country x document type x year, with a gallery and a product page | [0008](./docs/adr/0008-catalog-country-type-year.md) |
| Prices are USD only - `djmoney` and exchange rates are gone | [0006](./docs/adr/0006-single-currency-usd.md) |
| Dynamic rendering: every storefront URL answers twice from one view - search bots get the full Django-rendered page, people get the SPA shell (the vite-built `index.html` with this page's meta injected) and the Vue SPA takes over. ADR-0007 and ADR-0009 are superseded by it. | [0010](./docs/adr/0010-dynamic-rendering.md) |
| Buying is one modal: the cart, or one template bought straight off a card ("buy now"), and the mail carries one link to the purchases page | [0002](./docs/adr/0002-customer-and-purchases-page.md) |

The Verdoc component set is gone from the frontend - every view is drawn with the design's own
classes.

Everything below describes the code **as it is now** unless a line says otherwise.

## Commands - use the Makefile

**Prefer `make` targets over hand-rolled commands.** The root `Makefile` wraps everything in a
cross-platform way (recipes are just `cd` + `uv` / `uvx` / `docker compose` / `npm`; file ops go
through `uv run --no-project python`). Run `make help` for the full list. The project is
**docker-first**: `manage.py` and `psql` targets `exec` into the running stack
(`docker-compose.yaml` builds `frontend-nginx` on 80/443, `backend` gunicorn on 8000, `postgres`),
so bring it up first.

```bash
make init          # full bootstrap: check-deps → env → install → pre-commit → dev-infra → dev-migrate (NOT `up`)
make env           # create .env from *.dist (backend / frontend / postgres / backend/dev.env) where missing
make install       # backend + frontend (make install-backend / make install-frontend for one)

make up            # full stack in docker (build + run)
make down          # stop; make ps / make logs[-backend|-db|-nginx]

# Local development - backend & frontend on the host, only postgres in docker
# (avoids the rootless-podman 80/443 problem; no nginx). See "Local development" below.
make dev-infra     # postgres only (docker-compose.dev.yaml), published to localhost:5432
make dev-migrate   # migrate with the host backend against the dev db
make dev-backend   # runserver 0.0.0.0:8000 on the host
make dev-frontend  # vite dev server: open http://localhost:5173/ (proxies /static and /media to :8000)
make spa           # production SPA build: hashed assets into backend static, shell.html into templates
make dev-superuser / make dev-infra-down
make dev-reset     # recreate the dev-postgres container (keeps the psdshop_postgres volume/data)
make dev-nuke      # DROP the volume and bring an empty db up - needed after migrations are regenerated

# Any manage.py command - generic escape hatch (custom or built-in). Pass the args via c=.
make manage c="showmigrations"            # inside the backend container
make dev-manage c="seed_testdata --flush" # on the host against the dev db (auto-brings up dev-infra)
# The named targets below are just shortcuts for common commands - use `manage`/`dev-manage` for the rest.

# Django (run inside the backend container) - apps are: catalog, customer, mailing, sales
make migrate       # make manage c=showmigrations to inspect first
make makemigrations m="catalog customer mailing sales"
make superuser
make broadcast     # send QUEUED broadcasts (also cron, every 15 min); c="--id N --dry-run --test"
make prune-callbacks c="--dry-run"  # drop raw Plisio callbacks past the retention window (also cron, weekly)

# Translations (gettext; the e-mail copy lives in backend/locale/ru/LC_MESSAGES/django.po)
make messages / make compilemessages          # in the container
make dev-messages / make dev-compilemessages  # on the host
# .mo files are build output and untracked: startup.sh compiles them, and the test targets
# depend on compilemessages so a run never asserts against a stale catalogue.

# Tests
make test          # in the container; make dev-test on the host (t="sales" or t="sales.tests.DeliverTests")

# Seed test data for manual UI testing (catalog `seed_testdata` command):
#   make dev-manage c="seed_testdata --flush"   (host/dev)   or   make manage c="seed_testdata --flush" (container)
# Countries x document types x years with generated preview images, plus the layout edge cases
# (very long name, extreme prices, no year, hidden) and the content rows the storefront chrome
# needs: pages (home/info/contacts), welcome slides and the settings singleton. --flush wipes
# the catalog and the content pages/slides first.

# DB
make db-dump [DUMP=postgres/backups/dump.sql] / make db-restore DUMP=… / make psql

# nginx
make nginx-check   # envsubst + `nginx -t` in a stock nginx container (no image build, no certs)

# Quality
make lint          # ruff check + format --check (no edits)
make format        # ruff check --fix + ruff format
make pre-commit-install / make pre-commit
```

**Tooling:** dependencies and venvs are managed with **uv** - `backend/pyproject.toml` (+ `uv.lock`)
is the source of truth (no `requirements.txt`), and the backend image installs via `uv sync`.
Lint/format is **`uvx ruff@0.15.12`**; ruff config lives in `backend/pyproject.toml` -
**line-length 120**, `target-version = "py313"`, rule set `E, F, I, UP, B, W, C4, SIM`. pre-commit
lives at the **repo root** (`.pre-commit-config.yaml`, run via `uvx pre-commit`): ruff-check
`--fix` + ruff-format; mypy is commented out. Tests live in `catalog/tests.py`,
`content/tests.py`, `customer/tests.py`, `mailing/tests.py`, `sales/tests.py`,
`sales/tests_statistics.py` and `storefront/tests.py` (django `TestCase`, run with `make test` /
`make dev-test`) and cover the checkout/callback/delivery invariants plus the UA split - keep
them green. **The test targets name the apps explicitly**, so a new app must be added to both
`test` and `dev-test` in the Makefile or its tests silently never run. `sales/tests_statistics.py` is
deliberately separate: it holds the arithmetic behind the dashboard, not the fulfillment
invariants. Target runtime is **Python 3.13**.

## Environment & configuration

- Each service reads its own `.env` (copy from the `.env.dist` next to it): `backend/`,
  `frontend/`, `postgres/`. The backend also loads `postgres/.env` for the DB connection.
- **Local development** overrides live in `backend/dev.env` (copy from `backend/dev.env.dist`).
  It's layered on top of `backend/.env` when running the host backend
  (`uv run --env-file .env --env-file dev.env`), because `settings.py` reads only `os.environ`
  (no `read_env()`). It points `DATABASE_URL` at `localhost:5432` and sets `EMAIL_URL=consolemail://`.
  Its DB user/password/name **must match `postgres/.env`**.
- The frontend has the same idea via Vite's mode files: `frontend/.env.development` (copy from
  `frontend/.env.development.dist`) is layered on top of `frontend/.env` **only for `npm run dev`**
  (mode `development`). It points `VITE_API_URL` at the host backend
  (`http://localhost:8000/api`) - a knob that exists for the dev server only. `make env` creates
  it; the real file is gitignored (the `.env.development.dist` template stays tracked).
  `frontend/.env` carries `DOMAIN` alone, for nginx's `envsubst`.
- Settings use `django-environ`. Key vars: `DATABASE_URL`, `EMAIL_URL`, `PLISIO_SECRET_KEY`,
  `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS`.
- `vite.config.js` compiles the API base into the constant `__API_URL__`: `VITE_API_URL` in dev,
  and the same-origin `/api` in a production build, which is therefore not configurable - one
  domain, one origin. The same file keeps `base` out of the dev server: the built SPA lives under
  `/static/storefront/spa/`, the dev server answers from the root. The axios client in
  `src/api/index.js` uses Django's CSRF cookie/header.
- After first deploy, update the `django_site` row's domain to match your host - every absolute URL
  the backend hands out (download links, the purchases-page link in e-mails) is built from it plus
  `SITE_SCHEME` (`https` by default, set `SITE_SCHEME=http` in `dev.env` and point the site row at
  `localhost:8000` if you want those links to open locally). One function does that join:
  `backend/sites.py: absolute_url(path, request)` - build links through it rather than gluing the
  scheme and domain again.
- `SITE_ID = 1` is set **only under `DEBUG`**, because a local run has no `django_site` row
  matching its host.
- `EMAIL_URL`'s **scheme picks the backend**: `smtp://` in production, `consolemail://` in dev
  prints the message to the backend console. Do not pass `backend=` to `env.email()` - it pins SMTP
  and makes the scheme a no-op.
- The API answers **JSON only**; DRF's browsable renderer - a writable HTML form on every endpoint -
  is added back under `DEBUG` alone (`REST_FRAMEWORK` in `settings.py`).

## Architecture

### Order / fulfillment flow (the core domain)

Backend apps: `catalog` (products), `customer` (buyers and their access), `sales` (checkout,
payment, delivery), `mailing` (broadcasts).

1. **Catalog** - a flat `Product` carrying its own file plus `Country`, `DocumentType`, `year` and
   `ProductImage`: no stock, no scarcity, nothing to reserve
   ([ADR-0001](./docs/adr/0001-unlimited-copies-no-reservation.md),
   [ADR-0008](./docs/adr/0008-catalog-country-type-year.md)). A product is taken off the shelf with
   `is_active=False`, never deleted - `OrderItem.product` is `PROTECT`.
2. **Checkout** - `POST /api/order/` (`OrderCreateView` + `OrderSerializer`), payload
   `{email, language, products: [id]}`: a list of ids, because an order holds a product at most
   once and there are no quantities. Gets/creates the `Customer`, computes `total_price` **from the
   catalog** (never from the client), creates `Order` + `OrderItem`s **with a price snapshot**
   (`product_name`, `unit_price`). Then requests a Plisio invoice; the
   URL is stored on `Order.invoice_url`, and if the request fails the order is deleted - the
   endpoint answers **502** with `{detail, code: "invoice_failed", provider_code}`, passing Plisio's
   own message on instead of a blanket "Error creating invoice".
3. **Payment callback** - `POST /api/order/status` (`PlisioCallbackView`). **The invoice request
   sends its own `callback_url`, ending in `?json=true`** (`sales/views.py: callback_url()`): that
   parameter is what makes Plisio post JSON and sign the JSON body. Without it Plisio posts a form
   and signs PHP's `serialize()` of the sorted array - a different algorithm, so every payment
   would be refused at the door. Never drop it, and do not rely on the dashboard setting instead.
   The view verifies `verify_hash` (HMAC-SHA1 over the body, both as received and key-sorted -
   Plisio's own SDK does not sort, and each candidate is an HMAC with our key) against
   `PLISIO_SECRET_KEY`, stores the raw payload in `PaymentCallbackLog`
   **before** the atomic block, then upserts the `Transaction` **by `txn_id`** (a currency switch
   mints a new invoice for the same order). On PAID/OVERPAID: `order.mark_paid()` stamps `paid_at`
   once and only that first call sends the e-mail; `order.deliver()` hands the files over. On
   EXPIRED/CANCELLED there is nothing to undo - nothing was ever reserved. A duplicate callback is
   a 200 no-op.
4. **Delivery** - two independent tokens, both with a TTL
   ([ADR-0002](./docs/adr/0002-customer-and-purchases-page.md)). `Customer.access_token`
   (`PURCHASES_PAGE_TTL` = 24h) opens the **purchases page**, and the delivery e-mail carries that
   one link and nothing else (`sales/utils.send_purchases_link`). The per-file token
   (`DOWNLOAD_TTL` = 24h, on `OrderItem`) opens one file:
   `GET /api/files/<uuid>/`. The page is `GET /api/purchases/<customer_token>/`, with
   `POST .../refresh/<id>/` and `POST .../refresh-all/` re-issuing file tokens. An unknown,
   malformed or expired page token all answer the **same 404** - the API must not confirm that a
   token exists. `POST /api/send-links/` is the recovery path: it tops up anything undelivered,
   **rotates** `access_token` (this is how an old page link is revoked) and mails the new one; file
   tokens are deliberately left alone so links the customer already shared keep working.
   - **Every link a mail carries is built with `reverse()` under
     `translation.override(customer.language)`** (`Customer.get_purchases_url`,
     `mailing.services.make_unsubscribe_url`), then absolutised through `backend/sites.py`. The
     storefront routes live under `i18n_patterns`, so a path glued together by hand misses the
     language prefix and 404s - and the browser that opens the link is not the one the mail was
     sent from (ADR-0004).
   - `serve_order_item()` in `sales/views.py` is the single point a file is streamed from, and the
     only place a download writes to the database: it records the download **after** the file is
     open, so a refused link never counts. That is an `UPDATE` with `F()`, not a `save()`, so two
     parallel downloads add up to two. The counter answers "did the **customer** take the file", so
     `DownloadFileView` skips it for a staff session. The carve-out is on the session, not on the
     link, so a staff member following a real customer link is not counted either.
   - A dead SMTP never costs the customer their order: the callback logs and still answers 200 (a
     Plisio retry would send nothing, `paid_at` is stamped), and `send-links` answers 502 so the
     form can say to try again.
5. **Plisio only ever tells us about an invoice once, in the callback.** Its `operations/<id>`
   endpoint answers with nine fields unless the account has White Label enabled, and none of
   `amount`, `source_rate` or `commission`, so there is nothing to reconcile money against.
   `sales/plisio.py` therefore holds only the translation of a callback payload
   (`callback_to_fields()`, the single place a payload field becomes a `Transaction` column - a key
   the payload omits is left out entirely, so a repeat cannot blank what an earlier message filled)
   and `apply_order_status()`, the single place an invoice status turns into an order state change.

**Who counts as a buyer is defined once.** `CustomerQuerySet.buyers()` / `leads()` /
`subscribed_buyers()` in `customer/models.py`, keyed off `paid_at__isnull=False` - the stamp
`Order.mark_paid()` writes exactly once - via `Exists()` rather than a join, so it never disturbs
counts a caller annotates. The admin filter and the broadcast recipient list both go through it; do
not write a second definition. `OrderQuerySet.paid()` is the same rule seen from the order side and
is what the purchases page and `send-links` filter on. **Never filter by `status` instead**:
`STATUS_MAP` turns Plisio's `cancelled duplicate` - the callback about the invoice a customer
walked away from when switching coin - back into `PENDING`, so a status filter hides orders that
were paid and delivered.

**Checkout is rate limited at the edge** ([ADR-0005](./docs/adr/0005-checkout-rate-limits.md)):
`limit_req` in nginx on `/api/order/`, `/api/send-links/` and `/admin/login/` (the Plisio callback
stays unlimited - a retry we refuse is a payment we never hear about),
`MAX_ORDER_ITEMS`, and an MX check on the e-mail domain (`customer/validators.py`, fails open,
`VALIDATE_EMAIL_MX`). A repeated checkout of the same cart is sent back to the live invoice
(`Order.objects.reusable()`). A `Customer` row is created at checkout, before payment, so abandoned
checkouts leave leads behind - they are kept as funnel data, and the admin list filters down to
paying customers by default.

**State transitions live on the models** (`Order.mark_paid/deliver/release/refresh_download_tokens`),
each wrapped in `@atomic`; change those instead of touching row state in a view. They raise
`ValueError` on a violation, which views turn into 400/409.

### Statistics (`/admin/stats/`)

One page in the admin answering "how much did I make", "what sells" and "what does Plisio keep".
Everything in USD, days are **UTC** days (`TIME_ZONE = "UTC"`), and the page says so out loud.

- **The numbers live in `sales/statistics.py`** - plain functions over a half-open period, no HTTP
  and no templates, held by `sales/tests_statistics.py`. Two definitions are fixed there and
  nowhere else: money is the **`OrderItem` price snapshot** (editing a catalogue price cannot
  rewrite last month), and a sale is **`Order.paid_at`** - the same stamp
  `CustomerQuerySet.buyers()` keys off, PAID and OVERPAID alike. `sales/admin_views.py` only parses
  the period and renders.
- **Plisio's commission needs converting, and it divides.** It arrives in the invoice's
  cryptocurrency, and `source_rate` says how much of that currency one dollar buys - so the fiat
  value is `commission / source_rate`. Multiplying was the bug this line replaced: on a stablecoin
  the rate is 1 and both readings agree, on BTC it is about 1e-5 and the whole figure collapses to
  zero. An invoice missing either number, or carrying a zero rate, is left out rather than counted
  as free. `completed` and `mismatch` both count; a currency switch leaves a `cancelled duplicate`
  behind that does not.
- **Time to pay is split by the callbacks, not by the transaction.** `statistics.time_to_pay` is
  the whole wait (`paid_at - created_at`, median and average); `statistics.payment_stages` cuts it
  into new → pending and pending → completed. The middle stamp is the earliest
  `PaymentCallbackLog` carrying a `pending`/`pending internal` status - `Transaction` has a single
  `updated_at` that the paid callback overwrites - and the end is `paid_at`, so the two legs sum to
  the total. An order with no pending callback is left out of both legs instead of reading as
  instant; the page prints how many orders the figures cover.
- **"All time" starts at the first sale** (`statistics.first_sale_at()`), not at a fixed date. An
  empty shop falls back to the default 30 days.
- **A point on the revenue chart opens the orders paid that day**, on the ordinary changelist with
  `paid_at__gte`/`paid_at__lt`. Those lookups are only allowed because `paid_at` is in
  `OrderAdmin.list_filter`, and they are passed as aware datetimes in the shape Django's own date
  filter builds - a bare date arrives naive and warns on every click.
- **`admin.site` is ours.** `INSTALLED_APPS` names `backend.apps.ShopAdminConfig` instead of
  `django.contrib.admin`; `admin.site` is a lazy proxy onto the app config's `default_site`, so
  every `@admin.register` keeps working untouched. `ShopAdminSite` overrides `get_urls` **and**
  `get_app_list` - the sidebar and the dashboard are built from registered models alone, so without
  the second one the page would be reachable only by typing the URL.
- **Chart.js 4.5.1 is vendored** in `sales/static/sales/` (MIT, one UMD file) - the admin must not
  call a CDN. Its palette is read from the admin's CSS variables (`--link-fg` for the line,
  `--body-fg` for the dashed trend), so the theme toggle carries the chart with it; update it by
  replacing the file. Data rides in via `json_script`, there is no API endpoint. Days with no sales
  draw no point, and a 7-day trailing average (`statistics.moving_average`) rides alongside.
- **The CSV is not what the page shows.** A screen is cut to the top ten; the export carries every
  product sold in the period. It starts with a BOM or Excel mangles non-ASCII product names.

### Uploads: two roots, one volume

`MEDIA_ROOT` is `backend/products/media/` - product previews and slide images, public. nginx serves
them from `location /media/` off the `products` volume (mounted read-only there), and under `DEBUG`
Django serves the same tree itself.

The paid files live in `PRODUCT_FILES_ROOT` (`backend/products/private/`), **outside MEDIA_ROOT**,
on `catalog/storages.py: ProductFilesStorage`. It has no `base_url`, so `product.file.url` raises
instead of handing out a path, and no nginx location maps onto that directory: the only way to a
product file is `DownloadFileView`, behind a token. Both roots are read from settings on access, so
`TempUploadsMixin` (`backend/testing.py`) can redirect them - a test never writes into the tree.

Replacing an upload deletes the file it replaced (`Product.save`, `ProductImage.save`), and deleting
a row deletes its files (`post_delete`), including on a queryset delete.

### nginx

One domain. `frontend/nginx/site.conf.template` is rendered by nginx's `envsubst` (filter
`DOMAIN`); it holds only `listen` / `server_name` / the certificate paths and includes
**`site-body.conf`** from inside its `server` block - headers, locations, compression, timeouts.
Two more plain (non-template) files: `00-limits.conf` holds the `limit_req` zones, which belong to
the `http` context and must be declared exactly once, and `proxy-backend.conf` holds the
`proxy_pass` block that every backend location includes. Validate a config change with
**`make nginx-check`** - it renders the template with `envsubst` and runs `nginx -t` in a stock
nginx container with the config mounted, so it needs neither our image nor real certificates.
`frontend/nginx/ssl/` is a tracked empty directory: `frontend/Dockerfile` copies it, and without it
a fresh checkout cannot build the nginx image.

### Broadcasts (`mailing`)

A `Broadcast` is written in the admin (TinyMCE, one editor per language), saved as a **draft**,
test-mailed to `test_email` (one message per language), then **queued**; cron runs `broadcast`
every 15 min. Recipients are `Customer.objects.subscribed_buyers()`.

- **The sender is resumable, not restartable.** `BroadcastDelivery` is one row per
  `(broadcast, customer)` with a `UniqueConstraint`. The command first writes `PENDING` rows for
  everyone (`bulk_create(ignore_conflicts=True)`), then walks `PENDING` + `FAILED`, closing each row
  as its message goes out. So a crash costs the one message in flight, a repeated run cannot mail
  anyone twice, and re-queueing retries only what failed. `Broadcast` has **no counters** - they are
  annotations over the deliveries in `BroadcastAdmin.get_queryset`.
- **Bilingual from one row.** `mailing/translation.py` puts `subject` and `body` through
  modeltranslation, and `build_broadcast_email` reads them inside
  `translation.override(customer.language)`. A language left empty falls back to the site default.
  `BroadcastAdminForm.widgets` is keyed by the plain `body` - `TranslationAdmin` copies that widget
  onto `body_en` / `body_ru`, which is the only reason both get an editor.
- **Opting out is `Customer.is_subscribed`**, not a suppression table. The link in the footer goes
  to the SPA route `/unsubscribe/:token` (signed with `django.core.signing`, salt
  `broadcast-unsubscribe`, language in `?lang=`). The page **asks first**:
  `GET /api/unsubscribe/<token>/` only reads the token and answers `{email, is_subscribed}`, and
  `POST` on the same URL is the only thing that opts out. Keep that split - Gmail and Outlook
  pre-fetch every URL in a message, and a customer who opens the link out of curiosity should not
  lose the list either.

### Email delivery

Download links are e-mailed via whatever `EMAIL_URL` points to (SMTP in production). A **backup**
DKIM-signing relay is available as the `mail` service in `docker-compose.yaml`, on the ready-made
`boky/postfix` image, behind a compose **profile** so it does not start by default:

- Start it only when needed: `docker compose --profile mail up -d mail`, then set
  `EMAIL_URL=smtp://mail:587` in `backend/.env` and restart the backend. boky listens on **587**
  (submission); outbound to recipients' MX on 25 is handled by Postfix itself.
- DKIM: the selector is `mail` (boky default) and it must match the published
  `mail._domainkey.<domain>` DNS record. The private key is mounted read-only at
  `/etc/opendkim/keys/<domain>.private` from `secrets/opendkim/` (gitignored). The compose file
  carries `example.com` placeholders - replace them with the real sending domain. **Never
  regenerate a key that is already published** (do not set `DKIM_AUTOGENERATE`), and never commit
  or print it.

### i18n

Both ends are bilingual (en/ru). Backend uses **django-modeltranslation** for model content -
translated fields are declared in `catalog/translation.py` and `mailing/translation.py`
(`Broadcast.subject`, `Broadcast.body`). The catalog API has no `?lang=`: every payload carries
both languages (`name_en` / `name_ru`), so the SPA switches without a refetch and every visitor
gets an identical payload. **The interface language lives in the URL path prefix** (`/en/`,
`/ru/`, `i18n_patterns` on the server, the `/:lang` route param in vue-router) - there is no
`?lang=` anywhere anymore. Frontend uses vue-i18n (`src/i18n/locales/`); the router guard sets
the locale from the path.

**E-mail copy is gettext, and the language comes from `Customer.language`**
([ADR-0004](./docs/adr/0004-email-follows-the-customers-language.md)). It cannot come from the
request: the delivery mail is sent from the Plisio webhook, where the customer's browser is gone.
The storefront posts `language` with the checkout and the send-links form;
`sales/utils.send_purchases_link` and `mailing/services.build_broadcast_email` both wrap themselves
in `translation.override(customer.language)`. Strings live in
`backend/locale/ru/LC_MESSAGES/django.po` - msgids are the English text, so there is no `en`
catalogue. `makemessages` also picks up model verbose names and choice labels; leave those empty,
they are admin-only. `.mo` files are untracked build output (`startup.sh` and the `make test`
targets compile them); both compile calls pass `--ignore=.venv`, because the venv lives inside the
project directory here.

### Frontend

Vue 3 + Pinia (with `pinia-plugin-persistedstate` for the cart), Vue Router, axios, and
`glightbox` for the product gallery - that is the whole dependency list, and `npm ci` installs it
from the tracked `package-lock.json`. Pinia is registered **before** the router in `src/main.js`:
vue-router starts its first navigation from `install()`, and the `/` redirect reads the language
store. Stores in
`src/stores/`: `cart`, `catalog` (countries and document types), `content` (menu pages, site
settings, slides), `order`, `settings` (the language only - the currency store is gone with USD).
Every component under `src/components/` is now the storefront's own (`storefront/` plus the SVG
icons): the Verdoc set - `ViewBlock`, `ListView`, `CommonButton`, `ModalWindow` and the rest - was
deleted with M3, and no scss is left, so there is no sass toolchain either. Requests go through
`src/api/`: `catalog.js`, `content.js` and `order.js` (checkout, cart lines, purchases,
unsubscribe) - a view does not reach for the axios client itself.

**Dynamic rendering ([ADR-0010](./docs/adr/0010-dynamic-rendering.md)).** The SPA is the whole
interface for people; Django serves it as a shell (`storefront/shell.html`, built by `make spa`
from `frontend/index.html` - vite injects the `{{ storefront_meta }}` / `{{ LANGUAGE_CODE }}`
hooks at build time and moves the file into the backend templates). Bots get the Django-rendered
pages on the same URLs. vue-router mirrors `backend/backend/urlspace.py`; keep the two in sync
when a route is added. Data comes from `/api/catalog/...` (`src/api/catalog.js`) and
`/api/content/...` (`src/api/content.js`), and both presentations must stay content-equivalent -
a change lands in the bot template and the Vue view together. Two pieces of markup are literally
shared: `storefront/_bgs_decor.html` and `components/storefront/PageDecor.vue` carry the same
decor/wave block from the design, and the dark strip must stay on every page (the header is
`position: fixed`, so without it the content slides underneath). `App.vue` draws it once for every
page and puts the route's **named `hero` view** inside it: a listing route declares
`components: {default: Catalog, hero: HomeHero}`, every other route declares none and gets the bare
strip - the same split as `storefront/base.html` holding the strip and `storefront/catalog.html`
filling its `hero` block.

**What crawlers read** lives beside the storefront views and outside `i18n_patterns`:
`storefront/sitemaps.py` (`/sitemap.xml`, an index over `/sitemap-<section>.xml`) and
`storefront/templates/storefront/robots.txt`. The map is `django.contrib.sitemaps` with
`i18n`/`alternates`/`x_default`, so one entry carries both languages and its hreflang set; sections
list only what the storefront lists (`active()`, `non_empty()`, `with_product_counts()`), and the
`noindex` service pages are absent by construction. It is an index rather than one file because
`Sitemap.limit` counts per section. `x-default` is the address without a language prefix - the same
string `seo.x_default` puts in `<head>`, so the two presentations advertise one URL. robots.txt is
rendered by Django so its `Sitemap:` line is built from `django_site` + `SITE_SCHEME` like every
other absolute link.

**The grid shows one page, and the address says which.** `Catalog.vue` reads `?page=` and asks the
API for exactly that page; **how many pages there are comes from the server** (`total_pages` on the
paginated payload, `catalog.views.CatalogPagination`), so the SPA keeps no copy of the page size to
divide by - one did drift, and the grid offered pages the API answers 404 for.
`components/storefront/Pagination.vue` draws numbered links - a port of Django's
`Paginator.get_elided_page_range(on_each_side=1, on_ends=1)`, the same window `storefront/views.py`
asks for, so both presentations print the same numbers at the same addresses and a crawler reaches
page 6 from page 1. Page 1 carries no parameter - that is the listing's canonical address, and
anything that is not a whole number above 1 (`?page=abc`, `-3`, `2.5`) means page 1. A `?page=` past
the end lands on the last real page instead of "page not found" (the API answers 404 both for an
overshoot and for an unknown slug; asking for page 1 tells the two apart, and the URL is corrected
with it). Changing page - and only that, so a search does not pull the field it is typed in under
the header - scrolls the first card under the fixed header with `behavior: "instant"`: `style.css`
sets `scroll-behavior: smooth` on `<html>`, and an animated scroll lands late and dies on the
reader's first wheel. The picture boxes reserve their height (`.banner__media`, the `width`/`height`
on the hero image), so nothing has to chase the layout afterwards.
**Infinite scroll used to live here** and was removed: a range of pages needed a scroll anchor, two
observers and a guess at the reader's direction, and it still left `?page=` describing something
other than what was on screen (see `docs/journal.md`).

**The welcome banner is ours, not the mockup's slider.** `components/storefront/Banner.vue` and the
`.banner--static` block in `storefront/catalog.html` render the same box, dressed by `.banner` in
`shop.css`: one purple panel with a real `border-radius`, the slides stacked in one grid cell so the
height is the tallest slide's and never jumps, a crossfade between them, arrows, dots, swipe and the
left/right keys. Autoplay stops on hover, on focus, on a hidden tab and under
`prefers-reduced-motion`; the slide that is not showing is `inert`, so its link is out of the tab
order. The design's markup (`.slider-welcome`, `.content`, `.swiper-*`) is gone from both
presentations: it faked the rounded corners with two white gradient strips and two
`box-shadow: 0 0 0 30px #fff` masks painted over the slide, which only works on a white page.

**The product search is the server's** (`?q=` on `/api/catalog/products/`, `ProductQuerySet.search`
over `name_en`/`name_ru`, capped at `MAX_SEARCH_LENGTH`). It lives in `?q=` in the storefront URL
too, so a reload or a shared link keeps it, and every facet link carries it over. The design filters
the loaded cards in `app.js`; doing that here counted the pagination against the whole catalog, so
the grid offered a "load more" that added nothing visible. A new query starts at page 1.

**What the mockup does not ship lives in `storefront/css/shop.css`**, next to `style.css` and
linked by **both** presentations (`storefront/base.html` and `frontend/index.html`), so a button or
a page number looks the same whichever one the visitor got: `.btn-ghost` / `.btn-solid` on top of
the design's `.btn` (plus `.btn-ghost--light` for the purple slide) and the `.pagination` block.
The design's only filled button is the pink-blue gradient (`.btn-grade` / `.button`), which stays
where the designer put it - the hero and the product cards - and was too loud on "pay" and on a
page number. `style.css` itself stays a copy of the mockup.

**The header is `position: fixed` over a light page**, so `composables/useHeaderScroll.js` ports the
design's scroll handler: `header-scrolled` paints it black past the first pixel and `out` slides it
away while the reader moves down (never while the mobile menu is open). Without those classes it
dissolves into the content.

**Verify in a browser before calling a storefront stage done** - green tests and `curl` do not
catch a blank grid, a dead button or a layout that overflows at 320px. Run `make dev-backend`
plus `make dev-frontend` (or `make spa` and the backend alone), then click through: catalog,
filters, product page, add to cart, cart, checkout modal, both languages.

**Everything the API hands over is a model, not a payload** (`src/models/`). `Localized` turns the
`name_en`/`name_ru` pairs every endpoint carries into one property read against the active locale
with an English fallback - the rule modeltranslation applies on the server - and `Product`,
`Country`, `DocumentType`, `Page`, `Slide`, `SiteSettings` extend it. `Product` also owns the two
things that used to be copied around: `priceLabel` (USD, two decimals) and `route(lang)`. The api
modules construct them, so a view never sees raw JSON. One catch: `localStorage` holds JSON, so
`stores/cart.js` rebuilds its lines with `new Product(...)` in the persist plugin's `afterHydrate`
- without it `item.name` is undefined until the first `refresh()`.

The cart is a **set** of products (no quantities - an order holds a product at most
once); `stores/cart.js` persists it, the floating `cartlequebutton` from the design is
`components/storefront/CartButton.vue`. `Cart.vue` calls `cart.refresh()` on open, which asks
`GET /api/cart/items/?ids=` what those ids are now: localStorage may be months old, and the
invoice is written from the catalog, so a product off the shelf leaves the cart here rather than
failing at the checkout and a price that moved is corrected before the customer sees the total.

**One component takes money: `components/storefront/CheckoutModal.vue`.** It is the cart's pay button
and the "buy now" of every card and product page - the express path buys one template without
touching the cart. The markup is the design's (`.remodal.modalpay`, `.modal-buy__*`,
`.input-box*`), but remodal is not carried over, so Escape, the backdrop, the scroll lock and the
focus are the component's own. It closes **only after the invoice exists**; a failure prints
inside the modal (`errorMessageKey`), and the cart is cleared only on success.

Two routes share the "my purchases" name and they are not the same page: `/purchases`
(`views/MyPurchases.vue`) is the e-mail form you land on when the link is lost, `/purchases/:token`
(`views/Purchases.vue`) is the page the e-mail links to. The token in the URL is the whole
authentication, so a 404 from any of its calls means "the link is spent" and the page says so
instead of retrying. Prices there come from the order's snapshot.

`/unsubscribe/:token` (`views/Unsubscribe.vue`) is the third token page; it reads the token on
mount and waits for a click before opting anyone out (see Broadcasts above).

Anything that fetches shows which of "loading", "failed" and "empty" it is in - an empty result and
a dead backend must never look alike.

**A form that posts must show the failure.** `src/api/errors.js: errorMessageKey(error, overrides)`
maps an HTTP status onto an i18n key once; a form passes in what a status means in its own context
(`404` on `send-links` is "no purchases on this address", `502` at checkout is "the gateway
refused"). Never `console.error` and move on, and never close the payment modal before the request
comes back - a refused checkout used to look exactly like a working one. Plisio's own `detail`
stays out of the interface (English-only and technical); its `provider_code` goes to the console.

### Design and responsive layout

The design is a static build in **`design/`** (`index.html`, `product.html`, `style.css`, `app.js`,
`img/`, `fonts/`) - it is the source of truth for the storefront's look. Its `style.css` lives at
`backend/storefront/static/storefront/css/` and dresses both presentations, so a Vue component
reuses the design's class names rather than inventing its own. The jQuery plugins it ships with
(`remodal`, `swiper-bundle`, jQuery itself) are **not** carried over: the modal is our own
component, the welcome banner is `components/storefront/Banner.vue` on the `.banner` block in
`shop.css` - markup and styles of its own, nothing left of the mockup's slider (see below), and the
filters/burger/search in `app.js` are reactive state. `glightbox` stays, as
an npm package, for the product gallery.
`design/Инструкция по обновлению.txt` documents the year badge and the filter block the designer
added last - follow it when the markup differs from an older screenshot.

The `responsive-craft` skill (`/responsive-craft audit|build|preview`) is installed for responsive
work. Verify visually across widths, not just at named breakpoints - drag from ~320px up and watch
for horizontal overflow (a headless browser adds a ~15px scrollbar that real phones don't, so don't
tune breakpoints to headless pixel measurements).

## Local development

For day-to-day work you don't need the full docker stack (and under rootless podman
`frontend-nginx` can't bind 80/443). Instead run the app processes on the host and keep only
postgres in docker:

- `docker-compose.dev.yaml` runs **postgres only**, publishing it to `localhost:5432`, using the
  volume `psdshop_postgres`. It is the same volume the prod stack would use, so never run both
  postgres containers on one host at once - two instances on one data dir corrupt the DB. (Prod
  lives on its own server, so a local checkout's volume is independent and empty.)
- `backend/dev.env` overrides `backend/.env` for the host backend (see Environment above):
  `DEBUG=True`, `DATABASE_URL` → `localhost:5432`, `EMAIL_URL=consolemail://` (dev mail prints to
  the backend console).
- Typical loop: `make dev-infra` → `make dev-migrate` → `make dev-backend` (host, :8000) +
  `make dev-frontend` (vite, http://localhost:5173/ - the backend has to be up: the CSS, the
  previews and the API all come from :8000). No nginx locally. Seed a catalog once with `seed_testdata` so
  the storefront isn't empty.

## Conventions

- **Communicate with the user in Russian in this project.**
- **Never read `*.env` files** (they hold secrets) - use the matching `.env.dist` template instead,
  and never treat a commented-out line as active config.
- Keep code comments short and in English (self-documenting code); prefer a plain hyphen `-` over
  an em-dash in prose and comments. Exception: the `Makefile` descriptions and the docs under
  `docs/` are intentionally Russian.
- Backend style is enforced by ruff (line-length 120, double quotes) - run `make format` (or let
  pre-commit run it) before committing.
- Work happens on `dev`; PRs target `main`. History starts at the fork commit - the tree was
  cloned from Verdoc with `.git` removed, so nothing before it exists here.
- **Git commit messages are written in English, in the past tense**
  (`docs(adr): rewrote the catalog decision`), not the imperative. Conventional-Commit format, no
  co-authored tail. Only commit when the user explicitly asks.
- **After each action (with write to file), end your reply with a one-line summary written as a
  Conventional-Commit message:** `type(scope): что сделал` in Russian, past tense. Types: `feat`,
  `fix`, `refactor`, `style`, `docs`, `ci`, `test`, `chore`. Scopes: `catalog`, `customer`, `sales`,
  `backend`, `frontend`, `mail`, `Makefile`, `deps`, etc. Example:
  `ci(Makefile): added dev targets for local runs`. This is a recap of the work performed -
  **not** an instruction to create a git commit.
