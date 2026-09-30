"""axe against the dashboard's own rendered screens.

This is the gate the stylesheet tests cannot be. Every contrast defect this
project has shipped passed static analysis and was caught only by a browser
resolving the cascade and compositing pixels:

  - `.tool-mark` set `color: #fff` and, declared after the severity block at
    equal specificity, overrode a chip asking for dark ink — 2.15:1.
  - `.seg-count` set `opacity: 0.75`, blending a token that passes on its own
    down to 3.29:1.
  - `.pill-cost` set `opacity: 0.65` — 3.83:1.

In each case `test_dashboard_a11y.py` was green. A rule about what a
stylesheet *says* cannot catch a bug about what the browser *draws*.

The trap this walked into first time round: an empty dashboard passes
everything. Seeded with nothing but a client and a site, the first version of
this file reported all six screens clean *with the `.pill-cost` defect
deliberately reinstated*, because a severity chip, a score badge and a cost
pill have nothing to render on a site with no audit. A screen that renders
nothing is not a screen that renders correctly. So a real audit is run
against a local fixture site, and `test_the_audited_screens_actually_render`
fails when a colour-bearing component stops appearing — which is how this
coverage would otherwise rot without anyone noticing.

Skips rather than fails when Playwright or a built dashboard is absent: a
bare `pip install -e .[dev]` must still run the suite green. CI installs the
extra and builds the dashboard, so there it is a gate.
"""

from __future__ import annotations

import re
import socket
import threading
import time
from pathlib import Path

import pytest

from clauditseo import axe
from tests.parts import ANATOMY_READY, open_part, open_page_filter

DIST = Path(__file__).resolve().parents[1] / "dashboard" / "dist"

pytestmark = [
    pytest.mark.skipif(not axe.available(),
                       reason="needs clauditseo[render] and `playwright install chromium`"),
    pytest.mark.skipif(not (DIST / "index.html").is_file(),
                       reason="dashboard not built (npm run build in dashboard/)"),
]

# What each screen renders only once its own content is on the page, used
# instead of sleeping for a fixed 1.2s after `load` (relay item 014).
#
# Every entry was taken from a recorded sweep of the current code, not guessed:
# the class was observed present on that screen in the baseline this change is
# judged against. The chrome classes every screen shares — `shell`, `topbar`,
# `topnav`, `navbtn`, `homelink`, `globalsearch` — are deliberately NOT used.
# They mount with the shell, before the route's data has arrived, so waiting on
# one would resolve early and audit a half-painted screen. That is the failure
# this table exists to avoid, and it would be invisible: fewer classes captured
# reads as a faster sweep, not a broken one.
#
# A screen missing here keeps the flat wait. An absent entry is a decision, not
# an oversight.
READY: dict[str, str] = {
    "home": ".home-card",  # item 176: the sites are cards
    "admin": ".admin-tabs",
    # Admin is one section at a time (2026-09-03), so each tab is its own
    # route here: the sweep that loaded `#/admin` and audited every card
    # would otherwise audit the first tab and call the screen covered.
    # Each waits for what its own section fetches, where it fetches.
    "admin-providers": ".admin-tabs",
    "admin-keys": ".admin-tabs",
    "admin-models": ".tier-pick",
    "admin-prices": ".money-sub",
    "admin-brand": ".brand-name",
    "admin-operators": ".admin-tabs",
    "admin-database": ".advice-read",
    "admin-workbench": ".alist",
    "client": ".anat-layout",
    "client-landing": ".cl-landing .cl-lane",
    "client-crawl": ".part-page .cd-chart",
    "client-indexability": ".part-page .now-card",
    "client-urls": ".part-page .un-template",
    "client-speed": ".part-page .sp-card",
    "reports": ".stats-row",
    "workbench": ".wb-checks",
    "launch": ".dim-grid",
    "chat": ".inline-form",
    "dossier": ".dossier-url",
    "run": ".group-list",
    "run-page": ".url-links",
    "compare": ".card",
    "deliverable": ".md",
    "generate": ".inline-form",
    "run-blocked": ".group-list",
    "reports-blocked": ".stats-row",
}

# Every screen an operator actually works in. Hash routes, so one document
# load per route and the SPA reads the fragment on boot.
ROUTES = [
    ("home", "#/"),
    ("admin", "#/admin"),
    ("glossary", "#/glossary"),
    # Item 182: the button reference, every variant live and held.
    ("buttons", "#/buttons"),
    ("admin-providers", "#/admin?tab=providers"),
    ("admin-keys", "#/admin?tab=keys"),
    ("admin-models", "#/admin?tab=models"),
    ("admin-prices", "#/admin?tab=prices"),
    ("admin-brand", "#/admin?tab=brand"),
    ("admin-operators", "#/admin?tab=operators"),
    ("admin-database", "#/admin?tab=database"),
    ("admin-workbench", "#/admin?tab=workbench"),
    # `?tab=findings` since brief v24 step BM: the bare address is the
    # landing now, and every reveal pass below was written against Analyses.
    ("client", "#/sites/{site}?tab=findings"),
    # The landing itself (BM): the three lanes at full height.
    ("client-landing", "#/sites/{site}"),
    # The four parts brief v25 step BP moved to the three-block layout, on it.
    # `client` above drives their fixture findings on the layout of last
    # resort for that layout's machinery; these audit where they now live.
    ("client-crawl", "#/sites/{site}?tab=findings&part=crawl"),
    ("client-indexability", "#/sites/{site}?tab=findings&part=indexability"),
    ("client-urls", "#/sites/{site}?tab=findings&part=urls"),
    ("client-speed", "#/sites/{site}?tab=findings&part=speed"),
    ("reports", "#/sites/{site}/reports"),
    ("workbench", "#/sites/{site}/workbench"),
    ("launch", "#/sites/{site}/launch"),
    # Added closing UX-06. `ROUTES` listed seven of the fourteen `App.tsx`
    # serves, and the test beside it iterated this list — so a screen added
    # without a line here could never fail anything, while the WCAG 2.2 AA
    # claim was made for the whole app. Three of the seven missing are where
    # UX-01, UX-02 and WF-05 live.
    ("chat", "#/sites/{site}/chat"),
    ("dossier", "#/sites/{site}/dossier/{page}"),
    ("run", "#/runs/{run}"),
    ("run-page", "#/runs/{run}/page/{page}"),
    ("compare", "#/compare/{run}/{run2}"),
    ("deliverable", "#/client-reports/{report}"),
    ("generate", "#/reports/{run}"),
    # The same screen in the state the product cares most about. A blocked run
    # renders a different branch, and pointing `run` at a complete one leaves
    # that branch unpainted however many routes the list holds.
    ("run-blocked", "#/runs/{blocked_run}"),
    # The reports screen of the site whose crawl was refused. `reports` above
    # points at the main fixture site, whose runs are all `complete`, so the
    # branch that decides whether a blocked run's composite may be printed had
    # never been painted by this sweep in its whole life — the route was
    # listed, and listed is not painted.
    ("reports-blocked", "#/sites/{blocked_site}/reports"),
]

# The screens `App` paints INSTEAD of the router, before any route is read.
#
# Deliberately a second list rather than more rows in `ROUTES`, and the reason
# is mechanical: `ROUTES` has three importers — this file, `test_reflow.py`
# and `test_every_report_template_has_a_route_from_the_ui.py` — and both of
# the others read it as "hash routes an operator navigates". Appending a
# pre-router state there would silently re-populate a 320px reflow sweep and a
# generate-control walk with screens neither is about, and both would still
# look like coverage.
#
# Each row: the sweep's name, the `authState` member it paints, the hash the
# browser loads (any — the router never runs), the request to interfere with,
# what to do to it, and a class that only this screen draws. The last is the
# empty-capture guard: interception that stops working renders the ordinary
# signed-in app, which passes axe happily while testing none of this.
STATES = [
    # `classify` maps 401 to "auth", which is the only thing that reaches the
    # login gate — App clears the token and paints it.
    ("login", "need-token", "#/", ".inline-form", "401", "inline-form"),
    # A rejected `fetch` is not an `ApiError`, so `classify` says unreachable
    # and `answered` stays false. That is the branch a genuinely dead server
    # produces, as opposed to one answering 500.
    ("unreachable", "unreachable", "#/", ".server-down", "abort", "server-down"),
]

#: What the boot probe asks for. Intercepting this one request is the whole
#: mechanism: `App` decides which of the four states to paint from its answer,
#: so no server manipulation, no fixture variant and no build flag is needed.
PROBE_URL = "**/api/clients"

#: Classes that carry their own colour and therefore their own contrast risk.
#: If one of these stops appearing anywhere in the sweep, the sweep has
#: quietly stopped testing it — which is the failure mode that let a defect
#: sit behind six green screens.
MUST_RENDER = {
    "sev": "severity chip on a finding",
    "score": "score badge",
    "stat": "headline number",
    "tone": "action pill",
    "wb-status-ready": "tool status chip on the workbench",
    # The tab row was retired at the site-screen plan's step 5; the strip
    # and the reference row are the navigation now, and both are listed.
    "ref-link": "a reference link — Pages, Notes — above the pane",
    "pane-name": "the pane's own name, above it",
    "tone-source-sweep": "source tag on a sweep finding",
    "tone-source-brief": "source tag on a brief finding",
    "anat-headline": "the shared-cause headline",
    "ty-site": "the type marker on an analysis row",
    "arow": "an analysis row in a lane",
    # The lanes became the catalogue drawer (brief v4 Item 3e); a read
    # brief is a row in the read state there.
    "crow-read": "a read brief's row in the catalogue drawer",
    "fix-chk": "the fix-loop tick",
    "facts": "the facts half of an anatomy category",
    # The heading outline on a page is the drawn ladder now (`OutlineLadder`,
    # `.ho-ladder`). The tagged `.outline` list it replaced was retired at item
    # 144 (Q-51); `.outline` survives only in a heading fix body's was/now diff
    # (`part_page.tsx`), which the sweep does not expand, so it was never the
    # thing this row actually caught — the always-drawn ladder is.
    "ho-ladder": "the heading outline ladder on a page",
    "fact-mono": "a monospaced fact value — URL, filename, cipher",
    # The badge that carries a length on a title or description. It was
    # `.measure`, in the facts panel, until brief v13 step AO replaced that
    # panel with the part's own card and the panel became unreachable.
    "str-badge": "a length badge on a title or description",
    "mark-bar": "the fix-loop mark bar",
    "seq-step": "a step in the suggested order",
    "seq-next": "the step marked as next",
    "seq-badge": "the do-this-next badge",
    "tone-state-open": "a stored state chip on the record",
    "run-status": "the run status chip — the one state a screen must not "
                  "render as an ordinary score",
    # `trend-line` left with the dot chart (brief step 7, UX-06): the trend
    # is its sentence and the reading on each run's row now.
    # The probe panel (F-05). Added ahead of the fixture that paints them, so
    # this guard was seen to fail naming all three before either was staged —
    # CQ-115's second half. `PAIRS` gained the three colour rows in `2ef4052`
    # and could not have caught the 4.39:1 either way: a hand-kept table only
    # holds what somebody thought to add, and this one holds what the page
    # actually drew.
    "to-confirm-text": "an unmeasured [TO CONFIRM: ...] marker in a brief",
    "confirmed-value": "the value a probe measured, in place of the marker",
    "confirmed-source": "where that measured value came from",
    # UX-03, and the same precedent as the three above: added before the
    # screens that would paint them, so this guard was seen to fail naming
    # both. Measured at the time of adding — `.figures-note` and
    # `.figures-withheld` exist only in `expert.tsx`, whose `ExpertPanel` has
    # exactly one mount (`views.tsx:1506`, the run-page route), and `REVEAL`
    # has no entry for that route. So the block carrying the brief's own
    # statement of what it could not verify, and `styles.css:495-502` under
    # it, had never been audited by axe anywhere in the sweep's life. That is
    # CQ-153's live half. Adding them here is what makes the absence red
    # rather than invisible: the route was in `ROUTES` throughout, which is
    # configuration and not coverage (DISCIPLINE rule 4).
    "figures-note": "the derived-figures note on a brief",
    "figures-withheld": "the brief's own count of the figures it flagged",
}

#: A brief's prose, with one open question the fixture settles and one it
#: does not. Kept as a constant rather than inline so the two marker strings
#: are readable: each has to carry a subject term and a qualifier term or
#: `probes.probe_for` returns `None` and the marker renders inert.
BRIEF_REPORT = "\n\n".join([
    "## Transport and canonical host",
    "Every crawled page is served over HTTPS.",
    "[TO CONFIRM: whether the apex domain redirects to the www canonical"
    " host]",
    "Chain completeness cannot be established from a crawl.",
    "[TO CONFIRM: whether the certificate chain sends its intermediates]",
])

FIXTURE_HTML = (
    "<html lang='en'><head><title>Fixture home page for the audit</title>"
    "<meta name='viewport' content='width=device-width, initial-scale=1'>"
    "</head><body><main><h1>Home</h1><h4>Skipped level</h4>"
    "<img src='/a.png'><p>Short.</p>"
    "<a href='/promo'>promo</a> <a href='/deep'>deep</a> "
    "<a href='/gallery'>gallery</a> <a href='/thin'>thin</a> "
    "<a href='/schema'>schema</a> <a href='/dup'>dup</a> "
    "<a href='/many'>many</a> "
    + "".join(f"<a href='/p{i}'>page {i}</a> " for i in range(1, 9))
    + "</main></body></html>"
)
PROMO_HTML = (
    "<html lang='en'><head><title>Promo</title></head><body><main>"
    "<h1>Promo</h1><img src='/b.png'><p>Also short.</p>"
    "</main></body></html>"
)
#: One description, deliberately shared by twelve pages. `anatomy_view` sends
#: `"pages": len(urls)` with `"urls": urls[:10]`, so a check has to span more
#: than ten before the two disagree and a guard on the mark bar's page count
#: can fail at all. Twelve rather than eleven: a fixture sitting exactly on
#: the boundary passes whether the code says `> 10` or `>= 10`.
SHARED_DESC = (
    "<meta name='description' content='One of several pages sharing this "
    "description, so that a single check spans more pages than the wire "
    "carries URLs for.'>")

