"""The operator's mark reaches the screen on an installation that has a token.

UX-30, carried at High since report 034. `/api/brand` answers `icon_href` with
`/api/brand/logo?v=<stamp>`, and two places hand that path straight to the
browser: `favicon.ts` sets it as the `href` of `<link rel="icon">`, and the
admin panel's preview sets it as the `src` of an `<img>`. Neither is a call
made by `api.ts`, so neither carries `Authorization: Bearer <token>` — and
`serve_brand_logo` is declared `operator=op_dep`. The branded icon and the
preview are both a 401 the operator never sees an error for.

**Why nobody hit it while building the feature.** `auth` returns `None` — full
access — when no config token is set and no operator holds one, which is every
development install. The defect needs a credential to exist before it appears,
so the fixture here registers an operator, which is what makes these clauses
able to fail at all.

The two driven clauses reproduce what a browser does rather than assert what
the source says: a subresource load is an unauthenticated `fetch` of whatever
href the element carries, and a broken `<img>` reports `naturalWidth` 0.
`test_the_logo_route_still_refuses_an_unauthenticated_request` is the floor —
it passes on both trees, and it is what makes the other clauses mean anything,
because the moment that route stops needing a token the defect is gone for a
reason nobody chose.
"""

from __future__ import annotations

import re
import socket
import struct
import threading
import time
import zlib
from pathlib import Path

import httpx
import pytest

from clauditseo import axe
from tests.test_a11y_rendered import DIST

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"


def live(fn):
    """The two conditions the driven clauses need, applied per test.

    Per-test rather than module-level, for the reason `test_heading_fault.py`
    records: a module mark would take the static clauses with it, and those are
    the ones that must keep running in the browserless CI job.
    """
    fn = pytest.mark.skipif(
        not (DIST / "index.html").is_file(),
        reason="dashboard not built (npm run build in dashboard/)")(fn)
    return pytest.mark.skipif(
        not axe.available(),
        reason="needs clauditseo[render] and `playwright install chromium`")(fn)


def _png(width: int = 4, height: int = 4) -> bytes:
    """A real PNG, built rather than pasted.

    It has to decode: `naturalWidth` is 0 for a truncated file exactly as it is
    for a 401, so a fixture that is only PNG-shaped would make that clause pass
    for the wrong reason and fail for the wrong reason too.
    """
    def chunk(kind: bytes, body: bytes) -> bytes:
        return (struct.pack(">I", len(body)) + kind + body
                + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF))

    raw = b"".join(b"\x00" + b"\xff\x00\x00" * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b""))


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def guarded_server(tmp_path_factory):
    """A real server that requires a token, holding a registered logo.

    A real port rather than `TestClient`, for the reason `test_a11y_rendered`
    gives: the browser has to fetch the bundle over HTTP. The operator is
    created before the server starts, so `any_operator_tokens` is true for
    every request the browser makes.
    """
    import uvicorn

    from clauditseo import brand
    from clauditseo.api.app import create_app
    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate
    from clauditseo.persistence import repo

    db = tmp_path_factory.mktemp("branded-icon") / "clauditseo.db"
    conn = connect(db)
    migrate(conn)
    _id, token = repo.create_operator(conn, "Round 095", role="owner")
    brand.set_logo(conn, _png(), db.parent / "brand")
    conn.close()

    app = create_app(db_path=db)
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 30
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    if not server.started:
        pytest.fail("server did not start")
    try:
        yield f"http://127.0.0.1:{port}", token
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@pytest.fixture()
def signed_in(guarded_server):
    """A browser page holding the operator's token, as a signed-in one does."""
    from playwright.sync_api import sync_playwright

    base, token = guarded_server
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page(viewport={"width": 1280, "height": 900})
        pg.add_init_script(
            "localStorage.setItem('clauditseo:token', " + repr(token) + ")")
        try:
            yield pg, base
        finally:
            browser.close()


# --- the floor: it passes on both trees, and the rest rests on it -----------

