# PsdShop

Digital-goods storefront: the customer pays with cryptocurrency through Plisio and gets an e-mailed
link to a purchases page to download the files from. Vue 3 SPA + Django REST Framework + PostgreSQL
behind nginx in Docker Compose, on a single domain.

Domain vocabulary is in [`CONTEXT.md`](./CONTEXT.md); the decisions, the URL space, the open items
and the launch checklist are in [`docs/architecture.md`](./docs/architecture.md); traps worth
remembering are in [`docs/journal.md`](./docs/journal.md).

## Getting started

Needs Docker Compose (or podman), [uv](https://docs.astral.sh/uv/) and Node 22 for host runs,
certificates in `frontend/nginx/ssl` (`<domain>.crt` / `.key`), a Plisio key and an SMTP account.

```bash
make env      # copies every *.env.dist to .env where missing; fill them in afterwards
make help     # every target
```

Full stack in Docker (production-like, with nginx):

```bash
make up && make migrate
```

Local development - backend and frontend on the host, only postgres in Docker:

```bash
make init          # deps -> .env -> install -> pre-commit -> dev-postgres -> migrate
make dev-backend   # runserver on :8000
make dev-frontend  # vite on http://localhost:5173/ (needs dev-backend)
make dev-manage c="seed_testdata --flush"   # a catalog for manual testing
```

After the first deploy, point the `django_site` row at your domain - every absolute URL in the
mails is built from it: `UPDATE django_site SET domain='your-domain', name='...' WHERE id=1;`
Validate an nginx change with `make nginx-check` (envsubst + `nginx -t` in a stock container, no
image build and no real certificates).

## How it works

1. **Catalog.** A product is a template file with a country, a document type and a year; the same
   file is sold any number of times.
2. **Checkout.** `POST /api/order/` snapshots prices from the catalog, creates the order and asks
   Plisio for an invoice.
3. **Payment.** Plisio calls back to `POST /api/order/status`; the first paid callback stamps the
   order, issues download tokens and mails the purchases-page link.
4. **Delivery.** Two time-limited tokens: one opens the purchases page, one opens a single file.
   Both can be re-issued, and `POST /api/send-links/` mails a fresh page link.
5. **For crawlers.** Every URL answers twice from one view: a bot gets the Django-rendered page, a
   person gets the SPA shell with the same meta. `/sitemap.xml` is an index over per-section maps
   with hreflang, and `/robots.txt` is rendered by Django.

## Stack

**Frontend:** Vue 3, Pinia, Vue Router, axios, vue-i18n, glightbox; vite builds straight into the
backend's static tree (`make spa`), so there is no frontend service in production.
**Backend:** Django, DRF, django-modeltranslation, gunicorn, psycopg, PostgreSQL.
**Infra:** Docker Compose, nginx (TLS, rate limits, static), cron in the backend container for
broadcasts and callback-log retention.

## License

GPLv3, see LICENSE.
