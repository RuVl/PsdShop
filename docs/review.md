# Full-tree code review, 2026-09-02

Two-axis review of the whole tree at `dev` / `4b6ca52` (not a diff): **Standards** - does the code
follow this repo's documented rules and the Fowler smell baseline - and **Spec** - does the code do
what `docs/architecture.md` and `CLAUDE.md` say it does. The axes were reviewed separately and are
reported separately on purpose: a change can pass one and fail the other, and merging them lets one
mask the other.

Findings marked **verified** were re-read against the source after the review. `docs/module-depth.md`
covers module shape and is not repeated - the reviewers were told to report only what it missed.

**Status, 2026-09-03.** Everything below is fixed - the hard findings on both sides, the judgement
findings, the three `make init` problems the owner found by hand, and the documentation drift. Two
items were deliberately left as they are, each with the reason written at the code: the front page's
SEO block still swallows a failed fetch (the block is decorative, and "failed" and "empty" really do
render the same thing there), and `send-links` still calls `deliver()` per order in a loop (bounded
by one customer's order count; a queryset-level delivery would change the model API for no reader-
visible gain).

Four of the fixes proposed below turned out to be wrong when checked against the code and are
corrected in place: `reusable()` needs both halves of its filter, the `--flush` guard cannot be
`settings.DEBUG` alone, the canonical clamp belongs in `build_meta`, and vue-router cannot take the
Django slug pattern verbatim. The line numbers for the broadcast and `customer/admin.py` findings
were wrong in the first draft and have been corrected.

## Standards

### Hard - production blockers

1. **`backend/backend/settings.py:18-19` - `SITE_ID` is set under `DEBUG` only, so every
   request-less absolute URL raises in production.** (verified)
   `backend/sites.py:18` calls `Site.objects.get_current(request)`, which raises
   `ImproperlyConfigured` when `SITE_ID` is unset *and* `request is None`. Request-less callers:
   `mailing/management/commands/broadcast.py` -> `mailing/services.py` -> `make_unsubscribe_url`,
   `send_broadcast_test`, and `customer/admin.py:290`. Every broadcast delivery is written FAILED,
   one row at a time, because the per-row `except` swallows it. With a request the lookup is an
   exact `Host` match, so a `www.`/port mismatch raises `Site.DoesNotExist` and every storefront
   page 500s in `seo.build_meta`. `mailing/tests.py:118` creates the site at pk=1 and passes no
   request, which only works when `SITE_ID = 1` - so `make test` in the container cannot pass.
   Fix: `SITE_ID = env.int("SITE_ID", default=1)` outside the `if DEBUG` block.

2. **`backend/cronjob:1-2` + `backend/startup.sh:11` - both documented cron jobs die at import.**
   (verified)
   The crontab runs `/app/.venv/bin/python /app/manage.py broadcast` directly and `startup.sh` only
   does `service cron start`. Cron strips the container environment; `settings.py:10` reads
   `env("SECRET_KEY")` from `os.environ` alone, and the backend's env arrives purely through
   compose `env_file` (`docker-compose.yaml:67-69`). The project already solved this once for the
   other container - `postgres/entrypoint.sh:4-6` dumps the environment to
   `/etc/postgres-backup.env` with the comment "Cron jobs run with a stripped environment" - and
   the backend image has no equivalent. Broadcasts and `prune_callback_logs` are dead on launch day.
   Fix: dump the environment to a file in `startup.sh` and source it from each crontab line.

3. **`backend/sales/models.py:46` - `reusable()` finds unpaid orders by `status`, the exact trap
   `CLAUDE.md` forbids.** (verified)
   `self.filter(customer__email=email, status=Order.OrderStatus.PENDING)`. `STATUS_MAP`
   (`sales/plisio.py:31`) maps `cancelled duplicate` -> `PENDING`, and `apply_order_status`
   (`plisio.py:96-97`) writes the mapped status back unconditionally, bumping `updated_at`. A late
   duplicate callback after the `completed` one therefore leaves a **paid** order at
   `status=PENDING` with a live `invoice_url`. A repeat checkout of the same cart inside the hour
   gets 201 and the already-settled invoice, and no new order is created. `sales/tests.py:604-690`
   covers expiry, another customer and a failed invoice, never a paid order.
   Fix: add `paid_at__isnull=True` **alongside** the status filter. Dropping the status is wrong -
   it would make `EXPIRED`, `CANCELLED` and `ERROR` orders reusable, and Plisio has already killed
   those invoices. `paid_at` is the paid test, `status` excludes the dead invoices.