#: Shape 1 — a deep heading tree with a skip, so the outline has something to
#: be an outline of and `hcounts` spans more than two levels.
DEEP_HTML = (
    "<html lang='en'><head><title>Deep structure page about headings</title>"
    + SHARED_DESC +
    "</head><body><main><h1>Deep</h1>"
    + "".join(f"<h2>Section {i}</h2><h3>Detail {i}a</h3><h3>Detail {i}b</h3>"
             for i in range(1, 5))
    + "<h2>Last</h2><h4>Skipped a level here</h4>"
      "<img src='/d.png'><p>"
    + "Body text long enough not to be thin, repeated so the word count "
      "clears the floor. " * 6
    + "</p></main></body></html>"
)
#: Shape 2 — several images, mixed alt, so the images table has rows that
#: differ from each other rather than one row repeated, and one filename long
#: enough to need wrapping.
GALLERY_HTML = (
    "<html lang='en'><head><title>Gallery of images with mixed alt text</title>"
    + SHARED_DESC +
    "</head><body><main><h1>Gallery</h1>"
    "<img src='/photograph-of-the-team-standing-outside-the-office-building.png'>"
    "<img src='/g2.png' alt='A described image'>"
    "<img src='/g3.png'>"
    "<img src='/g4.png' alt=''>"
    "<p>Images above, some described and some not.</p>"
    "</main></body></html>"
)
#: Shape 3 — thin, so a content finding fires here and not everywhere.
THIN_HTML = (
    "<html lang='en'><head><title>Thin</title></head><body><main>"
    "<h1>Thin</h1><img src='/t.png'><p>Two words.</p></main></body></html>"
)
#: Shape 4 — structured data, so the schema category is not empty.
SCHEMA_HTML = (
    "<html lang='en'><head><title>Structured data page</title>"
    + SHARED_DESC +
    "<script type='application/ld+json'>"
    '{"@context":"https://schema.org","@type":"Organization",'
    '"name":"Fixture Co","url":"https://fixture.test/"}'
    "</script></head><body><main><h1>Schema</h1><img src='/s.png'>"
    "<p>A page carrying JSON-LD structured data for the schema category.</p>"
    "</main></body></html>"
)
#: Shape 5 — a canonical long enough that the mono fact cell has an unbroken
#: token to wrap, which is what the real-data-scale invariant is about.
DUP_HTML = (
    "<html lang='en'><head><title>Duplicate path page</title>"
    + SHARED_DESC +
    "<link rel='canonical' href='https://fixture.test/a-very-long-canonical-"
    "url-segment-that-will-not-break-on-its-own-anywhere-at-all/dup'>"
    "</head><body><main><h1>Dup</h1><img src='/u.png'>"
    "<p>Reached by more than one URL.</p></main></body></html>"
)
#: Shape 6 — the only page on this fixture site that the crawl truncates.
#:
#: `evidence.py` keeps `facts.headings[:HEADING_CAP]` and `facts.images
#: [:IMAGE_CAP]`, both 60, and stores the *uncapped* totals beside them. Every
#: other shape here is far under: measured over every `*_HTML` constant in
#: this file, the maxima were 15 headings (`DEEP_HTML`) and 4 images
#: (`GALLERY_HTML`). So `heading_total > len(headings)` was false on all
#: seventeen crawled pages, the branch that says what the crawl dropped had
#: never rendered in this repository's suite, and no clause could tell the
#: fixed state from the broken one. That is UX-60's fixture, and it is
#: DISCIPLINE rule 5 in the same breath: a guard whose fixture cannot express
#: the failure can only ever pass.
#:
#: 71 headings and 65 images, so both tails are non-empty and the two are
#: *different* non-empty numbers — 11 headings and 5 images. A page that
#: dropped the same count of each would pass under a component that read the
#: wrong total, which is the shape of every other near-miss in this file.
#:
#: No `SHARED_DESC`, deliberately: that constant's own comment turns on
#: twelve pages carrying it, and a thirteenth would move the boundary it was
#: sized to. Every image carries alt text, also deliberately — 65 images with
#: no alt would add a finding to every count on the fixture site, and this
#: page is here to be truncated rather than to be defective.
MANY_HTML = (
    "<html lang='en'><head><title>A page with more headings than a crawl keeps</title>"
    "<meta name='description' content='The one fixture page whose heading and "
    "image lists are longer than the crawl stores, so the notice saying so has "
    "something to say.'>"
    "</head><body><main><h1>Many</h1>"
    + "".join(f"<h2>Section {i}</h2><h3>Detail {i}</h3>" for i in range(1, 36))
    + "".join(f"<img src='/m{i}.png' alt='Figure {i}'>" for i in range(1, 66))
    + "<p>"
    + "Body copy, long enough that this page is not thin as well as long. " * 6
    + "</p></main></body></html>"
)
#: The eight that carry the shared defect and little else, so one check spans
#: eleven pages while its neighbours span one.
PLAIN_HTML = (
    "<html lang='en'><head><title>Page {n} of the fixture site</title>"
    + SHARED_DESC +
    "</head><body><main><h1>Page {n}</h1><img src='/p{n}.png'><p>"
    + "Ordinary body copy, long enough not to be thin. " * 6
    + "</p></main></body></html>"
)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def served(tmp_path_factory):
    """A real server on a real port, holding a real completed audit.

    TestClient cannot be used here — the browser has to fetch the bundle over
    HTTP for the cascade to resolve at all.
    """
    import uvicorn

    from clauditseo.api.app import create_app

    db = tmp_path_factory.mktemp("a11y") / "clauditseo.db"
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

    ids = _seed(db, f"http://127.0.0.1:{port}")
    try:
        yield f"http://127.0.0.1:{port}", ids
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def _old_page_part(base: str, site_id: str) -> str:
    """A part that still renders the old page, from this fixture's own
    payload. See `old_page_part` for why it is derived."""
    import httpx

    from tests.test_the_part_page_is_three_blocks import old_page_part

    view = httpx.get(f"{base}/api/sites/{site_id}/anatomy", timeout=30).json()
    return old_page_part(view)


