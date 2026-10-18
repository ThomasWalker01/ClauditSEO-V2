"""WF-59: the section refresh control starts what it says it starts.

The finding, first raised in report 051 and carried through report 099: the
Headings section offers "Refresh this section", describes it as "the smallest
run that covers Headings", and issues
`POST /api/sites/{id}/audits {"dims":["ONP"],"tier":"auto"}`. Three separate
claims are hidden in that request. `tier: "auto"` dispatches to `run_adaptive`,
which chooses its own tier up to T3; the run ends at `complete_run` with
`kind='audit'`, so it writes a score onto the site's history; and
`analyst_enabled=body.analyst or body.tier == "auto"` turned the analyst layer
on **regardless of what the caller asked for**, so the press spent model
tokens. The dimension was genuinely scoped. The depth and the spend were not.

**Q-18, answered by the operator on 2026-08-25**: keep `auto` and send
`analyst: false`, and correct the words in the same fix - the press stops
spending model tokens, breadth stays adaptive, and the control says what it
actually starts before the confirm. Both halves are guarded here.

The server half is the one that could not be asked for at all before this.
`analyst` was `bool = False` read through an `or`, so `false` and "unset" were
indistinguishable and no caller could request a bounded adaptive run. It is
now tri-state: `None` means "let the tier decide", which is what every caller
that says nothing has always meant, and an explicit `false` declines.

The screen half is asserted against `dashboard/src/anatomy.tsx` **with its
comments stripped**, which is not fussiness - this file's subject is a
sentence, the fix's own comments quote the sentence, and an assertion that a
comment can satisfy is DISCIPLINE rule 5's defect exactly. What the rendered
text says to a browser is `tests/test_section_refresh.py`'s job; that file
needs a built bundle and this one deliberately does not, so the rule holds in
the `python` gate as well as in `rendered-a11y`.
"""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import clauditseo.api.app as app_mod
from clauditseo import axe
import clauditseo.modules  # noqa: F401
from clauditseo.adaptive import run_adaptive
from clauditseo.analysts.mock import MockAnalyst
from clauditseo.api.app import create_app
from clauditseo.config import Settings
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.engine.types import Site
from clauditseo.persistence import repo, runs
from tests.conftest import FixtureSite
from tests.test_a11y_rendered import DIST, served  # noqa: F401  (reused fixture)
from tests.test_adaptive import FAST, _routes  # noqa: F401  (reused fixture site)


ANATOMY = Path("dashboard/src/anatomy.tsx")

#: Two patterns, deliberately, and this is the one detail in this file worth
#: reading twice. The obvious spelling is a single alternation compiled with
#: `re.S | re.M`, and it is wrong: `re.S` applies to the whole pattern, so the
#: `.` in the line-comment branch matches newlines too and that branch eats
#: everything from the first `//` to the end of the file. Measured on
#: `anatomy.tsx`: 122,420 bytes in, 4,757 out. A negative assertion over a
#: source file stripped that way cannot fail, which is DISCIPLINE rule 5 in
#: its purest form - the check's evidence was deleted before the check read
#: it, and the guard below went green against unfixed source because of it.
#:
#: `[ \t]` rather than `\s` for the same reason at smaller scale: `\s` matches
#: a newline, so the branch could start from the blank line above the comment.
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_LINE_COMMENT = re.compile(r"^[ \t]*//.*$", re.M)


def _strip_comments(source: str) -> str:
    """Source with its comments removed, so a claim about what a screen SAYS
    cannot be satisfied by a comment about what it used to say."""
    return _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", source))


# --- the server: an adaptive run that may be asked for without analysts ------

@pytest.fixture
def launcher(tmp_path, monkeypatch):
    """A site, a client, and the launch route with its worker intercepted.

    The worker is stubbed rather than allowed to run: this file's question is
    what `launch_audit` DECIDES, and letting the thread through would crawl a
    real domain to answer a question about one boolean. What the decision is
    handed to the worker as is captured too, because the recorded flag and the
    run's actual behaviour are two different facts and the defect was that
    they came from two different expressions.
    """
    db = tmp_path / "wf59.db"
    conn = connect(db)
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Refresh Co")
    site_id = repo.create_site(conn, client, "refresh.fixture")

    handed: list[tuple] = []
    monkeypatch.setattr(app_mod, "_execute_run",
                        lambda *args, **kwargs: handed.append(args))
    api = TestClient(create_app(db_path=db))
    api.db_path = db          # read by `_launch`, below
    yield conn, api, site_id, handed
    conn.close()


