"""F-10: every control that spends says so, from one shared component.

**Ordinary tests, not guards.** The behaviour did not exist before this
feature, so there was no prior failure to observe and DISCIPLINE rule 1 does
not apply — `FEATURES.md` says so for every entry in it. Each assertion here
was written with the feature and would have been false against the tree
before it: `.spend-mark` matched nothing and `SpendMark` was not exported.

**The negative case has teeth, and it is why this file exists in this shape.**
The first build of F-10 (`711557e`) was reverted (`e979b1c`) for marking
`tools.tsx`'s "Run all N" button — which calls `setConfirming(true)` and
opens a confirmation dialog. It spends nothing; the two buttons *inside* the
dialog do. That is exactly clause 2's "no control that does not spend carries
it", and nothing in the first build's tests could see it, because they only
ever asserted that marks were present. `test_the_dialog_opener_carries_no_mark`
below is the assertion that revert should have had.

The live test reuses `test_a11y_rendered.py`'s `served` fixture, whose
database has no `model_prices` row at all — so clause 4 (the marker appears
with no price configured) is proven by construction rather than by arranging
it. That one test needs a browser, so this file runs in two CI jobs: the
static tests gate in `python`, and the live one gates in `rendered-a11y`,
which is the only job with a browser and which fails on any skip.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from clauditseo import axe
from tests.test_a11y_rendered import DIST, served  # noqa: F401  (reused fixture)

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"

#: Where model spend actually originates, established from the server rather
#: than guessed from the client. `provider_from_settings` appears six times
#: in `app.py` and only three of those are a spend:
#:
#:   :705, :772   capability checks — "is an analyst configured", for
#:                `/api/meta` and the provider status panel. No call is made.
#:   :1639        POST /api/runs/{id}/advise          — spends
#:   :1728        POST /api/runs/{id}/expert/{tool}   — spends
#:   :1753        POST /api/runs/{id}/schema-audit    — spends
#:   :2213        the analyst layer inside a run — spends *conditionally*,
#:                and `adaptive.py:113` invokes it again for an auto-tier run,
#:                which is why the audit launcher is marked too.
#:
#: The first draft of this file asserted a count of three and was wrong; the
#: guard below is what caught it, which is the only reason it is written as a
#: count rather than a comment.
PAID_HANDLERS = 3
CAPABILITY_CHECKS = 2
ANALYST_LAYER = 1


def test_the_provider_call_sites_still_match_this_files_premise():
    """Guards this file's own premise. Every enumeration below rests on
    knowing exactly which handlers reach a model; if that changes, the
    enumerations silently stop covering the truth."""
    app = (Path(__file__).resolve().parents[1]
           / "clauditseo" / "api" / "app.py").read_text(encoding="utf-8")
    expected = PAID_HANDLERS + CAPABILITY_CHECKS + ANALYST_LAYER
    assert app.count("provider_from_settings(") == expected, (
        "a handler started or stopped reaching an LLM provider; re-derive "
        "which controls spend before trusting the rest of this file")


def test_the_adaptive_path_still_runs_analysts_itself():
    """The audit launcher is marked because an auto-tier run reaches the
    analyst layer without the operator ticking anything. If that stops being
    true, the launcher's mark becomes a clause 2 violation."""
    adaptive = (Path(__file__).resolve().parents[1]
                / "clauditseo" / "adaptive.py").read_text(encoding="utf-8")
    assert "run_analyst_layer(" in adaptive


# --------------------------------------------------------------------------
# Clause 3 — one shared component
# --------------------------------------------------------------------------

def test_spend_mark_is_defined_exactly_once():
    """B-22's diagnosis was five screens each deriving their own answer and
    disagreeing. A `SpendMark` defined twice is that defect wearing the
    feature's own name."""
    defined_in = [p.name for p in SRC.glob("*.tsx")
                  if re.search(r"^export function SpendMark\b",
                               p.read_text(encoding="utf-8"), re.M)]
    assert defined_in == ["components.tsx"], defined_in


def test_every_marking_file_imports_the_shared_component():
    """No file may render a `$` of its own devising: anything using the mark
    imports it from `components.tsx`."""
    for path in SRC.glob("*.tsx"):
        text = path.read_text(encoding="utf-8")
        if "<SpendMark" not in text:
            continue
        assert re.search(
            r'import\s*\{[^}]*\bSpendMark\b[^}]*\}\s*from\s*"\./components"', text), (
            f"{path.name} renders SpendMark without importing the shared one")


# --------------------------------------------------------------------------
# Clause 2 — the negative case, and the specific defect that caused the revert
# --------------------------------------------------------------------------