def test_the_logo_route_still_refuses_an_unauthenticated_request(guarded_server):
    """The counter-assertion. Not a thing this round changes — a thing the two
    clauses below are only evidence *because of*."""
    base, token = guarded_server
    bare = httpx.get(base + "/api/brand/logo", timeout=30)
    assert bare.status_code == 401, (
        "the logo route answered an unauthenticated request with "
        f"{bare.status_code}; if that is deliberate then UX-30 has been closed "
        "by opening the route, which is a decision and not a fix")
    with_token = httpx.get(base + "/api/brand/logo", timeout=30,
                           headers={"Authorization": "Bearer " + token})
    assert with_token.status_code == 200, with_token.text
    assert with_token.headers["content-type"] == "image/png", (
        "the fixture logo is not being served as the image it is, so a "
        "browser-level assertion below would be measuring the wrong thing")


# --- the tab icon ----------------------------------------------------------

@live
def test_the_tab_icon_is_something_the_browser_can_actually_load(signed_in):
    """Driven, and the reproduction rather than a reading of the source.

    A `<link rel="icon">` is loaded by the browser as a subresource: a plain
    unauthenticated GET of whatever the `href` says. So the clause fetches the
    href the same way, from inside the page. An href the browser can load
    answers 200; `/api/brand/logo?v=...` answers 401 and the tab keeps the
    built-in mark with nothing on screen to say why.
    """
    page, base = signed_in
    page.goto(base, wait_until="networkidle")
    page.wait_for_selector("nav", timeout=15000)
    # `applyBrandFavicon` runs once the session is established, which is one
    # round-trip after the nav paints. The built-in mark is a `data:` URI, so
    # "the answer has arrived" is "the href is no longer that".
    page.wait_for_function(
        "() => { const el = document.querySelector('link[rel=\"icon\"]');"
        " return el && !/^data:/.test(el.getAttribute('href') || ''); }",
        timeout=15000)

    href = page.eval_on_selector("link[rel='icon']", "el => el.getAttribute('href')")
    got = page.evaluate(
        "async (href) => { try { const r = await fetch(href);"
        " return { ok: r.ok, status: r.status, type: r.headers.get('content-type') }; }"
        " catch (e) { return { ok: false, status: 0, type: String(e) }; } }",
        href)
    assert got["ok"], (
        f"the tab icon points at {href!r}, which the browser cannot load: "
        f"{got['status']} {got['type']}. The operator's mark never reaches "
        "the tab, and nothing on the screen says so")


# --- the admin preview: the same defect, the second consumer ---------------

@live
def test_the_admin_panel_shows_the_logo_it_says_is_registered(signed_in):
    """Driven. `naturalWidth` is 0 for an image the browser failed to fetch,
    which is what the preview beside `replace logo` has been all along on any
    install with a token."""
    page, base = signed_in
    # Brand is a tab of its own since 2026-09-03.
    page.goto(base + "/#/admin?tab=brand", wait_until="networkidle")
    page.wait_for_selector("img.brand-logo", timeout=15000)
    # CQ-212. This was `wait_for_timeout(2000)`. The element exists as soon as
    # the panel knows a logo is registered; the question is whether bytes ever
    # arrive behind it, which is a load event later — and `complete` is the
    # signal the browser paints for exactly that, true once the fetch has
    # finished by either road. So the wait is on the event and not on a clock,
    # the same correction CQ-211 made in
    # `test_every_report_template_has_a_route_from_the_ui.py:447`.
    #
    # **It does not weaken the clause, and the distinction is the whole point.**
    # `complete` says the attempt is over; `naturalWidth` says whether it
    # arrived. A 401 behind an <img> fires `error`, which sets `complete` true
    # with `naturalWidth` 0 — so the defect this test was written for still
    # reaches the assertion below, and now reaches it as soon as the browser
    # knows rather than two seconds later. Waiting on `naturalWidth > 0` would
    # be the weakening: it would turn the finding into a timeout with no
    # message.
    #
    # The element cannot be here without a src to load: `admin.tsx:877` renders
    # it as `{logo && <img … src={logo} />}`, so the selector above already
    # guarantees the object URL is set, and `complete` cannot be true for the
    # no-src reason.
    page.wait_for_function(
        "() => { const el = document.querySelector('img.brand-logo');"
        " return el && el.complete; }",
        timeout=30000)

    width = page.eval_on_selector("img.brand-logo", "el => el.naturalWidth")
    assert width > 0, (
        "the admin panel renders a broken image where the operator's own logo "
        "should be — naturalWidth 0, which is what a 401 behind an <img> looks "
        "like on screen")


