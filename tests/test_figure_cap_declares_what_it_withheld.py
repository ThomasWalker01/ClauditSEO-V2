"""The figure cap says how many figures it withheld.

`ungrounded_figures` is uncapped and in document order; `ungrounded_figure_details`
then takes the first `FIGURES_TO_VERIFY_CAP` of them and throws the rest away
(`clauditseo/analysts/expert.py:2127,2151`). The cap itself is wanted - the panel
is a list a person reads, not a log - but it was **silent**: an operator shown
forty figures could not tell whether forty was all of them or the first forty of
fifty-five, and nothing stored against the run recorded the difference.

Silence is the defect, not the cap. These guards assert the product declares what
it withheld, in the envelope the panel reads, in the row the panel reads when the
brief is recalled, and on the cached replay - and three controls assert the
declaration stays zero when the cap did not bite, so the fix cannot be a wall.

The replay clauses re-judge rather than replay, which is `QUESTIONS.md` Q-2
answered `rewrite on re-judge` (operator, 2026-08-23) and CQ-162 closed with it:
the cache is keyed on the evidence bundle, so this path can ground a value again
as well as drop one, and `figures_still_derived` on the read path cannot.
"""

from __future__ import annotations

import dataclasses
import json

import pytest

from clauditseo.analysts.expert import FIGURES_TO_VERIFY_CAP, run_expert
from clauditseo.config import Settings
from clauditseo.crawler.crawl import crawl
from clauditseo.crawler.evidence import snapshot
from clauditseo.crawler.types import TierBudget
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.engine.types import Site, Tier
from clauditseo.persistence import repo, runs
from tests.test_expert_tools import StubExpert

FAST = TierBudget(max_pages=30, request_timeout_s=5, wall_clock_s=30, delay_s=0)


@pytest.fixture
def brief_site(make_site):
    """One page, because the crawl is scaffolding here and not the subject.

    The figures under test come from the brief's prose, not from the site; all
    the fixture has to do is give `snapshot` a real crawl to describe so that
    `run_expert` has evidence to ground numbers against.
    """
    head = ('<title>Fixture Home Page Title</title>'
            '<meta name="viewport" content="width=device-width">'
            '<link rel="canonical" href="/">')
    return make_site({
        "/robots.txt": (200, {"Content-Type": "text/plain"},
                        "User-agent: *\nAllow: /\n"),
        "/": (200, {}, f"<html><head>{head}</head><body><h1>Home</h1>"
                       "<p>The crawl reached this page.</p></body></html>"),
    })


#: Fifteen more than the cap, so the withheld count is a number the assertion
#: states rather than a boolean it infers. Five digits and no separators: the
#: extractor strips dates, times, clock pairs, WCAG references and dotted
#: versions, and treats 1-10 plus the HTTP status codes as vocabulary, so a
#: small or dotted number would be dropped for a reason that has nothing to do
#: with the cap.
OVER = FIGURES_TO_VERIFY_CAP + 15


def _report(count: int) -> str:
    lines = ["## CRAWL HEALTH SUMMARY", ""]
    # 700000, not 50000: the evidence these figures are grounded against
    # carries the fixture site's own URL, and `FixtureSite` binds port 0
    # (`tests/conftest.py:105`), so the OS hands it an ephemeral port —
    # 32768-60999 on Linux, 49152-65535 on Windows. `50001`-`50055` sat
    # inside that span, so whenever the port landed on one of them that
    # figure read as grounded, `withheld` fell by one and this module's
    # flagged total came out 54 instead of 55. That is KI-51's sixteenth
    # instance, on CI run 33437584252. Above 65535 no port can match.
    lines += [f"Metric {700000 + n} sessions were counted this period."
              for n in range(1, count + 1)]
    return "\n".join(lines)


def _db(tmp_path, ev):
    conn = connect(tmp_path / "expert.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Expert Co")
    site_id = repo.create_site(conn, client, "fixture.local")
    run_id = runs.create_run(conn, site_id, ["TEC"], "T2")
    runs.store_evidence(conn, run_id, ev)
    return conn, run_id


def _run(tmp_path, brief_site, report):
    ev = snapshot(crawl(brief_site.base_url + "/", Tier.T2, budget=FAST))
    conn, run_id = _db(tmp_path, ev)
    cfg = dataclasses.replace(Settings(), anthropic_api_key="")
    out = run_expert(conn, run_id, "crawl", ev, Site(domain="fixture.local"),
                     cfg, StubExpert(report), use_cache=False)
    assert out["status"] == "ok", out
    return conn, run_id, out