def test_the_dialog_opener_carries_no_mark():
    """The assertion the reverted build lacked.

    A control that opens a confirmation spends nothing, and marking one was
    the whole reason `711557e` was reverted.

    **This read `tools.tsx`'s working-set button until item 188 retired that
    screen.** The pair it was about moved to the Analyses catalogue, which
    inherited the batch run: `.run-all` opens the confirm and posts nothing,
    `.batch-commit` inside it commits. Same distinction, on the screen that now
    carries the risk. Read structurally rather than by line number, so the
    clause survives the file moving underneath it.
    """
    text = (SRC / "catalogue.tsx").read_text(encoding="utf-8")
    opener = re.search(r'className="run-all"(.*?)</PrimaryButton>', text, re.S)
    assert opener, "the confirm-dialog opener is no longer recognisable"
    assert "SpendMark" not in opener.group(1), (
        "the button that opens the confirmation dialog does not spend — the "
        "button inside the dialog does. This is the defect e979b1c reverted.")


def test_the_buttons_inside_the_dialog_do_carry_it():
    """The other half of the same distinction: the button inside the confirm
    calls `commit`, which POSTs, so it commits the spend and must be marked.
    Without this, 'no mark on the opener' would be satisfiable by marking
    nothing at all.

    Three buttons when `ConfirmRun` held them on the retired Tools screen, one
    now that `catalogue.tsx`'s `.batch-commit` is the committing control. The
    count is read from the file rather than asserted at 3, because what matters
    is that every committing button is marked - not how many there are.
    """
    text = (SRC / "catalogue.tsx").read_text(encoding="utf-8")
    commit = re.search(r'className="batch-commit"(.*?)</PrimaryButton>', text, re.S)
    assert commit, "the committing button is no longer recognisable"
    assert "onClick={commit}" in commit.group(1), (
        "the marked button no longer commits, so this clause would pass while "
        "guarding nothing")
    assert "<SpendMark />" in commit.group(1), (
        "the button that commits a paid call must be marked")


def test_free_controls_are_not_marked():
    """A mark that appears everywhere says nothing — clause 2, and the same
    'fires every time' failure this codebase has shipped before. These are
    real controls that issue no paid call: reading a stored report, cancelling
    the dialog, stopping a sweep, toggling an input panel."""
    # `catalogue.tsx` since item 188: its Cancel closes the confirm the
    # retired Tools screen's Cancel used to close, and its "stop" control is
    # the one that stops a batch now.
    cat = (SRC / "catalogue.tsx").read_text(encoding="utf-8")
    expert = (SRC / "expert.tsx").read_text(encoding="utf-8")
    panels = (SRC / "panels.tsx").read_text(encoding="utf-8")

    for label, text in (("Cancel", cat),
                        ("stop after this one", expert), ("close", panels)):
        # Item 183: these are the five variants now, not raw pills.
        m = re.search(r"<(?:Pill|SecondaryButton)[^>]*>\s*\{?[^<]*"
                      + re.escape(label), text, re.I)
        assert m, f"the {label!r} control is no longer recognisable"
        assert "SpendMark" not in m.group(0), (
            f"{label!r} issues no paid call and must not carry the mark")


def test_the_crawl_control_is_not_marked():
    """`/api/sites/{id}/audits` is a crawl, not a model call — it appears in
    none of `PAID`. The control that starts one must not claim to spend model
    tokens.

    Tools' crawl button held this until item 188. The surviving control that
    posts `/audits` with no analyst is the section refresh in `anatomy.tsx`,
    whose own comment records the same reasoning from the other direction: it
    was marked while the run enabled the analysts, and the mark went when
    `analyst: false` did.
    """
    text = (SRC / "anatomy.tsx").read_text(encoding="utf-8")
    m = re.search(r"onClick=\{start\}>(.*?)</PrimaryButton>", text, re.S)
    assert m, "the section-refresh control is no longer recognisable"
    assert "SpendMark" not in m.group(1), "a crawl is drawn as a model spend"
    assert "SpendButton" not in m.group(0), "the crawl is drawn as a spend"


# --------------------------------------------------------------------------
# Clause 1 — every spending control, and clause 4 — with no price known
# --------------------------------------------------------------------------

