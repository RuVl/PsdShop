# CLAUDE.md

Guidance for Claude Code (claude.ai/code) in this repository.

PsdShop is a digital-goods storefront: customers buy template documents (PSD/PDF), pay a **Plisio**
crypto invoice, and get one e-mailed link to a purchases page. Vue 3 SPA + Django REST Framework +
PostgreSQL behind nginx in Docker Compose, one domain. The rework of the Verdoc fork is finished;
the shop is not launched yet.

**Read before changing anything non-trivial:**

| | |
|---|---|
| Why the code is shaped this way - domain decisions, order flow, statistics, uploads, nginx, broadcasts, i18n, frontend, open items, launch checklist | [`docs/architecture.md`](./docs/architecture.md) |
| Traps that already cost time (Plisio signing, pagination, the banner, sitemaps, the admin file widget) | [`docs/journal.md`](./docs/journal.md) |
| What to call things | [`CONTEXT.md`](./CONTEXT.md) |

Add a journal entry in the same commit that closes a fork.

## Commands - use the Makefile

`make help` lists everything. The project is **docker-first**: `manage.py` and `psql` targets `exec`
into the running stack, so bring it up first.

```bash
make init          # bootstrap step 1: check-deps → install → pre-commit → env, then STOPS.
                   # Fill the .env files, then run `make dev-migrate` yourself (NOT `up`).
make env           # create .env from *.dist where missing
make install       # backend + frontend (install-backend / install-frontend for one)
make up / down / ps / logs[-backend|-db|-nginx]

# Local dev - app processes on the host, only postgres in docker (rootless podman cannot bind 80/443)
make dev-infra     # postgres only (docker-compose.dev.yaml), on localhost:5432
make dev-migrate / dev-backend (:8000) / dev-frontend (vite :5173) / dev-superuser / dev-infra-down
make spa           # production SPA build: hashed assets into backend static, shell.html into templates
make dev-reset     # recreate the dev-postgres container (keeps the psdshop_postgres volume)
make dev-nuke      # DROP the volume - needed after migrations are regenerated

# Any manage.py command; the named targets below are shortcuts for the frequent ones.
make manage c="showmigrations"              # in the backend container
make dev-manage c="seed_testdata --flush"   # on the host (auto-brings up dev-infra)

make migrate / makemigrations m="catalog customer mailing sales" / superuser
make broadcast     # send QUEUED broadcasts (also cron, every 15 min); c="--id N --dry-run --test"
make prune-callbacks c="--dry-run"          # drop raw Plisio callbacks past retention (also cron, weekly)
make messages / compilemessages             # gettext, in the container
make dev-messages / dev-compilemessages     # gettext, on the host
make test          # container; make dev-test on the host (t="sales" or t="sales.tests.DeliverTests")
make db-dump [DUMP=…] / db-restore DUMP=… / psql
make nginx-check   # envsubst + `nginx -t` in a stock nginx container (no image build, no certs)
make lint          # ruff check + format --check;  make format applies fixes
make pre-commit-install / pre-commit
```

`seed_testdata` builds countries x document types x years with generated previews, the layout edge
cases (very long name, extreme prices, no year, hidden) and the content rows the chrome needs
(pages, welcome slides, the settings singleton). `--flush` wipes them first.

Typical local loop: `make dev-infra` → `make dev-migrate` → `make dev-backend` +
`make dev-frontend` (the backend has to be up: CSS, previews and the API all come from :8000), then
seed a catalog once. There is no nginx locally. `docker-compose.dev.yaml` uses the same
`psdshop_postgres` volume the prod stack would, so never run both postgres containers on one host.
After `make spa`, restart the backend - Django caches `shell.html` in the template cache and the
built SPA will look broken until you do.

## Layout

```
backend/
  backend/    settings, urls, urlspace.py (the URL map vue-router mirrors), sites.py (absolute_url)
  catalog/    Product, Country, DocumentType, ProductImage, storages.py, seed_testdata
  content/    Page, Slide, SiteSettings
  customer/   Customer, CustomerQuerySet (buyers/leads/subscribed_buyers), validators.py
  sales/      checkout, plisio.py, statistics.py, admin_views.py, delivery views
  mailing/    Broadcast, BroadcastDelivery, the broadcast command
  storefront/ bot templates, shell.html, bots.py, seo.py, sitemaps.py, static/storefront/css/
  locale/ru/  gettext catalogue for e-mail copy
frontend/src/ api/ components/storefront/ composables/ i18n/ models/ stores/ views/
design/       the designer's static build - the source of truth for the look
```

## Tooling and style

- Dependencies and venvs are **uv**: `backend/pyproject.toml` + `uv.lock` are the source of truth
  (no `requirements.txt`), the image installs via `uv sync`.
- Lint/format is **`uvx ruff@0.15.12`**, config in `backend/pyproject.toml`: **line-length 120**,
  double quotes, `target-version = "py313"`, rules `E, F, I, UP, B, W, C4, SIM`. Run `make format`
  before committing. pre-commit lives at the repo root (`uvx pre-commit`); mypy is commented out.
