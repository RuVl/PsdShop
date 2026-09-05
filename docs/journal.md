# Journal

Traps that cost time and can bite again: what broke, why, and what the fix assumes. Newest first.
The architecture itself is in [`architecture.md`](./architecture.md).

## 2026-09-04 - the type filter wrapped, and the purchases page had no entrance

**The type facet.** `style.css` draws it as right-aligned wrapping 12px links
(`.filter-products-card-list`, `justify-content: flex-end`): three seeded types look like the
mockup, fourteen become three ragged rows that push the grid down and shift on every language switch
(Russian names are longer). Of four replacements compared on real data the clamped grid won -
nothing moves, one click to anything, the whole list in the DOM for the crawler. It is
`.type-filter__grid` in `shop.css` (both presentations link it) plus
`components/storefront/DocumentTypeFilter.vue`. The clamp is a `max-height`; the "Show all (N)"
button appears only if **measured** (`scrollHeight - clientHeight`), not counted - at 320px one long
name fills a row of its own, so "more than N chips" is a different question from "is there a third
row". The bot page renders the chips uncollapsed: no script to press a button with, and the links
must be on the page anyway.

**The purchases page.** `/<lang>/purchases/` - the form that re-sends the delivery link - was routed
in both presentations and linked from nothing but the e-mail, the very thing its user has lost. Now
a header menu entry and a footer line (`App.vue`, `storefront/base.html`).

**Cost.** The chips are the second place after the sidebar where `.current` is ours, not the
design's: a rename in `shop.css` silently takes the selected state with it. The button is SPA-only -
on the bot page the clamp has to become a CSS-only disclosure.

## 2026-09-03 - Django stamped the machine hostname into every outgoing e-mail

`django/core/mail/utils.py` caches `socket.getfqdn()` in `DNS_NAME`, and it reaches every message
twice: `message.py` builds `Message-ID: <...@that-hostname>`, and the SMTP backend hands it to the
relay as the EHLO name, which SendPulse writes into `Received:`. Both travel to the recipient in the
raw source (found in the first live test). A `Message-ID` domain that does not match `From:` is a
spam signal, and in production the name would be the container id - different on every rebuild.

`settings.py` pins `DNS_NAME._fqdn` to `EMAIL_FQDN`, defaulting to the domain of
`DEFAULT_FROM_EMAIL`, so the two cannot drift without a deliberate override. The container name in
`docker-compose.yaml` is for logs, not protection.

**Cost.** Only as good as `DEFAULT_FROM_EMAIL`: at the `.env.dist` placeholder it stamps
`example.com`, worse than a hostname. Check the header after any sender change - Gmail, "Show
original", the `Message-ID` line.

## 2026-09-03 - `style.css` is a copy of the mockup plus thirteen rewritten paths

`.banner` is not the only divergence, and the other one breaks silently: the design serves
`style.css` beside `fonts/` and `img/`, ours lives in `static/storefront/css/`, so every asset URL
moves one level up (`url("fonts/…")` -> `url("../fonts/…")`). Thirteen lines, plus stripped CRLF.
`diff <(tr -d '\r' < design/style.css) <(tr -d '\r' < backend/storefront/static/storefront/css/style.css)`
proves those are the *only* difference - no rule, colour or breakpoint touched, which is what the
rule really protects.

**Cost.** Re-copying an updated `style.css` without redoing the rewrite loses every font and
background image, and nothing fails - the page renders in a fallback font. Run that diff after any
re-copy: anything but `url(` lines is an accident.

## 2026-09-03 - cron in the backend container had no environment

`backend/cronjob` called `manage.py` directly and `startup.sh` only did `service cron start`. Cron
strips the environment, the settings come from compose `env_file`, and `settings.py` reads
`os.environ` alone - so every broadcast run and every callback prune died at import on `SECRET_KEY`,
logged nowhere anybody looked.

`startup.sh` dumps the environment to `/etc/psdshop-cron.env` (`chmod 600`) and each crontab line
sources it - what `postgres/entrypoint.sh` had done for `backup.sh` from the start, one directory
away. The dump is `compgen -e`, not a named list, so a new setting cannot quietly break the sender
months later; the crontab sets `SHELL=/bin/bash` because `printf %q` quoting is bash's.

**Cost.** Two containers, the same solution in two places. A third needs it extracted, not copied.

## 2026-09-03 - `SITE_ID` under `DEBUG` only: the whole site 500s on a fresh deploy

Every page of the first deploy, `/admin/login/` included, answered 500 with
`Site.DoesNotExist: Site matching query does not exist.` `SITE_ID = 1` sat inside `if DEBUG:`, so
production resolved the site by the request's `Host` (`backend/sites.py`, and the admin login view's
`get_current_site`). Nothing in the database matched, and the row could only be created in the admin
- the page refusing to open. `django.contrib.sites` is in `INSTALLED_APPS`, so Django's
`RequestSite` fallback never applies. The same gap killed broadcasts silently:
`make_unsubscribe_url` runs from cron with no request, where a missing `SITE_ID` raises
`ImproperlyConfigured` - once per recipient, each swallowed into a FAILED delivery row.