def test_the_cap_declares_how_many_figures_it_withheld(tmp_path, brief_site):
    """The count the operator cannot otherwise recover.

    Asserted against the envelope `run_expert` returns, which is what the panel
    renders for a brief that has just run. The list is still capped - that is
    the wanted behaviour - so the assertion is on both halves at once: forty
    shown, fifteen declared missing.
    """
    conn, _run_id, out = _run(tmp_path, brief_site, _report(OVER))
    try:
        assert len(out["figures_to_verify"]) == FIGURES_TO_VERIFY_CAP, (
            "the cap stopped capping; this guard is about what it says, not "
            f"whether it bites - got {len(out['figures_to_verify'])}")
        assert out["figures_withheld"] == OVER - FIGURES_TO_VERIFY_CAP, (
            "the cap withheld figures and did not say how many; "
            f"got {out.get('figures_withheld')!r}")
    finally:
        conn.close()


def test_a_brief_under_the_cap_withholds_nothing(tmp_path, brief_site):
    """The control that stops the declaration becoming a permanent warning.

    A brief with three figures has nothing withheld, and must say zero rather
    than a number that merely looks small. This fails if the fix declares a
    withholding whenever it counts figures at all.
    """
    conn, _run_id, out = _run(tmp_path, brief_site, _report(3))
    try:
        assert len(out["figures_to_verify"]) == 3, out["figures_to_verify"]
        assert out["figures_withheld"] == 0, (
            "a brief under the cap reported figures withheld; "
            f"got {out['figures_withheld']!r}")
    finally:
        conn.close()


def test_a_brief_exactly_at_the_cap_withholds_nothing(tmp_path, brief_site):
    """The boundary, because off-by-one here prints a false warning forever.

    Exactly `FIGURES_TO_VERIFY_CAP` figures are all shown, so nothing was
    withheld. A fix computing `total - CAP` without clamping, or comparing with
    `>=`, passes the two tests above and fails this one.
    """
    conn, _run_id, out = _run(tmp_path, brief_site,
                              _report(FIGURES_TO_VERIFY_CAP))
    try:
        assert len(out["figures_to_verify"]) == FIGURES_TO_VERIFY_CAP
        assert out["figures_withheld"] == 0, (
            "a brief exactly at the cap reported figures withheld; "
            f"got {out['figures_withheld']!r}")
    finally:
        conn.close()


def test_a_recalled_brief_still_says_what_the_cap_withheld(tmp_path, brief_site):
    """The half the envelope alone does not cover.

    `expert.tsx` renders the same panel from `runs.expert_report` when the
    operator reopens a stored brief, and that row is rebuilt column by column
    rather than replayed from the envelope. Without this the screen would say
    "15 withheld" on the run that produced it and nothing on the same brief an
    hour later - one screen, two answers, which is the state the fix must not
    ship.
    """
    conn, run_id, _out = _run(tmp_path, brief_site, _report(OVER))
    try:
        stored = runs.expert_report(conn, run_id, "crawl")
        assert stored is not None, "the brief was not stored against the run"
        assert len(stored["figures_to_verify"]) == FIGURES_TO_VERIFY_CAP
        assert stored["figures_withheld"] == OVER - FIGURES_TO_VERIFY_CAP, (
            "the recalled brief lost the count of what the cap withheld; "
            f"got {stored.get('figures_withheld')!r}")
    finally:
        conn.close()


def test_a_cached_replay_declares_the_same_withholding(tmp_path, brief_site):
    """A cache hit rebuilds the envelope from the stored payload.

    The cached branch returns `{**stored}` and never re-runs the extractor, so
    the count has to be in the payload the cache holds rather than computed
    beside it. Driven the way production does - two calls, `use_cache` left on -
    because that is the path that returns `cached: True`.
    """
    ev = snapshot(crawl(brief_site.base_url + "/", Tier.T2, budget=FAST))
    conn, run_id = _db(tmp_path, ev)
    cfg = dataclasses.replace(Settings(), anthropic_api_key="")
    try:
        first = run_expert(conn, run_id, "crawl", ev,
                           Site(domain="fixture.local"), cfg,
                           StubExpert(_report(OVER)))
        assert first["cached"] is False, first
        second = run_expert(conn, run_id, "crawl", ev,
                            Site(domain="fixture.local"), cfg,
                            StubExpert(_report(OVER)))
        assert second["cached"] is True, second
        assert second["figures_withheld"] == OVER - FIGURES_TO_VERIFY_CAP, (
            "the cached replay lost the count of what the cap withheld; "
            f"got {second.get('figures_withheld')!r}")
    finally:
        conn.close()


