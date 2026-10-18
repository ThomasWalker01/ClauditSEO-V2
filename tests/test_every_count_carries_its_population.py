"""Item 155: every count carries its population, and renders by it.

**The defect was the denominator, not a missing label.** The check table's
`35 of 68` on Twenty22 T3 was already a ratio — 23 of those 68 were never
fetched, and a page nobody looked at cannot be evidence that the fault is
absent. Labelling the 68 repairs nothing, because the bad half is the bottom
half. So a count travels as `{value, population, basis, of}` and the
population decides how it draws: one matching the page's scope renders plain,
one that differs renders `N of M` with its basis named.

**Why four of the six drive a doctored payload.** DISCIPLINE rule 5 first: on
this fixture the crawl, the record and the site are all sixteen pages and the
site size reads `unknown` (there is no sitemap to declare one), so the fixture
CANNOT tell a crawl denominator from a record denominator, and it cannot show
a label correctly disappearing either. A clause asserting `35 of 45` here
would pass against the old code, which is the failure mode the item's own test
list names by hand. The three regimes are therefore served through Playwright's
route interception — the idiom `test_a_cause_opens_to_its_templates` already
uses on this payload — with the page's own scope, the crawl's size and its
path set set to each regime and everything else the server's:

  full      crawl 16 of a 16-page site. The T3 case: nothing to disambiguate,
            so every label is expected to be ABSENT.
  pulse     crawl 3 of a 53-page site, 68 in the record. The T1 case: every
            count is expected to state its population.
  partial   crawl 12 of 16, record 16. The one regime where the two candidate
            denominators differ by a number the screen can be read for.

`test_a_count_rendered_without_a_population_fails` and the site-scoped clause
run against the server's own payload, because neither needs a regime — the
first asks whether the assembly is complete and the second reads a genuinely
page-less finding this fixture plants (`llms-txt-missing` on AI surface).

**Measured against the old code, DISCIPLINE rule 1.** The six rendered clauses
were run with `dashboard/src` stashed and the previous bundle rebuilt, the
server's new payload left in place: **all six failed**. Which way each failed
is the useful half, because two of them assert an absence and an absence is
trivially true on a screen that draws nothing:

  * the guard, the prevalence clause, the pulse and the strip foot failed on
    the thing itself — no `[data-population]` anywhere, `td.num` holding bare
    numbers, no `.part-coverage`, and a foot reading `16 of 16 pages · this
    audit's crawl` with no denominator named;
  * `test_a_matching_population_renders_without_a_ratio` asserts NO ratio is
    drawn, which the old bundle satisfies by drawing no counts at all. It
    failed on its second clause, which is in the file for exactly that reason:
    the absence only means something if the counts are there to have lost
    their labels;
  * the site-scoped clause failed the same way — no `.cause-prev` cell to read.

The eight contract clauses above them are ordinary tests for a payload that
did not exist, not guards, and none was seen to fail in the sense rule 1
means.
"""

from __future__ import annotations

import json

import pytest

from clauditseo.persistence import runs
from tests.test_a11y_rendered import DIST, served  # noqa: F401  (reused fixture)
from tests.parts import open_part

#: The part these clauses drive. Three-block, so it renders the checks table
#: (the prevalence surface) AND the length strips (146z's foot), which is what
#: lets one screen carry both the header's denominator and the foot's.
PART = "title-desc"

#: A part that renders the OLD layout's cause table and holds a finding naming
#: no page. Both halves matter: the cause table is the other prevalence
#: surface, and a page-less row is what a site-scoped count IS.
SITE_SCOPED_PART = "ai-surface"


