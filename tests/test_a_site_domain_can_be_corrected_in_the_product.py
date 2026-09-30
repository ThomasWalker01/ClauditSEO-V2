"""A site's domain is correctable through the product, and stored normalised.

WF-81, first raised in report 063 and carried High through 098 -- nine reports
without being taken. `sites.domain` was write-once: `create_site` takes it,
`SitePatch` carried `business_type`, `locale` and `target_market` and no
`domain`, and `repo.update_site` took the same three. The only route to a
mistyped domain was deleting the client and every run, finding, state,
snapshot and cost entry under it, or opening the database in SQL.

Not hypothetical. Measured read-only against `data/clauditseo.db` on
24 August 2026 -- of the six stored sites, one of the three real ones is the
literal string `https://www.13acme.com.au/`: scheme, host and trailing slash,
in the column every other row holds a bare host in.

**Why the shape matters as much as the field.** `clauditseo/crawler/crawl.py`
`site_host` is the one place a stored domain becomes the host it names, and
its own docstring records four call sites that each open-coded the same two
lines and each carried the same defect. It absorbs the malformed row -- it
returns `www.13acme.com.au` for that string, which is why the crawl works --
but it is not the only reader: `reporting/generate.py` slugs the deliverable's
filename from a domain, and the screens render the column raw. So a domain
edit that stored what was typed would let a second malformed row in through
the door built to fix the first.

The route therefore normalises rather than validating and refusing. Refusing
is the stricter design and it is **not** available here: `site_host`'s
docstring says validating on the way in is "gated on what happens to the rows
already there", and a route that refuses what the database already holds
cannot be used to correct that row -- which is this finding. Normalising on
the way through is what makes the refusal decidable later, because once every
correctable row can be corrected, the surviving malformed rows are a set the
operator can act on rather than a constraint on the fix.

**Deliberately out of scope, and named rather than left to be discovered:**
`POST /api/clients/{id}/sites` still stores what it is given, so a domain can
still be *created* malformed and only then corrected. That is CQ-108's half
and it changes what several existing tests observe; this file asserts nothing
about it, and the asymmetry is a smaller wrong than the one it replaces.
WF-82 -- no way to test whether a URL would be accepted without launching a
paid run -- shares this normaliser and is not closed by it: its remedy is a
route that has never existed.
"""

import socket
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from clauditseo.api.app import create_app
from clauditseo.crawler.crawl import site_host
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import repo
from tests.needs_build import needs_build


def _api(tmp_path) -> TestClient:
    db = tmp_path / "domain.db"
    conn = connect(db)
    migrate(conn)
    repo.seed_demo(conn)
    conn.close()
    return TestClient(create_app(db_path=db))


def _site(api: TestClient, domain: str) -> str:
    client = api.post("/api/clients", json={"name": "C"}).json()
    return api.post(f"/api/clients/{client['id']}/sites",
                    json={"domain": domain}).json()["id"]


#: The row the operator actually has, verbatim from `data/clauditseo.db`.
#: A fixture invented for this test would have been a shape the product's own
#: write path cannot produce, which is CQ-203's defect; this one was queried.
STORED_AS_A_URL = "https://www.13acme.com.au/"


def test_a_domain_typed_as_a_url_can_be_corrected_without_deleting_the_client(
        tmp_path):
    """The finding, stated as an assertion.

    Driven through the route the screen uses rather than through `repo`: what
    WF-81 says is absent is the *product's* route to the correction, and a
    repo-level call would prove the column is writable, which was never in
    doubt.
    """
    api = _api(tmp_path)
    site_id = _site(api, STORED_AS_A_URL)

    resp = api.put(f"/api/sites/{site_id}", json={"domain": "www.13acme.com.au"})

    assert resp.status_code == 200, resp.text
    assert resp.json()["domain"] == "www.13acme.com.au", (
        "the one field the whole audit hangs on still cannot be corrected "
        "through the product")
    assert api.get(f"/api/sites/{site_id}").json()["domain"] == \
        "www.13acme.com.au", "the correction did not survive being read back"


def test_a_correction_is_stored_in_the_shape_every_other_reader_expects():
    """`site_host` is the owner, called rather than reimplemented.

    A second copy of "strip the scheme and the trailing slash" is exactly what
    that function's docstring records four call sites having done, each
    carrying the same defect -- a scheme is `http://`, not the four characters
    `http`, so `httpwatch.com` was handed to `urlsplit` as though it had one.
    This asserts the route's answer equals the owner's, so a fifth copy fails
    here rather than in a deliverable's filename.
    """
    assert site_host(STORED_AS_A_URL) == "www.13acme.com.au"