def _launch(api, site_id: str, body: dict) -> str:
    # One audit at a time per site is the route's rule since the second audit
    # of 2026-09-02 (F-03): a second launch while one is in flight is a 409.
    # The worker here is stubbed, so every launched run stays `running`
    # forever; each launch settles the previous one first, because this
    # file's question is what the route DECIDES about the analyst layer, not
    # whether it refuses a duplicate - that has its own test.
    c = connect(api.db_path)
    with c:
        c.execute("UPDATE audit_runs SET status='cancelled'"
                  " WHERE site_id=? AND status IN ('pending','running')", (site_id,))
    c.close()
    resp = api.post(f"/api/sites/{site_id}/audits", json=body)
    assert resp.status_code == 202, resp.text
    return resp.json()["run_id"]


def test_an_adaptive_run_can_be_asked_for_without_analysts(launcher):
    """The half of Q-18 that is a capability rather than a wording change.

    `analyst: false` beside `tier: "auto"` used to be unsayable - the server
    read it through `body.analyst or body.tier == "auto"`, so the layer came
    on anyway and the caller had no way to know it had been overruled.
    """
    conn, api, site_id, handed = launcher
    run_id = _launch(api, site_id, {"dims": ["ONP"], "tier": "auto",
                                    "analyst": False})

    row = conn.execute("SELECT analyst_enabled FROM audit_runs WHERE id=?",
                       (run_id,)).fetchone()
    assert not row["analyst_enabled"], (
        "the run records itself as analyst-enabled after the caller declined")
    # And the worker was handed the same answer the row claims. Asserted
    # rather than assumed: the defect was two expressions for one question.
    assert handed and handed[0][5] is False, (
        f"the worker was started with a different answer: {handed!r}")


def test_saying_nothing_still_means_the_tier_decides(launcher):
    """The must-not-change direction, and the reason `analyst` is tri-state
    rather than defaulted to False.

    A caller that sends no `analyst` key at all - a scheduled pass, the CLI -
    has always meant "whatever this tier normally does". Reading an absent key
    as `false` would have turned the analysts off for every adaptive run in
    the product, which is a far larger change than the one asked for and one
    nothing on screen would announce.

    **This test used to name the launcher screen in that list, and it was
    wrong** - that is CQ-226, and it is why the clause at the end of this file
    exists. `dashboard/src/views.tsx` posts `analyst` on every press, so the
    body below was never the body the product's main caller sends, and this
    test went green for a year of rounds while WF-102 stood. The bodies here
    are still the right ones for the question this test asks; what was wrong
    was the claim about who sends them, so the claim is corrected rather than
    the bodies.
    """
    conn, api, site_id, _handed = launcher

    auto = _launch(api, site_id, {"dims": ["ONP"], "tier": "auto"})
    manual = _launch(api, site_id, {"dims": ["ONP"], "tier": "T2"})
    asked = _launch(api, site_id, {"dims": ["ONP"], "tier": "T2",
                                   "analyst": True})

    enabled = {r["id"]: r["analyst_enabled"] for r in conn.execute(
        "SELECT id, analyst_enabled FROM audit_runs").fetchall()}
    assert enabled[auto], "an adaptive run that was asked nothing lost its analysts"
    assert not enabled[manual], "a manual tier gained analysts it never asked for"
    assert enabled[asked], "a manual tier that asked for analysts did not get them"


def test_run_adaptive_declines_the_analysts_when_the_caller_does(tmp_path,
                                                                 monkeypatch):
    """End to end on the fixture `test_adaptive.py` engineered for this: CNT
    lands in CONCERN, which is the band that buys an analyst task.

    That test runs the same site with the analysts on and asserts
    `{"cnt-j", "pri-j"}` come back, so this one's zero is a measured
    difference rather than a fixture that could never have produced any. The
    escalation still happens, the deeper crawl still happens, and the bands
    are still recorded - declining the analysts must not quietly narrow the
    run to its pulse.
    """
    for var in ("CLAUDITSEO_BAND_HEALTHY", "CLAUDITSEO_BAND_WATCH",
                "CLAUDITSEO_BAND_CONCERN"):
        monkeypatch.delenv(var, raising=False)
    conn = connect(tmp_path / "declined.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Declined Co")
    site_id = repo.create_site(conn, client, "adaptive.fixture")
    run_id = runs.create_run(conn, site_id, ["TEC", "ONP", "CNT"], "T1",
                             analyst_enabled=False)
    cfg = dataclasses.replace(Settings(), anthropic_api_key="")
    server = FixtureSite(_routes()).start()
    notes: list[str] = []
    try:
        _result, esc = run_adaptive(conn, run_id, Site(domain="adaptive.fixture"),
                                    site_id, server.base_url + "/", cfg,
                                    ["TEC", "ONP", "CNT"], analyst=False,
                                    announce=notes.append,
                                    provider=MockAnalyst(), budgets=FAST)
    finally:
        server.stop()

    stored = runs.get_run(conn, run_id)
    assert not [f for f in stored["findings"] if f["source"] == "model-judgement"], (
        "a run that asked for no analyst came back with model judgements")

    # Breadth is untouched: the band still escalated and the deeper crawl
    # still ran. This is the clause that separates "declined the analysts"
    # from "ran a cheaper, different audit".
    assert esc["CNT"].band.name == "CONCERN"
    assert stored["tier"] == "T2", stored["tier"]
    assert any(label.startswith("Escalated crawl (T2)")
               for label in [s["label"] for s in stored["progress"]])

    # Said out loud. "No task escalated" and "a task escalated and was
    # declined" are different facts about this run, and the findings show
    # neither, so the progress log is the only place the difference can be
    # read at all.
    declined = [n for n in notes if "asked for no analyst" in n]
    assert declined, f"the declined analyst tasks were dropped silently: {notes!r}"
    assert "CNT" in declined[0].upper(), declined[0]
    conn.close()