4. **`backend/storefront/urls.py:30` - a matching product URL 500s.** (verified)
   `ProductSlugConverter.regex = r"\d+[-a-zA-Z0-9_]*"` matches `12abc`; `storefront/views.py:107`
   then runs `int(product_slug.split("-", 1)[0])` and raises `ValueError` on a crawlable address.
   `storefront/tests.py:233` only covers `999999-x`.
   Fix: `regex = r"\d+(?:-[-a-zA-Z0-9_]*)?"`, or parse with a match instead of `split`.

5. **`backend/customer/admin.py:57-83` - the request is stashed on the shared `ModelAdmin`.**
   `self._request = request` in `get_queryset`, read later by `access_token_url`. `ModelAdmin` is
   one instance per process and gunicorn runs `worker_class = "gevent"` with 1000 connections
   (`gunicorn.py:14-15`), so concurrent greenlets overwrite each other's request. This is the bug
   `sales/admin.py:32-39` documents as already fixed there.
   Fix: `obj.get_purchases_url(None)`, or the relative-`reverse()` approach
   `DownloadColumnsMixin.download_link` already uses.

### Hard - correctness

6. **`backend/storefront/views.py:64-70` - the bot listing ignores `?q=`.** (verified)
   The API filters with `.search(...)` (`catalog/views.py:75`); the bot branch never does. On
   `/en/germany/utility-bill/?q=vattenfall` a crawler gets the whole facet with a different page
   count and a person gets the filtered grid - the divergence `CLAUDE.md` calls cloaking. The bot
   pagination links (`catalog.html:103,111,114,119`) emit a bare `?page=N` and drop `q` as well.
   Fix: `products = products.search(request.GET.get("q"))` and carry `q` in the page links.

7. **A crashed broadcast can never be resumed** - `mailing/management/commands/broadcast.py:78`
   writes `status = SENDING`, the cron run picks only `QUEUED` (`broadcast.py:36`), and
   `mailing/admin.py:151-161` `_queue_one` re-queues only `DRAFT`/`FAILED`. A process killed
   mid-run strands the broadcast in `SENDING` with no path back, contradicting architecture.md's
   "resumable, not restartable" and the admin's own help text.
   Fix: accept `SENDING` in `_queue_one` - **not** in the cron run. `BroadcastDelivery` guarantees
   unique rows, not unique mail: `plan()` creates every row up front and `mark_sent()` runs after
   `.send()`, so a still-running process and a fresh one would both see the same rows outstanding,
   and a long broadcast is still `SENDING` at the next 15-minute tick. What makes the manual
   re-queue safe is a claim - a conditional `UPDATE … WHERE status = QUEUED`, the one-UPDATE-wins
   idiom `Order.mark_paid` already uses - with `_send_one` bailing out when it updates no rows.

8. **`backend/sales/statistics.py:252,256` - "late" is measured against the wrong window.**
   (verified)
   `took = paid_at - created_at` is compared to `INVOICE_WINDOW = Order.INVOICE_FROM_UPDATED` (1h),
   while the from-creation window is `INVOICE_FROM_CREATED` (1h10m, `models.py:93`). Everything
   paid between 60 and 70 minutes is reported late while `Order.is_expired()` still calls it live.
   Fix: compare against `Order.INVOICE_FROM_CREATED`.

9. **`backend/storefront/seo.py:48-50` - the canonical advertises a page that does not exist.**
   The bot view clamps with `Paginator.get_page` (`views.py:70`), so `?page=999` renders the last
   page while `<link rel=canonical>` still says `?page=999`; every out-of-range number becomes its
   own self-canonical duplicate.
   Fix: clamp, do not 404 - `storefront/tests.py:128` pins the `get_page` clamping and
   `Catalog.vue:105 landOnLastPage` corrects to the last page client-side, so clamping is what
   mirrors. The clamp belongs in `build_meta`, not in the bot branch: `catalog_meta` runs before
   the paginator exists and the SPA branch returns earlier, so the shell emits the same bad
   canonical today. Build the `Paginator` above the `is_bot` branch and thread it through.

