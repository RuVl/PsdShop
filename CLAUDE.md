# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

PsdShop is a digital-goods storefront: customers buy template documents (PSD/PDF), pay via
**Plisio** (crypto invoices), and receive a time-limited e-mailed link to a purchases page they
download the files from. Vue 3 SPA frontend + Django REST Framework backend + PostgreSQL, all
orchestrated with Docker Compose behind nginx, on a single domain.

Domain vocabulary is in [`CONTEXT.md`](./CONTEXT.md), decisions in [`docs/adr/`](./docs/adr/).

### Status: the code is mid-rework

The tree is a fork of **Verdoc**, a storefront for one-of-a-kind files. The infrastructure,
payment, delivery, broadcasts and admin statistics are reused; the catalog, the fulfillment model,
the currency and the whole design are being replaced. The roadmap, target schema and open
questions live in [`docs/plan.md`](./docs/plan.md) - **read it before changing models**.

What is decided but **not yet in the code** (each stage is R1..R7 in the plan):

| Decision | ADR | Stage |
|---|---|---|
| A product is a template sold any number of times - no `StockItem`, no `Allocation`, no reservation | [0001](./docs/adr/0001-unlimited-copies-no-reservation.md) | R2 |
| Catalog is country x document type x year, with a gallery and a product page | [0008](./docs/adr/0008-catalog-country-type-year.md) | R1 |
| Prices are USD only - `djmoney` and exchange rates go away | [0006](./docs/adr/0006-single-currency-usd.md) | R3 |
| Meta tags rendered by Django instead of a build-time prerender (`proposed`) | [0007](./docs/adr/0007-seo-for-a-spa.md) | R6 |

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
make dev-frontend  # vite dev server on 0.0.0.0:5173 (host, for the Verdoc-era SPA)
make islands / make dev-islands  # build the storefront vite islands into the backend static tree (--watch for dev)
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
make update-rates  # fetch currency rates (djmoney) - goes away in R3
make expire        # release allocations of expired PENDING orders - goes away in R2
make broadcast     # send QUEUED broadcasts (also cron, every 15 min); c="--id N --dry-run --test"
make prune-callbacks c="--dry-run"  # drop raw Plisio callbacks past the retention window (also cron, weekly)

# Translations (gettext; the e-mail copy lives in backend/locale/ru/LC_MESSAGES/django.po)
make messages / make compilemessages          # in the container
make dev-messages / make dev-compilemessages  # on the host
# .mo files are build output and untracked: startup.sh compiles them, and the test targets
# depend on compilemessages so a run never asserts against a stale catalogue.

# Tests
make test          # in the container; make dev-test on the host (t="sales" or t="sales.tests.DeliverTests")

# Seed test catalog for manual UI testing (catalog `seed_testdata` command):
#   make dev-manage c="seed_testdata --flush"   (host/dev)   or   make manage c="seed_testdata --flush" (container)
# Currently seeds the Verdoc-era catalog (countries x products x stock items) - rewritten in R1
# to cover countries x document types x years. --flush wipes the catalog first.

# DB
make db-dump [DUMP=backups/dump.sql] / make db-restore DUMP=… / make psql

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
`content/tests.py`, `customer/tests.py`, `mailing/tests.py`, `sales/tests.py` and
`sales/tests_statistics.py` (django `TestCase`, run with `make test` / `make dev-test`) and cover
the checkout/callback/delivery invariants - keep them green. `sales/tests_statistics.py` is
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
  (mode `development`); `vite build` (mode `production`) keeps using `frontend/.env`. It points
  `VITE_API_URL` at the host backend (`http://localhost:8000/api`). `make env` creates it; the real
  file is gitignored (the `.env.development.dist` template stays tracked).
- Settings use `django-environ`. Key vars: `DATABASE_URL`, `EMAIL_URL`, `PLISIO_SECRET_KEY`,
  `OPENEXCHANGERATES_APP_ID` (drops out in R3), `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`,
  `CSRF_TRUSTED_ORIGINS`.
- Frontend build injects `VITE_API_URL` as the compile-time constant `__API_URL__` (see
  `vite.config.js`); the axios client in `src/api/index.js` uses Django's CSRF cookie/header.
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

## Architecture

### Order / fulfillment flow (the core domain)

Backend apps: `catalog` (products), `customer` (buyers and their access), `sales` (checkout,
payment, delivery), `mailing` (broadcasts).

1. **Catalog** - today `Country` → `Product` → `StockItem`, where a unit is available exactly when
   no non-`RELEASED` `Allocation` points at it and stock is **derived**
   (`StockItem.objects.available()`, `Product.objects.with_available()`). **R1/R2 replace this**
   with a flat `Product` carrying its own file plus `Country`, `DocumentType`, `year` and
   `ProductImage` - no stock, no scarcity ([ADR-0001](./docs/adr/0001-unlimited-copies-no-reservation.md),
   [ADR-0008](./docs/adr/0008-catalog-country-type-year.md)).