# --- the screen: what the control asks for, and what it says it asks for ----

def _section_refresh_source() -> str:
    """`SectionRefresh`'s body with every comment removed.

    Comments are stripped because this fix's own comments quote the sentence
    under test - an assertion a comment can satisfy is a check whose evidence
    cannot disagree with it (DISCIPLINE rule 5), which is the defect this
    repository has shipped most often.

    Sliced to the one component rather than searched for across the file, so
    a matching string in `PageRefresh` below cannot answer a question about
    this control.
    """
    src = ANATOMY.read_text(encoding="utf-8")
    start = src.index("function SectionRefresh(")
    end = src.index("\nfunction ", start + 1)
    return _strip_comments(src[start:end])


def test_the_section_refresh_asks_for_no_analyst():
    """The request, read from the source that builds it.

    `tier: "auto"` stays - the operator's answer keeps the breadth adaptive -
    so this is not "the tier changed", it is "the spend was declined
    alongside it". Both are asserted, because dropping `auto` would satisfy
    the spend clause while silently answering a question the operator decided
    the other way.
    """
    body = _section_refresh_source()
    assert 'tier: "auto"' in body, (
        "the control no longer starts an adaptive run; Q-18 kept `auto`")
    assert re.search(r"analyst:\s*false", body), (
        "the control starts an adaptive run without declining the analysts, "
        "so the press spends model tokens (WF-59)")


def test_the_control_carries_no_spend_mark():
    """F-10 clause 2, applied to the control the fix changed.

    `SpendMark`'s own words are "This spends model tokens". The request names
    no analyst and the server starts none, so a mark here would now fire on
    every press for a run that provably invokes no model - the check that
    fires every time. It was right while the run enabled the analysts; it
    went with them.
    """
    body = _section_refresh_source()
    assert "SpendMark" not in body, (
        "a refresh that invokes no model marks itself as spending tokens")


def test_the_confirmation_names_the_depth_it_commits_to():
    """The wording half of Q-18.

    What was missing was never the dimension or the four sections that move
    with it - the confirmation named both, and ruled out page scope besides.
    It was DEPTH: the term that decides what a press costs, on a control
    whose label is "refresh" and whose text said "the smallest run". Each
    clause is asserted for its own reason rather than as one blob, so a
    rewrite that drops one of the three fails on that one.
    """
    body = _section_refresh_source()
    assert "T3" in body, (
        "the confirmation does not say how deep the run may go, which is the "
        "term that decides what a press costs")
    assert re.search(r"no analyst|No model", body), (
        "the confirmation does not say the run invokes no model")
    assert re.search(r"records a score|writes a score", body), (
        "the confirmation does not say the run writes a point on the site's "
        "score history")


def test_this_control_does_not_call_its_run_the_smallest_run():
    """The sentence itself. "Smallest dimension" is the true version of the
    claim and stays allowed - ONP really is the smallest dimension that
    covers Headings. What cannot be said is that the RUN is the smallest,
    when its depth is chosen by the engine and may reach T3.

    **Scoped to this control, and the first draft was not.** Written the way
    `test_no_screen_promises_an_audit_of_one_page` is written - forbidden
    across all 21 screens, on the argument that the phrasing is the kind that
    gets copied - it went red on `PageRefresh` forty lines below, whose title
    reads "the smallest run that covers Headings". That sentence is TRUE
    there: a page refresh is one page, one dimension, a fixed tier, no
    analyst and no score, which is the smallest run this engine can be asked
    for and the reason F-06 built it. A ban that flags a correct sentence is
    not a stricter guard, it is a wrong one, so the rule is scoped to the
    control whose run is adaptive. The two files differ on this deliberately:
    "an audit of one page" names a thing the product cannot do anywhere, and
    "the smallest run" names a thing one control can do and another cannot.
    """
    body = _section_refresh_source()
    assert not re.search(r"smallest run", body, re.I), (
        "the section control calls its run the smallest one when the depth "
        "is chosen by the engine and may reach T3")
    # And the true claim is still made, so this is a correction rather than a
    # deletion: a control that said nothing about scope would pass the line
    # above and be worse than the one that overclaimed.
    assert re.search(r"smallest\s+dimension", body), (
        "the control no longer says what it IS the smallest of")