10. **`backend/catalog/management/commands/seed_testdata.py:77-93` - `--flush` has no environment
    guard.** It deletes every `Country`, `DocumentType`, `Page` and `Slide` unconditionally (only
    `Product` is protected, by `PROTECT`), and `make manage c="seed_testdata --flush"` runs inside
    the production container.
    Fix: an explicit `--force`, required whenever `not settings.DEBUG`. A bare `settings.DEBUG`
    gate would break a passing test - the test runner forces `DEBUG=False`, and
    `catalog/tests.py:317-329` calls the command with `--flush`.

11. **`frontend/src/stores/catalog.js:10,22,27` - `failed` is written and never read.** No `.vue`
    consumes it. When `/catalog/countries/` or `/document-types/` dies, `CountrySidebar.vue:38`
    renders an empty list, `Catalog.vue:236` renders no type chips and `Catalog.vue:218` prints
    "All products" over `/germany/utility-bill/` - a dead backend looks exactly like an empty
    catalog. The reviewer explicitly disagrees with `docs/module-depth.md` here: the view surfaces
    `failed` for the product grid only, the facet fetch has no failed branch at all.
    Fix: render `catalogStore.failed` in `CountrySidebar.vue` and the chip row.

12. **`frontend/src/views/Purchases.vue:43-51,72` - `withTokenGuard` swallows every non-404** with
    `console.error`. "Refresh link" / "Refresh all" on a 500 or a timeout does nothing visible.
    Breaks `CLAUDE.md` "Never `console.error` and move on".
    Fix: a `refreshError` ref through `errorMessageKey(error)`, rendered next to the buttons.

13. **`frontend/src/views/Catalog.vue:264` vs `storefront/templates/storefront/catalog.html:130` -
    the SEO block is gated differently.** The SPA tests `selectedCountry?.seo_text_en`, the bot page
    tests the locale-resolved `selected_country.seo_text`. A country with `seo_text_ru` only shows
    the block to a crawler on `/ru/...` and never to a person - cloaking again.
    Fix: gate on the `Localized` getter, `selectedCountry?.seo_text`.

14. **`frontend/src/api/index.js:5` `timeout: 10000` vs `backend/sales/views.py:89` `timeout=30`.**
    A slow Plisio invoice aborts in the browser while the backend is still creating the order, and
    `CheckoutModal` shows `errors.network` for a checkout that succeeded.
    Fix: raise the client timeout above the backend's, or set it per-request on `createOrder`.

15. **`frontend/src/views/Catalog.vue:79-98,135` - `load()` has no in-flight generation guard.**
    Two fast page clicks, or a debounced `?q=` landing on a facet link, let a stale response
    overwrite `products` / `totalPages` / `state`.
    Fix: a `let requestId = 0` token; drop the response when it no longer matches.

16. **`frontend/src/views/Catalog.vue:141,155-158` - `searchTimer` is never cleared on unmount**, so
    `pushQuery` fires up to 300ms after leaving the catalog and rewrites the query of whatever route
    is current.
    Fix: `onBeforeUnmount(() => clearTimeout(searchTimer))`.

17. **`frontend/src/App.vue:20-30` - `body.lock` can survive navigation.** `menuOpen` and the class
    are cleared only by an explicit link click, so browser back/forward with the burger open leaves
    the page unscrollable.
    Fix: `watch(() => route.fullPath, closeMenu)`.

18. **`backend/gunicorn.py:11,21,26,31,35,38,53` - Russian comments.** `CLAUDE.md` Conventions:
    comments are English, and user asked to replace all russian comments to English.

### Judgement - duplication and shape

- **Duplicated Code.** `Page.objects.filter(is_published=True).exclude(slug=Page.HOME)` appears
  verbatim in `storefront/views.py:95`, `storefront/context_processors.py:12`, `content/views.py:20`
  and `storefront/sitemaps.py:99` - extract `PageQuerySet.menu()`.
  `DocumentType.objects.with_product_counts().filter(products_count__gt=0)` appears in
  `catalog/views.py:49`, `storefront/views.py:83` and `sitemaps.py:57` while `Country` already has
  `non_empty()` (`catalog/models.py:25`) - the asymmetry is what keeps the copies alive.
  `sales/statistics.py:398-401` re-inlines `sold_items(period)` (`:122`) character for character.
  On the frontend, `Catalog.vue:178 catalogTarget()` and `CountrySidebar.vue:31 target()` carry the
  same "`all`/`all` -> home, otherwise catalog, keep `?q=`" rule, and `typeNames` is written twice
  (`Catalog.vue:38`, `Cart.vue:20`).