def _seed(db_path: Path, base: str) -> str:
    """A client, a site, and one completed audit with real findings.

    The audit is what makes this test worth running: severity chips, score
    badges, the anatomy tree and the source tags only exist once something
    has actually been found.
    """
    from urllib.parse import quote

    import httpx

    from dataclasses import replace

    from clauditseo.crawler.crawl import crawl
    from clauditseo.crawler.types import TierBudget
    from clauditseo.crawler.evidence import snapshot
    from clauditseo.db.connection import connect
    from clauditseo.engine.core import run_audit
    from clauditseo.engine.types import Site, Tier
    from clauditseo.persistence import runs
    from tests.conftest import FixtureSite

    client = httpx.post(f"{base}/api/clients", json={"name": "Contrast Test"},
                        timeout=30).json()
    site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                      json={"domain": "https://fixture.test/",
                            "business_type": "local-service"}, timeout=30).json()

    # SEC since item 143 step BD: Security & transport left TEC, and without
    # its own dimension here that part would be swept empty.
    dims = ["TEC", "ONP", "A11Y", "CNT", "SEC"]
    routes = {
        "/robots.txt": (200, {"Content-Type": "text/plain"},
                        "User-agent: *\nAllow: /\n"),
        "/": (200, {}, FIXTURE_HTML),
        "/promo": (200, {}, PROMO_HTML),
        "/deep": (200, {}, DEEP_HTML),
        "/gallery": (200, {}, GALLERY_HTML),
        "/thin": (200, {}, THIN_HTML),
        "/schema": (200, {}, SCHEMA_HTML),
        "/dup": (200, {}, DUP_HTML),
        "/many": (200, {}, MANY_HTML),
    }
    for n in range(1, 9):
        routes[f"/p{n}"] = (200, {}, PLAIN_HTML.format(n=n))
    fixture = FixtureSite(routes).start()
    try:
        crawled = crawl(fixture.base_url + "/", Tier.T2,
                        budget=TierBudget(max_pages=30, request_timeout_s=5,
                                          wall_clock_s=30, delay_s=0))
        result = run_audit(Site(domain="https://fixture.test/"), crawled,
                           dims, Tier.T2)
    finally:
        fixture.stop()

    conn = connect(db_path)
    # Twice, because a brief finding seen once is a candidate, not an open
    # one — "model output varies a few percent run to run; once is not a
    # fact". Only on its second sighting does it reach the anatomy screen,
    # so a single-run fixture would render no brief findings at all.
    #
    # The tiers differ. `runs.site_trend` keys comparability on
    # `(engine_version, basis, tier, dimensions)`, so two runs at one tier
    # over one dimension set produce a
    # trend every point of which is `comparable: true` — and no assertion
    # about how a break is drawn could ever fail on it. That is the
    # two-page-fixture defect again: a guard written against a boundary the
    # fixture cannot express.
    #
    # The dead end, recorded because it is not visible from here: passing a
    # different tier to `create_run` does **nothing** to the trend. The
    # snapshot writer reads `result.tier`, not the run row's — see
    # `runs._snapshot_metrics`, `tier = result.tier.value` — so the two are
    # independent records of one fact and only the second reaches the chart.
    # A second `run_audit` would also work and would cost a second crawl of
    # the fixture site for nothing; `replace` re-labels the tier on the
    # result already computed above, which is the whole of what the trend
    # reads.
    #
    # THREE runs, T3 T2 T3 — brief v16f, and the order is the whole of it. A
    # point now reads against the nearest earlier point measured the SAME
    # WAY, so a fixture of one T2 and one T3 has no pair at all: every guard
    # about how a pairing is drawn, linked or named would pass on a screen
    # with no pairing on it, which is DISCIPLINE rule 4's "listed is not
    # painted" in its exact form.
    #
    # The two T3 runs give the fixture its one pair, and the T2 goes BETWEEN
    # them rather than at either end:
    #
    #   - the newest audit's partner is then reached across both a
    #     verification and a differently-measured audit, which is the case
    #     the item is about and the one the operator's own history produced;
    #   - the two newest READINGS still differ in tier, so the crawl-diff
    #     gate below the runs table renders its refusal sentence and
    #     `test_the_crawl_diff_gates_on_comparability` still has a pair that
    #     differs;
    #   - the trend still holds points the server calls incomparable — two
    #     steps of them — which `seeded_trend` asserts as this fixture's own
    #     capability.
    #
    # What a third run costs, measured rather than assumed: the run that
    # LAST MOVED a finding state is now the second audit and not the newest.
    # A brief finding reaches `open` on its second sighting, so the second
    # run promotes them and the third finds nothing left to change. The
    # standing pill names the mover and the run picker defaults to the
    # newest, so the two no longer coincide — which
    # `test_the_scope_bar_is_three_columns.py` now asserts as the two facts
    # they are, rather than as the accident they were.
    #
    # The third run costs no crawl and no audit, for the same reason the
    # second does not: `replace` re-labels the tier on the result above.
    for n, tier in enumerate((Tier.T3, Tier.T2, Tier.T3)):
        run_result = replace(result, tier=tier)
        run_id = runs.create_run(conn, site["id"], dims, tier.value)
        # The evidence, not only the scores. `facts` on the anatomy payload
        # is read out of `crawl_evidence`, and the endpoint filters on
        # `crawl_evidence IS NOT NULL` — so without this the fixture answers
        # `facts: null` for every page and the facts half of all seventeen
        # categories can never render, whatever the sweep clicks. Two runs
        # were spent debugging the picker for a screen that had nothing to
        # show.
        runs.store_evidence(conn, run_id, snapshot(crawled))
        runs.complete_run(conn, run_id, run_result)
        # A brief finding reusing a check id the sweep also raises. This is
        # the exact collision that put "19 of 42 images lack alt text"
        # directly above "five informative images lack alt attributes" with
        # nothing saying they were different questions.
        runs.record_expert_findings(
            conn, run_id, "images", "test-model",
            [{"code": "img-alt-missing", "severity": "high",
              "summary": "Two informative images lack alt attributes.",
              "affected_urls": ["https://fixture.test/"]}])
        # And one under a part that still renders the cause table, so a
        # brief's source tag is painted somewhere the colour sweep can
        # reach it: Images renders three blocks since brief v15 step AR,
        # and a checks table carries counts rather than tags.
        runs.record_expert_findings(
            conn, run_id, "crawl", "test-model",
            [{"code": "sitemap-stale", "severity": "medium",
              "summary": "The sitemap lists a page the crawl could not fetch.",
              "affected_urls": ["https://fixture.test/promo"]}])
        # The brief's own prose, and a measured probe against one of the two
        # questions it leaves open (CQ-115, F-05). Findings alone were not
        # enough: `ReportView` is what renders `[TO CONFIRM: ...]`, and only
        # a stored *report* gives the run screen a `show <tool>` button to
        # open one with — so for the sweep's whole life the probe panel was
        # never on a page axe visited, and `.confirmed-source` shipped at
        # 4.39:1 past a green sweep because of it.
        #
        # Two markers, not one, because the panel has two states and they
        # draw different classes. The apex question is settled below and
        # renders `.confirmed-value` + `.confirmed-source`; the certificate
        # question is deliberately left unanswered and renders
        # `.to-confirm-text`. One marker could only ever paint one of them.
        #
        # The text is not free-form. `probes.probe_for` requires a subject
        # term *and* a qualifier term, so an invented sentence resolves to
        # no probe and the marker renders inert — indistinguishable, on
        # screen, from a question this product cannot measure. Both strings
        # below were checked through `confirm_items` before being pasted.
        runs.store_expert_report(
            # `content-brief`: `render-blocking` retired at item 141 step 3a,
            # `js-rendering` at item 165 and `entity-graph` at item 145. This report is only a VEHICLE for the
            # UX-79 lapsed-figures state and needs a tool with a stored report,
            # so the page route offers a `show <tool>` control to open one with.
            #
            # NOT `speed`, the brief that superseded render-blocking: `speed`
            # is site-scoped, and this route is a page route --
            # `test_every_reveal_selector_opens_everything_it_matches` records
            # in terms that "a site-scoped brief has no control on this route".
            # Tried it, and it timed out waiting for a button that cannot
            # exist there.
            #
            # `content-brief` is page-scoped. The UX-79 note below still names
            # the live instance of this state as the operator's `js-rendering`
            # report on run `1d85ff71…`, which stays readable after retirement.
            conn, run_id, "content-brief",
            {"model": "test-model",
             "report": BRIEF_REPORT,
             "findings": [{"code": "img-alt-missing", "severity": "high",
                           "summary": "Two informative images lack alt "
                                      "attributes."}],
             # UX-79. Two flagged figures, neither of which appears in
             # `BRIEF_REPORT` above — so `figures_still_derived` re-judges the
             # stored list down to nothing on the way out and the panel has a
             # total to account for with no list to show it against. That is
             # the state the live corpus already holds (`js-rendering` on the
             # operator's run `1d85ff71…` serves nine flagged and none
             # re-derived), and the state that used to render *nothing*:
             # the derived-figures block was gated on the list alone.
             #
             # `figures_withheld` is deliberately absent, which stores NULL —
             # migration 0027's "never recorded". So the flagged total here
             # comes from the stored list alone, which is the harder case:
             # a fixture that also carried a withheld count could pass on the
             # count rather than on the re-judge.
             "figures_to_verify": [{"value": "97531", "context": ""},
                                   {"value": "86420", "context": ""}],
             "tokens": 1200, "tokens_in": 900, "tokens_out": 300,
             "cost": 0.004})
        runs.store_probe_result(
            conn, run_id,
            {"probe_id": "apex-redirect", "target": "fixture.test",
             "status": "measured",
             "value": "apex 301s to https://www.fixture.test/",
             "source": "curl -sIL",
             "detail": {"hops": 1}})
        # It moves to the SECOND iteration with brief v16f, and where it sits
        # is an assertion rather than an accident. The runs table's link is
        # now the trend's partner — the nearest earlier run on the same
        # basis — and the pair here is the first and third runs, both T3.
        # The verification is seeded between them, directly beneath the
        # newest audit, so the comparison the table offers reaches across
        # both it and the T2: the relation this fixture exists to put under
        # strain, at its widest. Seeded after the LAST iteration it would be
        # the newest row, which is the state report 053 read live and the one
        # that hides the pairing defect entirely.
        #
        # A verification between two audits, so the runs table holds the
        # ordinary shape of the product's core loop — audit, verify, audit —
        # rather than audits alone. Seeded here, inside the first iteration,
        # and not after the loop: `list_runs` orders `created_at DESC`, so a
        # verification added last would be *newest*, and the pairing defect
        # it exists to expose only appears when one sits below an audit.
        # Report 053 read that state live on the real database and three
        # `vs previous` links still rendered, because the verification
        # happened to be on top.
        #
        # It re-uses the crawl and result already computed rather than
        # crawling again. That makes its composite equal to the audits',
        # which is not what a real verification looks like — a real one reads
        # a handful of pages and scores them — but the number is not what any
        # branch here turns on. `kind` is, and a second crawl would buy a
        # different figure for the price of doubling this fixture's runtime.
        # Recorded so the next reader does not take the equal scores for a
        # bug: if a guard ever needs the composites to differ, that is a
        # deliberate second crawl and its own change.
        if n == 1:
            verify_id = runs.create_run(conn, site["id"], dims, "T2",
                                        kind="verify")
            runs.store_evidence(conn, verify_id, snapshot(crawled))
            runs.complete_run(conn, verify_id, replace(result, tier=Tier.T2))
    # A second site whose robots.txt refuses, so the fixture holds a run that
    # lands `blocked`. Without one, every screen branch for the product's most
    # consequential status — "this site refused to be crawled" — renders
    # nothing, and a guard written beside it could only ever pass. 503 rather
    # than a disallow rule: a refusal the crawler cannot read at all is the
    # case that produces `blocked` rather than an empty allowed crawl.
    refused = FixtureSite({
        "/robots.txt": (503, {"Content-Type": "text/plain"}, "unavailable"),
        "/": (200, {}, THIN_HTML),
    }).start()
    try:
        blocked_site = httpx.post(
            f"{base}/api/clients/{client['id']}/sites",
            json={"domain": "https://refused.test/"}, timeout=30).json()
        blocked_crawl = crawl(refused.base_url + "/", Tier.T2,
                              budget=TierBudget(max_pages=5, request_timeout_s=5,
                                                wall_clock_s=20, delay_s=0))
        blocked_result = run_audit(Site(domain="https://refused.test/"),
                                   blocked_crawl, dims, Tier.T2)
    finally:
        refused.stop()
    blocked_id = runs.create_run(conn, blocked_site["id"], dims, "T2")
    runs.store_evidence(conn, blocked_id, snapshot(blocked_crawl))
    runs.complete_run(conn, blocked_id, blocked_result)

    conn.close()
    # Every id the sweep needs to reach a route. A route that cannot be
    # given an id renders an error page, and an error page passes axe while
    # testing nothing — which is the "listed is not painted" trap one level
    # further out.
    detail = httpx.get(f"{base}/api/sites/{site['id']}", timeout=30).json()
    runs_seen = [r["id"] for r in (detail.get("runs") or [])]
    assert runs_seen, "the fixture stored no runs, so no run route can load"
    # The compare route means "compare two audits", and `run2` used to be
    # whatever sat at index 1 — which was the older audit only because the
    # fixture held nothing else. With a verification stored between them,
    # index 1 is that verification, and `#/compare/{run}/{run2}` would
    # quietly render the refusal branch instead of a comparison: the same
    # screen id covering a different screen, which is the "listed is not
    # painted" trap this file already carries three comments about. Picked by
    # kind so the route keeps meaning what its name says.
    audits_seen = [r["id"] for r in (detail.get("runs") or [])
                   if r.get("kind") == "audit"]
    assert len(audits_seen) > 1, (
        "the fixture stores fewer than two audits, so the compare route has "
        f"no pair to render: {[(r.get('kind')) for r in detail.get('runs') or []]}")
    # The fixture's *capability*, asserted rather than assumed: the trend it
    # seeds must contain a point the server calls incomparable. Without one,
    # every guard about how a break is drawn passes on a chart that has no
    # break in it — coverage inherited from a fixture nobody re-checked,
    # which is the thing DISCIPLINE rule 4 forbids claiming.
    seeded_trend = detail.get("trend") or []
    assert any(not p["comparable"] for p in seeded_trend), (
        "the fixture's trend has no incomparable point, so nothing about a "
        f"break can be tested: {[(p['tier'], p['comparable']) for p in seeded_trend]}")
    pages_seen = httpx.get(
        f"{base}/api/runs/{runs_seen[0]}/pages", timeout=30).json()["pages"]
    # Planted before the deliverable is generated, not after: a report
    # is a snapshot of the record at the moment it is rendered, so a
    # row added afterwards made the stored document and every later
    # render of the same run two different documents.
    # A finding that names more pages than the payload's ten-URL cut. The
    # sweep's duplicate checks emit one row per member page since brief
    # v11 step AH, so the audits above no longer produce one; a stored row
    # from before that change still has the shape - one `title-duplicate`
    # naming every page of its group - and the live record holds such
    # rows. One is planted here, in the store, so the guards on the cut
    # (`test_the_fixture_has_a_finding_that_exceeds_the_url_truncation`,
    # the mark bar's page count, `test_a_count_reaches_what_it_counted.py`)
    # keep a case to judge.
    import json as _json

    from clauditseo.persistence.repo import create_id, now_iso
    _conn = connect(db_path)
    _run = _conn.execute("SELECT id FROM audit_runs WHERE site_id=? ORDER BY started_at DESC LIMIT 1",
                         (site["id"],)).fetchone()["id"]
    # Twelve pages the crawl fetched, so the row is not "gone" before a
    # test makes one of them so: the eight plain pages and four others.
    #
    # **`TEC/http-status-error` since brief v17 step AX**, and the check id
    # is the only thing about this row that has changed. It was
    # `CNT/duplicate-content` until Content gained a renderer of its own,
    # and five files read this one row - it is the only finding on this
    # fixture with more pages than the payload carries URLs, so every
    # clause about a capped list, a count that opens it, a cause that
    # groups into templates and a mark bar that counts what a re-crawl
    # would touch depends on it. Crawl & sitemaps has no renderer and so
    # still has the cause table those clauses drive.
    _urls = ([f"{fixture.base_url}/p{n}" for n in range(1, 9)]
             + [f"{fixture.base_url}{path}" for path in ("/", "/promo", "/deep", "/gallery")])
    with _conn:
        _conn.execute(
            "INSERT INTO findings (id, run_id, dimension, check_id, severity, source, summary,"
            " affected_urls, affected_total, evidence, recommendation, fingerprint, created_at)"
            " VALUES (?, ?, 'TEC', 'http-status-error', 'medium', 'deterministic', ?, ?, 12, ?,"
            " 'Fix or remove the pages that error.', ?, ?)",
            (create_id(), _run, '12 pages returned an error status.',
             _json.dumps(_urls), _json.dumps({"paths": [f"/p{n}" for n in range(1, 9)] + ["/", "/promo", "/deep", "/gallery"]}),
             "legacy-capped-list-group", now_iso()))
        _conn.execute(
            "INSERT OR REPLACE INTO finding_states (site_id, fingerprint, state, changed_by_run,"
            " updated_at) VALUES (?, ?, 'open', ?, ?)",
            (site["id"], "legacy-capped-list-group", _run, now_iso()))

        # A finding that legitimately names NO page, on a part that still
        # renders the old page (brief v16e, relay 136f).
        #
        # `test_a_count_reaches_what_it_counted.py::test_a_finding_that_
        # names_no_page_offers_no_control` drives it: an affordance opening
        # onto nothing is worse than none, and a site-scoped finding is the
        # case that produces one. That clause named Accessibility, and had
        # been re-pointed at whichever part had not yet gained a renderer -
        # until Accessibility gained one too, at which point this fixture's
        # ONLY page-less findings were the A11Y scope statements, which the
        # part page draws as neither a row nor a card. The clause had
        # nothing left to stand on in either layout.
        #
        # `llms-txt-missing` rather than an invented id: it is a real check
        # that really names no page (`ais.py`, `affected_urls=[]`), it is
        # INFO and not a scope statement so the section screen draws it as a
        # row, and `ai-surface` has no entry in `PART_RENDERERS`. Planting a
        # row whose shape the product does not produce would make the clause
        # guard a thing that cannot happen.
        #
        # If `ai-surface` ever gains a renderer, move this to another
        # old-page part rather than moving the clause: what it needs is a
        # page-less row on a screen that draws rows, and this fixture is
        # where that is arranged.
        _conn.execute(
            "INSERT INTO findings (id, run_id, dimension, check_id, severity, source, summary,"
            " affected_urls, affected_total, evidence, recommendation, fingerprint, created_at)"
            " VALUES (?, ?, 'AIS', 'llms-txt-missing', 'info', 'deterministic', ?, '[]', 0, ?,"
            " 'Consider publishing an llms.txt.', ?, ?)",
            (create_id(), _run, "No llms.txt file found.",
             _json.dumps({"status": 404}), "site-scoped-no-page", now_iso()))
        _conn.execute(
            "INSERT OR REPLACE INTO finding_states (site_id, fingerprint, state, changed_by_run,"
            " updated_at) VALUES (?, ?, 'open', ?, ?)",
            (site["id"], "site-scoped-no-page", _run, now_iso()))
    _conn.close()

    made = httpx.post(f"{base}/api/reports", timeout=120, json={
        "template": "run", "audience": "internal", "run_ids": [runs_seen[0]]})
    # A deliverable needs no model, so generation refusing here is a broken
    # fixture rather than an environment this sweep should tolerate. It used to
    # yield `""` on any non-201, which substituted `#/client-reports/` for the
    # route: a URL that renders the not-found branch, passes axe, and reports
    # the deliverable screen as swept. The sweep downgraded itself and said
    # nothing, which is the failure mode every route list in this file already
    # carries a comment about.
    #
    # Asserted rather than excused. If a deliverable genuinely cannot be made
    # in this environment, that is worth a red sweep and a look, not a quietly
    # narrower one.
    assert made.status_code == 201, (
        f"the fixture could not create a deliverable ({made.status_code}): "
        f"{made.text[:300]}. Without one the {'{report}'} route degrades to "
        "#/client-reports/ and this sweep silently stops covering it.")
    report_id = (made.json() or {}).get("id", "")
    assert report_id, (
        f"POST /api/reports returned 201 with no id: {made.text[:300]}")


    return {
        "site": site["id"],
        # The database itself, so a test can read or amend what was stored
        # rather than arrange a screen state directly. `test_heading_fault.py`
        # un-places a stored finding with it, which is the only way to render
        # the case of a finding raised before a check began recording where
        # its fault is.
        "db": str(db_path),
        "run": runs_seen[0],
        "run2": audits_seen[1],
        "page": quote(pages_seen[0]["url"], safe=""),
        "report": report_id,
        "blocked_run": blocked_id,
        # The site itself, not only its run. Screens that list runs are
        # reached per site, so a blocked run reachable only by its own id
        # leaves every per-site listing rendering complete runs alone.
        "blocked_site": blocked_site["id"],
    }