# --- WF-102: the launcher's own body, read off the browser that sends it -----
#
# CQ-226 is why this clause exists rather than another dict. The guard above
# asserts the tri-state over `{"dims": ["ONP"], "tier": "auto"}` — a body with
# no `analyst` key — and its docstring asserted, as the reason that body was
# the right one, that "every existing caller ... sends no `analyst` key at
# all". The launcher screen does send one. `dashboard/src/views.tsx` posts
# `analyst` unconditionally from a `useState(false)` that the auto tier never
# renders a control for, so every default press said `analyst: false`, which
# the tri-state honours exactly as asked and the layer stayed off. The guard
# passed throughout, because the body it was written from was not the body the
# product sends.
#
# So this one does not write a body. It presses the button and reads what the
# browser actually put on the wire, then posts that same captured body through
# the real route. A hand-written dict cannot re-open the gap, because there is
# no hand-written dict left to drift.

def live(fn):
    fn = pytest.mark.skipif(
        not (DIST / "index.html").is_file(),
        reason="dashboard not built (npm run build in dashboard/)")(fn)
    return pytest.mark.skipif(
        not axe.available(),
        reason="needs clauditseo[render] and `playwright install chromium`")(fn)


@live
def test_the_body_the_launcher_actually_posts_still_lets_the_tier_decide(
        served, launcher):  # noqa: F811
    """WF-102, measured on the wire rather than read off the source.

    Two halves, and both are needed. The browser half says what the screen
    sends when an operator presses Run audit with the screen exactly as it
    loads — `tier` at its `useState("auto")` default and no analyst control
    rendered at all, which is the case the finding is about. The server half
    posts that captured body, unedited, at the real route and reads
    `analyst_enabled` off the row.

    The launch is intercepted, so nothing crawls: the browser never reaches a
    real route, and the replay's worker is the `launcher` fixture's stub.
    """
    from playwright.sync_api import sync_playwright

    base, ids = served
    sent: list[str] = []

    def capture(route):
        sent.append(route.request.post_data or "")
        route.fulfill(status=202, content_type="application/json",
                      body='{"run_id": "intercepted", "status": "running"}')

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        try:
            page.route("**/api/sites/*/audits", capture)
            page.goto(f"{base}/#/sites/{ids['site']}/launch",
                      wait_until="domcontentloaded")
            # One dimension, because the button is disabled on an empty set.
            # Which one is irrelevant to the question; that something is
            # ticked is not.
            dim = page.locator("label:has(code.dim-code) input[type=checkbox]")
            dim.first.wait_for(timeout=15000)
            dim.first.check()
            # Nothing else is touched. The tier picker keeps its default and
            # the analyst layer renders no control at all on `auto`, which is
            # exactly the state every default press is made from.
            tier_now = page.evaluate(
                """() => {
                    const t = [...document.querySelectorAll(
                        'input[type=radio]:checked, input[type=checkbox]:checked')]
                        .map((e) => e.closest('label')?.textContent ?? '');
                    return t.join(' | ');
                }""")
            page.get_by_role("button", name="Run audit").click()
            page.wait_for_timeout(1500)
        finally:
            browser.close()

    assert sent, (
        "the launcher never posted — the press did not reach the route, so "
        f"this test measured nothing. Checked controls were: {tier_now!r}")
    body = json.loads(sent[0])

    # The premise, before the claim. A screen that had somehow left `auto` is
    # a screen this test is not about, and it would pass the assertion below
    # for the wrong reason.
    assert body.get("tier") == "auto", (
        f"the launcher was not on its default tier: {body!r}")

    # The finding itself. `false` is a caller's answer under the tri-state, so
    # a screen that renders no analyst control must not send one.
    assert body.get("analyst") is not False, (
        "the launcher posts `analyst: false` on a tier whose analyst control "
        f"it never renders, so every default press declines the layer: {body!r}")

    # And the consequence, at the route rather than in the reading of it.
    conn, api, site_id, handed = launcher
    run_id = _launch(api, site_id, body)
    row = conn.execute("SELECT analyst_enabled FROM audit_runs WHERE id=?",
                       (run_id,)).fetchone()
    assert row["analyst_enabled"], (
        "the body the launcher posts starts an adaptive run with no analyst "
        f"layer, while the screen marks the press as spending: {body!r}")
    assert handed and handed[0][5] is True, (
        f"the worker was started with a different answer: {handed!r}")