`SITE_ID = 1` is unconditional now, `storefront/migrations/0001_ensure_site.py` guarantees the row
on an older database, and a `Tags.database` check warns at `migrate` time while the domain is still
`example.com` - the placeholder does not 500, it silently mails links to example.com.

**Cost.** The domain is still a manual admin step; the check is the only thing that shouts about it.
Tests that run only with `DEBUG=True` cannot see this - `mailing/tests.py` created the pk=1 site row
by hand, which is what hid the bug.

## 2026-08-31 - a storage without `base_url` breaks the admin file widget

`/admin/catalog/product/<id>/change/` answered 500 with
`ValueError: This file is not accessible via a URL.` `ProductFilesStorage` has no `base_url` on
purpose - a paid file exits only through `DownloadFileView` - but `AdminFileWidget` asks for the URL
twice: `is_initial()` in Python and `<a href="{{ widget.value.url }}">` in the template.

`catalog/admin.py: ProductFileInput` subclasses **`AdminFileWidget`** (a bare `ClearableFileInput`
loses the admin template, the `file-upload` class and `use_fieldset`), overrides `is_initial()` with
an `isinstance(value, FieldFile)` check and computes `value_url` in Python; the template is the
admin's copy with the link made conditional. Conditional rather than removed, because `ImageField`
subclasses `FileField` - `formfield_overrides` would also catch a preview field if one is added to
`Product` - and the check is on the fact (`try: value.url`), not the storage class: S3-style
storages have no `base_url` either.

**Cost.** An upstream template copy minus one condition, so a Django markup change passes it by. Any
new `FileField` on a private storage inherits the problem.

## 2026-08-30 - numbered pages instead of infinite scroll

The owner asked to drop infinite scroll ("it just causes more bugs") and why `?page=` did not match
what was on screen.

**Why it kept breaking.** Holding a *range* of pages needs a scroll anchor, two
`IntersectionObserver`s and a guess at the reader's direction - and `?page=` still meant "how much
is loaded", not "what is visible". Three attempts, four bugs: a freshly rendered page is short
(images have not loaded), so the "load previous" block is on screen, the observer honestly reports
it and the reader is dragged one page up; `style.css` sets `scroll-behavior: smooth` on `<html>`, so
`scrollIntoView` animated and died on the first wheel; and the anchor was the grid itself, whose top
moves on every insert.

**What replaced it.** One page on screen, the same page in the address. The drifting value is the
server's now: `CatalogPagination` returns `total_pages`, so the SPA keeps no copy of the page size
(one copy did drift - `PAGE_SIZE = 24` in the view against 100 in the API - and the grid offered
pages the API answered 404 for). `Pagination.vue` ports
`Paginator.get_elided_page_range(on_each_side=1, on_ends=1)`, verified against the bot page over
1..12 pages, so both presentations print the same numbers at the same addresses.

**Cost.** No skimming the whole catalog in one gesture, and one request per page.

## 2026-08-30 - the banner was rewritten instead of ported

The mockup's rounded panel is a fake: two white gradient strips over the top edge and two
`box-shadow: 0 0 0 30px #fff` corner masks - it only works on a white page and it paints over the
slide. The `.swiper-*` classes assumed a plugin we do not ship (height measured in JavaScript on
init), and `style.css` only colours the arrows: `position`, `z-index` and the chevron came from
`swiper-bundle.css`.

So `.banner` in `shop.css` is ours: a real `border-radius` with `overflow: hidden`, slides in one
grid cell so the height is the tallest slide's and never jumps. **This is the one place where our
markup deliberately diverges from `design/index.html`** - a designer change has to be carried in by
hand.

On phones the shared height shows a gap under short slides. Fix it by shrinking the tallest slide
(smaller image, smaller type, tighter padding), not by pinning a height; `.banner__body` needs
`flex: 0 0 auto` - with `1 1 auto` it eats the free height and leaves an empty purple band.

## 2026-08-29 - the Plisio callback signature: `?json=true` is not optional

**Two separate ways every real payment was being refused.**

1. **Form and JSON bodies are signed differently.** Without `?json=true` Plisio posts
   `application/x-www-form-urlencoded` and computes `verify_hash` from PHP's `serialize()` of the
   sorted array; our `validate_hash` HMACs the JSON string, so a form callback could never pass - no
   fixing of the parsing would have helped.