#: Screens whose colour-bearing parts only exist after a click. Auditing the
#: landing state alone would have said nothing about severity chips or source
#: tags, both of which live inside a category that has to be opened first.
#: (selector, click-them-all).
#:
#: This once read `.anat-leaf:not(:has(.n-zero))`, to avoid ending the sweep on
#: an empty category that renders no findings and therefore no severity chips.
#: That reason expired when `_sweep_page` began auditing *every* revealed state
#: rather than only the last one: the filter then bought nothing and cost eight
#: of seventeen categories, so the "nothing open here" panel — a real screen an
#: operator sees on any clean category — had never been audited. Measured
#: before removing it: 8 of 17 opened.
#:
#: Steps, in order — clicking a tab navigates away from what the previous
#: step opened, so a single selector cannot cover both. Learned by making the
#: tabs one selector alongside the tree and watching four components stop
#: rendering.
REVEAL = {
    # TWO PASSES, because the halves of a category want opposite states and
    # one pass can only be in one of them. The findings tree wants NO page —
    # a filter narrows it, and the categories that drop out never open. The
    # facts panels want a page, because without one they do not render at
    # all. Doing both in one pass traded five categories for four classes and
    # said so nowhere: every selector still matched something, so nothing
    # failed. Each pass gets its own page load, and the reveal tallies are
    # keyed by pass so the trade shows up in the output.
    "client": [
        # Pass 1 — the whole findings tree, unfiltered.
        # Parts are visited through the address since the sidebar's
        # retirement (brief v24 step BO): `@every-part` opens each in turn
        # and closes it again, see `_run_reveal`.
        [("@every-part", False),                       # every category
         # A NAMED part, not "whichever is last non-zero" (relay 136f).
         #
         # This read `.anat-leaf:not(:has(.n-zero))` and ended on whichever
         # part happened to be the last with a count - so which screen the
         # three steps below ran against was decided by the fixture's
         # zero/non-zero pattern, and any new finding could move it. Adding
         # one page-less row to `ai-surface` did exactly that: the pass
         # ended on a part whose only finding is INFO with no pages, there
         # were no fix cards, `.fix-chk` matched nothing, and four clauses
         # went red for a reason none of them was about.
         #
         # Mobile by name, which is the part this selector already ended on:
         # it was the last category with a count, and naming it changes what
         # this pass exercises not at all while making it stop depending on
         # that being true.
         #
         # NOT Crawl & sitemaps, which was the first attempt and is wrong
         # for a reason worth keeping: it holds the 12-page
         # `TEC/http-status-error` row, and
         # `test_the_mark_bar_counts_the_pages_the_server_would_recrawl`
         # derives the widest finding, opens ITS part and ticks it. Marking
         # the same row here left that clause un-ticking it, and the bar it
         # waits for never appeared. Two passes must not mark the same row.
         #
         # URLs & parameters since Mobile moved to the three-block layout
         # (brief v20): that layout has no `table.causes` and no tick, so the
         # pass matched nothing past this line and the mark bar never rendered.
         # This part is still on the across-the-site table, carries findings
         # in the fixture, and is not Crawl & sitemaps, for the reason above.
         # When it moves to three blocks this line moves again.
         ("@part:URLs & parameters", True),
         ("table.causes .group-toggle", True),         # every cause open (brief v2 step E)
         (".fix-chk", True),                           # mark, revealing the bar
         # then every pane: the step names that stay on this screen —
         # steps 1 and 6 are other routes — and the reference row.
         ('a.seq-name[href*="?tab="]', True),
         # The step walk ends on the Record; its runs, trend and crawl diff
         # are its Audits view since brief v24 step BN.
         ('.record-view a:text-is("Audits")', True),
         (".ref-link", True)],
        # Pass 2 — a part that still renders the cause table, for the
        # source tags on its rows. Title & description, Headings and
        # Images render three blocks with a checks table instead (brief
        # v13 AO, v14 AP, v15 AR), and a brief's tag is not painted there.
        [("@part:Crawl & sitemaps", True),
         ("table.causes .group-toggle", True),
         # The depth block's bars (brief v16b), last in this pass because a
         # pressed bar narrows the cause table under it - stepping on them
         # before the toggles above would leave those with nothing to open.
         # Each press replaces the last, so the sweep audits the block
         # unpressed, pressed on a bar inside three, and pressed past it.
         (".cd-chart .cd-bar", True)],
        # Pass 3 — the facts panels, which need a page. A category must be
        # open first or the fill has nothing to wait on; the choice then
        # stands while the rest are walked.
        [("@every-open-part", True),                   # something to render into
         # Item 174: the filter is page mode's control, drawn once One page
         # is pressed.
         (".mode-switch .mode-seg:nth-child(2)", True),
         (".page-find", True, "/promo"),               # the page, once
         ("@every-part", False)],                      # every category, with facts
    ],
    "workbench": [[(".wb-head", True)]],
    # The analyses table is folded since brief v2 step G; the narrow-run
    # wording and the scores it holds are captured once it is open. Not on
    # the blocked site, which has no analysis and so no fold - its
    # `.table-scroll` is the audits-with-no-analysis table, always open.
    "reports": [[(".analyses-all > summary", True)]],
    # CQ-197. The confirm-run dialog, which is where this product commits
    # money. Its own pass because it is modal: it covers the screen, so any
    # step after it in the same pass would click into a backdrop.
}

# The schedule dialog, the other place a press commits money. A fourth pass on
# `client` for the reason the fourth one gives: the passes above are already in
# states this one would destroy, and a modal over a tab-walked screen audits
# the modal against whatever tab happened to be last.
#
# Numbered itself one too high until round 108, and deferred to a block it
# had numbered one too low: this was inserted between the literal and the
# `.pill-read` append and took that one's position without either sentence
# moving — CQ-219. `test_the_reveal_passes_name_their_own_position.py` derives
# both ordinals from the parsed source now, so the next insertion cannot
# repeat it quietly. (Written out in the old wording first, and the guard
# caught the quotation as a claim — which is the guard working, so the
# sentence is paraphrased rather than the matcher loosened.)
# The scheduler is on the Audit pane since brief v2 step A, so its pass
# opens that pane by the step's name first.
REVEAL["client"].append([('a.seq-name:text-is("Audit")', True),
                         (".schedule-open", True)])

# The stored brief, opened so its prose — and the probe panel inside it — is
# on a page axe visits (CQ-115). A fifth pass on `client`, because the four
# above are already in states this one would destroy.
#
# **The dead end, recorded because the guess was reasonable and wrong.** The
# first attempt put this on the `run` route against `.pill-btn:has(.brief-ran)`
# — the `show <tool>` control in `ExpertPanel`, which does read stored reports
# and does render `ReportView`. The reveal matched **nothing**, and the reason
# is not that the selector was mistyped: `ExpertPanel` is mounted at
# `views.tsx:1243` on the **run-page** route, not on `run`, and it is passed
# `PAGE_EXPERTS` — the page-scoped subset. `images` is site-scoped, so
# it could never have appeared there whatever the route. A site brief's stored
# report is opened from the Analyses lane and nowhere else.
#
# The pane is opened by the step's accessible name rather than by position:
# the pass above walks every pane and ends on Notes, and a `.pill-read`
# step after that would find an empty panel.
REVEAL["client"].append(
    [('a.seq-name:text-is("Analyses")', True),
     # The catalogue is Analyses' own body with no part open since brief v24
     # step BO, so no control stands between the pane and the read button.
     (".crow-read .crow-act button.btn-secondary", True)],
)


#: Selectors whose rendered text a test asserts on, each mapped to the route
#: that asserts it. Kept beside the sweep because capturing it costs one
#: evaluate per audit, and an unbounded "capture everything" would make the
#: fixture's whole screen a test input.
#:
#: A tuple until `.table-scroll` was added, and the pairing was the part that
#: was assumed. The coverage guard below read `swept["client"]` for every
#: selector in the list, so a selector asserted on any other route reported
#: itself uncaptured however well it had rendered — which is what
#: `.table-scroll` did on the run it was added. Widening that guard to "seen
#: on any route" was the obvious repair and is the wrong one: it would let
#: `.facts` pass on text captured from a screen no assertion reads. The route
#: is now stated rather than defaulted, so the guard checks the pair it is
#: actually about.
TEXT_UNDER_TEST = {
    ".mark-bar": "client",
    ".facts": "client",
    # The trend's break rules (brief v16f). `.trend-frame` was the paragraph
    # that listed every break in prose; the item replaced it with rules drawn
    # on the chart, and the rule's own label is where the boundary is now
    # named in rendered text.
    ".st-break-name": "client",
    ".st-now": "client",
    ".runs-table": "client",
    ".table-scroll": "reports-blocked",
    # CQ-197. A surface that exists only after a press was audited by nothing:
    # the sweep loaded fourteen routes and never opened a dialog on any of
    # them, so the WCAG 2.2 AA claim the profile makes for the whole dashboard
    # was unverified on both of the screens where money is committed. These
    # two selectors are *inside* their dialogs, so text under them can only be
    # captured if the dialog actually opened and painted - being in `REVEAL`
    # is not evidence, which is the same distinction
    # `test_every_route_the_app_serves_is_either_swept_or_excused` draws for
    # routes.
    ".sched-block": "client",
}

#: Every dialog the app renders, mapped to the evidence that the sweep opened
#: it. Checked against the tree below rather than trusted: a third dialog
#: added without a row here is exactly the gap CQ-197 records, and a hand-kept
#: list of two is how a partial fix passes (DISCIPLINE rule 3).
#:
#: Each value is a LIST, one entry per `role="dialog"` in that file, and that
#: is CQ-204's sibling defect — CQ-217, carried for ten reports. This mapped a
#: file name to a single selector, and the population it was checked against
#: was the set of file *names* containing `role="dialog"`. So a second dialog
#: added to `tools.tsx` beside the one already there changed neither side:
#: same file name, same set, no new evidence required, green. The guard
#: written so a third dialog could not ship unswept could not see a third
#: dialog in a file that already had one — the `ROUTES` shape its own
#: docstring cites as precedent, one level in, with the population derived
#: from the tree correctly and then compared by a matcher coarser than the
#: thing being counted.
#:
#: Each entry is the `TEXT_UNDER_TEST` key that lives inside that dialog. It
#: has to be inside: a selector on the control that *opens* the dialog would
#: be captured whether or not the press did anything, which is a check drawing
#: its evidence from the thing it checks.
#: One entry since item 188 retired the Tools screen, which held the other
#: dialog. The shape stays a list per file for the reason CQ-217 above
#: records - a second dialog in a file that already has one must still need
#: its own evidence.
DIALOG_EVIDENCE = {
    "schedule.tsx": [".sched-block"],
}


def _dialogs_by_file(src: Path) -> dict[str, int]:
    """How many dialogs each `.tsx` under `src` renders — the population.

    A dict of counts rather than a set of names, so that two dialogs in one
    file are two members. Extracted from the guard below so the counting can
    be exercised against a tree that HAS a doubled file, which the real tree
    does not: a matcher's blind spot cannot be demonstrated on data that does
    not contain the thing it is blind to.
    """
    counts = {}
    for path in sorted(src.glob("*.tsx")):
        found = path.read_text(encoding="utf-8").count('role="dialog"')
        if found:
            counts[path.name] = found
    return counts


def _intercept(pg, how: str) -> None:
    """Make the boot probe fail in one specific way.

    Two answers, and they are not interchangeable — `classify` reads a 401 as
    the operator's token and anything that never became a response as the
    server. Aborting is what produces a rejected `fetch`, which is the only
    way to reach `answered == false` on the outage screen.
    """
    if how == "401":
        pg.route(PROBE_URL, lambda route: route.fulfill(
            status=401, content_type="application/json",
            body='{"detail": "unauthorized"}'))
    elif how == "abort":
        pg.route(PROBE_URL, lambda route: route.abort())
    else:                                   # pragma: no cover - typo guard
        raise AssertionError(f"unknown interception {how!r}")


def _sweep_page(url: str,
                passes: list[list[tuple]] | None,
                ready: str | None = None,
                intercept: str | None = None,
                last_resort: bool = False) -> tuple[dict, set[str]]:
    """Load, reveal, audit — in one browser pass.

    Deliberately not `axe.run_page`: that loads and audits with nothing in
    between, which is right for auditing a client's site and wrong here,
    where much of what carries colour is behind a disclosure.

    Every revealed state is audited, not just the last. Opening only the
    first category left the brief source tag and the reconciliation note
    untested, because they live on one category out of seventeen.
    """
    from playwright.sync_api import sync_playwright

    def audit(pg) -> tuple[list, set[str]]:
        result = pg.evaluate("""() => axe.run(document, {
            runOnly: { type: 'tag',
                       values: ['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa'] },
            resultTypes: ['violations'],
        }).then(r => ({ violations: r.violations.map(v => ({
            id: v.id, impact: v.impact,
            nodes: v.nodes.map(n => ({ target: n.target,
                                       failureSummary: n.failureSummary })),
        })) }))""")
        classes = set(pg.evaluate(
            """() => [...new Set([...document.querySelectorAll('[class]')]
                 .flatMap(e => [...e.classList]))]"""))
        # Rendered text, for the handful of places where the *wording* is the
        # thing under test. There is no JS test runner in this project, so a
        # component's copy is observable nowhere else.
        #
        # `textContent` where there is no `innerText`, which is every SVG
        # element: `innerText` is defined on `HTMLElement` alone, so an
        # `<svg><text>` returns `undefined` and arrives here as `None`. The
        # whole sweep died on `NoneType has no attribute strip` the first time
        # a selector named one (brief v16f's break-rule labels). `innerText`
        # stays the first choice because it is the one that respects
        # visibility, which is what "rendered text" means for HTML.
        texts = {sel: [t.strip() for t in pg.eval_on_selector_all(
                     sel, "els => els.map(e => e.innerText ?? e.textContent ?? '')")
                 if t and t.strip()]
                 for sel in TEXT_UNDER_TEST}
        return result["violations"], classes, texts

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            violations: list = []
            classes: set[str] = set()
            texts: dict = {}
            seen: set = set()
            reveals: dict[str, list[int]] = {}

            for i, reveal in enumerate(passes or [None], start=1):
                # A fresh PAGE per pass, not a fresh `goto`. These are hash
                # routes: navigating to a URL the browser is already on is a
                # no-op, so the document never reloads and the SPA keeps the
                # state the previous pass left it in — the second pass found
                # zero of everything because it was still sitting on the last
                # tab pass one clicked.
                pg = browser.new_page()
                if last_resort:
                    # The old layout's machinery on fixture parts that have
                    # findings (brief v25 step BP, `tests/last_resort.py`).
                    from tests.last_resort import on_the_layout_of_last_resort
                    on_the_layout_of_last_resort(pg)
                if intercept:
                    # Before `goto`, because the request being answered is the
                    # one `App` issues on mount. Routed per page rather than
                    # per context so a state pass cannot leak into the next.
                    _intercept(pg, intercept)
                pg.goto(url, timeout=30_000, wait_until="load")
                if ready:
                    # Allowed to raise, like the `.facts` waits below. A
                    # screen whose own content never appears is a failure to
                    # report, not a slower one to sit through -- and the flat
                    # 1.2s it replaces made "never rendered" and "rendered
                    # late" the same silent outcome.
                    pg.wait_for_selector(ready, timeout=15_000)
                else:
                    pg.wait_for_timeout(1_200)
                pg.add_script_tag(content=axe.AXE_JS.read_text(encoding="utf-8"))

                more, extra, extra_text = audit(pg)
                classes |= extra
                for sel, found in extra_text.items():
                    texts.setdefault(sel, []).extend(found)
                for v in more:
                    key = (v["id"], tuple(v["nodes"][0]["target"]))
                    if key not in seen:
                        seen.add(key)
                        violations.append(v)
                _run_reveal(pg, audit, reveal, i, reveals, classes, texts,
                            violations, seen)
                pg.close()
            return ({"violations": violations, "reveals": reveals,
                     "texts": texts}, classes)
        finally:
            browser.close()