@pytest.mark.parametrize("filename,expected", [
    # audit-structured-data, advise-on-page, x2 try-again, and F-04's
    # "Advise again". The fifth is the one the read-back made necessary:
    # once stored advice mounts there is no un-advised state to click
    # through, so the panel needs its own way back to a paid call, and a
    # control that reaches the provider carries the mark like the rest.
    ("advice.tsx", 5),
    ("analyses.tsx", 1),  # AnalysisRow(spends); the lanes and triage's controls left (brief v4 3c, 3e)
    ("catalogue.tsx", 3),  # the drawer's run and re-run (brief v4 Item 3e), and run-all's commit (3f)
    # `run {tool}`, and only that. This was 2 — the second was the section
    # refresh's committing button, marked on the same ground as `views.tsx`'s
    # launcher: the endpoint is the same for all of them and the TIER was
    # what separated them. Tools' crawl sends `tier: "T2"` with no analyst, so
    # `analyst_enabled` is false and nothing reaches a model; the launcher and
    # the section refresh both sent `tier: "auto"`, which `app.py` recorded as
    # `analyst_enabled` whatever the caller asked, and `adaptive.py` acted on
    # without the operator ticking anything.
    #
    # WF-59 (Q-18, operator 2026-08-25) made the tier decide breadth alone.
    # The section refresh still sends `tier: "auto"` and now sends
    # `analyst: false` beside it, which `app.py` honours, so that control
    # cannot invoke a model on any instance and the mark went with the spend —
    # `SpendMark` reads "This spends model tokens", and a mark that fires
    # every time is clause 2's own prohibition. `views.tsx`'s launcher sends
    # no `analyst` key at all, which still means "let the tier decide", so it
    # is unchanged and still marked.
    ("anatomy.tsx", 1),
    ("panels.tsx", 1),    # ReportHead's re-run
    ("expert.tsx", 4),    # tool(unstored), re-run, vs-deep, run-all/remaining
    # The audit launcher. An audit is a crawl, but the analyst layer rides on
    # it: `app.py:2295` runs it when `analyst` is set, and `adaptive.py:113`
    # runs it unprompted for an auto-tier run, which is this picker's default.
    # And (item 178) the five quick audits of ClientDetailView, one map: they
    # send no `analyst` key either, so the tier decides as it does here.
    ("views.tsx", 2),
    # Item 178's other spend controls, each a SpendButton: the Providers check
    # (a billable call), a Workbench dims audit (no `analyst` key, as above),
    # the part page's analysis and content brief, Speed's two depths (one map),
    # and Reports' Generate for the run report (the plan brief).
    ("admin.tsx", 1),
    ("workbench.tsx", 1),
    ("part_page.tsx", 2),
    ("speed_now.tsx", 1),
    # Generate for the run report, and the $ on the Generate card's sentence
    # saying the run report writes the plan with a model.
    ("reports.tsx", 2),
    # The scan chooser's cells: one mark, inside the cost caption every cell
    # that reaches a model renders (the quick depth is free and unmarked).
    # Twelve controls, one purchase surface, absent from this list until the
    # second audit of 2026-09-02 (F-02, F-27).
    ("scanmatrix.tsx", 1),
])
def test_each_file_marks_the_controls_it_owns(filename, expected):
    """Clause 1, enumerated from the grep that produced it rather than from
    memory. Counting per file rather than in total means a mark moved from
    one screen to another is caught instead of cancelling out."""
    text = (SRC / filename).read_text(encoding="utf-8")
    # Item 178: `SpendButton` draws the mark itself, so a control it renders
    # counts as marked here as a literal `<SpendMark />` does.
    found = text.count("<SpendMark />") + len(re.findall(r"<SpendButton\b", text))
    assert found == expected, (
        f"{filename}: expected {expected} marked controls, found {found}")


def test_no_figure_is_welded_inside_a_control():
    """The entry's own instruction: this removes on-button figures rather
    than adding to them. A `cost-tag` between a `<Pill ...>` and its
    `</Pill>` is a price welded into the control that commits the spend.
    (`pill-cost` was renamed to `cost-tag` and every `<button>` became a
    `<Pill>` in the item-140 tone migration.)"""
    offenders = []
    for path in SRC.glob("*.tsx"):
        for m in re.finditer(r"<Pill\b.*?</Pill>",
                             path.read_text(encoding="utf-8"), re.S):
            if "cost-tag" in m.group(0):
                offenders.append(f"{path.name}: {m.group(0)[:80]}")
    assert not offenders, offenders


@pytest.mark.skipif(not axe.available(),
                    reason="needs clauditseo[render] and `playwright install chromium`")
@pytest.mark.skipif(not (DIST / "index.html").is_file(),
                    reason="dashboard not built (npm run build in dashboard/)")
