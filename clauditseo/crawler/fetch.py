from __future__ import annotations

import time

import httpx

from .types import USER_AGENT, Page

#: What a browser says it accepts when it navigates to a page - Chromium's
#: own - so the crawler is served the page a visitor is (item 241). A site
#: whose cache or image plugin varies on `Accept` otherwise hands the crawler
#: one page and the image pass's browser another: twenty22 served `.png`
#: files to a request that named no WebP and `.png.webp` to Chromium, from
#: two cached copies that did not even agree on the call-to-action image, so
#: the browser's measurements joined to none of the crawler's records.
BROWSER_ACCEPT = ("text/html,application/xhtml+xml,application/xml;q=0.9,"
                  "image/avif,image/webp,image/apng,*/*;q=0.8")


class Fetcher:
    """Thin wrapper around httpx with an identifiable user agent, redirect
    tracking, and a per-request timeout. One instance per crawl."""

    def __init__(self, timeout_s: float, user_agent: str = USER_AGENT):
        self.user_agent = user_agent
        self._client = httpx.Client(
            headers={"User-Agent": user_agent, "Accept": BROWSER_ACCEPT},
            timeout=timeout_s,
            follow_redirects=True,
            max_redirects=10,
        )

    def fetch(self, url: str) -> Page:
        started = time.monotonic()
        try:
            resp = self._client.get(url)
        except httpx.HTTPError as exc:
            return Page(url=url, requested_url=url, status=0,
                        elapsed_ms=(time.monotonic() - started) * 1000,
                        error=f"{type(exc).__name__}: {exc}")
        content_type = resp.headers.get("content-type", "")
        is_text = content_type.startswith(("text/", "application/xml",
                                           "application/xhtml", "application/rss",
                                           "application/json"))
        return Page(
            url=str(resp.url),
            requested_url=url,
            status=resp.status_code,
            # Every Set-Cookie, one per line: a dict of the response's items
            # kept only the last, and `SEC/cookie-flags` must see each cookie
            # (item 143 step BD). The key and its string type are unchanged.
            headers={**{k.lower(): v for k, v in resp.headers.items()},
                     **({"set-cookie": "\n".join(resp.headers.get_list("set-cookie"))}
                        if len(resp.headers.get_list("set-cookie")) > 1 else {})},
            content=resp.text if is_text else "",
            content_type=content_type,
            elapsed_ms=(time.monotonic() - started) * 1000,
            redirect_chain=[str(r.url) for r in resp.history],
            # The status code of each hop, parallel to redirect_chain (item 137,
            # FEATURES F-13). Kept beside the URLs rather than folded into them
            # so nothing that reads redirect_chain as a URL list changes; it is
            # what lets `redirect-temporary` tell a 302 from a 301. Absent on
            # runs crawled before this, and the check simply does not fire there.
            redirect_statuses=[r.status_code for r in resp.history],
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "Fetcher":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