def _run_reveal(pg, audit, reveal, pass_no, reveals, classes, texts,
                violations, seen) -> None:
    """One pass's disclosures, audited as they open.

    Tallies land under `<pass>:<selector>` so two passes over one route stay
    distinguishable: a selector that matches eight things in the unfiltered
    pass and five in the page-filtered one is reporting a real difference,
    and merging them would hide exactly the trade this split exists to make
    visible.
    """
    def collect() -> None:
        more, extra, extra_text = audit(pg)
        # `.update`, not `|=`: an augmented assignment would rebind a name
        # the enclosing scope owns, and the caller would silently keep the
        # set it started with.
        classes.update(extra)
        for sel, found in extra_text.items():
            texts.setdefault(sel, []).extend(found)
        for v in more:
            key = (v["id"], tuple(v["nodes"][0]["target"]))
            if key not in seen:
                seen.add(key)
                violations.append(v)

    for step in (reveal or []):
        selector, together, *rest = step
        if selector.startswith("@"):
            _reveal_parts(pg, selector, together, pass_no, reveals, collect)
            continue
        # A third element means "type this", not "click this". Not every
        # surface hides behind a disclosure: the facts half of a category is
        # gated on a chosen page, and the picker is a text input no click can
        # reach.
        fill = rest[0] if rest else None
        count = len(pg.query_selector_all(selector))
        key = f"{pass_no}:{selector}"
        reveals[key] = [count, 0]
        if fill is not None:
            if count:
                pg.click(selector)
                pg.keyboard.type(fill, delay=20)
                # Allowed to raise. A fixed sleep makes "never appeared" and
                # "appeared after I looked" the same silent outcome, and two
                # runs went to the wrong one.
                #
                # Either shape: a part with its own renderer answers a
                # narrow with a "now" card, and a part still on the old
                # page answers with a facts panel. Which one this sweep
                # lands on depends on which part has something open, and
                # that moves whenever a fixture row does - it moved at
                # brief v17 step AX. What the sweep is about is the
                # surface being revealed at all, not its shape.
                pg.wait_for_selector(".now-card, .facts", timeout=8_000)
                collect()
                reveals[key][1] = count
            continue
        for i in range(count):
            targets = pg.query_selector_all(selector)
            if i >= len(targets):
                break
            try:
                targets[i].click(timeout=2_000)
            except Exception:      # noqa: BLE001 - a control that will
                continue           # not open is not an audit failure
            reveals[key][1] += 1
            pg.wait_for_timeout(500)
            collect()
            if not together:
                # Selections toggle; close it again so the next one opens
                # from a known state.
                targets = pg.query_selector_all(selector)
                if i < len(targets):
                    try:
                        targets[i].click(timeout=2_000)
                    except Exception:  # noqa: BLE001
                        pass


_PARTS_JS = """async ([want]) => {
  const m = location.hash.match(/#\\/sites\\/([^?/]+)/);
  if (!m) return [];
  const cats = (await (await fetch(`/api/sites/${m[1]}/anatomy`)).json()).categories
    .filter((c) => c.group !== 'workflow');
  if (want === '@every-open-part') return cats.filter((c) => (c.total?.value ?? 0) > 0).map((c) => c.key);
  if (want.startsWith('@part:')) {
    const label = want.slice(6);
    const c = cats.find((x) => x.label === label) || cats.find((x) => x.label.includes(label));
    return c ? [c.key] : [];
  }
  return cats.map((c) => c.key);
}"""

_SET_PART_JS = """(key) => {
  const [path, query = ''] = location.hash.split('?');
  const q = new URLSearchParams(query);
  if (!q.get('tab')) q.set('tab', 'findings');
  if (key) q.set('part', key); else q.delete('part');
  location.hash = path + '?' + q.toString();
}"""


def _reveal_parts(pg, selector, together, pass_no, reveals, collect) -> None:
    """The parts the sidebar's rows used to open, visited through the address
    (brief v24 step BO). `@every-part` opens each part and closes it again;
    `@every-open-part` opens each part with something open, leaving the last
    one open (the unfiltered count is `UNFILTERED_NON_EMPTY`); `@part:<label>`
    opens one part and leaves it open. The tally is the same pair as a click
    step's: how many the step names, and how many it opened."""
    keys = pg.evaluate(_PARTS_JS, [selector])
    key = f"{pass_no}:{selector}"
    reveals[key] = [len(keys), 0]
    for k in keys:
        pg.evaluate(_SET_PART_JS, k)
        try:
            pg.wait_for_function(
                "(k) => new URLSearchParams(location.hash.split('?')[1] || '').get('part') === k",
                arg=k, timeout=5_000)
        except Exception:      # noqa: BLE001 - a part that will not open is
            continue           # not an audit failure
        pg.wait_for_timeout(500)
        reveals[key][1] += 1
        collect()
        if not together:
            pg.evaluate(_SET_PART_JS, "")
            pg.wait_for_timeout(200)


@pytest.fixture(scope="module")
def swept(served):
    """One browser pass per route, shared by the tests below."""
    base, ids = served
    out = {name: _sweep_page(base + "/" + route.format(**ids),
                             REVEAL.get(name), READY.get(name),
                             last_resort=(name == "client"))
           for name, route in ROUTES}
    # The pre-router states, in the same dict and audited by the same rules.
    # Kept in one mapping deliberately: `test_screen_has_no_detectable_
    # violations` is the gate that carries the WCAG 2.2 AA claim, and a
    # separate fixture would have meant a separate test making a quieter one.
    out.update({name: _sweep_page(base + "/" + route, None, ready, how)
                for name, _state, route, ready, how, _marker in STATES})
    return out


@pytest.mark.parametrize("name", [r[0] for r in ROUTES] + [s[0] for s in STATES])
def test_screen_has_no_detectable_violations(swept, name):
    result, _ = swept[name]
    violations = result.get("violations", [])
    if violations:
        lines = []
        for v in violations:
            node = (v.get("nodes") or [{}])[0]
            summary = (node.get("failureSummary") or "").splitlines()
            lines.append(
                f"  {v.get('id')} ({v.get('impact')}, "
                f"{len(v.get('nodes') or [])} node(s)): "
                f"{' '.join(node.get('target') or [])}\n"
                f"      {summary[-1] if summary else ''}")
        pytest.fail(f"axe found {len(violations)} violation(s) on {name}:\n"
                    + "\n".join(lines))



def test_every_colour_bearing_component_appeared_somewhere(swept):
    """Six clean screens mean nothing if the components were never drawn.

    This exact hole was live: with only a client and a site seeded, the whole
    sweep passed while `.pill-cost` carried a 3.83:1 defect, because no cost
    pill had anything to appear on.
    """
    seen: set[str] = set()
    for _, classes in swept.values():
        seen |= classes
    missing = {c: why for c, why in MUST_RENDER.items() if c not in seen}
    assert not missing, (
        "these never rendered in the sweep, so nothing was tested about them: "
        + "; ".join(f".{c} ({why})" for c, why in sorted(missing.items())))


@pytest.mark.parametrize("name", [s[0] for s in STATES],
                         ids=[s[0] for s in STATES])
def test_the_state_the_sweep_claims_to_have_audited_is_the_one_it_drew(
        swept, name):
    """Interception that silently stops working is a green sweep of nothing.

    The `ready` wait already raises if the screen never paints, but it waits
    on a selector these screens share with ordinary ones -- `.inline-form` is
    on chat and generate too -- so it cannot tell "the login gate" from "some
    screen that happens to have a form". Asserted from both ends instead: the
    marker this screen draws is present, and the signed-in shell is absent.

    Without the second half a broken `PROBE_URL` glob would route nothing,
    `App` would reach `ok`, the router would paint the app, and axe would pass
    it -- reporting coverage of a screen it never loaded.
    """
    marker = next(m for n, _s, _r, _rd, _h, m in STATES if n == name)
    _result, classes = swept[name]
    assert marker in classes, (
        f"the {name} state drew no .{marker}, so the sweep audited something "
        "else -- the boot-probe interception did not take")
    assert "topbar" not in classes, (
        f"the signed-in shell rendered on the {name} pass, so `App` reached "
        "`ok` and this is a sweep of the ordinary app wearing the state's "
        "name")


#: Routes `App.tsx` dispatches that this sweep deliberately does not load,
#: with the reason. Only redirects belong here: they render nothing of their
#: own, so auditing them audits their destination twice.
ROUTES_NOT_SWEPT = {
    "clients": "redirects to Home",
    "client": "redirects to the selected site",
    # Item 188 retired the Tools screen. The route is kept as a redirect so
    # stored links still land somewhere useful - `#/tools/<site>/<tool>` on
    # that site's Analyses catalogue, where the capability moved - and a
    # redirect has no screen to audit. It is excused rather than removed from
    # the list, which is the distinction this pair already draws.
    "tools": "redirects to the site's Analyses catalogue, or to Home",
}

#: `parts[0] === "<name>"` in App.tsx's dispatcher, which is how a hash route
#: is claimed. Anything it claims either appears in ROUTES or is excused
#: above, by name, in this file.
DISPATCHED = re.compile(r'parts\[0\]\s*===\s*"([a-z-]+)"')
#: Sub-routes are claimed on `parts[2]` — under `sites` and under `runs`
#: both, so they are matched by bare name rather than by an assumed parent.
#: Matching only `parts[0]` would call `#/sites/{id}/chat` covered because
#: `#/sites/{id}` is in the list, which is the same "listed is not painted"
#: mistake one level up.
DISPATCHED_SUB = re.compile(r'parts\[2\]\s*===\s*"([a-z-]+)"')


def test_the_trend_says_where_a_comparison_stops_being_one(swept):
    """The caveat the server computes has to reach the operator as text.

    `site_trend` has marked points `comparable: false` since migration 0012
    and gained `tier` in the key at `a82a3bd`. None of it reached the client:
    `SiteDetail["trend"]` was typed `{ value, captured_at }`, so the fact was
    structurally invisible and the chart drew one unbroken `<path>` across an
    engine change and a tier change alike.

    Asserted on rendered text, not on a `title` and not on the component
    source, because provenance says a stated limitation must appear in
    rendered text - a caveat only a hover reveals is the breach, not the fix.
    The fixture seeds T3, T2, T3, so two boundaries exist and the assertion
    has something that can fail.

    **Read off the rule labels since brief v16f**, where it used to read off
    `.trend-frame`, the paragraph that listed every break in prose. The item
    dropped that paragraph and drew the breaks instead, so this clause moved
    with the fact rather than being retired with the element: a rule label is
    a `<text>` node in the document, which is what "rendered text" asks for,
    and it names the term that moved rather than merely reporting that one
    did.
    """
    captured = [t for t in (swept["client"][0]["texts"].get(".st-break-name") or [])
                if t]
    assert captured, (
        "no break rule captured any text in the sweep, so the trend renders "
        "no statement of where a comparison stops being one")
    said = " ".join(captured)
    assert "T3" in said and "T2" in said, (
        "the trend names no tier, so the boundary the server flagged is not "
        f"stated on the screen: {said!r}")


def test_every_route_the_app_serves_is_either_swept_or_excused():
    """Inverted, because the old direction could not fail.

    It iterated ROUTES and asserted each still existed in `App.tsx` — so
    adding a screen was invisible to it, and seven of fourteen went unswept
    while the WCAG claim was made for the whole app. The list has to be
    checked against what the dispatcher serves, not the other way round.

    Being in ROUTES is not being covered, either: a route can load and paint
    nothing, which is what the anatomy facts panels did for months. This test
    only proves the sweep visits it. `MUST_RENDER` and the empty-capture
    guard are what prove something was drawn.
    """
    app = (Path(__file__).resolve().parents[1] / "dashboard" / "src"
           / "App.tsx").read_text(encoding="utf-8")
    served = set(DISPATCHED.findall(app)) | set(DISPATCHED_SUB.findall(app))
    swept: set[str] = set()
    for _, route in ROUTES:
        segments = route.replace("#/", "").split("/")
        swept.add(segments[0])
        if len(segments) > 2:
            swept.add(segments[2])
    missing = sorted(served - swept - set(ROUTES_NOT_SWEPT))
    assert not missing, (
        "App.tsx serves routes the accessibility sweep never loads, so the "
        "WCAG 2.2 AA claim does not hold for them: "
        + ", ".join(f"#/{m}" for m in missing)
        + ". Add them to ROUTES, or name them in ROUTES_NOT_SWEPT with the "
          "reason — do not trim the list to make this pass.")


