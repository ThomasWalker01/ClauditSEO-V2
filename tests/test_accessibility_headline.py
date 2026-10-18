"""F-09: accessibility carries its own total, separately from the SEO composite.

**Ordinary tests, not guards.** `FEATURES.md` says so for every entry in it:
the behaviour did not exist before this feature, so there is no prior failure
to observe and DISCIPLINE rule 1 does not apply. Every assertion here was
written with the feature and would have been false against the tree before it
— `AccessibilityScore` did not exist, `.headline-a11y` matched nothing, and
the run screen decomposed one number into a table with an `A11Y` row in it
reading `0.0%`.

**Why a zero-weight row was worth a feature.** `DEFAULT_WEIGHTS["A11Y"] = 0.0`
is "reported, never scored", and `composite()` renormalises a zero-weight
dimension out of the total. So accessibility — 803 of the 2,122 findings this
product has ever produced, 381 of them `high` — was rendered as a component of
the SEO score contributing nothing to it. The number was already stored on
every run; nothing had ever read it.

**Split across the two CI legs, for the reason `test_spend_mark.py` records.**
Clauses 1 and 2 are about arithmetic and about which value the card is handed,
and both can be established without a browser. Clause 3 is about what a
component *draws* in a state — an accessibility sweep that did not execute —
and that cannot be read off the source, so it is driven at a real server with
a real browser. In the `python` job those tests skip themselves at collection;
`.github/workflows/ci.yml` runs this file in `rendered-a11y` as well, where
both conditions hold and any skip fails the job.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import pytest

from clauditseo import axe
from clauditseo.engine.scoring import DEFAULT_WEIGHTS, composite
from clauditseo.engine.types import SubScore
from tests.test_a11y_rendered import DIST, served  # noqa: F401  (reused fixture)

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"
VIEWS = SRC / "views.tsx"

#: JSX/TS comments, blanked rather than deleted so line numbers survive into
#: any failure message. Copied in spirit from `test_dashboard_a11y.py`: a guard
#: that reads prose about the code instead of the code is a guard that passes
#: on a comment.
COMMENT = re.compile(r"/\*.*?\*/|//[^\n]*", re.S)

#: The two conditions the live tests need, as `test_spend_mark.py` states them:
#: a browser and a built bundle. Applied per test rather than to the module,
#: because the static half of this file must keep gating in the `python` job.
NEEDS_BROWSER = pytest.mark.skipif(
    not axe.available() or not (DIST / "index.html").is_file(),
    reason="needs clauditseo[render], `playwright install chromium`, and a "
           "built dashboard (npm run build in dashboard/)")


def _source(path: Path) -> str:
    return COMMENT.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)),
                       path.read_text(encoding="utf-8"))


def _component(name: str) -> str:
    """The body of one component, from its `function` line to the next one.

    Scoped deliberately. "Does the card recompute the score" is a question
    about `AccessibilityScore`, and asking it of the whole file would be
    answered by arithmetic anywhere in it — including the composite's own,
    which is not this feature's business.
    """
    text = _source(VIEWS)
    start = text.index("function %s(" % name)
    return text[start:text.index("\nfunction ", start + 1)]


# ---- clause 1: the composite is the same number it always was --------------

def test_accessibility_contributes_nothing_to_the_composite():
    """Clause 1, at the arithmetic that produces the stored figure.

    The claim being proved is that this feature is presentational: taking
    accessibility out of the decomposition the card draws cannot move the
    number drawn beside it, because it was never in it. A deliberately
    terrible A11Y score is used — 12.0 against seven dimensions in the high
    eighties — so that a weight which had crept above zero would show up here
    as several whole points rather than as a rounding difference.
    """
    scored = {"TEC": 88.0, "ONP": 91.0, "CNT": 84.0, "PRF": 79.0,
              "OFP": 95.0, "AIS": 87.0, "LOC": 90.0, "A11Y": 12.0}
    subs = {d: SubScore(dimension=d, score=v, weight=DEFAULT_WEIGHTS[d])
            for d, v in scored.items()}

    with_it, out = composite(subs)
    without_it, _ = composite({d: s for d, s in subs.items() if d != "A11Y"})

    assert with_it == without_it, (
        "accessibility moves the composite — this feature separates a "
        "dimension that is still being summed into the SEO score, and clause "
        "1 is not met: %s with it, %s without" % (with_it, without_it))
    assert out["A11Y"].weight == 0.0, (
        "A11Y came out of composite() with a share of the total. The front "
        "card presents it as a separate score on the strength of this being "
        "zero: %s" % out["A11Y"].weight)
    # And it is still there to be read. Weight 0 means "not summed", not
    # "discarded" — the card has nothing to render if the sub-score stops
    # being returned.
    assert out["A11Y"].score == 12.0


def test_the_zero_weight_this_feature_rests_on_is_still_zero():
    """Guards this file's own premise, in the manner `test_spend_mark.py`
    guards its enumeration of paid handlers.

    Everything here rests on accessibility being outside the composite. If
    that weight is ever raised — which `FEATURES.md` explicitly leaves open,
    "re-weighted by changing one number" — a separate headline stops being the
    honest presentation, and this file should be re-argued rather than quietly
    kept green.
    """
    assert DEFAULT_WEIGHTS["A11Y"] == 0.0, (
        "A11Y now carries weight in the composite. The front card states it "
        "as a total of its own, outside the composite — that presentation is "
        "wrong the moment this is non-zero.")


# ---- clause 2: the stored number, never a recomputed one -------------------

def test_the_card_is_handed_the_stored_subscore():
    """Clause 2. The value reaching the card comes from `data.subscores`,
    which `persistence/runs.py:get_run` parses out of the `subscores` column
    the engine wrote at run time — so what the headline draws is that run's
    own recorded figure and not a second opinion about it.
    """
    assert re.search(
        r"<AccessibilityScore\s+sub=\{\(data\.subscores \?\? \{\}\)\.A11Y\}",
        _source(VIEWS)), (
        "the accessibility headline is not being handed the stored A11Y "
        "sub-score from the run payload")


def test_the_card_does_no_arithmetic_on_the_score():
    """Clause 2's negative half, which is the half worth testing.

    "Renders the stored subscore, verbatim, never one recomputed by the card
    itself" is not provable by finding a correct expression; it is provable by
    there being no other kind. So within this component `score` may be
    formatted and may be nothing else. `toFixed` is formatting — it changes
    how a number is written, not which number it is.

    `coverage` is deliberately exempt: it is multiplied by 100 to say "62%
    measured", which is a second stored field being displayed, not the score
    being adjusted by it. A card that scaled the score by its coverage would
    be exactly the recomputation clause 2 forbids, and this assertion sees it,
    because it would have to touch `score` to do it.
    """
    body = _component("AccessibilityScore")
    uses = re.findall(r"sub!?\??\.score\s*([^\s,)}]*)", body)
    assert uses, "AccessibilityScore no longer reads the stored score at all"
    assert all(u.startswith(".toFixed(") for u in uses), (
        "the accessibility headline computes with the stored score instead of "
        "formatting it — clause 2 forbids a second number: %s" % (uses,))


def test_the_composite_decomposition_no_longer_lists_accessibility():
    """The other half of "separately": a table decomposing the composite has
    no row for a dimension the composite does not contain. That row could only
    ever read `0.0%` — the composite's honest arithmetic, and a false account
    of a dimension marked `high` in the findings list on the same screen.

    It is not dropped from the screen; it is the headline beside it, which is
    what the assertion above establishes.
    """
    assert 'filter(([d]) => d !== "A11Y")' in _source(VIEWS), (
        "the run screen's dimension table is back to listing every sub-score "
        "including A11Y, at a weight of zero")


# ---- clause 3: an absence is not a zero, driven at the running product -----

@NEEDS_BROWSER
def test_the_headline_draws_the_score_the_run_stored(served):
    """Clauses 1 and 2 at the running product, on a real stored audit.

    Rule 12: the acceptance signal is something the operator sees on a screen,
    so it is read off the screen. The rendered number is compared against what
    the API returns for that run, which is the column the engine wrote — if
    the card ever starts computing its own, the two stop matching.

    Clause 1 is asserted here in the form the entry asked for: against a run
    already in a database, the stored composite is exactly the sum of the
    sub-scores by their stored weights, and A11Y's term in that sum is zero.
    Nothing the card does to the table can move it.
    """
    import httpx
    from playwright.sync_api import sync_playwright

    base, ids = served
    run = httpx.get("%s/api/runs/%s" % (base, ids["run"]), timeout=30).json()
    subs = run["subscores"]
    assert "A11Y" in subs, (
        "the fixture's audit did not score accessibility, so this test would "
        "assert nothing — seed a run whose dimensions include A11Y")

    # Clause 1, against what is stored rather than against a model of it.
    assert subs["A11Y"]["weight"] == 0.0
    total = sum(s["score"] * s["weight"] for s in subs.values())
    assert total == pytest.approx(run["composite_score"], abs=0.01), (
        "the stored composite is not the stored sub-scores by their stored "
        "weights: %s against %s" % (total, run["composite_score"]))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        try:
            pg.goto("%s/#/runs/%s" % (base, ids["run"]), wait_until="load",
                    timeout=30_000)
            pg.wait_for_selector(".headline-a11y", timeout=30_000)
            shown = pg.locator(".headline-a11y").inner_text()
            expected = "%.1f" % subs["A11Y"]["score"]
            assert expected in shown, (
                "the accessibility headline reads %r, and the run stored %s"
                % (shown, expected))
            assert "accessibility / 100" in shown

            # It is a second total, not a component of the first: the table
            # decomposing the composite has no accessibility row.
            dims = pg.locator(".headline-dims").inner_text()
            assert "A11Y" not in dims, (
                "A11Y is still a row of the composite's decomposition: %r"
                % dims)
            # …and the composite is still on the screen beside it.
            assert "composite / 100" in pg.locator(".headline").inner_text()
        finally:
            browser.close()


@NEEDS_BROWSER
def test_a_sweep_that_did_not_run_reads_not_assessed_and_never_zero(served):
    """Clause 3, and the reason the entry wrote it "not optional".

    `composite()`'s own invariant, inherited rather than restated: 0.0 is a
    measurement meaning perfectly bad, and no measurement at all is a
    different statement that a number cannot make. An accessibility sweep that
    did not execute stores `coverage: 0` — and a headline drawing that as
    `0.0` would tell a client their site is as inaccessible as a site can be,
    on the evidence of nobody having looked.

    Arranged by amending what the fixture stored rather than by contriving a
    run that fails to sweep: `coverage: 0` is the row the engine writes, and
    writing it directly is the same row an unmeasured run produces. `run2` is
    amended, not `run` — the test above reads `run`, and a fixture amended out
    from under a sibling is a test that passes in one order.
    """
    from playwright.sync_api import sync_playwright

    base, ids = served
    conn = sqlite3.connect(ids["db"])
    try:
        stored = json.loads(conn.execute(
            "SELECT subscores FROM audit_runs WHERE id=?",
            (ids["run2"],)).fetchone()[0])
        assert stored["A11Y"]["coverage"] > 0, (
            "the fixture already stores an unmeasured accessibility sweep, so "
            "this test proves nothing about the branch it names")
        stored["A11Y"] = {**stored["A11Y"], "score": 0.0, "coverage": 0.0,
                          "unmeasured": ["the accessibility sweep did not run"]}
        conn.execute("UPDATE audit_runs SET subscores=? WHERE id=?",
                     (json.dumps(stored), ids["run2"]))
        conn.commit()
    finally:
        conn.close()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        pg = browser.new_page()
        try:
            pg.goto("%s/#/runs/%s" % (base, ids["run2"]), wait_until="load",
                    timeout=30_000)
            pg.wait_for_selector(".headline-a11y", timeout=30_000)
            shown = pg.locator(".headline-a11y").inner_text()
            assert "not assessed" in shown, (
                "an accessibility sweep that did not run reads %r" % shown)
            # The stored score is 0.0 and must not appear as one. Asserted on
            # the figure element rather than on the text, so the sentence
            # naming what was not measured stays free to say what it needs to.
            assert not pg.locator(
                ".headline-a11y .headline-number:not(.headline-unassessed)"
            ).count(), ("an unmeasured accessibility sweep is being drawn as "
                        "a headline figure")
            # The composite is untouched by any of it — the run still has one
            # and still prints it.
            assert "composite / 100" in pg.locator(".headline").inner_text()
        finally:
            browser.close()