@pytest.mark.parametrize("typed,stored", [
    ("https://www.13acme.com.au/", "www.13acme.com.au"),
    ("HTTP://Example.COM", "example.com"),
    ("  example.com  ", "example.com"),
    ("example.com", "example.com"),
])
def test_what_is_typed_is_normalised_before_it_is_stored(tmp_path, typed,
                                                         stored):
    """Including the case that needs no work.

    The last row is the one that makes the others evidence rather than
    coincidence: a normaliser that mangles an already-correct domain would
    pass every other case here.
    """
    api = _api(tmp_path)
    site_id = _site(api, "placeholder.test")

    assert api.put(f"/api/sites/{site_id}",
                   json={"domain": typed}).json()["domain"] == stored


def test_a_domain_that_normalises_to_nothing_is_refused(tmp_path):
    """The column is what every run, deliverable and crawl hangs on, so
    clearing it is not one of the corrections on offer -- unlike
    `business_type`, where `""` is a real answer meaning "not filed yet"."""
    api = _api(tmp_path)
    site_id = _site(api, "example.com")

    resp = api.put(f"/api/sites/{site_id}", json={"domain": "   "})

    assert resp.status_code == 422, resp.text
    assert api.get(f"/api/sites/{site_id}").json()["domain"] == "example.com", (
        "a refused correction still moved the stored value")


def test_a_correction_says_how_much_was_produced_under_the_old_domain(tmp_path):
    """The route's existing honesty, extended rather than re-decided.

    `update_site`'s docstring: a correction "does not touch anything already
    produced", and `analyses_before` is how the caller says that plainly
    instead of implying the fix reaches backwards. A domain is the strongest
    case for it -- every stored run, finding and deliverable was gathered
    against the old string -- so it would be the worst field to report the
    change silently on.
    """
    api = _api(tmp_path)
    site_id = _site(api, STORED_AS_A_URL)

    body = api.put(f"/api/sites/{site_id}",
                   json={"domain": "www.13acme.com.au"}).json()

    assert "domain" in body["changed"], (
        "the domain moved and the response does not list it among what "
        f"changed: {body['changed']}")


def test_a_correction_to_the_value_already_stored_changes_nothing(tmp_path):
    """Normalisation runs before the comparison, or re-saving the row the
    screen is already showing reports a change that did not happen -- and on
    this field that reads as "every stored analysis is now stale"."""
    api = _api(tmp_path)
    site_id = _site(api, "example.com")

    body = api.put(f"/api/sites/{site_id}",
                   json={"domain": "https://example.com/"}).json()

    assert body["changed"] == [], (
        "a domain that normalises to what is already stored is reported as a "
        f"change: {body['changed']}")


def test_the_record_screen_offers_the_correction(tmp_path):
    """DISCIPLINE rule 4 — evidence the screen posts the field, not evidence
    of what it paints.

    **The weaker of the two clauses about this control, and labelled as such
    since round 113.** It said "the rendered sweep is what paints it" and the
    rendered sweep did not, so for eleven reports this string match stood in
    for a rendered assertion — CQ-221. Measured under mutation: wrap the
    element in `{false && ...}` and this clause still passes while
    `test_the_correction_control_can_be_pressed_and_reaches_the_server` below
    fails. It is kept because it is the clause that still runs where
    playwright is not installed, not because it is sufficient.

    The affordance invariant is the reason this assertion exists rather than
    the route being taken as enough: the screen names the domain on every
    client row, and a route nothing can reach leaves the finding's own
    sentence -- "nothing in the product can correct it" -- true.
    """
    home = Path("dashboard/src/home.tsx").read_text(encoding="utf-8")
    assert "SiteDomain" in home, (
        "the record screen has no control that corrects a domain, so the "
        "route added for it is reachable only by hand")


# --- the control, as the operator drives it --------------------------------
#
# CQ-221 (High, first raised at report 099, strict xfail with round 113 as its
# deadline). `test_the_record_screen_offers_the_correction` above recorded
# WF-81 closed on `assert "SiteDomain" in home` — a string read out of a
# source file — and deferred the rest to "the rendered sweep", which does not
# paint this control. So the affordance half of WF-81 was closed by a matcher
# that a comment naming the component would satisfy: render `<SiteDomain>`
# behind `{false && ...}` and that assertion stays green while the operator
# has nothing to press.
#
# What follows presses it. The string assertion above is kept rather than
# replaced, because it is the cheap clause that still runs where playwright is
# not installed, and it is now labelled as the weaker of the two rather than
# standing in for the stronger.