#: `authState` members that paint nothing of their own, with the reason. Same
#: contract as `ROUTES_NOT_SWEPT`: a member is here or it is swept, and the
#: reason is written down rather than implied by absence.
STATES_NOT_SWEPT = {
    "checking": "App returns null while the boot probe is in flight — there "
                "is no document to audit",
    "ok": "renders the router, which is every entry in ROUTES",
}

#: The union `App` declares for `authState`. Read from the source rather than
#: restated here, because a hard-coded list of four is exactly how a fifth
#: state ships unswept — the mistake `ROUTES` made with seven of fourteen.
AUTH_STATES = re.compile(r"\[authState,[^\]]*\]\s*=\s*useState<([^>]+)>", re.S)


def test_every_full_screen_state_the_app_renders_is_either_swept_or_excused():
    """The route guard beside this one cannot see these, by construction.

    It enumerates what the *dispatcher* claims — `parts[0] === "..."` — so it
    is blind to every screen `App` paints before the router runs. Signing in
    and the server being unreachable are both such screens, both are states a
    real operator meets, and both sat outside the one gate that enforces WCAG
    2.2 AA on this product while the claim was made for the whole app.

    That is the same "listed is not painted" failure the route guard was
    inverted to catch, one level further up, and it needs its own population
    for the same reason: the dispatcher regex can never grow to include a
    screen that has no route.
    """
    app = (Path(__file__).resolve().parents[1] / "dashboard" / "src"
           / "App.tsx").read_text(encoding="utf-8")
    union = AUTH_STATES.search(app)
    assert union, (
        "could not find App.tsx's `authState` union, so this guard is "
        "asserting nothing — the declaration moved or was renamed, and the "
        "population has to be re-derived rather than the guard deleted")
    declared = set(re.findall(r'"([a-z-]+)"', union.group(1)))
    assert declared, (
        f"App.tsx's `authState` union parsed to no members: {union.group(1)!r}")

    swept = {state for _, state, *_ in STATES}
    missing = sorted(declared - swept - set(STATES_NOT_SWEPT))
    assert not missing, (
        "App renders full-screen states the accessibility sweep never loads, "
        "so the WCAG 2.2 AA claim does not hold for them: "
        + ", ".join(missing)
        + ". Add them to STATES, or name them in STATES_NOT_SWEPT with the "
          "reason — do not trim the union to make this pass.")


@pytest.mark.parametrize("name", [r[0] for r in ROUTES])
def test_every_reveal_selector_opens_everything_it_matches(swept, name):
    """A reveal that stops matching fails nothing on its own — it just audits
    less, silently, which is the exact rot this file exists to prevent.

    Both halves matter. `matched == 0` catches a selector left behind by a
    class rename. `opened < matched` catches a control that is present but
    disabled, which is how the page-scoped panels on the anatomy screen went
    unswept: their pill is disabled until a page is chosen, and a click that
    does nothing is not a click that failed.
    """
    result, _ = swept[name]
    for selector, (matched, opened) in result["reveals"].items():
        assert matched, f"{name}: reveal selector {selector!r} matched nothing"
        assert opened == matched, (
            f"{name}: {selector!r} matched {matched} but only opened {opened}")


#: The bar's count and its buttons must each name what they are counting.
FINDING_UNIT = re.compile(r"\d+\s+finding")
PAGE_UNIT = re.compile(r"\d+\s+page")


def test_the_mark_bar_names_what_it_counts(swept):
    """The bar counted findings while the row beside it counted pages.

    `1 marked fixed here` above a row reading `11` in a Pages column, and a
    button reading `verify these 1 now`, are two units in one bar with
    neither named — and `these 1` is not grammatical, so nothing signals
    which is meant. Both numbers were always true. Verifying one finding does
    re-crawl eleven pages; the bar just never said so, and the sentence that
    would have — the button's `title` — is only reachable by hovering.
    """
    result, _ = swept["client"]
    bars = result["texts"].get(".mark-bar") or []
    assert bars, "the mark bar never rendered, so its wording was not tested"
    text = " ".join(bars)
    assert FINDING_UNIT.search(text), f"no findings unit named in: {text!r}"
    assert PAGE_UNIT.search(text), f"no pages unit named in: {text!r}"


@pytest.mark.parametrize("sel,route", sorted(TEXT_UNDER_TEST.items()))
def test_every_text_selector_captured_something(swept, sel: str, route: str):
    """A selector that captures nothing asserts against an empty string.

    This has already held silently twice. `.mark-bar` sat in MUST_RENDER by
    class while the bar itself never painted, so its wording went untested
    until a reveal step was added to tick a box. `.facts` was then added here
    on the belief that the Security & transport panel was swept — it is not:
    `anatomy.tsx:1315` gates the whole facts half of every category on
    `data.facts`, which is null until a page is chosen, and the picker is a
    text input no click can reach. The assertion written against it passed
    its own guard clause and told us nothing.

    Class presence is not enough, which is why this is separate from
    MUST_RENDER: a class can appear on an empty container. Text is what the
    assertions are about, so text is what must be non-empty.
    """
    captured = [t for t in (swept[route][0]["texts"].get(sel) or []) if t]
    assert captured, (
        f"{sel} captured no text on {route}, the route whose assertions read "
        "it, so every assertion about its wording is being made against an "
        "empty string")


def test_every_dialog_the_app_renders_is_opened_by_the_sweep():
    """CQ-197: a surface that exists only after a press was swept by nothing.

    The population is derived from the tree rather than from this file's own
    list - the promoted *guard's population* invariant. A hand-kept list of
    two dialogs would pass forever while a third was added unswept, which is
    the shape this finding has: `ROUTES` was once the population for route
    coverage and the test read it in the direction that could not fail, so
    seven of fourteen screens went unswept while the WCAG claim was made for
    all of them. Same defect, one level in - the routes are covered now, the
    states behind a press are not.

    This test only proves each dialog is *declared* with evidence.
    `test_every_text_selector_captured_something` is what proves the dialog
    actually opened and painted, which is the same division of labour
    `test_every_route_the_app_serves_is_either_swept_or_excused` states for
    routes: being listed is not being covered.
    """
    src = Path(__file__).resolve().parents[1] / "dashboard" / "src"
    rendered = _dialogs_by_file(src)
    assert rendered, (
        "no file under dashboard/src renders `role=\"dialog\"`; the grep has "
        "stopped working and this guard is asserting over nothing")
    assert set(rendered) == set(DIALOG_EVIDENCE), (
        f"the dialogs the app renders are {sorted(rendered)}, not "
        f"{sorted(DIALOG_EVIDENCE)} - a dialog was added or removed and the "
        "rendered sweep no longer covers what this file claims it does")
    for name, count in rendered.items():
        assert len(DIALOG_EVIDENCE[name]) == count, (
            f"{name} renders {count} dialog(s) and DIALOG_EVIDENCE names "
            f"{len(DIALOG_EVIDENCE[name])} piece(s) of evidence for it - a "
            f"dialog was added beside one already there, which is the case "
            f"this guard was blind to until round 108 (CQ-217). Every dialog "
            f"needs its own selector from INSIDE it, or it ships unswept.")
    for name, selectors in DIALOG_EVIDENCE.items():
        assert len(set(selectors)) == len(selectors), (
            f"{name} names the same evidence selector twice, so one of its "
            f"dialogs is being vouched for by the other one's contents")
        for sel in selectors:
            assert sel in TEXT_UNDER_TEST, (
                f"{name}'s dialog names {sel!r} as its evidence and that "
                "selector is not captured by the sweep, so nothing reads it")


def test_the_dialog_population_counts_dialogs_and_not_the_files_holding_them(
        tmp_path):
    """CQ-217, driven rather than asserted.

    The real tree has one dialog per file, so no assertion over it can tell a
    per-file matcher from a per-dialog one. This builds the tree that can: one
    `.tsx` with two `role="dialog"` in it, and one with a single dialog.

    RED before this round, where the derivation returned a set of file names
    and the doubled file was one member of it.
    """
    dialog = '<div role="dialog" id="%s" />\n'
    (tmp_path / 'twice.tsx').write_text(
        (dialog % 'a') + (dialog % 'b'), encoding='utf-8')
    (tmp_path / 'once.tsx').write_text(
        dialog % 'c', encoding='utf-8')
    (tmp_path / 'none.tsx').write_text(
        '<div id="plain" />\n', encoding='utf-8')

    assert _dialogs_by_file(tmp_path) == {"once.tsx": 1, "twice.tsx": 2}, (
        "the dialog population cannot distinguish a file with two dialogs "
        "from a file with one, so a dialog added beside an existing one adds "
        "no evidence requirement and ships unswept")


#: Categories with something open, counted with NO page filter applied. A
#: page narrows the findings, so a sweep that chooses one before walking the
#: tree walks a smaller tree. Was 8 on the two-page fixture and 5 once a page
#: was chosen; the fourteen-page fixture opened 9, and 10 since the fixture
#: seeds a brief finding under Crawl & sitemaps as well (brief v15 step AR,
#: so a brief's source tag is painted on a part that still renders the cause
#: table). The number is expected to move whenever the fixture's content
#: shapes change — what must not move is that both passes report the
#: unfiltered figure.
#:
#: 11 since relay 136f seeds one page-less finding on AI surface. That part
#: had nothing open, so it was not counted; the row moves it into the tally
#: without changing any other part. Why the row exists at all is written
#: where it is planted, beside the `TEC/http-status-error` one.
#: 12 since item 141 (brief v19 step BB): the URLs & parameters part gained the
#: ten free sweep checks, and the fixture's URLs trip some of them, so `urls`
#: is now a non-empty category where before it held only brief-only checks.
UNFILTERED_NON_EMPTY = 12


def test_the_findings_tree_is_swept_with_no_page_chosen(swept):
    """The two halves of a category want opposite states.

    The findings tree wants no page — a filter narrows it, and the categories
    that drop out are never opened. The facts panels want a page, because
    without one they do not render at all. Satisfying one by choosing a page
    early costs the other silently: the reveal still reports every selector
    it matched, so nothing fails, and the tree quietly shrinks.

    Asserted on the count rather than on the ordering, because the ordering
    is the thing likely to be rearranged again.
    """
    reveals = swept["client"][0]["reveals"]
    matched = [v[0] for k, v in reveals.items()
               if k.endswith("@every-open-part")]
    assert matched, "no non-empty-category step ran on the client route"
    assert max(matched) == UNFILTERED_NON_EMPTY, (
        f"the findings tree was swept with a page filter active: "
        f"{max(matched)} non-empty categories where {UNFILTERED_NON_EMPTY} "
        "are open unfiltered — the narrowed ones were never opened")


def test_the_fixture_has_a_finding_that_exceeds_the_url_truncation(served):
    """The fixture must be able to express a finding wider than the wire.

    `anatomy_view` sends `"pages": len(urls)` with `"urls": urls[:10]`, so a
    finding spanning more than ten pages reports a count the URL list cannot
    account for. Any guard on the mark bar's page number — the one that says
    what a verify will actually re-crawl — is vacuous while the two numbers
    are equal, because the truncation never bites and a reader of either
    field gets the same answer.

    Asserted on the fixture rather than on the bar: this is the capability
    the harness needs before the bar can be tested at all.
    """
    import httpx

    base, ids = served
    site_id = ids["site"]
    anat = httpx.get(f"{base}/api/sites/{site_id}/anatomy", timeout=30).json()
    spans = [(f["pages"], len(f["urls"]), f["check_id"])
             for c in anat["categories"] for f in c["findings"]]
    assert spans, "the fixture produced no findings at all"
    widest = max(spans)
    assert widest[0] > widest[1], (
        "no fixture finding spans more than the 10-URL wire truncation — "
        f"widest is {widest[2]} at pages={widest[0]}, urls={widest[1]}, so a "
        "guard on the mark bar's page count cannot fail")


def test_a_late_response_for_another_page_is_not_rendered(served):
    """Evidence must be labelled with the page it actually came from.

    `2ed927a` stopped blanking `data` on a page change so the picker would
    survive being typed into. That left this screen's fetch with no ordering
    guard: between choosing a page and its reply landing, every category
    count, every finding list and the whole facts panel show the previous
    page's data under the new page's name, and two replies resolving out of
    order leave it that way.

    Driven rather than read from source, because the defect is about which
    reply wins. The ordering is decided rather than raced: `/p1`'s response
    is held open while `/p2` is chosen and answered, and the handler firing
    is asserted — an earlier attempt at this passed against unfixed code and
    the delay was never confirmed to have applied.

    It also needs a fixture with two non-empty pages one keystroke apart.
    Editing `/p1` to `/p2` never empties the box, so the picker commits
    exactly twice; on the old two-page fixture every move cleared the field
    first and put a third request in flight with no controlled order.
    """
    import re as _re

    from playwright.sync_api import sync_playwright

    base, ids = served
    site_id = ids["site"]
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        # The cause table and its tick are the layout of last resort's (brief
        # v25 step BP); these parts are drawn there for this page.
        from tests.last_resort import on_the_layout_of_last_resort
        on_the_layout_of_last_resort(pg)
        try:
            pg.goto(f"{base}/#/sites/{site_id}", wait_until="load", timeout=30_000)
            # The next statement queries `.anat-leaf`, so that is the marker
            # this screen is ready -- proven by the code below rather than
            # guessed at, and it raises instead of sleeping through a screen
            # that never arrived.
            pg.wait_for_selector(ANATOMY_READY, timeout=15_000)
            # Content, and on its three-block page since brief v17 step
            # AX. What this clause is about is the narrow - a reply for
            # the page you were typing must not render under the page you
            # chose - and both pages have one. No part that keeps the old
            # page shows anything page-identifying in `.facts`
            # (Accessibility's reads "LANGUAGE en / LANDMARKS main" on
            # every page), so the assertion had nothing to hold; the
            # "now" card carries the page's own opening words.
            open_part(pg, "Content")
            pg.wait_for_timeout(500)

            parked = []

            def hold(route):
                # Parked, not slept in. A `time.sleep` here blocks the sync
                # driver, so the browser cannot issue the SECOND request
                # either — the replies then arrive in order and the defect
                # cannot appear. Measured: with a sleep, /p2 was not sent
                # until 5.83s, after /p1 landed at 5.44s.
                parked.append(route)

            pg.route(_re.compile(r"/anatomy\?page=.*%2Fp1(&run_id=[^&]*)?$"), hold)

            open_page_filter(pg)
            pg.click(".page-find")
            pg.keyboard.type("/p1", delay=30)      # held open
            pg.wait_for_timeout(400)
            pg.keyboard.press("Backspace")         # never empties the box
            pg.keyboard.type("2", delay=30)        # answers immediately
            pg.wait_for_selector(".now-card", timeout=8_000)
            pg.wait_for_timeout(500)
            assert parked, (
                "the route handler never fired, so nothing was held and this "
                "test proves nothing about ordering")
            for route in parked:
                route.continue_()              # the superseded reply, late
            pg.wait_for_timeout(3_000)
            shown = " ".join(
                t for t in pg.eval_on_selector_all(
                    ".now-card", "els => els.map(e => e.innerText)") if t)
            assert "Page 2" in shown, (
                f"the chosen page's facts never rendered: {shown[:300]!r}")
            assert "Page 1" not in shown, (
                "a superseded reply for /p1 was rendered under /p2's label: "
                f"{shown[:300]!r}")
        finally:
            browser.close()