def test_a_legacy_replay_states_the_total_rather_than_replaying_silence(
        tmp_path, brief_site):
    """CQ-162, unblocked by `QUESTIONS.md` Q-2 - `rewrite on re-judge`.

    Thirty-eight of the forty-seven payloads in the operator's `analyst_cache`
    were written before `figures_withheld` existed. Replaying one used to take
    the list and the count out of the payload and rebuild the total from them,
    so the total equalled the shown length; the panel's sentence is gated on
    the total exceeding it, and an over-cap legacy brief replayed forty figures
    with no sign that fifteen were withheld. The number that would have said so
    was in hand one statement earlier, in the tuple `ungrounded_figure_details`
    already returns on this path, and was discarded.

    **What this test used to assert, and why it does not any more.** It was
    `test_a_replay_of_a_payload_written_before_the_count_stores_null`, and it
    pinned the replay of a legacy payload to a NULL `figures_withheld` -
    migration 0027's "never recorded" - on the ground that the replay had no
    honest way to know the count and a `0` would be "the reassuring answer that
    migration refuses to invent". That ground was right about a *default* and
    it is not right about a *measurement*: the cache is keyed on `bundle_hash`,
    the hash of this very evidence, so re-deriving here is the same call on the
    same inputs the fresh path makes. Whether the stored row may carry that
    re-judgement was not this guard's to decide, which is why it sat as an open
    question through reports 084-087; the operator answered it on 2026-08-23
    and the guard moved onto the measurement rather than being dropped.

    Driven by stripping the key from the stored payload rather than by ageing a
    fixture: the payload without the key *is* the legacy row, and the cache is
    keyed on the evidence bundle so the stripped row is the one the replay
    finds.
    """
    import json

    ev = snapshot(crawl(brief_site.base_url + "/", Tier.T2, budget=FAST))
    conn, run_id = _db(tmp_path, ev)
    cfg = dataclasses.replace(Settings(), anthropic_api_key="")
    try:
        first = run_expert(conn, run_id, "crawl", ev,
                           Site(domain="fixture.local"), cfg,
                           StubExpert(_report(OVER)))
        assert first["cached"] is False, first

        row = conn.execute("SELECT task, model_id, bundle_hash, result"
                           " FROM analyst_cache").fetchone()
        payload = json.loads(row["result"])
        assert payload.pop("figures_withheld", None) is not None, (
            "the fixture no longer models a legacy payload: the live path "
            "stopped putting the count in the cached payload, so stripping it "
            "proves nothing")
        payload.pop("figures_flagged", None)
        with conn:
            conn.execute("UPDATE analyst_cache SET result=? WHERE task=? AND"
                         " model_id=? AND bundle_hash=?",
                         (json.dumps(payload), row["task"], row["model_id"],
                          row["bundle_hash"]))

        second = run_expert(conn, run_id, "crawl", ev,
                            Site(domain="fixture.local"), cfg,
                            StubExpert(_report(OVER)))
        assert second["cached"] is True, second
        assert second.get("figures_withheld") == OVER - FIGURES_TO_VERIFY_CAP, (
            "a replay of a payload that never carried the count replayed "
            "silence instead of re-judging what it has the evidence to "
            f"re-judge; got {second.get('figures_withheld')!r}")
        assert second.get("figures_flagged") == OVER, (
            "the replayed panel states a total equal to its own shown length, "
            "so the sentence that would say figures were withheld cannot "
            f"draw; got {second.get('figures_flagged')!r}")
        assert (len(second["figures_to_verify"]) + second["figures_withheld"]
                == second["figures_flagged"]), (
            "the three numbers the panel's one sentence is built from did not "
            "come from one pass, which is the whole of UX-79 recurring on the "
            f"replay: {len(second['figures_to_verify'])} + "
            f"{second['figures_withheld']} != {second['figures_flagged']}")

        stored = conn.execute(
            "SELECT figures_withheld FROM expert_reports WHERE run_id=? AND"
            " tool_id=?", (run_id, "crawl")).fetchone()
        assert stored["figures_withheld"] == OVER - FIGURES_TO_VERIFY_CAP, (
            "the row the panel is rebuilt from when the brief is reopened did "
            "not keep what the replay measured, so the count survives the "
            "envelope and not the recall; the column reads "
            f"{stored['figures_withheld']!r}")
    finally:
        conn.close()