# --- the static clause, which is the one the browserless job runs ----------

#: Somewhere a literal path into the API is handed to the browser to fetch on
#: its own account. Two shapes, because UX-30 was found on two elements and
#: this clause could previously only see one of them (CQ-213):
#:
#: * an attribute written in the markup — ``src={"/api/..."}``,
#:   ``src={`/api/...`}``, ``src="/api/..."``, and the same three under
#:   ``href``, which is how the defect reached ``<link rel="icon">``;
#: * the same attribute set from script — ``setAttribute("href", "/api/...")``
#:   and ``setAttribute("src", "/api/...")``, which is the call `favicon.ts`
#:   makes and therefore the road the tab-icon half actually travelled.
#:
#: An interpolated leading expression matches neither, and does not need to —
#: a path the browser fetches has to start somewhere, and the API's start here.
#: `href` is deliberately not narrowed to subresource elements: an ``<a>`` the
#: operator clicks carries no Authorization header either, so it is the same
#: defect under a different element and belongs in the same net.
BROWSER_LOADS = re.compile(
    r"""\b(?:src|href)=\{?["'`]/api/"""
    r"""|\.setAttribute\(\s*["'`](?:src|href)["'`]\s*,\s*["'`]/api/""")


def test_the_matcher_can_see_the_defect_this_clause_was_written_for():
    """Rule 5, and CQ-210's shape. The clause below reports "none found"
    whether the defect is absent or the regex is wrong, so the regex is shown
    a known instance of what it is looking for — one per shape it claims to
    cover, since a matcher that sees one of two is what CQ-213 was."""
    shipped = "src={`/api/brand/logo?v=${tick}`}"
    assert BROWSER_LOADS.search(shipped), (
        "the matcher cannot see the exact attribute UX-30 was found on, so a "
        "clean result below would mean nothing")

    # The other half of UX-30, and the reason CQ-213 was raised: the tab icon
    # never carried a `src`. It reached the browser as a `<link rel="icon">`
    # href, and `favicon.ts` puts it there with `setAttribute`. Both spellings
    # are shown, because the markup form is what a new screen would write and
    # the script form is what the module that actually shipped the defect did.
    tab_icon_markup = '<link rel="icon" href="/api/brand/logo?v=1" />'
    assert BROWSER_LOADS.search(tab_icon_markup), (
        "the matcher cannot see an href pointed at a guarded route, which is "
        "the element half of UX-30 was found on")
    tab_icon_script = 'el.setAttribute("href", "/api/brand/logo?v=" + tick)'
    assert BROWSER_LOADS.search(tab_icon_script), (
        "the matcher cannot see an href set from script, which is the call "
        "`favicon.ts` makes and so the road that half of UX-30 travelled")

    assert not BROWSER_LOADS.search('api.get("/api/brand")'), (
        "the matcher fires on an authorized client call, so it would report a "
        "correct module as defective")
    # `favicon.ts:67` at HEAD, verbatim in shape: the href is an object URL
    # already fetched through the authorized client, so the variable form must
    # not match. This is the negative that keeps the widening above honest —
    # without it, the fix for CQ-213 would report the module that was repaired
    # to close UX-30 as the module that still carries it.
    assert not BROWSER_LOADS.search('el.setAttribute("href", href)'), (
        "the matcher fires on an attribute set from a variable, so it would "
        "report the object-URL fix UX-30 was closed with as the defect")


def test_no_screen_asks_the_browser_to_load_a_guarded_api_path():
    """Every `/api/` route in this product is declared `operator=op_dep`. A
    browser loading one by itself sends no Authorization header, so any module
    doing it has UX-30 again under a different element."""
    offenders = {
        path.name: BROWSER_LOADS.findall(path.read_text(encoding="utf-8"))
        for path in sorted(SRC.glob("*.ts*"))
        if BROWSER_LOADS.search(path.read_text(encoding="utf-8"))
    }
    assert not offenders, (
        f"{offenders} hand an API path to the browser to fetch. The browser "
        "sends no token, so the request is a 401 and the element renders "
        "empty — fetch it through `api.blob` and hand over an object URL")