def test_the_business_type_select_is_not_buried_under_the_row_link(served):
    """KI-07. `home.tsx:167` states the requirement this breaks, in the
    comment explaining why the select was deliberately placed outside the
    row anchor: "a select wrapped in an anchor is a select you cannot use."
    `styles.css:141` stretches `.row-link::after` across the whole
    `.linked-row`, and the escape at `:142` lifts `button` and
    `a:not(.row-link)` back above it — `select` is not in that list, so
    `.biz-select` sits underneath and the click lands on the row link
    instead, navigating away from Home.

    Driven rather than read from source, because the defect is about which
    element the compositor hands the click to, which only a real browser
    resolves — the CSS is the explanation, not the proof.
    """
    from playwright.sync_api import TimeoutError as PWTimeout, sync_playwright

    base, ids = served
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        try:
            pg.goto(f"{base}/#/", wait_until="load", timeout=30_000)
            # Item 176: the type is edited behind the card, whose name is the
            # link - the select must still take its own click once opened.
            pg.wait_for_selector(".home-card", timeout=15_000)
            pg.click(".home-card .home-card-manage > summary")
            pg.wait_for_selector(".biz-select", state="visible", timeout=15_000)
            start_url = pg.url

            try:
                pg.click(".biz-select", timeout=3_000)
            except PWTimeout as exc:
                pytest.fail(f"the select could not be clicked at all: {exc}")

            pg.wait_for_timeout(300)
            assert pg.url == start_url, (
                f"clicking the business-type select navigated the page "
                f"({start_url} -> {pg.url}) — the row link underneath it "
                "received the click instead of the select opening")
        finally:
            browser.close()


def test_the_mark_bar_counts_the_pages_the_server_would_recrawl(served):
    """The bar must name the number the verify will actually act on.

    `anatomy_view` sends `"pages": len(urls)` with `"urls": urls[:10]`, and
    the anatomy bar counted the truncated list — so a finding on twelve pages
    read `across 10 pages` directly above a Pages column reading `12`, while
    the server re-crawled all twelve. The record's bar computes the same
    number from `affected_urls`, which is not truncated, so the two screens
    disagreed for the same marks.

    Asserted against the API's own figure rather than a literal, so the test
    says "these two agree" rather than pinning a number that moves with the
    fixture. `test_the_mark_bar_names_what_it_counts` could not see this: it
    matches `\d+\s+page` and a wrong number is still a number, and on a
    two-page fixture the truncation never bit.
    """
    import httpx
    from playwright.sync_api import sync_playwright

    base, ids = served
    site_id = ids["site"]
    anat = httpx.get(f"{base}/api/sites/{site_id}/anatomy", timeout=30).json()
    widest = max(((f["pages"], f["check_id"], c["key"])
                  for c in anat["categories"] for f in c["findings"]
                  if f["source"] == "deterministic"), default=None)
    assert widest and widest[0] > 10, (
        f"the fixture has no tickable finding past the truncation: {widest}")
    true_pages, check_id, cat_key = widest
    # The part the widest row is actually on, which this clause computed
    # and then threw away: it opened a part picked some other way and
    # looked for the row there. Right while one fixture row was the widest
    # and lived on the part being opened; wrong the moment the row moved,
    # which it did at brief v17 step AX.
    want = next(c["label"] for c in anat["categories"] if c["key"] == cat_key)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        # The cause table and its tick are the layout of last resort's (brief
        # v25 step BP); these parts are drawn there for this page.
        from tests.last_resort import on_the_layout_of_last_resort
        on_the_layout_of_last_resort(pg)
        try:
            pg.goto(f"{base}/#/sites/{site_id}", wait_until="load", timeout=30_000)
            # The anatomy has loaded -- proven rather than guessed at, and it
            # raises instead of sleeping through a screen that never arrived.
            pg.wait_for_selector(ANATOMY_READY, timeout=15_000)
            open_part(pg, want)
            # The category's own findings table, which is what the next
            # statement reads a row out of.
            pg.wait_for_selector("table.findings:not(.catalogue-table)", timeout=15_000)
            # Instances stand under their causes since brief v2 step E.
            for i in range(pg.locator("table.causes .group-toggle").count()):
                pg.locator("table.causes .group-toggle").nth(i).click()
            pg.wait_for_timeout(150)

            row = pg.query_selector(f"tr:has(code:text-is('{check_id}'))")
            assert row, f"no row for {check_id} on the anatomy screen"
            tick = row.query_selector(".fix-chk")
            assert tick, f"{check_id} offers no tick, so the bar never appears"
            tick.click()
            pg.wait_for_selector(".mark-bar", timeout=8_000)
            pg.wait_for_timeout(400)

            bar = pg.eval_on_selector(".mark-bar", "e => e.innerText")
            said = [int(n) for n in re.findall(r"(\d+)\s+pages?", bar)]
            assert said, f"the bar named no page count at all: {bar!r}"
            assert true_pages in said, (
                f"{check_id} spans {true_pages} pages and the server would "
                f"re-crawl all of them; the bar said {said} — "
                f"{bar!r}")
        finally:
            browser.close()


def test_the_security_panel_names_which_end_of_the_tls_range_it_reports(swept):
    """`TLSv1.3` alone reads as the site's floor and is its ceiling.

    One handshake reports the highest version both ends agreed on, so a
    server still accepting TLS 1.0 rendered identically to one that refuses
    it — a displayed value whose stated limitation appeared nowhere in
    rendered text, which is the promoted provenance clause. The floor was
    measured in the same crawl and dropped at `snapshot()`.

    The fixture is served over http, so both figures are absent here; what
    is asserted is that the row says which figure it is and that the absence
    is stated rather than shown as `?`.
    """
    # Lower-cased before matching: `.fact-key` sets `text-transform:
    # uppercase`, and `innerText` returns what was rendered rather than what
    # the markup says, so a label written in prose comes back shouting.
    facts = " ".join(swept["client"][0]["texts"].get(".facts") or []).lower()
    assert facts, "no facts panel rendered, so the TLS row was not tested"
    assert "accepts down to" in facts, (
        f"the security panel reports no floor at all: {facts[:400]!r}")


def test_the_fixture_has_a_verification_between_two_audits(served):
    """A run kind the fixture cannot store is a screen branch no guard can see.

    Same shape as the blocked run below, and named by the loop's own guard
    rather than inferred: `test_site_reading_runs.py` states as its stated
    limitation that its client-side check is a source check because "the
    rendered sweep has no fixture site carrying a verification, and building
    one is a separate change". This is that change.

    **Position is the assertion, not merely presence.** `list_runs` orders
    `created_at DESC`, and the two defects this net exists to make visible
    only appear when a verification sits *between* two audits: the runs table
    offers `vs previous` on adjacent rows, so a verification below the newest
    audit removes that audit's link, and a verification that is itself newest
    hides the defect entirely. Report 053 read exactly that state live and
    said so — three links still rendered because the verification happened to
    be on top. A fixture seeding one last would reproduce the blind spot it
    was built to remove.

    Asserts the shape, not the screens. What the two screens then do with it
    is WF-65 and UX-42, and neither is touched here — this is the net.
    """
    import httpx

    base, ids = served
    stored = httpx.get(f"{base}/api/sites/{ids['site']}", timeout=30).json()
    kinds = [r["kind"] for r in (stored.get("runs") or [])]
    assert "verify" in kinds, (
        "no run in the fixture is a verification, so no branch that turns on "
        f"a run's kind can be rendered or asserted. Stored kinds: {kinds}")
    i = kinds.index("verify")
    assert 0 < i < len(kinds) - 1 and kinds[i - 1] == "audit"         and kinds[i + 1] == "audit", (
        "the fixture stores a verification but not between two audits, so "
        "the newest audit has no verification under it and the pairing the "
        f"runs table offers is never put under strain. Stored kinds: {kinds}")


def test_one_comparison_is_offered_and_it_reaches_across_a_verification(swept):
    """The comparison pairs with the nearest earlier run on the same basis.

    WF-65, and brief v16f. `list_runs` orders `created_at DESC` and lists
    every kind, so the product's own loop — audit, verify, audit — puts a
    verification directly under the newest audit. The runs table offered
    `vs previous` only where the *adjacent row* was also a reading, so the
    newest audit lost its link exactly when the loop had just produced
    something to compare. WF-65 replaced adjacency with consecutiveness among
    readings; v16f replaced that in turn with the trend's own partner, because
    two consecutive readings at different tiers measure different populations
    and the comparison offered between them was one the crawl diff on the same
    screen already refuses to draw.

    Counted, not merely present, and the count is what makes this an
    assertion rather than a restatement. The fixture stores
    `[T3 audit, verify, T3 audit, T2 audit]` newest first — see the fixture
    guard below — so:

      - under CONSECUTIVE READINGS it is **two**: the newest T3 to the T2
        under it, and that T2 to the first T3 — and both of those are
        comparisons across a tier change, which is the pairing the crawl diff
        on this same screen already refuses to draw and which v16f stops
        offering;
      - under the PARTNER rule it is exactly **one**: the two T3 runs, joined
        across both the verification and the T2 between them, and nothing
        offered for the T2, which nothing before it measured like.

    **Renamed, and what the rename gives up is worth saying.** This was
    "the newest audit offers a comparison": WF-65's defect was a verification
    directly beneath the newest audit stealing its link, and the fixture's
    two audits made the old rule answer zero. Under the partner rule a row
    between two points is skipped whatever it is, so that defect is not
    expressible any more, and the fixture now needs three audits for other
    guards' sake — on which the adjacent-row rule also answers one. What the
    count still separates is consecutive-readings from the partner rule.
    Which ROW carries the link is asserted on the href in
    `test_the_score_trend_is_drawn.py::test_the_runs_table_names_the_partner_and_links_to_it`,
    where the fixture is the operator's own nine points and adjacency would
    render eight links rather than one.
    """
    # One capture of the table, not every capture joined: the sweep opens
    # the Audit pane in more than one pass since brief v2 step A, and the
    # pairing is a property of the table, not of how often it was read.
    text = (swept["client"][0]["texts"].get(".runs-table") or [""])[0]
    assert text, "the runs table never rendered, so its Compare column was "\
                 "not tested — is the History tab still swept?"
    assert text.lower().count("vs previous") == 1, (
        "the runs table offers "
        f"{text.lower().count('vs previous')} comparisons where the fixture's "
        "two audits, separated by a verification, are one pairing: the "
        f"newest audit has no `vs previous` link. Rendered: {text[:600]!r}")


def test_the_runs_table_says_in_text_what_a_narrow_run_is(swept):
    """UX-42. Removing the `title` is half the fix; this is the other half.

    The source guard in `test_dashboard_a11y.py` can only say the sentence
    is no longer in an attribute — a fix that deleted the `title` and wrote
    nothing in its place would satisfy it completely, and would leave the
    operator with two bare words where there had at least been a hover.
    This asserts the sentence reaches the screen, on the table that shows
    the term.

    Read from `innerText`, which is what a browser lays out: an `sr-only`
    span or a second `title` would not appear here, and neither would text
    behind a `display: none`. Same reason the mark-bar assertions read this
    and not the markup.
    """
    text = " ".join(swept["client"][0]["texts"].get(".runs-table") or []).lower()
    assert text, "the runs table never rendered, so its wording was not tested"
    assert "narrow audit" in text, (
        "no narrow run is listed, so the caption under test cannot have "
        f"rendered — has the fixture's verification gone? Rendered: {text[:300]!r}")
    assert "re-read a named handful" in text, (
        "the table uses the term 'narrow audit' and never says what it means "
        "in text a keyboard reaches — the caption is missing or its wording "
        f"has drifted from the source guard's phrase. Rendered: {text[:600]!r}")


def test_the_fixture_has_a_blocked_run_to_render(served):
    """A screen branch the fixture cannot reach is a branch no guard can see.

    `blocked` is the most consequential status the product has — "this site
    refused to be crawled" — and every surface that would show it (WF-02,
    UX-02, UI-03) is unrendered today because the fixture stores two
    `complete` runs and nothing else. A chip, a `blocked` case in the run
    headline, a marked score cell: all of them would paint nothing here, and
    a test written beside them could only ever pass.

    Same shape as the two-page fixture that could not express the defects its
    guards were written against, and the reason this is ranked above the work
    it protects rather than beside it.
    """
    import httpx

    base, ids = served
    statuses = [s.get("last_run_status")
                for s in httpx.get(f"{base}/api/overview", timeout=30).json()["sites"]]
    assert "blocked" in statuses, (
        "no site in the fixture reports a blocked run, so no blocked-state "
        f"branch can be rendered or asserted. Reported: {statuses}")