2. **Checkout** - `POST /api/order/` (`OrderCreateView` + `OrderSerializer`). Gets/creates the
   `Customer`, computes `total_price`, creates `Order` + `OrderItem`s **with a price snapshot**
   (`product_name`, `unit_price`), and (today) allocates units. Then requests a Plisio invoice; the
   URL is stored on `Order.invoice_url`, and if the request fails the order is deleted - the
   endpoint answers **502** with `{detail, code: "invoice_failed", provider_code}`, passing Plisio's
   own message on instead of a blanket "Error creating invoice".
3. **Payment callback** - `POST /api/order/status` (`PlisioCallbackView`). Verifies `verify_hash`
   (HMAC-SHA1) against `PLISIO_SECRET_KEY`, stores the raw payload in `PaymentCallbackLog`
   **before** the atomic block, then upserts the `Transaction` **by `txn_id`** (a currency switch
   mints a new invoice for the same order). On PAID/OVERPAID: `order.mark_paid()` stamps `paid_at`
   once and only that first call sends the e-mail; `order.deliver()` hands the files over. On
   EXPIRED/CANCELLED: `order.release()` (which stops being needed once stock is gone). A duplicate
   callback is a 200 no-op.
4. **Delivery** - two independent tokens, both with a TTL
   ([ADR-0002](./docs/adr/0002-customer-and-purchases-page.md)). `Customer.access_token`
   (`PURCHASES_PAGE_TTL` = 24h) opens the **purchases page**, and the delivery e-mail carries that
   one link and nothing else (`sales/utils.send_purchases_link`). The per-file token
   (`DOWNLOAD_TTL` = 24h; on `Allocation` today, on `OrderItem` after R2) opens one file:
   `GET /api/files/<uuid>/`. The page is `GET /api/purchases/<customer_token>/`, with
   `POST .../refresh/<id>/` and `POST .../refresh-all/` re-issuing file tokens. An unknown,
   malformed or expired page token all answer the **same 404** - the API must not confirm that a
   token exists. `POST /api/send-links/` is the recovery path: it tops up anything undelivered,
   **rotates** `access_token` (this is how an old page link is revoked) and mails the new one; file
   tokens are deliberately left alone so links the customer already shared keep working.
   - `serve_allocation()` in `sales/views.py` is the single point a file is streamed from, and the
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
`limit_req` in nginx on `/api/order/` and `/api/send-links/` (the Plisio callback stays unlimited),
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
- **The stock forecast section is Verdoc-era and goes away in R3** together with the derived stock
  count - a template never runs out.
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
`proxy_pass` block that every backend location includes. Validate a config change with `nginx -t`
before deploying it (render the template with `sed`, mount it into a throwaway `nginx` container
with dummy certs).

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
(`Broadcast.subject`, `Broadcast.body`). The catalog endpoints have no `?lang=`:
`TranslationFieldsMixin` expands `name` into `name_en` and `name_ru` on every response, so the
storefront picks one client-side. Frontend uses vue-i18n (`src/i18n/locales/`), and the router
reads `?lang=` on any route, which is how a link from an e-mail opens in the right language.

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

Vue 3 + Pinia (with `pinia-plugin-persistedstate` for the cart), Vue Router, axios. Stores in
`src/stores/` (`cart`, `order`, `settings`, `languages`, and `currencies` until R3).

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
`img/`, `fonts/`) - it is the source of truth for the storefront's look, and R5 ports it into Vue
components. The jQuery plugins it ships with (`remodal`, `swiper-bundle`, `glightbox`, jQuery
itself) are **not** carried over as-is: the modal is our own component, swiper has a
framework-agnostic element build, and the filters/burger/sorting in `app.js` become reactive state.
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
  `make dev-frontend` (vite, :5173). No nginx locally. Seed a catalog once with `seed_testdata` so
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
- Work happens on `dev`; PRs target `main`. The repository has **no git history yet** - it was
  cloned from Verdoc with `.git` removed.
- **Git commit messages are written in English, in the past tense**
  (`docs(adr): rewrote the catalog decision`), not the imperative. Conventional-Commit format, no
  co-authored tail. Only commit when the user explicitly asks.
- **After each action (with write to file), end your reply with a one-line summary written as a
  Conventional-Commit message:** `type(scope): что сделал` in Russian, past tense. Types: `feat`,
  `fix`, `refactor`, `style`, `docs`, `ci`, `test`, `chore`. Scopes: `catalog`, `customer`, `sales`,
  `backend`, `frontend`, `mail`, `Makefile`, `deps`, etc. Example:
  `ci(Makefile): added dev targets for local runs`. This is a recap of the work performed -
  **not** an instruction to create a git commit.
