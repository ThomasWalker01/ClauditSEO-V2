"""The display cap must not decide which client-facing figures are caveated.

`ungrounded_figure_details` returns the first `FIGURES_TO_VERIFY_CAP` flagged
figures, and `run_expert` hands **that capped list** to
`record_expert_findings` (`clauditseo/analysts/expert.py:2328`), which sets
`figure_unverified` per finding by asking whether the finding's summary quotes
one of them. `generate.py:115-116` prints `ANALYST_FIGURE_NOTE` only when that
flag is true.

So the cap — a bound on how long a panel a person is asked to read — silently
decides which numbers reach a client marked as derived. A brief that flags
forty-five figures caveats the first forty and prints the last five into the
document as though they had been checked. That is CQ-08's remaining half,
carried since report 001; round 073 closed the other half by making the cap
declare its own count (`FIGURES_TO_VERIFY_CAP`, `figures_withheld`), which
landed on the screen the operator reads and not on the artefact that leaves
the building.

The cap stays. What changes is that the *judgement* is made against every
figure the extractor found, and only the *display list* is capped. These
guards assert that on the fresh path, on the cached replay, and in the
rendered client document — the three places the flag has to survive — with a
control that a grounded figure is still not marked, so the fix cannot be a
wall that caveats everything.
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
from clauditseo.reporting.generate import _expert_section, tool_runs_for
from clauditseo.reporting.render import ANALYST_FIGURE_NOTE
from tests.test_expert_tools import StubExpert

FAST = TierBudget(max_pages=30, request_timeout_s=5, wall_clock_s=30, delay_s=0)

#: Five past the cap, so there is a band of figures the cap drops and a band it
#: keeps, and the assertions can name a member of each. Five digits and no
#: separators for the reason `test_figure_cap_declares_what_it_withheld` records:
#: the extractor treats 1-10, HTTP status codes, dates, clock pairs and dotted
#: versions as vocabulary, so a smaller number would be dropped for a reason
#: that has nothing to do with the cap.
OVER = FIGURES_TO_VERIFY_CAP + 5

#: The first figure the cap drops, and the last one it keeps. Both are quoted in
#: a **finding summary**, which is the text `_expert_section` prints into the
#: client document; a figure in the prose alone never leaves the app.
# 700000 rather than 50000, and the reason is not cosmetic: see
# tests/test_a_figure_vocabulary_cannot_collide_with_a_fixture_port.py.
# The fixture server's ephemeral port reaches 65535, and a figure
# whose digits match it reads as grounded rather than withheld.
from clauditseo.checks import check_costs

FIRST_DROPPED = 700000 + FIGURES_TO_VERIFY_CAP + 1
LAST_KEPT = 700000 + FIGURES_TO_VERIFY_CAP

#: Distinct REAL check ids, one per figure.
#:
#: Synthetic `code-001 ... code-041` until Q-54, which taught the index
#: parser to drop a row naming a check the app does not have. Every row of
#: this fixture was such a row, so the whole report parsed to nothing and
#: four guards about figure capping failed for a reason that had nothing to
#: do with figures.
#:
#: Sorted so the mapping from n to id is stable between runs - an unstable
#: one would make `DROPPED_CODE` name a different check each time and the
#: assertions below chase it.
_REAL_CHECKS = sorted(c.split("/")[-1] for c in check_costs())


def _code(n: int) -> str:
    """The nth id. Distinct per n, which is all the fixture needs of it —
    `_merge_by_code` collapses a repeated code, and the cap could then
    never separate two rows."""
    return _REAL_CHECKS[n % len(_REAL_CHECKS)]


DROPPED_CODE = _code(FIGURES_TO_VERIFY_CAP + 1)
KEPT_CODE = _code(FIGURES_TO_VERIFY_CAP)


def _report(count: int) -> str:
    """One finding per figure, distinct codes, all in the index block.

    Distinct codes because `_merge_by_code` collapses a repeated code into one
    row — same-code findings would be joined into a single summary carrying
    every figure, and the cap could then never separate them, which would make
    the guard vacuous.

    The figures live in the summaries rather than the prose because
    `ungrounded_figure_details` scans summaries first and prose second, in
    document order. Prose figures cannot push a summary figure past the cap;
    only other summaries can. So a guard built from prose would assert against
    a defect the ordering rule already prevents.
    """
    rows = "\n".join(
        f"high | {_code(n)} | Organic sessions fell {700000 + n} percent "
        f"since the rebuild. |" for n in range(1, count + 1))
    return ("## CRAWL HEALTH SUMMARY\n\n"
            "The sitemap does not agree with what the crawl reached.\n\n"
            "```clauditseo-findings\n"
            "severity | code | summary | urls\n"
            f"{rows}\n"
            "```\n")


def _db(tmp_path, ev):
    conn = connect(tmp_path / "expert.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Expert Co")
    site_id = repo.create_site(conn, client, "fixture.local")
    run_id = runs.create_run(conn, site_id, ["TEC"], "T2")
    runs.store_evidence(conn, run_id, ev)
    return conn, run_id


#: A five-digit number the brief's own context carries verbatim, so the control
#: below quotes a genuinely *grounded* figure rather than one the extractor
#: happens to treat as vocabulary.
#:
#: It goes in a crawled URL, measured rather than assumed: the `local-signals`
#: host's context lists every crawled page with its title, H1 and word count, and no page body text
#: (the page table, `SITE_URL_OR_PAGE_LIST`). A number the
#: crawl reached as part of a URL is therefore grounded; one in the title or the
#: body is not. (It lived in `robots.txt` when this test was hosted on
#: `url-hygiene`, whose context echoed the robots body; item 141 retired that
#: brief, and its successor host echoes the crawled URL list rather than robots.
#: `llms-txt-builder` hosted it next, until item 145 retired that brief.)
GROUNDED = "83214"


@pytest.fixture
def brief_site(make_site):
    """One page, because the crawl is scaffolding here and not the subject.

    The figures under test come from the brief's prose and index, not from the
    site; all the fixture has to do is give `snapshot` a real crawl to describe
    so `run_expert` has evidence to ground numbers against — and carry
    `GROUNDED` where the context will see it.
    """
    head = ('<title>Fixture Home Page Title</title>'
            '<meta name="viewport" content="width=device-width">'
            '<link rel="canonical" href="/">')
    # `GROUNDED` lives in a crawled URL, which is what the local-signals host's
    # context echoes (its page table). Linked from the home page so the crawl
    # reaches it; the number then appears in the rendered context and a figure
    # quoting it is grounded rather than flagged.
    home = (f"<html><head>{head}</head><body><h1>Home</h1>"
            "<p>The crawl reached this page.</p>"
            f'<a href="/page-{GROUNDED}/">more</a>'
            "</body></html>")
    return make_site({
        "/robots.txt": (200, {"Content-Type": "text/plain"},
                        "User-agent: *\nAllow: /\n"),
        "/": (200, {}, home),
        f"/page-{GROUNDED}/": (200, {}, f"<html><head>{head}</head><body>"
                              "<h1>More</h1><p>Another reached page.</p></body></html>"),
    })


@pytest.fixture
def crawled(brief_site):
    """One crawl, reused by every clause here — `run_expert` needs evidence to
    ground figures against, and the crawl is scaffolding rather than subject."""
    return snapshot(crawl(brief_site.base_url + "/", Tier.T2, budget=FAST))


def _run(tmp_path, crawled, report, *, use_cache=True, conn=None, run_id=None):
    """The real production path, in the real order: record then store.

    Hosted on the legacy `local-signals` brief, not `crawl`: `_report` is the
    legacy pipe-index shape, and `crawl` (which superseded crawl-health) is a
    contract brief that reads a JSON block instead. The cap-and-caveat feature
    under test is generic; the legacy path it exercises is still live for the
    non-contract briefs. It moved off `url-hygiene` when item 141 retired that
    brief (replaced by the contract `urls`), and off `llms-txt-builder` when
    item 145 retired that one. This host's context lists the crawled URLs, which
    is where `GROUNDED` lives. It is a single call, which the declared-figure clauses need.
    """
    if conn is None:
        conn, run_id = _db(tmp_path, crawled)
    cfg = dataclasses.replace(Settings(), anthropic_api_key="")
    out = run_expert(conn, run_id, "local-signals", crawled,
                     Site(domain="fixture.local"), cfg, StubExpert(report),
                     use_cache=use_cache)
    assert out["status"] == "ok", out
    return conn, run_id, out


def _flags(conn, run_id) -> dict[str, bool]:
    """`check_id -> figure_unverified`, read from the stored evidence."""
    return {r["check_id"]: json.loads(r["evidence"] or "{}").get("figure_unverified")
            for r in conn.execute(
                "SELECT check_id, evidence FROM findings WHERE run_id=?"
                " AND dimension='EXP:local-signals'", (run_id,))}


def test_a_figure_the_cap_dropped_is_still_marked_unverified(tmp_path, crawled):
    """The stored judgement, which is what the renderer reads.

    Asserted on both bands at once so a fix that simply stopped capping would
    not pass: the display list must still hold exactly `FIGURES_TO_VERIFY_CAP`
    entries while the finding beyond it carries the flag.
    """
    conn, run_id, out = _run(tmp_path, crawled, _report(OVER), use_cache=False)
    try:
        shown = {f["value"] for f in out["figures_to_verify"]}
        assert len(out["figures_to_verify"]) == FIGURES_TO_VERIFY_CAP, (
            "the cap stopped capping; this guard is about which figures are "
            f"judged, not which are shown - got {len(out['figures_to_verify'])}")
        assert str(FIRST_DROPPED) not in shown, (
            f"{FIRST_DROPPED} is inside the display cap, so this clause is "
            "vacuous - the report fixture no longer overflows it")

        flags = _flags(conn, run_id)
        assert flags.get(KEPT_CODE) is True, (
            f"{KEPT_CODE} quotes {LAST_KEPT}, which the cap kept, and it is "
            f"not marked derived; got {flags.get(KEPT_CODE)!r}")
        assert flags.get(DROPPED_CODE) is True, (
            f"{DROPPED_CODE} quotes {FIRST_DROPPED}, which the analyst flagged "
            "as derived and the display cap dropped; the display bound decided "
            f"whether a client is warned. got {flags.get(DROPPED_CODE)!r}")
    finally:
        conn.close()


def test_the_dropped_figure_carries_its_caveat_into_the_client_document(
        tmp_path, crawled):
    """Rule 12's shape, applied to the artefact: the deliverable is what this
    finding is about, and a flag in the database that never renders is the
    half round 073 already closed on the other surface."""
    conn, run_id, _out = _run(tmp_path, crawled, _report(OVER), use_cache=False)
    try:
        site_id = conn.execute("SELECT site_id FROM audit_runs WHERE id=?",
                               (run_id,)).fetchone()["site_id"]
        section, _ = _expert_section(conn, tool_runs_for(conn, site_id), site_id, "client")
        line = next((ln for ln in section.splitlines()
                     if DROPPED_CODE in ln), None)
        assert line, "the finding beyond the cap did not reach the document"
        assert ANALYST_FIGURE_NOTE in line, (
            f"{FIRST_DROPPED} was printed to a client as though it had been "
            f"checked, because the display cap dropped it. Row: {line}")
    finally:
        conn.close()


def test_the_cached_replay_marks_what_the_fresh_run_marked(tmp_path, crawled):
    """A cache hit re-records the findings against the asking run
    (`expert.py:2220`), reading the payload rather than recomputing. So the
    payload has to carry the uncapped judgement or the caveat survives one run
    and not its replay — the shape `figures_withheld` was given its own clause
    for at round 073."""
    report = _report(OVER)
    conn, run_id, _first = _run(tmp_path, crawled, report)
    try:
        site_id = conn.execute("SELECT site_id FROM audit_runs WHERE id=?",
                               (run_id,)).fetchone()["site_id"]
        second_run = runs.create_run(conn, site_id, ["TEC"], "T2")
        runs.store_evidence(conn, second_run, crawled)
        _c, _r, out = _run(tmp_path, crawled, report, conn=conn,
                           run_id=second_run)
        assert out["cached"] is True, (
            "the second call did not replay from cache, so this clause did not "
            f"exercise the replay path; got {out.get('cached')!r}")

        flags = _flags(conn, second_run)
        assert flags.get(DROPPED_CODE) is True, (
            f"on the cached replay {DROPPED_CODE} lost the caveat the fresh "
            f"run gave it; got {flags.get(DROPPED_CODE)!r}")
    finally:
        conn.close()


#: A real check id for the grounded row. It read `grounded` until Q-54
#: taught the parser to drop rows naming checks the app does not have, and
#: the row this control depends on was one of them. `robots-missing` is the
#: check the summary is actually about.
GROUNDED_CODE = "robots-missing"

_GROUNDED_REPORT = f"""## CRAWL HEALTH SUMMARY

The sitemap does not agree with what the crawl reached.

```clauditseo-findings
severity | code | summary | urls
high | {GROUNDED_CODE} | the crawl reached /page-{GROUNDED}/ but robots.txt names no sitemap. |
```
"""


def test_a_grounded_figure_is_still_not_marked(tmp_path, crawled):
    """The control. Widening the judged set past the display cap must not
    become "mark everything": a number the crawl measured is not a number the
    analyst derived, and a caveat on every row teaches a client to skim the
    one marker that means something."""
    conn, run_id, _out = _run(tmp_path, crawled, _GROUNDED_REPORT,
                              use_cache=False)
    try:
        assert _flags(conn, run_id).get(GROUNDED_CODE) is False, (
            "a figure the crawl grounded was marked as derived; the judgement "
            "widened to every number rather than to every flagged one")
    finally:
        conn.close()
