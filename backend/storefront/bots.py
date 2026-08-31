"""The User-Agent split behind dynamic rendering: bots get Django HTML, people get the SPA."""

import re

from django.http import HttpRequest

# Search crawlers plus the link-preview fetchers of messengers and social networks - none of them
# run JavaScript reliably, so they all get the server-rendered page. Both branches are built from
# the same data on the same URL; the pattern only decides the presentation, never the content.
BOT_UA_RE = re.compile(
    r"googlebot|yandex|bingbot|duckduckbot|baiduspider|applebot|slurp"
    r"|facebookexternalhit|twitterbot|telegrambot|whatsapp|linkedinbot|slackbot|pinterest"
    r"|petalbot|mail\.ru",
    re.IGNORECASE,
)


def is_bot(request: HttpRequest) -> bool:
    return bool(BOT_UA_RE.search(request.headers.get("User-Agent", "")))
