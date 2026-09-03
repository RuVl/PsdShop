# Journal

Traps that cost time and can bite again: what broke, why, and what the fix assumes. Newest first.
The architecture itself is in [`architecture.md`](./architecture.md).

## 2026-08-29 - the Plisio callback signature: `?json=true` is not optional

**Two separate ways every real payment was being refused.**

1. **A form and a JSON body are signed differently.** Without `?json=true` Plisio posts
   `application/x-www-form-urlencoded` and computes `verify_hash` from PHP's `serialize()` of the
   sorted array. Our `validate_hash` computes an HMAC over the JSON string, so a form callback could
   never pass - no amount of fixing the parsing would have helped.
2. **Even in JSON mode we disagreed with Plisio.** The official
   [plisio-python](https://github.com/Plisio/plisio-python) hashes the body **in the order received**
   and with `ensure_ascii=True`; we had `sort_keys=True, ensure_ascii=False`. That matches only if
   Plisio happens to send alphabetical keys and no non-ASCII.

On top of that, when the body *was* a form, `request.data` was a `QueryDict`, whose `copy()` stays a
`QueryDict`: `pop()` returns a **list** and `dict()` wraps every value in a list, so the comparison
was `"abc" == ["abc"]` - always false.

**Fix.** `validate_hash` accepts both readings of the body (as received and key-sorted) - each is
still an HMAC with our key, so nothing can be forged, and the key-order lottery is gone. The body is
normalised once at the top of the view (`request.data.dict()` for a `QueryDict`, `dict(...)`
otherwise). And `callback_url` with `?json=true` now ships with every invoice
(`sales/views.py: callback_url()`) instead of being configured in the dashboard: a parameter that
decides whether any payment is accepted must not rest on someone's memory.

**Why the tests were silent.** They signed the payload with the same function they verified with,
and posted `format="json"` - the shape of a request that production never sends. A test that picks
its own convenient request format tests itself, not the integration. For an external webhook the
request format is part of the contract and belongs in the test: the current ones post a form and
sign the way the SDK signs (keys out of alphabetical order, a Cyrillic value).

**Cost.** In dev `callback_url` is built from the `django_site` row (`localhost:8000`), which Plisio
cannot reach, so local payments are still exercised with a forged signed callback.

## 2026-08-29 - security review: what was left alone, and why

Deliberate trade-offs, so they do not get "fixed" by accident later:

- **The callback has no authentication** - that is how Plisio works, a signature instead of a
  session. The body influences nothing except through `callback_to_fields` and `apply_order_status`.
- **Checkout has no CSRF.** DRF's `APIView` is csrf_exempt and the buyer is anonymous, so there is
  nothing to protect but our own spend - which is what the `limit_req` zone, `MAX_ORDER_ITEMS` and
  the MX check cover.
- **`/api/send-links/` does confirm that an address has purchases** (404 vs 200). Without it the
  recovery form cannot tell someone they mistyped their address. Rate limited to 5 r/m.
- **Token guessing is pointless**: UUID4, 24h TTL, the same 404 for unknown, malformed and expired,
  and `refresh` scoped by customer (`of_customer`).

Fixed at the same time, and easy to regress: the callback HMAC is compared with
`hmac.compare_digest`; the Plisio key travels in a query string and `requests` puts the full URL in
the exception text, so log writes go through `redact()` (a test fails the build if the key reappears
in a log record); `/admin/login/` has its own `limit_req` zone, because Django does not lock an
account after failed attempts; and DRF's browsable renderer - a writable HTML form on every endpoint
- is enabled under `DEBUG` alone.

## 2026-08-30 - numbered pages instead of infinite scroll

The owner asked to drop infinite scroll ("it just causes more bugs") and asked why `?page=` did not
match what was on screen.

**Why it kept breaking.** Holding a *range* of pages needs a scroll anchor, two
`IntersectionObserver`s and a guess at the reader's direction - and `?page=` still described "how
much is loaded", not "what is visible". Three attempts produced four different bugs: a freshly
rendered page is short (images have not loaded), so the "load previous" block is on screen, the
observer honestly reports it and the reader is dragged to the page above the one they asked for;
`style.css` sets `scroll-behavior: smooth` on `<html>`, so `scrollIntoView` animated and died on the
reader's first wheel; and the anchor was the grid itself, whose top moves on every insert.

**What replaced it.** One page on screen and the same page in the address. The value that used to
drift is now the server's: `CatalogPagination` returns `total_pages`, so the SPA holds no copy of
the page size (one copy did drift - `PAGE_SIZE = 24` in the view against 100 in the API - and the
grid offered pages the API answered 404 for). `Pagination.vue` is a port of
`Paginator.get_elided_page_range(on_each_side=1, on_ends=1)`, verified against the bot page by
walking 1..12 pages, so both presentations print the same numbers at the same addresses.

**Cost.** No skimming the whole catalog in one gesture, and one request per page.

## 2026-08-30 - the banner was rewritten instead of ported

The mockup's rounded panel is a fake: two white gradient strips over the top edge and two
`box-shadow: 0 0 0 30px #fff` masks at the corners. It only works on a white page and it paints over
the slide. The `.swiper-*` classes carried assumptions of a plugin we do not ship (it measured
height in JavaScript on init), and the arrow styling in `style.css` only colours them - `position`,
`z-index` and the chevron itself came from `swiper-bundle.css`.

So `.banner` in `shop.css` is ours: a real `border-radius` with `overflow: hidden`, slides in one
grid cell so the height is the tallest slide's and never jumps. **This is the one place where our
markup deliberately diverges from `design/index.html`** - a change from the designer has to be
carried into `.banner` by hand.

On phones the shared height is what hurts: a short slide shows the gap. It is fixed by making the
tallest slide shorter (smaller image, smaller type, tighter padding) rather than by pinning a
height, and `.banner__body` needs `flex: 0 0 auto` - with `1 1 auto` it eats the free height and
leaves an empty purple band under the text.

## 2026-08-29 - the sitemap is an index, and robots.txt is a view

Splitting into `/sitemap-<section>.xml` was not cosmetic: an overflow test showed that
`Sitemap.limit` applies **per section**, so with a limit of 10 the combined file served 24 URLs.
One file over four sections could quietly pass the protocol's 50 000 while every section looked
"within limits".

`django.contrib.sitemaps` with `i18n`, `alternates` and `x_default` is used rather than a generator
of our own, because the framework already walks items once per language and reverses with the active
language - exactly what `i18n_patterns` does - and a hand-written one would drift away from
`storefront/seo.py`, which builds the same hreflang set for `<head>`.

`robots.txt` is a Django view (`content_type="text/plain"`) so its `Sitemap:` line comes from
`backend.sites.absolute_url`: the domain and scheme already live in one place (`django_site` +
`SITE_SCHEME`), and a static file or an nginx `location` would duplicate that knowledge.

**Watch out:** the framework builds `x-default` by removing the language prefix (`/en/info/` →
`/info/`), i.e. it points at an address that answers 302, not 200. That is standard practice and
`seo.x_default` repeats the same formula, but the redirect has to be verified by hand.

## 2026-08-29 - `make dev-frontend` served nothing

Vite applies `base` in dev too, and `server.proxy` sent all of `/static` - including the dev
server's own base - to Django, where only the `make spa` build lives. The fix is to apply `base`
only when `mode === 'production'`, vite's own idiom, already used there for `__API_URL__`.

A second bug hid behind it: vue-router starts its first navigation from `install()`, so the
`/` → `/en/` redirect asked the language store for an answer before pinia was active. Pinia is now
registered before the router in `main.js`. Production never showed it, because there Django
redirects the bare root.

**Cost.** Asset URLs differ between dev and production; reproduce production paths with `make spa`,
not with the dev server.

## 2026-08-31 - a storage without `base_url` breaks the admin file widget

`/admin/catalog/product/<id>/change/` answered 500 with
`ValueError: This file is not accessible via a URL.` `ProductFilesStorage` has no `base_url` on
purpose - a paid file is only reachable through `DownloadFileView` - but `AdminFileWidget` asks for
the URL twice: `is_initial()` in Python and `<a href="{{ widget.value.url }}">` in the template.

`catalog/admin.py: ProductFileInput` subclasses **`AdminFileWidget`** (not a bare
`ClearableFileInput`, which loses the admin template, the `file-upload` class and `use_fieldset`),
overrides `is_initial()` with an `isinstance(value, FieldFile)` check and computes `value_url` in
Python; the template is a copy of the admin's with the link made conditional. The link is
conditional rather than removed because `ImageField` subclasses `FileField`, so
`formfield_overrides` would also catch a preview field if one is ever added to `Product`, and the
check is on the fact (`try: value.url`) rather than on the storage class - S3-style storages do not
set `base_url` either.

**Cost.** That template is an upstream copy minus one condition, so a widget markup change in Django
will pass it by. Any new `FileField` on a private storage inherits this problem.

## 2026-09-03 - `SITE_ID` under `DEBUG` only: the whole site 500s on a fresh deploy

Every page of the first deploy, `/admin/login/` included, answered 500 with
`Site.DoesNotExist: Site matching query does not exist.` `SITE_ID = 1` was set inside the
`if DEBUG:` block, so in production `Site.objects.get_current(request)` (`backend/sites.py`, and
Django's own `get_current_site` in the admin login view) fell back to resolving the site by the
request's `Host`. Nothing in the database matched that host, and the row could only be created in
the admin - which was the page refusing to open. `django.contrib.sites` is in `INSTALLED_APPS`, so
the `RequestSite` fallback Django has for that function never applies.

The same gap killed broadcasts silently: `make_unsubscribe_url` is called from the cron command with
no request at all, where a missing `SITE_ID` raises `ImproperlyConfigured` instead - once per
recipient, each one swallowed into a FAILED delivery row.

`SITE_ID = 1` is now unconditional, `storefront/migrations/0001_ensure_site.py` guarantees the row
exists on an older database, and a `Tags.database` check warns at `migrate` time while the domain is
still `example.com` - the point being that the placeholder does not 500, it silently mails links to
example.com.

**Cost.** The domain is still a manual step in the admin; the check is the only thing that shouts
about it. A test that only ever runs with `DEBUG=True` cannot see any of this - `mailing/tests.py`
had been creating the site row at pk=1 by hand, which is exactly what hid the bug.

## 2026-09-03 - cron in the backend container had no environment

`backend/cronjob` called `manage.py` directly and `startup.sh` only did `service cron start`. Cron
strips the environment, the backend's settings come from compose `env_file`, and `settings.py` reads
`os.environ` alone - so every broadcast run and every callback prune died at import on
`SECRET_KEY`. Nothing logged it anywhere anybody looked.

`startup.sh` now dumps the environment to `/etc/psdshop-cron.env` (`chmod 600`) and each crontab
line sources it, which is what `postgres/entrypoint.sh` had already been doing for `backup.sh` since
the beginning - the pattern existed one directory away. The dump is `compgen -e`, not a named list,
so a new setting cannot quietly break the sender months later; the crontab sets `SHELL=/bin/bash`
because `printf %q` quoting is bash's.

**Cost.** Two containers now solve this the same way in two places. If a third ever needs cron,
extract the dump instead of copying it a third time.

## 2026-09-03 - `style.css` is a copy of the mockup plus thirteen rewritten paths

`CLAUDE.md` says our copy of the designer's stylesheet stays a copy, with `.banner` as the one
deliberate divergence. It is not quite the whole story, and the missing half is the kind that
breaks silently: the design serves `style.css` from the same directory as `fonts/` and `img/`,
while ours lives in `static/storefront/css/`, so every asset URL in it is rewritten one level up
(`url("fonts/…")` -> `url("../fonts/…")`). Thirteen lines, and the CRLF line endings stripped.

Verified with `diff <(tr -d '\r' < design/style.css) <(tr -d '\r' < backend/storefront/static/storefront/css/style.css)`:
those rewrites are the *only* difference - no rule, colour or breakpoint of the mockup has been
touched, which is what the rule is really protecting.

**Cost.** Re-copying an updated `style.css` from the designer without redoing the rewrite loses
every font and every background image, and nothing fails - the page just renders in a fallback
font. Run that diff after any re-copy: anything in it other than `url(` lines is an accident.

## 2026-09-03 - Django stamped the machine hostname into every outgoing e-mail

The first live SendPulse test arrived with `standard-intel-de-1-v-2-7005287-516006-main` in the
body, which is only the text of Django's own `sendtestemail`. The leak underneath it is not:
`django/core/mail/utils.py` caches `socket.getfqdn()` in `DNS_NAME`, and two call sites use it on
*every* message - `message.py` builds `Message-ID: <...@that-hostname>` and the SMTP backend hands
it to the relay as the EHLO name, which SendPulse then writes into a `Received:` header. Both
travel to the recipient in the raw source.

Beyond the ugliness, a `Message-ID` whose domain does not match `From:` is a spam signal, and in
production the name would have been the container id - different on every rebuild.

`settings.py` now pins `DNS_NAME._fqdn` to `EMAIL_FQDN`, which defaults to the domain of
`DEFAULT_FROM_EMAIL`, so the two cannot drift apart without someone setting the override on
purpose. `docker-compose.yaml` also names the backend container, but that is for logs only - it is
not what protects the header.

**Cost.** The default is only as good as `DEFAULT_FROM_EMAIL`: left at the `.env.dist` placeholder
it stamps `example.com`, which is worse than a hostname. Check the header itself after any change
to the sender address - Gmail, "Show original", the `Message-ID` line.
