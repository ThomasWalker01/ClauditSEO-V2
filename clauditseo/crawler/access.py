"""What one audit may do at a site's firewall: wait once, and show a pass the
owner gave it.

A CDN's bot protection can refuse the headless browser while the crawl's plain
requests pass. This module never disguises the audit. It pauses and asks again
once, it checks the browser before the crawl's burst of requests, and where the
site's owner issued a header it sends that header to that site and nowhere else.

The header is held by `secrets.py`, not the database, so a backup carries none,
and it never reaches a third party: a page's scripts, images and analytics load
from other hosts, and `set_extra_http_headers` would hand the secret to each.
"""

from __future__ import annotations

import logging
import os
import time
from contextvars import ContextVar
from dataclasses import dataclass
from urllib.parse import urlsplit

from clauditseo import secrets

from .types import BrowserChallenged

log = logging.getLogger("clauditseo.access")

#: How long a refused browser waits before asking again, once.
RETRY_WAIT_S = 300


@dataclass
class RunAccess:
    host: str
    header: tuple[str, str] | None = None
    #: Set once the firewall has refused after the wait, or before the crawl:
    #: the browser passes after it do not ask again.
    refused: BrowserChallenged | None = None
    say: object = None


_run: ContextVar[RunAccess | None] = ContextVar("site_access", default=None)


def _bare(host: str) -> str:
    host = (host or "").lower()
    return host[4:] if host.startswith("www.") else host


def open_run(site_id: str, domain: str, say=None) -> RunAccess:
    """Start one run's access on this thread. A run has a thread of its own."""
    host = urlsplit(domain if "//" in domain else f"//{domain}").hostname or domain
    run = RunAccess(host=_bare(host), header=secrets.site_header(site_id), say=say)
    _run.set(run)
    return run


def _is_the_site(run: RunAccess, url: str) -> bool:
    return _bare(urlsplit(url).hostname or "") == run.host


def _attach(request) -> None:
    """Every request, redirects included: httpx copies a request's headers onto
    the redirect it follows, wherever that goes."""
    run = _run.get()
    if run is None or run.header is None:
        return
    name, value = run.header
    request.headers.pop(name, None)
    if _is_the_site(run, str(request.url)):
        request.headers[name] = value


def event_hooks() -> dict:
    """For an httpx client that talks to the site."""
    return {"request": [_attach]}


def install(target) -> None:
    """Send the pass from a Playwright context or page, to the site alone."""
    run = _run.get()
    if run is None or run.header is None:
        return
    name, value = run.header

    def add(route):
        if _is_the_site(run, route.request.url):
            route.continue_(headers={**route.request.headers, name: value})
        else:
            route.continue_()
    target.route("**/*", add)


def retried(load):
    """`load()`, asked again once after a pause if a firewall refused it."""
    run = _run.get()
    if run is None:
        return load()
    if run.refused is not None:
        raise run.refused
    try:
        return load()
    except BrowserChallenged as refused:
        if run.say:
            run.say(f"{refused.vendor} bot protection refused the browser: "
                    f"waiting {RETRY_WAIT_S // 60} minutes to ask once more")
        time.sleep(RETRY_WAIT_S)
    try:
        return load()
    except BrowserChallenged as refused:
        run.refused = refused
        if run.say:
            run.say(f"{refused.vendor} bot protection refused the browser again: "
                    "the browser checks stop here")
        raise


def refused_by() -> str | None:
    """The vendor that stopped this run's browser, stored with the run."""
    run = _run.get()
    return run.refused.vendor if run is not None and run.refused is not None else None


def each_page(urls, visit, on_error) -> dict:
    """`visit` over `urls`, stopping at a firewall, which every later page would
    only meet again. Any other failure is that page's own."""
    out: dict = {}
    for url in urls:
        try:
            out[url] = retried(lambda: visit(url))
        except BrowserChallenged as refused:
            log.warning("browser pass stopped: %s", refused)
            break
        except Exception as error:                # noqa: BLE001 - one page's
            on_error(url, error)
    return out


def probe_browser(start_url: str) -> str | None:
    """One browser load before the crawl, the vendor where it was refused.

    The browser passes read the crawl's pages, so they cannot run ahead of it.
    This is the part that can: a firewall already refusing the browser is known
    before the crawl, and the passes then spend nothing on it. It is switched off
    with the trace pass, since a suite cannot launch a browser per fixture audit.
    """
    from clauditseo.renderer import Renderer

    run = _run.get()
    if run is None or os.environ.get("CLAUDITSEO_TRACE_PERF", "1") in ("0", "", "false", "no"):
        return None
    renderer = Renderer()
    if not renderer.available():
        return None
    try:
        renderer.render(start_url)
    except BrowserChallenged as refused:
        run.refused = refused
        if run.say:
            run.say(f"{refused.vendor} bot protection refused the browser before the "
                    "crawl: the browser checks will not run")
        return refused.vendor
    except Exception as error:                    # noqa: BLE001 - a look, not a gate
        log.warning("browser probe failed: %s", error)
    return None