@pytest.fixture
def browser():
    """A browser rather than a page: each clause serves the anatomy payload
    under its own regime, and a route has to be attached before the first
    navigation."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch()
        try:
            yield b
        finally:
            b.close()


def live(fn):
    from clauditseo import axe

    fn = pytest.mark.skipif(
        not (DIST / "index.html").is_file(),
        reason="dashboard not built (npm run build in dashboard/)")(fn)
    return pytest.mark.skipif(
        not axe.available(),
        reason="needs clauditseo[render] and `playwright install chromium`")(fn)


def _payload(base: str, site: str) -> dict:
    import httpx

    return httpx.get(f"{base}/api/sites/{site}/anatomy", timeout=60).json()


# --- the contract, on the wire ----------------------------------------------

def test_a_count_refuses_a_population_that_is_not_legal():
    """Three populations are legal and a fourth is a component having invented
    a denominator of its own, which is what one assembly point exists to stop.
    Refused where the count is minted rather than caught at the renderer,
    because by then the wrong number is already on the payload."""
    assert runs.POPULATIONS == ("crawl", "site", "record")
    for legal in runs.POPULATIONS:
        assert runs.count(3, legal)["basis"]
    with pytest.raises(ValueError):
        runs.count(3, "pages")
    with pytest.raises(ValueError):
        runs.count(3, "")


def test_a_basis_override_needs_a_denominator_to_describe() -> None:
    """`basis` names the denominator in words, so without an `of` it describes
    nothing and would render as a bare word beside a plain number.

    The override exists for one narrow case: an `of` that is a **subset** of
    the population rather than its whole extent, where the population's own
    word describes the wrong set. It is not a fourth population -- the
    population still says which of the three legal sets the value lives in,
    which is what `matchesScope` reads and what forbids a `site` ratio.
    """
    assert runs.count(3, "crawl", of=9)["basis"] == "crawled"
    assert runs.count(3, "crawl", of=9, basis="traced")["basis"] == "traced"
    assert runs.count(3, "crawl", of=9, basis="traced")["population"] == "crawl", (
        "the override moves the WORD, never the population")
    with pytest.raises(ValueError):
        runs.count(3, "crawl", basis="traced")


def test_a_sampled_templates_count_says_traced_and_not_crawled(tmp_path) -> None:
    """The defect this override was built for, in the shape that produced it.

    A Speed template's page count is the pages of that template THIS RUN
    TRACED, over the pages it traced. Those are crawled pages, so the
    population is and stays `crawl` -- but the denominator is the traced
    subset, and `POPULATION_BASIS["crawl"]` is "crawled", so the strip rendered
    **`1 of 12 pages crawled` about a run that crawled 48**.

    **Invisible until the trace began sampling.** Before 935d8c0 every readable
    page was traced, so traced and crawled were the same set and the sentence
    was true by accident. Birch could not show it either -- one template, every
    page traced. It took twenty22's twelve templates on run `95ac5495`, which
    is why this fixture is built that way: **more crawled pages than traced
    ones, and more than one template.** A fixture where every page is traced
    cannot express the failure (DISCIPLINE rule 5).
    """
    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate
    from clauditseo.persistence import repo

    conn = connect(tmp_path / "clauditseo.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn, "item 155")
    site_id = repo.create_site(conn, repo.create_client(conn, op, "Co"), "x.test")
    run_id = runs.create_run(conn, site_id, ["PRF"], "T2")

    # Two templates, four crawled pages, two traced -- one per template. The
    # numbers are all different on purpose: 2 traced of 4 crawled means a count
    # reading "2 of 2" cannot be mistaken for a crawl ratio, and a basis word
    # of "crawled" is provably false rather than merely unclear.
    pages = []
    for path in ("/a/one", "/a/two", "/b/one", "/b/two"):
        page = {"url": f"https://x.test{path}", "status": 200,
                "content_type": "text/html"}
        if path.endswith("/one"):
            # `device_profile` is what `speed_now_payload` requires to call a
            # page traced -- a trace with no stated profile is a number with
            # no conditions, which the part refuses to draw a gauge from.
            page["perf"] = {"traced": True, "ttfb_ms": 100.0,
                            "device_profile": "mid-tier mobile, 4G",
                            "lcp": {"ms": 1200.0}, "resources": []}
        pages.append(page)
    conn.execute("UPDATE audit_runs SET status='complete', crawl_evidence=?"
                 " WHERE id=?",
                 (json.dumps({"start_url": "https://x.test/",
                              "pages": pages}), run_id))
    conn.commit()

    now = runs.speed_now_payload(conn, run_id)
    assert now and now.get("templates"), "no templates to judge"
    assert len(now["templates"]) == 2, "the fixture must hold more than one"
    for t in now["templates"]:
        c = t["pages"]
        assert c["population"] == "crawl", "these are crawled pages"
        assert c["basis"] == "traced", (
            f"{t['pattern']}: the denominator is the traced subset, so the "
            f"basis may not be the crawl's own word -- got {c['basis']!r}")
        assert c["of"] == 2, "the denominator is the traced set, which is 2"
    # And the crawl's own extent is a different, larger number, which is what
    # made the old wording false rather than just loose.
    assert now["traced"]["value"] == 2
    assert now["traced"]["of"] == 4, (
        "traced-of-readable is the crawl ratio, and it is not the same "
        "denominator the per-template count uses")
    conn.close()


def test_the_site_population_is_not_a_page_set(tmp_path):
    """A site-scoped count has a population like any other; it simply is not a
    page set. So the `site` population carries no size, and there is nothing
    for a renderer to divide by even if it tried — which is stronger than
    asking every renderer to remember not to."""
    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate

    conn = connect(tmp_path / "pop.db")
    migrate(conn)
    pops = runs.populations_payload(conn, None, record_pages=68)
    assert pops["site"]["size"] is None
    assert runs.count(1, "site")["of"] is None


def test_a_findings_count_carries_no_page_denominator():
    """`12 of 68` where the 12 are findings and the 68 pages is two different
    things divided. The population still travels — the sidebar badge says the
    record raised these, not the crawl — and `of` is what stays absent."""
    c = runs.count(12, "record")
    assert c["of"] is None and c["population"] == "record"
    assert c["basis"] == "in the record"


def test_the_page_scope_reads_bj_site_size_and_not_the_record(served):  # noqa: F811
    """The scope is what decides plain against ratio, and its extent is 150
    BJ's site size. Reading the record instead would make every count plain on
    a full record and a third of a crawl, which is the defect wearing a
    different number."""
    base, ids = served
    v = _payload(base, ids["site"])
    assert v["populations"]["scope"]["pages"] == v["headline"]["site_size"]["size"]
    # On this fixture that is None - there is no sitemap, so the size is
    # unknown - and the record is 16. The two must not be confused even here,
    # which is the case that would hide the substitution.
    assert v["populations"]["record"]["size"] == len(v["pages"])
    assert v["populations"]["scope"]["pages"] != v["populations"]["record"]["size"]


def test_the_crawl_population_carries_the_set_it_fetched(served):  # noqa: F811
    """Prevalence is affected OF ASSESSED, so the numerator has to be
    intersected with what the run fetched — a size alone cannot do that, and a
    record accumulated across runs would otherwise report more affected pages
    than the run looked at and read above 100%."""
    base, ids = served
    v = _payload(base, ids["site"])
    crawl = v["populations"]["crawl"]
    assert crawl["size"] == len(crawl["paths"]) > 0
    assert all(p.startswith("/") for p in crawl["paths"]), crawl["paths"][:5]
    # Normalised the one way, or the client's intersection silently drops a
    # page: `/x` and `/x/` are one page.
    assert not [p for p in crawl["paths"] if p != "/" and p.endswith("/")]


def test_the_part_count_is_over_the_record_and_says_so(served):  # noqa: F811
    """`Category.pages` has always been the pages carrying an open finding
    across every run, not the pages this run fetched — open state is
    site-scoped. The screen had no way to know that. Now the count says it.

    And it carries no `of` (audit F7, 2026-09-18). It did, and this clause
    asserted it: `of=len(record_page_list)` made the record a denominator, so
    the Analyses headline read "affect the same 1 of 1 pages in the record" —
    100% — about a 53-page site. `POPULATION_BASIS` says of this population
    that it is "never a prevalence denominator", and a non-null `of` IS the
    ratio form by `Counted`'s own contract. The population is still named; what
    is gone is the division.
    """
    base, ids = served
    v = _payload(base, ids["site"])
    for cat in v["categories"]:
        c = cat["pages"]
        assert c["population"] == "record", cat["key"]
        assert c["of"] is None, (cat["key"], c)
        # Still a real subset of the record, which is what the dropped `of`
        # used to assert in passing.
        assert c["value"] <= len(v["pages"]), (cat["key"], c)
        # And the findings counts come with theirs. 155 put them on a `counts`
        # sibling beside three integers; item 156 converted the three in place
        # and removed the sibling, so this reads the field itself —
        # `test_category_carries_no_bare_integer_count` below is what holds
        # that shape.
        assert cat["total"]["of"] is None, cat["key"]
        assert cat["total"]["population"] == "record", cat["key"]


# --- the three regimes ------------------------------------------------------

def _regime(data: dict, which: str) -> dict:
    """The payload as it would arrive under one coverage regime.

    Only the populations and 150 BJ's headline are touched. The categories,
    the findings and the record's page list stay the server's, so what is
    under test is the render rule and not a hand-built screen.
    """
    paths = list(data["populations"]["crawl"]["paths"])
    if which == "full":
        crawl, site, record = len(paths), len(paths), len(paths)
    elif which == "pulse":
        paths, crawl, site, record = paths[:3], 3, 53, 68
    elif which == "partial":
        paths, crawl, site, record = paths[:12], 12, len(paths), len(paths)
    else:                                            # pragma: no cover
        raise AssertionError(which)
    data["populations"] = {
        "crawl": {"size": crawl, "basis": "crawled", "paths": paths},
        "site": {"size": None, "basis": "across the site", "paths": []},
        "record": {"size": record, "basis": "in the record", "paths": []},
        "scope": {"pages": site, "basis": "on the site"},
    }
    pct = round(crawl / site * 100) if site else None
    data["headline"] = {
        "run_id": (data.get("headline") or {}).get("run_id") or "r",
        "site_size": {"size": site, "declared": site, "discovered": crawl,
                      "gap": 0, "unknown": False, "unknown_reason": None},
        "coverage": {"crawled": crawl, "size": site, "pct": pct,
                     "unknown": False, "unknown_reason": None},
        "assessed": {"assessed": 0, "total": 1, "pct": 0},
        "audited": crawl,
    }
    return data


def _open(browser, base: str, site_id: str, part: str, regime: str | None,
          last_resort: bool = False):
    """The part page, open, with the anatomy payload under `regime`. With
    `last_resort` the part draws on the across-the-site layout, where the
    cause table lives (`tests/last_resort.py`)."""
    pg = browser.new_page(viewport={"width": 1400, "height": 1000})
    if last_resort:
        from tests.last_resort import on_the_layout_of_last_resort
        on_the_layout_of_last_resort(pg)

    if regime:
        def anatomy(route):
            body = _regime(route.fetch().json(), regime)
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps(body))

        pg.route("**/api/sites/*/anatomy*", anatomy)

    pg.goto(f"{base}/#/sites/{site_id}?tab=findings", wait_until="load")
    pg.wait_for_selector(".anat-layout", timeout=20_000)
    open_part(pg, _label(base, site_id, part))
    pg.wait_for_selector(".part-coverage, .part-page, table.causes", timeout=15_000)
    pg.wait_for_timeout(350)
    return pg


def _label(base: str, site_id: str, key: str) -> str:
    view = _payload(base, site_id)
    return next(c["label"] for c in view["categories"] if c["key"] == key)


def _counts(pg) -> list[dict]:
    """Every count the screen drew, with the population it carries."""
    return pg.eval_on_selector_all(
        ".anat-pane [data-population]",
        "els => els.map(e => ({pop: e.getAttribute('data-population'),"
        " of: e.getAttribute('data-of'), value: e.getAttribute('data-value'),"
        " text: e.textContent.trim(), cls: e.className}))")


# --- the one that matters ---------------------------------------------------

@live
def test_a_count_rendered_without_a_population_fails(served, browser):  # noqa: F811
    """Not "the label is present" — which passes forever and catches nothing,
    and which is how 139a's ordering defect repeated across four blocks
    written at different times.

    This walks the numeric cells the part page actually drew and fails on one
    that carries no population. A count added later as a bare `{n}` in a
    `td.num` fails here without anybody having to remember the rule, which is
    the only property that makes the guard worth having.
    """
    base, ids = served
    pg = _open(browser, base, ids["site"], PART, None)

    cells = pg.eval_on_selector_all(
        ".anat-pane td.num",
        "els => els.map(e => ({text: e.textContent.trim(),"
        " pop: e.querySelector('[data-population]')"
        "        ? e.querySelector('[data-population]').getAttribute('data-population')"
        "        : (e.getAttribute('data-population') || '')}))")
    # DISCIPLINE rule 5, before the loop is believed: a screen with no numeric
    # cell passes a `for` loop over nothing.
    assert len(cells) >= 3, f"the part page drew no counts to check: {cells}"

    bare = [c for c in cells
            if c["text"] not in ("", "—", "-") and not c["pop"]]
    assert not bare, (
        "numeric cells rendered without a population — each of these is a "
        f"number whose denominator the reader has to guess: {bare}")

    # And every population drawn is one of the three that are legal. A fourth
    # would mean a component invented a denominator of its own, which is the
    # thing the one assembly point exists to prevent.
    drawn = {c["pop"] for c in _counts(pg)}
    assert drawn and drawn <= {"crawl", "site", "record"}, (
        f"a count carries a population that is not legal: {drawn}")


# --- the rule, in each regime ----------------------------------------------

@live
def test_prevalence_never_uses_the_record_as_its_denominator(served, browser):  # noqa: F811
    """`35 of 45 crawled`, never `35 of 68`.

    The `partial` regime exists for this clause alone: it is the only one where
    the crawl and the record are different numbers, so the denominator on
    screen can be read for which of the two it is. The record is still a legal
    population elsewhere on the page — the strip foot uses it — and this clause
    is narrow on purpose: not "the record never appears", but "no prevalence is
    taken over it".
    """
    base, ids = served
    pg = _open(browser, base, ids["site"], PART, "partial")

    prev = pg.eval_on_selector_all(
        ".check-prev [data-population], .cause-prev [data-population]",
        "els => els.map(e => ({pop: e.getAttribute('data-population'),"
        " of: e.getAttribute('data-of'), text: e.textContent.trim()}))")
    assert prev, "no prevalence cell rendered, so this clause reads nothing"

    for cell in prev:
        assert cell["pop"] != "record", (
            "a fault rate is being stated over the record — over pages this "
            f"run never fetched: {cell}")
        if cell["pop"] == "crawl":
            assert cell["of"] == "12", (
                f"prevalence divided by {cell['of']} where the crawl was 12 "
                f"and the record 16: {cell}")
            assert "crawled" in cell["text"], cell


@live
def test_a_fault_the_run_did_not_look_at_is_counted_beside_the_rate(served, browser):  # noqa: F811
    """The correction the ruling's own arithmetic needs, and the reason it is
    not a degradation.

    `35 of 68` becomes `35 of 45 crawled` in the ruling's example, which
    assumes the 35 affected pages are inside the 45. They need not be:
    `finding_states` is site-scoped and accumulates across runs, so a record
    can hold a fault on pages the latest run did not fetch. Intersecting the
    numerator and stopping there would drop them silently — one wrong
    impression traded for another. So the cell states both halves, and they sum
    to the number it used to show alone.
    """
    _CELLS = (
        "els => els.map(e => ({check: e.closest('tr').querySelector('code')"
        "                        .textContent.trim(),"
        " inside: Number(e.querySelector('[data-population]')"
        "                 ?.getAttribute('data-value') ?? -1),"
        " outside: Number(e.querySelector('.prev-outside')"
        "                  ?.getAttribute('data-outside') ?? 0),"
        " text: e.textContent.trim()}))")

    base, ids = served
    pg = _open(browser, base, ids["site"], PART, "partial")
    cells = pg.eval_on_selector_all(".check-prev", _CELLS)
    assert cells, "no prevalence cell rendered"
    # DISCIPLINE rule 5: the `partial` regime drops four of sixteen crawled
    # paths, so at least one check must have an affected page outside the
    # assessed set or this clause reads nothing.
    outside = [c for c in cells if c["outside"] > 0]
    assert outside, (
        "no check on this regime has an affected page outside the crawl, so "
        f"the second half of the cell is never drawn: {cells}")
    for c in outside:
        assert "more in the record" in c["text"], c
        assert c["inside"] + c["outside"] > c["inside"], c

    # And the two halves reconcile, read off the screen itself rather than
    # asserted against a number written here: widening the assessed set to the
    # whole crawl must recover exactly the pages the partial regime put
    # outside it. `inside + outside` under `partial` equals `inside` under
    # `full`, per check. That is the claim "nothing was lost, only divided
    # correctly", stated as an equality rather than as a comment.
    wide = _open(browser, base, ids["site"], PART, "full")
    whole = {c["check"]: c for c in wide.eval_on_selector_all(".check-prev", _CELLS)}
    assert whole, "the full regime drew no prevalence cell to reconcile against"
    for c in cells:
        full = whole.get(c["check"])
        if full is None:
            continue
        assert full["inside"] == c["inside"] + c["outside"], (
            f"{c['check']} does not reconcile: {c} against {full}")
        assert full["outside"] == 0, (
            f"{c['check']} still holds pages outside a crawl that covered "
            f"everything: {full}")


@live
def test_a_matching_population_renders_without_a_ratio(served, browser):  # noqa: F811
    """The T3 case. On a full-coverage run the labels correctly disappear,
    because there is nothing to disambiguate — which is why this rule beats
    "every count states its scope" on that option's own cost.
    """
    base, ids = served
    pg = _open(browser, base, ids["site"], PART, "full")

    ratios = [c for c in _counts(pg) if " of " in c["text"]]
    assert not ratios, (
        "counts are still stating a ratio on a run that covered the whole "
        f"site, where the ratio can only be N of N: {ratios}")
    # And they are counts, not absences: the populations are still on them, so
    # the day coverage drops the labels come back without a code change.
    assert _counts(pg), "nothing rendered, so the absence above proves nothing"


@live
def test_a_t1_pulse_states_its_population_on_every_count(served, browser):  # noqa: F811
    """The other end of the same rule: every count reads `3 of 3 crawled`
    under a header reading `3 of 53 on the site`, which is honest and readable.
    """
    base, ids = served
    pg = _open(browser, base, ids["site"], PART, "pulse")

    header = pg.text_content(".part-coverage")
    # Item 180 (ruling 20260918-0404): the head names its noun.
    assert "3 pages audited of 53 known" in header, (
        f"the part header does not state coverage from 150 BJ: {header!r}")

    page_counts = [c for c in _counts(pg)
                   if c["of"] and c["pop"] in ("crawl", "record")]
    assert page_counts, "no page count rendered on the pulse"
    for c in page_counts:
        assert " of " in c["text"], (
            "a page count is rendered plain on a run that covered 3 of 53 "
            f"pages, so it reads as the whole site: {c}")


@live
def test_a_site_scoped_count_is_not_rendered_as_a_page_ratio(served, browser):  # noqa: F811
    """A site-scoped count has a population like any other; it simply is not a
    page set. So it sits inline with the part's other counts and is never
    dressed as `0 of 45`, which would read as a fault that 45 pages were
    checked for.

    Driven by a finding this fixture genuinely plants rather than a doctored
    one: `llms-txt-missing` on AI surface names no page, which is what makes a
    count site-scoped.
    """
    base, ids = served
    view = _payload(base, ids["site"])
    cat = next(c for c in view["categories"] if c["key"] == SITE_SCOPED_PART)
    pageless = [f for f in cat["findings"] if f["pages"] == 0]
    assert pageless, (
        f"{SITE_SCOPED_PART} holds no finding that names no page, so this "
        "clause has nothing to drive")

    pg = _open(browser, base, ids["site"],
               SITE_SCOPED_PART, "partial", last_resort=True)
    cells = pg.eval_on_selector_all(
        "table.causes .cause-prev [data-population]",
        "els => els.map(e => ({pop: e.getAttribute('data-population'),"
        " of: e.getAttribute('data-of'), text: e.textContent.trim()}))")
    assert cells, "the cause table drew no prevalence cell"
    site = [c for c in cells if c["pop"] == "site"]
    assert site, (
        "the page-less finding's count is not site-scoped, so it is being "
        f"counted over a page set: {cells}")
    for c in site:
        assert c["of"] in (None, ""), (
            f"a site-scoped count carries a page denominator: {c}")
        assert " of " not in c["text"], (
            f"a site-scoped count is dressed as a page ratio: {c}")


@live
def test_the_strip_foot_and_the_part_header_name_different_denominators(served, browser):  # noqa: F811
    """146z's foot shipped `45 of 68 pages - this audit's crawl`, with M as the
    record count. That stays legal — crawl of record is a what-we-know
    statement, not a prevalence — but it now sits on a page whose header says
    `45 of 53 on the site`. Two ratios over the same numerator must not read as
    a contradiction, so the foot names its denominator: `in the record`.
    """
    base, ids = served
    pg = _open(browser, base, ids["site"], PART, "pulse")

    foot = pg.text_content(".strip-foot")
    header = pg.text_content(".part-coverage")
    assert foot, "the length strips drew no foot"
    assert "in the record" in foot, (
        f"the strip foot does not name its denominator: {foot!r}")
    assert "known" in header and "in the record" not in header, (
        f"the header and the foot do not name different populations: "
        f"{header!r} / {foot!r}")
    # The two Ms are different numbers here, which is the whole reason the
    # foot had to start naming its own.
    assert "of 53" in header and "of 53" not in foot, (
        f"both ratios read the same denominator: {header!r} / {foot!r}")


# --- item 156: the type, not the convention ---------------------------------

def test_category_carries_no_bare_integer_count(served):  # noqa: F811
    """Item 156, and the reason it is a contract clause rather than a rendered
    one.

    155's protection was real and incomplete, and its own report said so:
    `test_a_count_rendered_without_a_population_fails` catches every renderer
    that EXISTS, because `Counted` is the one component. But `open`,
    `regressed` and `total` were still integers on `Category`, so a component
    written next month could read `part.total` and render it bare and no
    rendered clause would notice — the rule lived in a convention about which
    field to read rather than in the type of the field. That is the exact shape
    of 139a: a rule that was true, written down, and invisible to the next
    block written against it.

    So this walks the payload and fails on a count-shaped field that is a bare
    integer. A future integer count added to `Category` fails here BEFORE any
    component reads it, which a rendered clause cannot do.

    **The type change was the audit.** It broke nine consumers, and two of
    them were renders rather than arithmetic: `{current.total}` in the
    truncation note on the part pane, and the Triage table's `open` column.
    Both had been drawing a count with no population since long before 155,
    and neither was reachable by a rendered guard over the part page.
    """
    base, ids = served
    view = _payload(base, ids["site"])
    assert view["categories"], "no categories to walk"

    #: Fields on `Category` that are counts and must carry their population.
    #: Named rather than sniffed: a field that merely holds a number is not a
    #: count — `brief_dropped` is a tally inside one brief's answer and
    #: `notes` rides in a badge's title as a sentence, not as a figure.
    COUNTS = ("open", "regressed", "total", "pages")
    for cat in view["categories"]:
        for field in COUNTS:
            got = cat[field]
            assert isinstance(got, dict), (
                f"{cat['key']}.{field} is a bare {type(got).__name__} — a "
                "count whose denominator the reader has to guess, and which "
                "no rendered guard can catch before it is drawn")
            assert set(got) == {"value", "population", "basis", "of"}, (
                cat["key"], field, got)
            assert got["population"] in runs.POPULATIONS, (cat["key"], field, got)
            assert isinstance(got["value"], int), (cat["key"], field, got)
        # The findings counts are not subsets of a page set, so none of them
        # carries a page denominator. `12 of 68` would divide two things.
        for field in ("open", "regressed", "total"):
            assert cat[field]["of"] is None, (cat["key"], field, cat[field])
        # And they still agree with each other and with the payload's own
        # total, which is what the nine broken consumers were reading.
        assert cat["open"]["value"] + cat["regressed"]["value"] <= cat["total"]["value"], cat["key"]
    assert view["total"] == sum(c["total"]["value"] for c in view["categories"])

    # The `counts` sibling 155 added is GONE, not left beside the three as a
    # second way to read the same number — which is the drift this item
    # exists to close rather than to double.
    assert all("counts" not in c for c in view["categories"]), (
        "the `counts` sibling survives beside the three it was standing in "
        "for, so there are two ways to read one number again")