def test_the_mark_renders_with_no_price_configured(served):
    """Clause 4, the one that matters, driven at the running product.

    `served` seeds a real client, site and completed audit and configures no
    `model_prices` at all, so this proves the marker's presence in the state
    the acceptance signal names: the app renders every cost in tokens and
    there is no dollar figure anywhere to draw. A marker that needed a price
    would be absent here.

    **Guarded at collection, not inside the body, and that is the fix rather
    than the decoration.** The first version imported `sync_playwright` on
    the line above its own `pytest.skip`, so the `python` job — which
    installs no extras by design — raised `ModuleNotFoundError` before ever
    reaching the guard, and both matrix legs went red. The two markers on
    this test are `test_a11y_rendered.py`'s module-level pair, copied rather
    than invented: this test needs the same browser and the same built
    bundle, for the same reason.

    **A skip here is not this clause going quiet.** `.github/workflows/ci.yml`
    runs this file in the `rendered-a11y` job too, where both conditions
    hold, and that job fails on *any* skip — so the clause is enforced on
    every push and pull request, and cannot rot into a green no-op the day
    the browser install breaks. The `python` job keeps every static test in
    this file; only this one needs a browser.
    """
    from playwright.sync_api import (TimeoutError as PWTimeout,
                                     sync_playwright)

    base, ids = served
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        try:
            # The Analyses catalogue since item 188 retired Tools: same
            # opener-and-commit pair, on the screen that inherited the batch.
            pg.goto(f"{base}/#/sites/{ids['site']}?tab=findings",
                    wait_until="load", timeout=30_000)

            # `RUN_LABEL` is the only thing in the DOM that distinguishes
            # this control. It was one of three until CQ-239 at round 121:
            # the other two were branches of a `Record` keyed on `ran`, a
            # state whose setter had not existed since 12 August 2026, so
            # the product could never render them. The tuple shape is kept
            # because the wait below iterates it — one predicate, per KI-15.
            OPENERS = ("Run all ",)

            # Wait for the opener itself, never for a shared style class —
            # KI-15. On the retired Tools screen two controls carried
            # `.pill-run` under *mutually exclusive* conditions: the opener
            # behind `!!runs.length` and the crawl control behind the inverse.
            # Before the completed-audit fetch landed only the second existed,
            # so a wait on the shared class returned onto a DOM that could not
            # yet hold the opener — the
            # search below found nothing, and the failure message re-queried
            # and printed `['Run all 24']`, the opener that had rendered in
            # between. Roughly one run in two under `-n auto`, where the fetch
            # is slower and the window is wider.
            #
            # The wait runs the *same* predicate the search does, so the two
            # cannot disagree about what an opener is. A selector that only
            # approximated it — `:has-text`, a positional index — would put
            # the same class of defect back with a different mechanism.
            try:
                pg.wait_for_function(
                    """(prefixes) => [...document.querySelectorAll(
                         "button.run-all")].some((b) => prefixes.some(
                           (p) => (b.textContent || "").trim().startsWith(p)))""",
                    arg=list(OPENERS), timeout=30_000)
            except PWTimeout:
                raise AssertionError(
                    "no confirm-dialog opener rendered within 30s: "
                    + repr([b.text_content() for b
                            in pg.query_selector_all("button.run-all")]))

            # Selected by its own label, not as "the first .pill-run" — the
            # crawl control and the per-brief Run button share that class, and
            # picking by position made this test both wrong and flaky under a
            # parallel suite.
            opener = None
            for button in pg.query_selector_all("button.run-all"):
                text = (button.text_content() or "").strip()
                if text.startswith(OPENERS):
                    opener = button
                    break
            assert opener is not None, (
                "the confirm-dialog opener did not render: "
                + repr([b.text_content() for b
                        in pg.query_selector_all("button.run-all")]))
            assert opener.query_selector(".spend-mark") is None, (
                "the dialog opener must not carry the mark (e979b1c)")

            opener.click()
            pg.wait_for_selector(".batch-confirm", timeout=30_000)

            committing = pg.query_selector_all(".batch-confirm .batch-commit")
            assert committing, "the dialog rendered no committing buttons"
            for button in committing:
                assert button.query_selector(".spend-mark") is not None, (
                    "with no model_prices configured anywhere, a committing "
                    f"button still lost its mark: {button.text_content()!r}")

            cancel = [b for b in pg.query_selector_all(".batch-confirm button")
                      if (b.text_content() or "").strip() == "Cancel"]
            assert cancel and cancel[0].query_selector(".spend-mark") is None, (
                "Cancel spends nothing and must not carry the mark")
        finally:
            browser.close()