2. **Even in JSON mode we disagreed with Plisio.** The official
   [plisio-python](https://github.com/Plisio/plisio-python) hashes the body **in the order received**
   with `ensure_ascii=True`; we had `sort_keys=True, ensure_ascii=False` - a match only for
   alphabetical keys and pure ASCII.

And on a form body `request.data` was a `QueryDict`, whose `copy()` stays one: `pop()` returns a
**list** and `dict()` wraps every value in a list, so the comparison was `"abc" == ["abc"]`.

**Fix.** `validate_hash` accepts both readings of the body (as received and key-sorted) - each is
still an HMAC with our key, so nothing can be forged and the key-order lottery is gone. The body is
normalised once at the top of the view (`request.data.dict()` for a `QueryDict`, `dict(...)`
otherwise), and `callback_url` ships `?json=true` with every invoice
(`sales/views.py: callback_url()`) instead of living in the dashboard: a parameter that decides
whether any payment is accepted must not rest on someone's memory.

**Why the tests were silent.** They signed the payload with the function they verified with and
posted `format="json"` - a request shape production never sends. A test that picks its own
convenient format tests itself, not the integration; for an external webhook the request format is
part of the contract. The current tests post a form and sign the way the SDK signs (keys out of
alphabetical order, a Cyrillic value).

**Cost.** In dev `callback_url` comes from the `django_site` row (`localhost:8000`), which Plisio
cannot reach, so local payments still need a forged signed callback.

## 2026-08-29 - security review: what was left alone, and why

Deliberate trade-offs, so they do not get "fixed" by accident later:

- **The callback has no authentication** - that is how Plisio works, a signature instead of a
  session. The body influences nothing except through `callback_to_fields` and `apply_order_status`.
- **Checkout has no CSRF.** DRF's `APIView` is csrf_exempt and the buyer anonymous, so there is
  nothing to protect but our own spend - covered by the `limit_req` zone, `MAX_ORDER_ITEMS` and the
  MX check.
- **`/api/send-links/` does confirm that an address has purchases** (404 vs 200); without it the
  recovery form cannot tell someone they mistyped. Rate limited to 5 r/m.
- **Token guessing is pointless**: UUID4, 24h TTL, the same 404 for unknown, malformed and expired,
  `refresh` scoped by customer (`of_customer`). The owner asked again on 2026-09-05, so the
  arithmetic is written down: uuid4 is `os.urandom`, 122 bits, 5.3e36 values; a scan at 10k req/s
  for a year covers 6e-26 of the space. The risk is a leaked link, not enumeration - which the 24h
  TTL and the rotation in `SendDownloadLinksView` answer. `/api/purchases/` and `/api/files/` got
  the `tokenscan` zone anyway (120 r/m, burst 40): not a defence - it defends nothing that 122 bits
  do not - but so a scanner cannot fill the log and the database with the attempt. The burst is the
  honest worst case: open the page, refresh every link, pull all `MAX_ORDER_ITEMS` files. Django 6
  already sends `Referrer-Policy: same-origin`, so the token does not travel off-site in a
  `Referer`; do not loosen `SECURE_REFERRER_POLICY` thinking it is a hardening.

Fixed at the same time, and easy to regress: the callback HMAC is compared with
`hmac.compare_digest`; the Plisio key travels in a query string and `requests` puts the full URL in
the exception text, so log writes go through `redact()` (a test fails the build if the key reappears
in a log record); `/admin/login/` has its own `limit_req` zone, because Django does not lock an
account after failed attempts; and DRF's browsable renderer - a writable HTML form on every endpoint
- is enabled under `DEBUG` alone.

## 2026-08-29 - the sitemap is an index, and robots.txt is a view

Splitting into `/sitemap-<section>.xml` was not cosmetic: an overflow test showed `Sitemap.limit`
applies **per section**, so with a limit of 10 the combined file served 24 URLs. One file over four
sections could quietly pass the protocol's 50 000 while every section looked "within limits".

`django.contrib.sitemaps` with `i18n`, `alternates` and `x_default` beats a generator of our own:
the framework already walks items once per language and reverses with the active language - exactly
what `i18n_patterns` does - and a hand-written one would drift away from `storefront/seo.py`, which
builds the same hreflang set for `<head>`. `robots.txt` is a Django view
(`content_type="text/plain"`) so its `Sitemap:` line comes from `backend.sites.absolute_url`: domain
and scheme already live in one place (`django_site` + `SITE_SCHEME`), and a static file or an nginx
`location` would duplicate that knowledge.

**Watch out:** the framework builds `x-default` by removing the language prefix (`/en/info/` →
`/info/`), i.e. an address that answers 302, not 200. That is standard practice and `seo.x_default`
repeats the formula, but the redirect has to be verified by hand.

## 2026-08-29 - `make dev-frontend` served nothing

Vite applies `base` in dev too, and `server.proxy` sent all of `/static` - including the dev
server's own base - to Django, where only the `make spa` build lives. The fix is to apply `base`
only when `mode === 'production'`, vite's own idiom, already used there for `__API_URL__`.

A second bug hid behind it: vue-router starts its first navigation from `install()`, so the
`/` → `/en/` redirect asked the language store before pinia was active. Pinia is now registered
before the router in `main.js`. Production never showed it - there Django redirects the bare root.

**Cost.** Asset URLs differ between dev and production; reproduce production paths with `make spa`,
not with the dev server.