def test_a_blocked_run_carries_no_score_on_the_reports_screen(swept):
    """The score a screen may print is decided by status, and this screen was
    never told the status.

    `hasScore` has existed since `7402181` and is applied at six render sites;
    `reports.tsx` is the seventh and eighth and could not apply it, because
    neither row shape `site_reports` returns carries `status`. So the one
    screen that lists every audit a client has ever had printed 80.0 and 95.0
    for two runs that fetched nothing — the composite robots.txt and the
    sitemap produce on their own.

    Asserted on rendered text rather than on source: which branch renders is
    the defect, and a gate can be moved without changing what a reader of the
    source expects. `.table-scroll` is every table on the screen, which for
    this site is the runs table alone — it has no analyses, which is why it is
    the site the assertion is made against.

    The decimal is the assertion, not the word. `ScoreBadge` renders
    `score.toFixed(1)`, and nothing else in these rows carries a decimal
    point: the date is hyphenated and the tier is `T2`.
    """
    import re

    result, _classes = swept["reports-blocked"]
    tables = " ".join(result["texts"].get(".table-scroll") or [])
    assert tables, (
        "the reports screen rendered no table for the blocked site, so "
        "nothing here was tested")
    assert "not scored" in tables.lower(), (
        "the blocked run's score cell says nothing about why it is empty: "
        f"{tables[:400]!r}")
    printed = re.search(r"\d+\.\d", tables)
    assert not printed, (
        "a run that fetched nothing is printed with a composite score on the "
        f"reports screen: {printed.group(0)!r} in {tables[:400]!r}")


def test_the_blocked_run_screen_shows_the_findings_it_promises(swept):
    """A blocked run's evidence is real, and the screen says so in its own copy.

    `7402181` moved the results gate from `hasResults` to `hasScore` so a
    blocked run would stop printing a composite built from robots.txt alone.
    Correct — but that gate wrapped the findings table, the priority plan,
    the analyst band and the cost log as well as the headline, so the card
    added directly above it says "The findings below come from robots.txt and
    the sitemap" over an empty page.

    Two predicates, two questions: `hasScore` asks whether a screen may PRINT
    a composite; `hasResults` asks whether the run produced findings a screen
    may read. The regression was applying one of them by position — where the
    old gate happened to sit — rather than by meaning.

    Asserted on the swept classes for that route rather than on source: the
    defect is which block renders, and a gate can be moved without changing
    what a reader of the source expects.
    """
    _result, classes = swept["run-blocked"]
    assert any(c.startswith("tone-sev-") for c in classes), (
        "the blocked run screen rendered no severity chip, so its findings "
        "are gated off — the card above them promises they are there")


def test_a_brief_whose_figures_all_lapse_still_accounts_for_them(served):
    """UX-79's second half, and the one only a browser can see.

    `expert_report` re-judges a stored brief's flagged-figure list on the way
    out. When today's rule re-derives *none* of them the list is empty, and
    the derived-figures block used to be gated on that list alone — so the
    operator whose spot-check list lost every value got no list, no total and
    no reason, which is the finding's own impact one layer out.

    **Observed before it was written, not predicted.** Driven against the
    operator's own instance on 23 August 2026, run `1d85ff71…`, brief
    `js-rendering`: the served payload carries nine flagged figures of which
    the re-judge keeps none, and Playwright painted **zero** `.figures-withheld`
    elements on that panel. After the gate was widened the same panel served
    `Showing 0 of the 9 derived figures this brief flagged — spot-check the
    brief itself before quoting figures from it.`

    The fixture reproduces that state rather than the easy one: the seeded
    brief stores two figures neither of which appears in `BRIEF_REPORT`, and
    stores no `figures_withheld` at all. So the total has to come from the
    stored list through the re-judge, and a panel that passed by reading a
    withheld count would fail here.

    `render-blocking` is reachable on this route because `/api/runs/{id}/expert`
    does not filter by page — the fixture's brief carries a NULL `page_url`
    and the page briefs come from the lanes payload's page-scoped rows, which
    list it under its header name, `Render path analysis`. The report was
    stored under the Images brief until brief v15 step AQ made that one
    site-scoped, and a site-scoped brief has no control on this route.
    Checked at
    `app.py:2057` and `expert.tsx:793` rather than assumed; the comment above
    `REVEAL["client"]` records what guessing at this cost last time.
    """
    from playwright.sync_api import sync_playwright

    base, ids = served
    url = f"{base}/#/runs/{ids['run']}/page/{ids['page']}"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            pg = browser.new_page()
            pg.goto(url, timeout=30_000, wait_until="load")
            # The stored brief's own control, once the index that knows it
            # is stored has arrived: before that the same name is the run
            # control, and pressing it asked the server for a crawl of the
            # fixture's loopback host (422) instead of opening the report.
            pg.wait_for_selector("button:has-text('show Content · Content brief for a page')",
                                 timeout=15_000)
            pg.click("button:has-text('show Content · Content brief for a page')")
            pg.wait_for_selector(".expert-report", timeout=15_000)
            pg.wait_for_timeout(500)
            painted = pg.eval_on_selector_all(
                ".figures-withheld", "els => els.map(e => e.innerText)")
            items = pg.eval_on_selector_all(".figures-note li", "els => els.length")
        finally:
            browser.close()

    assert len(painted) == 1, (
        "the brief lost every flagged figure to the re-judge and the panel "
        f"said nothing about it; .figures-withheld matched {painted!r}")
    assert items == 0, (
        f"the fixture's figures were expected to lapse entirely; {items} "
        "list item(s) painted, so this guard is not exercising the empty case")
    assert "0 of the 2" in painted[0], (
        "the sentence does not state the shown count against the total the "
        f"brief flagged: {painted[0]!r}")
    assert "the first" not in painted[0], (
        "the sentence still calls a re-judged subset a prefix of the stored "
        f"list: {painted[0]!r}")


# --------------------------------------------------------------------------
# UX-99 — a scan cell says which scan it starts.
#
# These live in this module rather than a file of their own, and that is a
# deliberate reversal. Round 143 first wrote them as
# `tests/test_a_scan_cell_names_the_scan_it_starts.py`, which under the
# pinned suite's `-n auto --dist loadfile` put them on their own worker with
# their own uvicorn and their own Chromium — a fourth concurrent browser in a
# suite whose two open flakes, KI-22 and KI-51, are both "fails under load,
# passes serially". Three consecutive verifying runs then went red on those
# two nodes, and both passed serially straight afterwards.
#
# That is not proof the new file caused it. The historical rate on an
# unchanged tree is about one red in three, so it may well have been the
# coin. But DISCIPLINE rule 6 says a round with *any* reason to suspect its
# own diff says so rather than re-running until green, and reusing `served`
# from inside the module that already defines it removes the mechanism
# entirely instead of arguing about whether it fired.
#
# The finding: the chooser is a grid, four scopes down the side and three
# depths across the top, and the two axes exist only in layout. The scope
# lives in a sibling `.scan-rowhead`, the depth in a sibling `.scan-colhead`,
# with no `headers`, no `aria-labelledby` and no table role tying either to
# the button between them. So the twelve accessible names were twelve
# durations — `~4m`, `~11m` — and an operator who cannot see the grid could
# tell how long each scan would take and nothing at all about which one it
# was, on the screen where the product asks for money.
#
# `button-name` cannot catch this, and the rendered-axe sweep above never
# did: every one of the twelve has *a* name. A name that is accurate and
# useless is not a violation any generic rule can state, which is why these
# assert the content of the name rather than its existence.
#
# `scripts/prove_fail.py` cannot answer for them either — it swaps in the
# parent commit's *source*, and `dashboard/dist/` is gitignored, so the
# browser would go on reading whichever bundle is already on disk and the
# guard would report NOT PROVEN about a tree it never tested. The failure was
# observed directly instead: run against the unfixed bundle these reported
# `12 of 12 scan cells carry no aria-label`, quoted in the fix commit.

#: Copied from `scanmatrix.tsx`'s `SCOPES` and `DEPTHS`, because the claim is
#: that the rendered name carries these exact words. Twelve is their product
#: and is asserted as their product — a grid that lost a row should fail
#: loudly here, not quietly assert less.
SCAN_SCOPES = ("Page", "Nav", "Site", "Full")
SCAN_DEPTHS = ("Quick", "Standard", "Deep")

#: `getAttribute` rather than a computed accessible name: `aria-label` is what
#: the fix adds, so asking for the attribute makes a failure say which cell is
#: missing it rather than reporting a name assembled from somewhere else.
_SCAN_LABELS_JS = """() => [...document.querySelectorAll("button.scan-cell")]
     .map((b) => b.getAttribute("aria-label"))"""

_SCAN_CELLS_JS = """() => document.querySelectorAll("button.scan-cell").length"""


@pytest.fixture(scope="module")
def scan_cell_labels(served):
    """The twelve `aria-label`s, read once from the running product.

    Module-scoped because the page load is the whole cost; the four tests
    below are four questions about one reading, not four sessions. `served`
    is this module's own fixture, so no second server and no second browser
    are stood up for them.
    """
    from playwright.sync_api import TimeoutError as PWTimeout, sync_playwright

    base, ids = served
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        try:
            pg.goto(f"{base}/#/sites/{ids['site']}?tab=history",
                    wait_until="load", timeout=30_000)
            try:
                pg.wait_for_function(_SCAN_CELLS_JS + " > 0", timeout=30_000)
            except PWTimeout:
                raise AssertionError(
                    "no `.scan-cell` ever rendered on the history tab, so "
                    "nothing below asserted anything about the grid; buttons "
                    "present: "
                    + repr(pg.locator("button").all_inner_texts()[:20]))
            yield pg.evaluate(_SCAN_LABELS_JS)
        finally:
            browser.close()


def test_the_scan_grid_still_offers_one_cell_per_scope_and_depth(scan_cell_labels):
    """The population, before anything is asserted about it.

    Without this a grid rendering two cells would pass everything below by
    having less to be wrong about — DISCIPLINE rule 5's check that cannot
    disagree with itself.
    """
    assert len(scan_cell_labels) == len(SCAN_SCOPES) * len(SCAN_DEPTHS), (
        f"expected {len(SCAN_SCOPES) * len(SCAN_DEPTHS)} scan cells "
        f"({len(SCAN_SCOPES)} scopes x {len(SCAN_DEPTHS)} depths), got "
        f"{len(scan_cell_labels)}: " + repr(scan_cell_labels))


def test_every_scan_cell_names_its_scope_and_its_depth(scan_cell_labels):
    """UX-99 itself: each of the twelve says which scan pressing it starts."""
    missing = [lab for lab in scan_cell_labels if not lab]
    assert not missing, (
        f"{len(missing)} of {len(scan_cell_labels)} scan cells carry no "
        "`aria-label`, so their accessible name is still the visible duration "
        "alone: " + repr(scan_cell_labels))

    unnamed = [
        lab for lab in scan_cell_labels
        if not (any(s.lower() in lab.lower() for s in SCAN_SCOPES)
                and any(d.lower() in lab.lower() for d in SCAN_DEPTHS))
    ]
    assert not unnamed, (
        "these labels name a scope or a depth but not both, which leaves the "
        "operator on the same axis-guessing problem UX-99 describes: "
        + repr(unnamed))


def test_no_two_scan_cells_announce_the_same_thing(scan_cell_labels):
    """Twelve controls, twelve names.

    The defect's shape was collapse: twelve buttons announcing a handful of
    durations between them, so a duration heard twice was two different
    purchases. A label naming only the depth would satisfy the test above and
    still collapse four ways; this is what refuses that.

    `key=repr` because an unfixed grid reads back twelve `None`s and this has
    to be able to *say* so rather than raise `TypeError` comparing them.
    """
    assert len(set(scan_cell_labels)) == len(scan_cell_labels), (
        "two or more scan cells announce identically, so the accessible name "
        "still does not distinguish the purchases: "
        + repr(sorted(scan_cell_labels, key=repr)))


def test_the_scan_label_still_says_which_cells_spend_model_tokens(scan_cell_labels):
    """The regression the fix could have introduced, asserted against.

    `SpendMark` marks the paid cells with an `sr-only` phrase *inside* the
    button, and an `aria-label` overrides the button's whole subtree. So a
    label naming only the scope and the depth would have closed UX-99 by
    deleting the spend mark from the one audience that cannot see the `$`
    beside it — trading an accessibility finding for a disclosure one, on the
    same control, in the same commit. F-10 clause 1 requires the mark on
    every surface that reaches a model; this is one.

    Eight and four, both derived from the two axes rather than typed: the free
    column is `Quick` alone, so the paid count is every scope times the other
    two depths. A grid that grew a fourth depth moves both numbers without
    anyone editing them.
    """
    spends = [lab for lab in scan_cell_labels
              if "spends model tokens" in (lab or "").lower()]
    free = [lab for lab in scan_cell_labels if "free" in (lab or "").lower()]

    assert len(spends) == len(SCAN_SCOPES) * (len(SCAN_DEPTHS) - 1), (
        f"expected {len(SCAN_SCOPES) * (len(SCAN_DEPTHS) - 1)} cells to "
        f"announce that they spend model tokens, got {len(spends)}; a label "
        "that overrides `SpendMark` without restating it removes the mark "
        "from the only audience that cannot see the `$`: "
        + repr(scan_cell_labels))
    assert len(free) == len(SCAN_SCOPES), (
        f"expected the {len(SCAN_SCOPES)} `Quick` cells to announce "
        f"themselves as free, got {len(free)}: " + repr(scan_cell_labels))
    assert not [lab for lab in spends if lab in free], (
        "a cell announces itself as both free and spending tokens: "
        + repr([lab for lab in spends if lab in free]))