- **`backend/catalog/models.py:198`** - `ordering = ["-year", "name"]`: Postgres sorts NULLs first
  on `DESC`, so undated products head the catalog, and year+name is not a total order, so rows can
  repeat or vanish between pages. Use `F("year").desc(nulls_last=True), "name", "pk"`.
- **`backend/storefront/views.py:81-82,126-127`** run `Country.objects.non_empty()` twice per
  render - two COUNT-annotated scans over all products. Evaluate once, filter `is_popular` in Python.
- **`backend/storefront/context_processors.py:11`** - `SiteSettings.load()` is an eager
  `get_or_create` on every template render, including `shell.html` (which uses neither value) and
  every admin page. `nav_pages` is lazy on purpose; make this one `SimpleLazyObject` too.
- **`backend/storefront/views.py:87`** - `if home_page or (not selected_country and not
  selected_type)`: `home_page` is only set inside that same condition (line 52), so the first
  disjunct is dead.
- **`backend/storefront/views.py:45`** - the `all/all` 301 drops the query string; redirect with
  `request.GET.urlencode()` when non-empty.
- **`backend/storefront/templates/storefront/_sidebar.html:14,28,34`** reads `type_slug` defined by
  whoever includes it (`catalog.html:23`, `product.html:5`) - pass it explicitly or the next
  includer gets a `NoReverseMatch`. **`base.html:26,29`** includes `_lang_switch.html` twice, so
  `id="lang-gb-clip"` is emitted twice on every page.
- **`backend/storefront/seo.py:165` vs `:104`** - `page_meta` runs `strip_tags`, `product_meta`
  does not. `seo.py:176` `mark_safe(render_to_string(...))` is redundant.
- **`backend/static/storefront/css/style.css`** differs from `design/style.css` by 13 lines of
  `../fonts/` / `../img/` rewrites plus CRLF stripping. Necessary, but only `.banner` is recorded
  as a deliberate divergence, so a straight re-copy of a designer update will silently break fonts
  and backgrounds. Record the rewrite in the journal or in a header comment.
- **`backend/catalog/management/commands/seed_testdata.py:95-117,212`** - without `--flush` a
  second run raises `IntegrityError` on the country slugs and duplicates the slides.
  `update_or_create` keyed on slug/position would make it re-runnable.
- **`backend/sales/models.py:138`** - the "already paid" log prints `None` when the losing caller's
  instance predates the winning UPDATE; refresh the field or drop the value.
- **`backend/sales/views.py:294-296`** - `order.deliver()` per order in a loop, each a
  `SELECT … FOR UPDATE` plus `bulk_update`; one queryset would be one round trip. **`:110`** calls
  `payload.get("data")` twice in one expression.
- **`frontend/src/components/storefront/LangSwitch.vue:11`** hardcodes `/^\/(en|ru)/` two lines
  under `import {SUPPORT_LOCALES}` - build the regex from the constant.
- **Speculative Generality - `frontend/src/router/index.js:23,29,35,42,49`**: `meta.name` and
  `meta.parent` are set on five routes and read nowhere; `routes.main` in the locale files exists
  only for them. Dead keys alongside: `buttons.buy`, `purchases.page.file`.
- **`frontend/src/views/Product.vue:50-53,95`** builds `listingTarget` and the sidebar from
  `route.params`, not from the loaded product. Django 301s a wrong facet
  (`storefront/views.py:110-115`) but a client-side navigation does not, so the breadcrumb can point
  at a listing the product is not in.
- **`frontend/src/components/storefront/ProductCard.vue:30`** mounts a `CheckoutModal` per card -
  with `PAGE_SIZE = 100` that is 100 modals, each with its own stores and watchers. Hoist one into
  `Catalog.vue`.
- **`frontend/src/router/index.js`** has no route for `/:lang/all/all/`, which the documented URL
  space 301s to `/:lang/`, and no `scrollBehavior`.