NEEDS_BROWSER = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("playwright")
    is None, reason="playwright is not installed")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def served():
    """A real server holding one site whose domain is stored as a URL.

    `STORED_AS_A_URL` rather than a tidy host, because the row the operator
    actually has is the malformed one and the home screen strips the scheme
    when it draws it — so the drawn column and the stored column differ, and
    a control prefilled from the drawn value would look correct against a
    stored value that is not. That difference is what these clauses read.
    """
    import tempfile

    import httpx
    import uvicorn

    tmp = Path(tempfile.mkdtemp(prefix="sitedomain"))
    db = tmp / "clauditseo.db"
    app = create_app(db_path=db)
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port,
                            log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.time() + 30
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    if not server.started:
        pytest.fail("server did not start")

    base = f"http://127.0.0.1:{port}"
    try:
        client = httpx.post(f"{base}/api/clients",
                            json={"name": "Domain Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": STORED_AS_A_URL}, timeout=30).json()
        yield base, site["id"]
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def _stored_domain(base: str, site_id: str) -> str:
    """What the server holds, off the route the screen reads."""
    import httpx

    return httpx.get(f"{base}/api/sites/{site_id}", timeout=30).json()["domain"]


def _open_editor(pg, base: str):
    """Home, then the correction control opened. Returns its text input."""
    pg.goto(f"{base}/#/", wait_until="load", timeout=30_000)
    # The row first, so a screen that painted no sites at all fails saying
    # that rather than timing out on the control. Then the collapsed control:
    # `SiteDomain` renders a bare button until it is opened, and only the open
    # editor carries `span.site-domain` -- so waiting on the wrapper would be
    # waiting for the thing the click produces.
    pg.wait_for_selector(".home-card", timeout=30_000)
    # Item 176: editing is behind the card, in its closed "Edit this site".
    # Pressed only while closed: a second call on the same page (the hash does
    # not reload) would otherwise close it again.
    if not pg.eval_on_selector(".home-card .home-card-manage", "d => d.open"):
        pg.click(".home-card .home-card-manage > summary")
    edit = pg.query_selector(
        'button[aria-label^="correct the stored domain"]')
    assert edit is not None, (
        "the home screen paints no control that corrects a domain, so the "
        "route added for WF-81 is reachable only by hand — which is the "
        "finding, unchanged")
    edit.click()
    field = pg.wait_for_selector("span.site-domain input", timeout=15_000)
    return field


@NEEDS_BROWSER
@needs_build
def test_the_correction_control_can_be_pressed_and_reaches_the_server(served):
    """CQ-221 where the operator meets it. DISCIPLINE rule 12.

    Three things a source-string match cannot see: that the control renders at
    all, that pressing it opens an editor, and that saving reaches the route.
    The last is asserted against the server rather than against the screen,
    because the screen showing the new value proves only that a browser
    variable changed.
    """
    from playwright.sync_api import sync_playwright

    base, site_id = served
    assert _stored_domain(base, site_id) == STORED_AS_A_URL, (
        "precondition: the fixture no longer holds the malformed row, so a "
        "correction cannot be told from a value that was already right")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        try:
            field = _open_editor(pg, base)
            assert field.input_value() == STORED_AS_A_URL, (
                "the editor opened prefilled with something other than the "
                f"stored string: {field.input_value()!r}. Prefilling from the "
                "drawn column is the defect the component's own docstring "
                "warns about — it would offer to correct a value that already "
                "looks correct")
            field.fill("www.13acme.com.au")
            pg.click("span.site-domain button:has-text('save')")
            pg.wait_for_function(
                "() => !document.querySelector('span.site-domain input')",
                timeout=15_000)

            assert _stored_domain(base, site_id) == "www.13acme.com.au", (
                "the control was driven through open, type and save, and the "
                "server still holds "
                f"{_stored_domain(base, site_id)!r}")
        finally:
            browser.close()


@NEEDS_BROWSER
@needs_build
def test_the_editor_reopens_holding_what_the_server_stored(served):
    """CQ-222, at the screen. Depends on the clause above having saved.

    The server normalises through `crawl.site_host`, so what it stores is not
    what was typed. `SiteDomain` seeded `value` with `useState(row.domain)` —
    an initialiser, not a subscription — so after one correction the field
    went on offering the typed string back while the button beside it named
    the stored one. Typing a form the normaliser changes is what makes the
    two distinguishable: `HTTP://Example.COM/` is stored `example.com`, and a
    field that reopens on the typed string is showing a value the product
    does not hold.

    Module-scoped fixture, so this runs against the site the clause above
    corrected — reopening is the whole assertion and a fresh mount would not
    be a reopen.
    """
    from playwright.sync_api import sync_playwright

    base, site_id = served

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        try:
            field = _open_editor(pg, base)
            field.fill("HTTP://Example.COM/")
            pg.click("span.site-domain button:has-text('save')")
            pg.wait_for_function(
                "() => !document.querySelector('span.site-domain input')",
                timeout=15_000)
            assert _stored_domain(base, site_id) == "example.com", (
                "precondition: the server did not normalise, so a field "
                "holding the typed string cannot be told from a correct one")

            reopened = _open_editor(pg, base)
            assert reopened.input_value() == "example.com", (
                "the editor reopened holding "
                f"{reopened.input_value()!r} — what was typed, not what is "
                "stored. The control exists to make the stored value visible "
                "and stops doing so the moment it is used.")
        finally:
            browser.close()
