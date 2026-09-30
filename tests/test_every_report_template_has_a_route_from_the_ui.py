"""WF-21: the comparison document exists and has no door.

Carried at High by every report from 026 to 094 - sixty-eight of them - and
routed `engineering` in the DISPOSITIONS cohort, which is what selects it here.
The claim has never moved: `TEMPLATES = ("run", "comparison", "monthly-trend")`
(`clauditseo/reporting/generate.py:24`), `POST /api/reports` accepts all three
and `clauditseo/cli.py` asks for all three, but the dashboard's only route to
that endpoint that *creates* a document posts `run_ids: [runId]` - one id,
structurally incapable of the two a comparison needs - and its template
`<select>` offers `Run report` and `Monthly trend report` only.

**The affordance invariant's shape, not a missing feature.** `CompareView`
names the object in its own heading - "Run comparison" - renders four buckets
of findings diffed between two runs, and offers no route to the artefact of
it. The one place in the product holding both run ids is the one place that
could not ask for the document about them.

**Why the registry clause is derived and not listed.** DISCIPLINE rule 3: a
hard-coded list of three is how template four ships with no door. The set of
templates comes from `TEMPLATES` itself, so this file cannot be the thing that
knows the answer. Its empty-population floor is asserted separately and named
in its own message, because CQ-207 records what happens when a clause goes red
through its floor and the round reads that as the clause working.

**Deriving the population was never the weak half - CQ-210 was the matcher.**
The registry clause this file shipped with took its templates from `TEMPLATES`
and then decided whether each had a door by asking whether the name appeared
in any `<option value>` or posted `template:` literal anywhere under
`dashboard/src`. Neither regex is bound to a `<select>` that feeds `template`,
so a decorative option in an unrelated select on an unrelated screen read as a
route. Measured when the finding was taken: nine names came back and only
three were templates. Report 095 ranked it High as demonstrated failure class
3 - a verification gate defeated by weak matching - and named it the same
defect as CQ-207 one round later, which is what makes it a class.

**What decides it now: a control pressed in a browser.**
`_templates_a_control_can_post` walks `ROUTES` - `test_a11y_rendered.py`'s
derived route list, which its own clauses require to cover every hash route
`App.tsx` dispatches - presses every button whose text leads with the verb,
once per template option the screen offers, and records the `template` field
of the `/api/reports` body that leaves the browser. Measured after the change:
`{comparison: [compare], monthly-trend: [generate], run: [generate]}` - three
names, all templates, each attributed to the screen that posted it. The
regexes are kept as a browserless floor and are required to stay a superset of
what the walk finds, which is all a source scan can honestly be.

**Why the driven clauses and not source matching alone.** DISCIPLINE rule 4 -
a template name present in a source file is not evidence a control paints, and
`<option value="comparison">` on the single-run screen would satisfy a source
check while posting one run id and answering 422. The live clauses drive the
screen and then read either the `reports` row the server wrote or the request
the browser sent, so what is asserted is an act rather than a string.

**`reports.tsx` is deliberately not the answer.** Its regenerate control can
already reproduce a comparison, because it replays a stored deliverable's own
`run_ids` - but only for a comparison that exists. It is a door out of a room
nothing can enter, which is why WF-21 survived the round that built it.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import pytest

from clauditseo import axe
from clauditseo.reporting.generate import TEMPLATES
from tests.test_a11y_rendered import DIST, ROUTES, served  # noqa: F401  (reused fixture)

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


#: Every template name that appears anywhere under `dashboard/src` in one of
#: the two shapes a literal template value is written in: an `<option>` value,
#: and a `template:` key in a posted object.
#:
#: **This is a floor and not the evidence - CQ-210.** The comment that stood
#: here called the audience values landing in the set "harmless, the set is
#: only ever asked whether it *contains* a template name". That was the
#: defect: neither regex is bound to a `<select>` that feeds `template`, so a
#: decorative `<option value="X">` in an unrelated select on an unrelated
#: screen reads as a route to template X. Measured when CQ-210 was taken:
#: nine names came back and six of them - `all`, `client`, `empty`,
#: `internal`, `missing`, `present` - are not templates and never were.
#: `test_the_source_matcher_admits_a_name_no_control_can_ask_for` below pins
#: that, so the weakness is asserted rather than described.
#:
#: What it is still good for: it is browserless, so it runs in the CI job that
#: has no Chromium, and a template named in no source file at all cannot have
#: a control. It is required to be a *superset* of what the driven pass finds
#: - if it ever stops being one, the regexes have gone blind to a shape the
#: dashboard now writes, and the driven clause says so.
OPTION = re.compile(r'<option\s+value="([\w-]+)"')
POSTED = re.compile(r'template:\s*"([\w-]+)"')

#: A button whose own text *leads* with the verb. Every control in the product
#: that posts to `/api/reports` does: `Generate`, `Generate comparison
#: report`, `regenerate`. Located by what the control says it does rather than
#: by class or position, for the reason the clause below it already gives.
#:
#: Anchored rather than a bare substring, and the reason is measured: `generat`
#: unanchored also matched the Tools screen's `Content brief generator` card,
#: which posts nowhere - one screen, one wasted press-and-wait per walk. A
#: control that spends is labelled with its verb first.
GENERATOR = re.compile(r"^(re)?generat", re.I)

#: An audience value, never a template, and present in the source set because
#: `<option value="client">` is painted by two screens. It is the decoy the
#: lens clause uses: the source matcher admits it, and no control can ask for
#: it, so the driven pass must not.
DECOY = "client"


def offered() -> dict[str, set[str]]:
    """Template names to the dashboard modules that can ask for them."""
    out: dict[str, set[str]] = {}
    for path in sorted(SRC.glob("*.tsx")):
        text = path.read_text(encoding="utf-8")
        for name in set(OPTION.findall(text)) | set(POSTED.findall(text)):
            out.setdefault(name, set()).add(path.name)
    return out


def test_the_template_registry_is_not_empty():
    """The floor, stated on its own so the clause below cannot pass through it.

    CQ-207 is the case: a clause reported as proven red had gone red through
    its own empty population, and the tooltip it was aimed at passed. If
    `TEMPLATES` were ever emptied, the derived clause would iterate nothing and
    report success for a product with no documents at all.
    """
    assert len(TEMPLATES) >= 3, (
        "the template registry has shrunk below the three templates the "
        "product has always rendered, so the derived clause below would be "
        f"asking about almost nothing: {TEMPLATES!r}")
    assert "comparison" in TEMPLATES, (
        "`comparison` has left the registry, so this file is now pointed at "
        f"a template the product no longer renders: {TEMPLATES!r}")


def test_every_template_the_product_renders_is_at_least_named_in_the_source():
    """The floor, browserless. **Not the affordance evidence - CQ-210.**

    This clause used to be the registry clause, and it was the finding: it
    derived its population from `TEMPLATES` - correctly - and then decided
    membership with a matcher that a decorative `<option>` satisfies. A fourth
    template added to `generate.py` with a stray option value somewhere and no
    control at all would have passed it.

    It is kept, demoted and renamed, because it is the only clause in this file
    that runs where there is no browser, and a template named in no source file
    whatever cannot possibly have a control. Passing it means nothing about the
    affordance; failing it is still real.
    `test_every_template_the_product_renders_can_be_pressed_from_a_screen` is
    the clause that answers the invariant.
    """
    have = offered()
    missing = sorted(t for t in TEMPLATES if t not in have)
    assert not missing, (
        "the product renders a template whose name appears nowhere under "
        f"dashboard/src, so no control can be asking for it: {missing!r} are "
        "in TEMPLATES and in no `<option value>` or posted `template:`. This "
        "is the floor, not the affordance clause - the driven clause below is "
        f"the one that answers that. Named: "
        f"{ {k: sorted(v) for k, v in sorted(have.items())} }")


def _templates_a_control_can_post(
        base, ids, page) -> tuple[dict[str, set[str]], list[str]]:
    """Every template value the running dashboard actually posts, by screen.

    **This is the answer CQ-210 asked for: something a browser can be asked.**
    The population of screens is `ROUTES` from `tests/test_a11y_rendered.py`,
    which is derived rather than typed - that file requires it to cover every
    hash route `App.tsx` claims, so a screen added tomorrow joins this walk
    without anyone editing this file.

    On each screen: every enabled `button` whose own text names generating,
    pressed once per option of that screen's `select[aria-label="template"]`
    where it has one. What is recorded is the `template` field of the
    `/api/reports` body the press produced - so the evidence is a control that
    posts, not a string in a module.

    **The post is aborted deliberately.** What is being measured is what the
    screen asks for, not what the server does with it. Letting it through would
    write a document and a `reports` row for every press, on a database shared
    with every other file that reuses `served` - the cleanup problem
    `_drop_new_comparisons` exists for below, multiplied by every screen. It
    also makes the walk cheap: no renderer runs.

    **Recorded so the next person does not undo it.** Bounding each press with
    `expect_request` rather than a wait is what keeps this affordable: a button
    that names generating but posts nowhere costs the timeout once and nothing
    else, where a fixed wait would cost it on every button on every route.
    """
    from playwright.sync_api import TimeoutError as PlaywrightTimeout

    posted: dict[str, set[str]] = {}
    #: One line per press, so a clause that goes red says which control on
    #: which screen was pressed with which option and whether anything left
    #: the browser. Without it the only output is a missing template name,
    #: which does not distinguish "no control" from "the walk misread the
    #: screen" - and both happened while this was being written.
    presses: list[str] = []
    screen = {"name": ""}

    def record(route):
        body = route.request.post_data
        if body:
            try:
                template = json.loads(body).get("template")
            except ValueError:
                template = None
            if isinstance(template, str):
                posted.setdefault(template, set()).add(screen["name"])
        route.abort()

    page.route("**/api/reports", record)
    for name, hash_route in ROUTES:
        screen["name"] = name
        # A clean document per screen rather than a hash change on the last
        # one: a same-document hash navigation leaves the previous screen's
        # markup up until React re-renders, and a button scan that races that
        # attributes one screen's control to another.
        page.goto("about:blank")
        page.goto(f"{base}/" + hash_route.format(**ids), wait_until="load")
        # `networkidle` and not a selector, and this is the dead end worth
        # recording. The first shape of this walk waited on `h1, h2` - and
        # `App.tsx:256` renders a persistent `<h1>` in the chrome, so the wait
        # returned on the app shell and the button scan ran before any screen
        # whose control arrives with its data. Measured: `comparison` came
        # back missing while `run` and `monthly-trend` were pressed happily,
        # because `ReportView` paints its control synchronously and
        # `CompareView` paints its own only after the diff loads. A screen
        # selector cannot fix that generally - the walk does not know what any
        # given screen paints - so what is waited on is the screen's own
        # fetches going quiet.
        try:
            page.wait_for_load_state("networkidle", timeout=20_000)
        except PlaywrightTimeout:
            pass

        captions = page.eval_on_selector_all(
            "button", "(els) => els.map((e) => e.innerText.trim())")
        values = page.eval_on_selector_all(
            'select[aria-label="template"] option',
            "(els) => els.map((e) => e.value)") or [None]

        # Located by caption and re-resolved before every press, not by the
        # index of the first scan. The second dead end worth recording: an
        # aborted post makes the screen render an `ErrorNote`, which changes
        # how many buttons are on the page - so on the second pass through a
        # screen's template options, `nth(index)` pointed at a different
        # control and the press was silently lost. Measured: `monthly-trend`
        # disappeared from the result while `run`, pressed first on the same
        # screen, survived.
        for caption in sorted({c for c in captions if GENERATOR.search(c)}):
            for value in values:
                # No `count()` guard either, and it is the same mistake as
                # the `is_enabled()` one wearing different clothes: `count()`
                # does not wait, and a control mid-press is showing its busy
                # caption - `Generating...` - so a name lookup taken straight
                # after the previous press matched nothing and the option was
                # skipped. Everything that needs to wait is left to `click`.
                button = page.get_by_role(
                    "button", name=caption, exact=True).first
                if value is not None:
                    page.select_option('select[aria-label="template"]', value)
                try:
                    with page.expect_request(
                            lambda r: (r.method == "POST"
                                       and r.url.endswith("/api/reports")),
                            timeout=6_000):
                        # No `is_enabled()` guard, and this is the third dead
                        # end. `expect_request` returns the moment the request
                        # leaves the browser, which is well before the screen
                        # clears its own busy flag - so a guard that skipped
                        # disabled buttons skipped the *second* option on
                        # every screen with a template `<select>`. Measured:
                        # `run` was pressed and `monthly-trend` was reported
                        # as having no control at all. `click` already waits
                        # for the control to become actionable, so the wait is
                        # left where Playwright does it properly.
                        button.click(timeout=4_000)
                    presses.append(f"{name}/{caption!r}/{value!r} -> posted")
                except PlaywrightTimeout:
                    presses.append(f"{name}/{caption!r}/{value!r} -> no post")
    page.unroute("**/api/reports", record)
    return posted, presses


@live
def test_every_template_the_product_renders_can_be_pressed_from_a_screen(
        served, browser_page):
    """The affordance clause. **Driven, because CQ-210.**

    The clause this replaces derived its population from `TEMPLATES` and then
    decided membership by asking whether the name appeared in any
    `<option value>` or any posted `template:` literal anywhere under
    `dashboard/src`. Neither regex is bound to a `<select>` that feeds
    `template`, so it answered yes for six names that are not templates at all
    - and would have answered yes for a fourth template with a decorative
    option and no control, which is the exact case the population was derived
    for. Demonstrated failure class 3, a verification gate defeated by weak
    matching.

    What is asserted here comes off the wire: a control was pressed and the
    dashboard posted that template.
    """
    base, ids = served
    posted, presses = _templates_a_control_can_post(base, ids, browser_page)

    missing = sorted(t for t in TEMPLATES if t not in posted)
    assert not missing, (
        "the product renders a template no control on any screen posts, which "
        f"is the affordance invariant: {missing!r} are in TEMPLATES. Pressed "
        f"across the {len(ROUTES)} screens the app dispatches: "
        f"{ {k: sorted(v) for k, v in sorted(posted.items())} }. Every press: "
        + "; ".join(presses))

    # The regex floor is kept as a *superset* check and nothing more. If a
    # control posts a template the source scan cannot see, the scan has gone
    # blind to a shape the dashboard now writes - an interpolated value, a
    # ternary - and the browserless job's floor is silently answering about
    # less than it thinks.
    unseen = sorted(k for k in posted if k not in offered())
    assert not unseen, (
        "a control posted a template the source matcher cannot see, so the "
        f"browserless floor is narrower than the product: {unseen!r} were "
        "pressed and are matched by neither OPTION nor POSTED. Widen the "
        "regexes or state why the floor no longer covers this shape.")


@live
def test_the_source_matcher_admits_a_name_no_control_can_ask_for(
        served, browser_page):
    """The lens. CQ-207's remedy, applied to CQ-210's mechanism.

    A guard that reports a property it does not test is the class report 095
    named after finding it twice in two rounds, and the answer both times is
    the same: assert the lens rather than declare it. This clause states the
    defect as a measurement, so the driven pass cannot quietly decay back into
    a source match without going red.

    `client` is an audience value. It is painted as `<option value="client">`
    by two screens, so the source matcher admits it; no control anywhere posts
    it as a template, so the driven pass must not. Observed against the old
    mechanism when this was taken: `"client" in offered()` was `True`.
    """
    base, ids = served
    assert DECOY in offered(), (
        f"{DECOY!r} is no longer matched by the source scan, so it has stopped "
        "being a decoy and this clause proves nothing. Pick another value the "
        "matcher admits and no control posts, or - if the matcher has been "
        "bound to a template `<select>` - retire this clause deliberately.")

    posted, presses = _templates_a_control_can_post(base, ids, browser_page)
    assert posted, (
        "no control on any screen posted a template, so the driven pass "
        "measured nothing and the assertion below would pass vacuously")
    assert DECOY not in posted, (
        f"the driven pass reported {DECOY!r} as a template a control can ask "
        "for. It is an audience value. Either a screen now genuinely posts it "
        "as a template, or this pass has degraded into the source match "
        "CQ-210 was raised against. Pressed: "
        f"{ {k: sorted(v) for k, v in sorted(posted.items())} }. "
        + "; ".join(presses))


#: The compare screen's two frame sentences, by the words that carry them.
#: WF-02 wrote the first and WF-28 the second, and both are prose this round's
#: change lands directly beneath - so they are asserted rather than assumed.
FRAME = ("Current audit", "Baseline audit")


@live
def test_the_comparison_screen_offers_a_control_that_produces_the_document(
        served, browser_page):
    """Driven. The screen holding both run ids can ask for the document.

    Located by what the control does rather than by a class or a position: any
    `button` on the screen whose own text names generating or producing a
    report. A guard keyed on a selector would pass on a control that had been
    moved somewhere unreachable, and DISCIPLINE rule 12 asks for the thing the
    operator can actually press.
    """
    base, ids = served
    browser_page.goto(f"{base}/#/compare/{ids['run']}/{ids['run2']}",
                      wait_until="load")
    browser_page.wait_for_selector("h2", timeout=15_000)
    heading = browser_page.inner_text("h2")
    assert "comparison" in heading.lower(), (
        "the compare screen did not render, so nothing below is evidence "
        f"about it: heading was {heading!r}")

    verbs = browser_page.eval_on_selector_all(
        "button", "(els) => els.map((e) => e.innerText.trim())")
    offers = [v for v in verbs
              if "report" in v.lower() or "generate" in v.lower()]
    assert offers, (
        "the screen names a run comparison, renders four buckets diffed "
        "between two runs, and offers no route to the document about them - "
        f"the buttons present were {verbs!r}")


@live
def test_the_document_the_control_produces_is_a_comparison_of_both_runs(
        served, browser_page):
    """Driven, then read back out of the row the server wrote.

    The press is the evidence, not the markup: a control posting `run_ids` of
    length one answers 422 and would leave a screen that looks identical to a
    working one. What is asserted here is the stored `reports` row - its
    template, and that its `run_ids` are the two the screen was showing.
    """
    base, ids = served
    before = _comparisons(ids["db"])
    try:
        browser_page.goto(f"{base}/#/compare/{ids['run']}/{ids['run2']}",
                          wait_until="load")
        browser_page.wait_for_selector("h2", timeout=15_000)
        button = browser_page.query_selector(
            "xpath=//button[contains(translate(., 'REPORT', 'report'),"
            " 'report')]")
        assert button is not None, (
            "no control on the compare screen names a report, so there is "
            "nothing to press - the same absence the clause above reports")
        button.click()
        # CQ-211. This was `wait_for_timeout(5_000)`. The screen paints an
        # explicit completion signal - `dashboard/src/views.tsx` renders
        # "Saved to {path} - open the document" exactly when the post
        # resolves - so the wait is on that and not on a clock. The file runs
        # in the rendered-a11y sweep under `-n auto --dist loadfile` beside
        # seven other workers launching Chromium, which is the condition
        # KI-51 records for a clause that passes alone and fails in the
        # pinned suite; a fixed five seconds is a coin toss under that load,
        # and a timeout here is a real failure with a real message rather
        # than an empty diff five seconds later.
        browser_page.wait_for_selector("text=open the document",
                                       timeout=30_000)

        made = [r for r in _comparisons(ids["db"]) if r not in before]
        assert made, (
            "pressing the control produced no comparison document: the stored "
            f"comparisons were {before!r} before and are unchanged after")
        for _template, run_ids in made:
            assert set(json.loads(run_ids)) == {ids["run"], ids["run2"]}, (
                "the document was written against runs other than the two the "
                f"screen was comparing: {run_ids!r} against "
                f"{[ids['run'], ids['run2']]!r}")
    finally:
        # The fixture database is shared with every other file that reuses
        # `served`, and this is the only clause in the suite that adds a row to
        # `reports` by pressing something. Left behind, it would turn up in
        # `test_deliverable_regenerate.py`'s table as an extra row that file
        # did not stage.
        _drop_new_comparisons(ids["db"], before)


@live
def test_the_comparison_screen_still_states_the_two_runs_it_diffed(
        served, browser_page):
    """Must-not-change, and it passes on both trees.

    The control this round adds lands directly under the two frame sentences
    WF-02 and WF-28 put there, and a new block is exactly the kind of edit that
    displaces prose. Neither sentence is this finding's subject; both are the
    reason the buckets above them mean anything.
    """
    base, ids = served
    browser_page.goto(f"{base}/#/compare/{ids['run']}/{ids['run2']}",
                      wait_until="load")
    browser_page.wait_for_selector("h2", timeout=15_000)
    body = browser_page.inner_text("body")
    for phrase in FRAME:
        assert phrase in body, (
            f"the compare screen no longer states {phrase!r}, so the buckets "
            "it renders no longer say what they were counted against")


def _comparisons(db: str) -> list[tuple[str, str]]:
    conn = sqlite3.connect(db)
    try:
        return conn.execute(
            "SELECT template, run_ids FROM reports WHERE template='comparison'"
        ).fetchall()
    finally:
        conn.close()


def _drop_new_comparisons(db: str, before: list[tuple[str, str]]) -> None:
    conn = sqlite3.connect(db)
    try:
        keep = [r for r in conn.execute(
            "SELECT id, template, run_ids FROM reports WHERE"
            " template='comparison'").fetchall()
            if (r[1], r[2]) not in before]
        for row in keep:
            conn.execute("DELETE FROM reports WHERE id=?", (row[0],))
        conn.commit()
    finally:
        conn.close()


@pytest.fixture()
def browser_page():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            yield pg
        finally:
            browser.close()