- **`frontend/src/i18n/index.js:26`** passes `i18n` as a second argument the signature (`:32`) does
  not declare.
- **`frontend/src/views/Catalog.vue:36`** - `fetchPage('home').catch(() => null)` silently hides a
  failed SEO block, the same silence `docs/module-depth.md` faults `stores/content.js` for.

### On `docs/module-depth.md`

The catalog-listing duplication it records has **already diverged** (finding 6), so it is a live
cloaking bug rather than a latent one - it belongs above the Plisio work in that document's
order-of-work list. Its `storefront/rendering.py` proposal stands. Its "already deep, do not touch"
verdict on `sales/statistics.py` is too generous: findings 8 and the `sold_items` duplication are
both inside that file.

## Spec

Spec sources: `docs/architecture.md` (primary), `CLAUDE.md`, `CONTEXT.md`, `docs/journal.md`. There
is no issue tracker and no separate PRD.

### Launch checklist and open items, as they actually stand

Two checklist items are **blockers**, both reported under Standards above: the cron environment
(finding 2) and `SITE_ID` (finding 1). "Point the `django_site` row at the real domain" is a hard
prerequisite rather than a nicety - until that row matches the `Host` exactly, every storefront page
500s in `seo.build_meta`.

Still open, confirmed against the code:

- one domain - placeholders remain (`frontend/.env.dist:3`, `docker-compose.yaml:79-91` `example.com`)
- payment logos - `design/index.html:537` has `.footer__pays`; neither `base.html:48-61` nor `App.vue` does
- `?year=` filter - absent from `catalog/views.py:64-75`, `views/Catalog.vue` and the bot templates
- tokens in logs - `frontend/nginx/site-body.conf:22` uses the default combined format, nothing stripped
- no 2FA - no `django-otp` in `backend/pyproject.toml`
- slides are not recompressed - `content/models.py:51-80` has no `build_variants`, unlike `catalog/models.py:283`

Everything else on the checklist is in place: `frontend/nginx/ssl/.gitkeep` tracked, `make
nginx-check`, the sitemap index and robots view, the `mail` compose profile, the postgres backup cron.

### Implemented but contradicting the spec

- **Bot pages ignore `?q=`** - architecture.md: "the bot template renders the same data the API
  returns, never more and never less". Detail in Standards finding 6.
- **`CustomerAdmin` stashes the request on the ModelAdmin** - `sales/admin.py:35-37` documents this
  as a fixed bug; `customer/admin.py` does it again. Standards finding 5.
- **Checkout aborts before Plisio can answer** - architecture.md: "`POST /api/order/` calls Plisio
  (30s timeout)" and "never close the payment modal before the request comes back", against a 10s
  client timeout. Standards finding 14.
- **Russian-only `seo_text` never renders in the SPA** - the documented rule is "one property read
  against the active locale with an English fallback". Standards finding 13.

### Documentation drift

- `CLAUDE.md:127-128` and `docs/architecture.md:171` name `Order.mark_paid/deliver/release/
  refresh_download_tokens`, "each `@atomic`; they raise `ValueError`". `release` and
  `refresh_download_tokens` do not exist - token reissue is `OrderItemQuerySet.reissue_tokens`
  (`sales/models.py:175`) - and `mark_paid` (`sales/models.py:124`) is neither `@atomic` nor raising.
- `docs/architecture.md:45` says `access_token` "rotates on every mail that carries it". The
  delivery mail deliberately does not: `sales/views.py:193` calls `ensure_access_token()`, commented
  "Deliberately not a rotation". Only `send-links` rotates.
- `docs/architecture.md` (Broadcasts) says unsubscribe carries "language in `?lang=`".
  `mailing/services.py:35-38` puts it in the path prefix, and `mailing/tests.py:80` asserts the
  absence of `?lang=`.
- `frontend/nginx/00-limits.conf:5` cites "ADR-0001"; `docs/adr/` does not exist.

### Scope creep

None material. Every endpoint, model and admin page traces to a documented decision.

## Not covered

The 320px browser pass `CLAUDE.md` mandates was not run - the reviewers were read-only and did not
start a dev server. `Cart.vue:132` and `Purchases.vue:203` are the only fixed-track grids (both
stack down at 560px) and are the first places to check by hand.