- Runtime is Python 3.13. Frontend deps are installed with `npm ci` from the tracked lock file.
- Tests are django `TestCase`s in `catalog/`, `content/`, `customer/`, `mailing/`, `sales/tests.py`,
  `sales/tests_statistics.py` and `storefront/`. **The test targets name the apps explicitly**, so a
  new app must be added to both `test` and `dev-test` or its tests silently never run.
  `tests_statistics.py` is deliberately separate: dashboard arithmetic, not fulfillment invariants.
- **Verify storefront work in a browser** - green tests and `curl` do not catch a blank grid, a dead
  button or a layout that overflows at 320px. Click through catalog, filters, product page, add to
  cart, cart, checkout modal, in both languages. The `responsive-craft` skill is installed; drag the
  width from ~320px up rather than checking named breakpoints (a headless browser adds a ~15px
  scrollbar that real phones do not, so do not tune breakpoints to headless measurements).

## Configuration

- Each service reads its own `.env`, copied from the `.env.dist` beside it (`backend/`, `frontend/`,
  `postgres/`); the backend also loads `postgres/.env` for the DB connection. Settings use
  `django-environ`: `DATABASE_URL`, `EMAIL_URL`, `PLISIO_SECRET_KEY`, `ALLOWED_HOSTS`,
  `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS`.
- **Local overrides** are `backend/dev.env`, layered on top of `backend/.env`
  (`uv run --env-file .env --env-file dev.env`) because `settings.py` reads only `os.environ`. Its
  DB user/password/name **must match `postgres/.env`**. The frontend mirrors this with
  `frontend/.env.development`, which applies to `npm run dev` alone.
- `vite.config.js` compiles the API base into `__API_URL__`: `VITE_API_URL` in dev, same-origin
  `/api` in a production build - not configurable, one domain, one origin.
- **Every absolute URL is `django_site` + `SITE_SCHEME`**, joined by
  `backend/sites.py: absolute_url(path, request)`. Build links through it. `SITE_ID = 1` is set
  under `DEBUG` only, because a local run has no matching site row.
- `EMAIL_URL`'s **scheme picks the backend** (`smtp://`, `consolemail://`). Do not pass `backend=`
  to `env.email()` - it pins SMTP and makes the scheme a no-op.
- The API answers **JSON only**; DRF's browsable renderer is enabled under `DEBUG` alone.

## Rules that break things quietly

- **Never read `*.env` files** - they hold secrets. Use the matching `.env.dist`, and never treat a
  commented-out line as active config.
- **`?json=true` stays on the Plisio callback URL.** Without it the signature algorithm changes and
  every payment is refused at the door. Details in the journal.
- **Never filter orders by `status`** to find paid ones - `STATUS_MAP` turns `cancelled duplicate`
  back into `PENDING`. Use `OrderQuerySet.paid()` / `CustomerQuerySet.buyers()`, the single
  definitions keyed off `paid_at`.
- **Row state changes go through the model methods** (`Order.mark_paid/deliver`,
  `OrderItemQuerySet.reissue_tokens`, `Broadcast.claim/finish`); the ones that can be called out of
  turn raise `ValueError`, which views turn into 400/409.
- **Money is the `OrderItem` snapshot**, never the current catalog price, and Plisio's commission is
  `commission / source_rate` - dividing, not multiplying.
- **Links inside e-mails are built with `reverse()` under `translation.override(customer.language)`**
  and absolutised via `backend/sites.py`; storefront routes live under `i18n_patterns`, so a
  hand-glued path 404s.
- **A paid file has exactly one exit**, `DownloadFileView` behind a token: `PRODUCT_FILES_ROOT` sits
  outside `MEDIA_ROOT`, its storage has no `base_url`, and no nginx location points at it.
- **The bot page and the Vue view are one change**, built from the same queryset and the same meta
  (`storefront/seo.py`); a divergence is cloaking. vue-router mirrors `backend/backend/urlspace.py`.
- **`style.css` stays a copy of the mockup** - our own CSS goes to `storefront/css/shop.css`, linked
  by both presentations. The one deliberate exception is `.banner`.
- **The dark decor strip belongs on every page**: the header is `position: fixed` and without it the
  content slides underneath.
- **Show failures.** Anything that fetches must distinguish loading / failed / empty, and a form that
  posts must surface the error through `src/api/errors.js: errorMessageKey`. Never `console.error`
  and move on, and never close the payment modal before the request comes back.
- **The catalog API carries both languages** (`name_en` / `name_ru`) and has no `?lang=`; the
  interface language is the URL path prefix.

## Conventions

- **Communicate with the user in Russian.** Notes, docs and code comments are English.
- Keep comments short and self-documenting; prefer a plain hyphen `-` over an em-dash in prose.
  Exception: the `Makefile` descriptions are Russian.
- Work happens on `dev`; PRs target `main`. History starts at the fork commit.
- **Git commit messages are English, past tense** (`docs(adr): rewrote the catalog decision`), in
  Conventional-Commit format, with no co-authored tail. Only commit when the user explicitly asks.
- **After each action that writes a file, end the reply with a one-line Conventional-Commit summary
  in Russian, past tense:** `type(scope): что сделал`. Types: `feat`, `fix`, `refactor`, `style`,
  `docs`, `ci`, `test`, `chore`. Scopes: `catalog`, `customer`, `sales`, `backend`, `frontend`,
  `mail`, `Makefile`, `deps`. This is a recap, **not** an instruction to create a git commit.