def test_a_legacy_replay_under_the_cap_measures_zero_rather_than_fifteen(
        tmp_path, brief_site):
    """The control that stops the fix above being a constant.

    A legacy payload whose brief flagged three figures withheld nothing, and
    the replay must say `0` - measured, from the same re-derivation - rather
    than a number carried over from the over-cap case or a NULL that says
    nothing. A fix that writes the withheld count from anywhere but this
    payload's own prose passes the guard above and fails here.
    """
    import json

    ev = snapshot(crawl(brief_site.base_url + "/", Tier.T2, budget=FAST))
    conn, run_id = _db(tmp_path, ev)
    cfg = dataclasses.replace(Settings(), anthropic_api_key="")
    try:
        first = run_expert(conn, run_id, "crawl", ev,
                           Site(domain="fixture.local"), cfg,
                           StubExpert(_report(3)))
        assert first["cached"] is False, first

        row = conn.execute("SELECT task, model_id, bundle_hash, result"
                           " FROM analyst_cache").fetchone()
        payload = json.loads(row["result"])
        payload.pop("figures_withheld", None)
        payload.pop("figures_flagged", None)
        with conn:
            conn.execute("UPDATE analyst_cache SET result=? WHERE task=? AND"
                         " model_id=? AND bundle_hash=?",
                         (json.dumps(payload), row["task"], row["model_id"],
                          row["bundle_hash"]))

        second = run_expert(conn, run_id, "crawl", ev,
                            Site(domain="fixture.local"), cfg,
                            StubExpert(_report(3)))
        assert second["cached"] is True, second
        assert len(second["figures_to_verify"]) == 3, second["figures_to_verify"]
        assert second.get("figures_withheld") == 0, (
            "a legacy replay of an under-cap brief did not measure its own "
            f"withholding; got {second.get('figures_withheld')!r}")
        assert second.get("figures_flagged") == 3, (
            "the total on an under-cap replay is not the three figures the "
            f"brief flagged; got {second.get('figures_flagged')!r}")
    finally:
        conn.close()


def test_a_recalled_brief_states_the_total_it_was_drawn_from(tmp_path,
                                                             brief_site):
    """UX-79: the shown count and the withheld count are computed differently.

    `expert_report` re-judges the stored list through `figures_still_derived`
    on the way out and serves `figures_withheld` — a count `run_expert`
    computed at run time as `len(found) - len(declared)` — beside it
    unchanged. So the panel's one sentence states two numbers under two rules:
    `shown + withheld` no longer equals what the brief flagged, and the shown
    list is a filtered subset rather than the first N of anything.

    Reproduced the way the corpus already holds it rather than by inventing a
    shape: measured read-only at report 084, 28 of 189 stored values across 38
    briefs are values today's rule would not produce. One stored value is
    rewritten to a number the prose does not contain, which is exactly that
    state — the row is the operator's history and predates the rule.

    `figures_flagged` is the fix's key and it is *derived, never stored*, on
    the precedent `expert.py`'s cache branch already records for
    `replay_underived`: a stored key would leave every row written before it
    replaying the defect, and this one can be rebuilt from the two columns
    that are already there.
    """
    conn, run_id, _out = _run(tmp_path, brief_site, _report(OVER))
    try:
        row = conn.execute(
            "SELECT figures FROM expert_reports WHERE run_id=? AND tool_id=?",
            (run_id, "crawl")).fetchone()
        stored_figures = json.loads(row["figures"])
        assert len(stored_figures) == FIGURES_TO_VERIFY_CAP, stored_figures
        # A value the prose never carried, so today's rule cannot re-derive it.
        # Seven digits: outside the vocabulary the extractor treats as
        # non-numeric, and not one of the `700001…` values `_report` writes.
        stored_figures[0] = dict(stored_figures[0], value="9876543")
        with conn:
            conn.execute(
                "UPDATE expert_reports SET figures=? WHERE run_id=? AND"
                " tool_id=?",
                (json.dumps(stored_figures), run_id, "crawl"))

        served = runs.expert_report(conn, run_id, "crawl")
        assert served is not None, "the brief was not stored against the run"
        shown = len(served["figures_to_verify"])
        assert shown == FIGURES_TO_VERIFY_CAP - 1, (
            "the re-judge did not drop the value the prose no longer carries, "
            f"so this guard is not exercising UX-79; shown {shown}")

        assert "figures_flagged" in served, (
            "the recalled brief serves a shown list and a withheld count "
            "computed under different rules and nothing saying what they were "
            "drawn from; the panel's sentence cannot be honest without it")
        assert served["figures_flagged"] == OVER, (
            "the flagged total is not what the brief flagged: expected "
            f"{OVER} (stored {FIGURES_TO_VERIFY_CAP} + withheld "
            f"{OVER - FIGURES_TO_VERIFY_CAP}), got "
            f"{served['figures_flagged']!r}")
        assert shown < served["figures_flagged"], (
            "the sentence would claim the whole flagged set is on screen")
        # The old sentence's arithmetic, stated so the regression is named:
        # shown + withheld is what the panel used to add up, and it is short
        # of the flagged total by every value the re-judge dropped.
        assert shown + served["figures_withheld"] != served["figures_flagged"], (
            "this guard assumes the re-judge dropped something; if the two "
            "sums agree there is nothing here for it to catch")
    finally:
        conn.close()
