# PsdShop

Digital-goods storefront: the customer pays with cryptocurrency through Plisio and gets an e-mailed
link to a purchases page where every bought file can be downloaded. Vue 3 SPA + Django REST
Framework + PostgreSQL, behind nginx in Docker Compose.

The domain vocabulary is in [`CONTEXT.md`](./CONTEXT.md), the decisions in [`docs/adr/`](./docs/adr/),
the smaller ones in [`docs/journal.md`](./docs/journal.md), and the state of the rework - including
the launch checklist - in [`docs/plan.md`](./docs/plan.md).

## Getting started

### Prerequisites

* Docker and Docker Compose (or podman with the compose plugin).
* [uv](https://docs.astral.sh/uv/) and Node 22 for running things on the host.
* SSL certificates for HTTPS in `frontend/nginx/ssl` (`<domain>.crt` and `<domain>.key`).
* API keys: Plisio, and an SMTP account for outgoing mail.

### Setup

1. **Prepare environment files**

   `make env` copies every `*.env.dist` to `.env` where missing (`backend/`, `frontend/`,
   `postgres/`, plus `backend/dev.env` and `frontend/.env.development` for local dev). Fill them
   in afterwards.

2. **Choose a workflow**

   * Full stack in Docker (production-like, includes nginx):

     ```bash
     make up        # build + run backend, postgres, frontend-nginx
     make migrate   # apply migrations inside the backend container
     ```

   * Local development - backend and frontend on the host, only postgres in Docker:

     ```bash
     make init         # deps -> .env -> install -> pre-commit -> dev-postgres -> migrate
     make dev-backend  # runserver on the host (:8000)
     make dev-frontend # vite dev server on http://localhost:5173/ (needs dev-backend)
     ```

   `make help` lists every target; [`CLAUDE.md`](./CLAUDE.md) has the detailed reference.

3. **Point the site row at your domain**

   Every absolute URL handed out by e-mail is built from it:

   ```postgresql
   UPDATE django_site SET domain='your-domain', name='human-readable name' WHERE id=1;
   ```

4. **Seed a catalog** for manual testing:

   ```bash
   make dev-manage c="seed_testdata --flush"
   ```

5. **Before deploying an nginx change**, validate it: `make nginx-check` renders the site template
   and runs `nginx -t` in a throwaway container - no image build and no real certificates needed.

## How it works

1. **Catalog.** Products are template files grouped by country and document type, with a year, a
   description and a gallery. The same file is sold any number of times.
2. **Checkout.** `POST /api/order/` snapshots prices, creates the order and asks Plisio for an
   invoice; the customer is redirected to it.
3. **Payment.** Plisio calls back to `POST /api/order/status`. The first paid callback stamps the
   order, issues download tokens and mails the purchases-page link.
4. **Delivery.** Two time-limited tokens: one opens the purchases page, one opens a single file.
   Both can be re-issued, and `POST /api/send-links/` mails a fresh page link.
5. **For crawlers.** Every storefront URL answers twice from one view: a bot gets the Django-rendered
   page, a person gets the SPA shell with the same meta. `/sitemap.xml` is an index over per-section
   maps carrying both languages with hreflang, and `/robots.txt` is rendered by Django so its
   `Sitemap:` line always names the real host.

## Technology stack

**Frontend:** Vue 3, Pinia, Vue Router, axios, vue-i18n, glightbox. Built by vite straight into
the backend's static tree (`make spa`), so there is no separate frontend service in production.

**Backend:** Django, Django REST Framework, django-modeltranslation, gunicorn, psycopg,
PostgreSQL.

**Infra:** Docker Compose, nginx (TLS, rate limits, static), cron in the backend container for
broadcasts and callback-log retention.

## License

Distributed under the **GPLv3** License. See LICENSE for more information.
