"""Gate G7: (1) a generated report contains no number lacking a source tag;
(2) every number in analyst-written narrative exists verbatim in the
evidence bundle. Both are automated checks that run on every generation."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import clauditseo.modules  # noqa: F401
from clauditseo.analysts.layer import run_analyst_layer
from clauditseo.analysts.mock import MockAnalyst
from clauditseo.config import Settings
from clauditseo.crawler.crawl import crawl
from clauditseo.crawler.types import TierBudget
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.engine.core import run_audit
from clauditseo.engine.types import Site, Tier
from clauditseo.persistence import repo, runs
from clauditseo.reporting import generate as gen
from clauditseo.reporting.checks import (ReportCheckError, ungrounded_narrative_numbers,
                                        unsourced_number_lines)
from tests.conftest import FixtureSite
from tests.test_history_g4 import BROKEN_PROMO, GOOD_PROMO, _routes

FAST = TierBudget(max_pages=20, request_timeout_s=5, wall_clock_s=30, delay_s=0)
DIMS = ["TEC", "ONP", "PRF", "OFP"]  # PRF/OFP add not-assessed findings keyless


@pytest.fixture
def db_with_runs(tmp_path):
    conn = connect(tmp_path / "g7.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Report Co")
    site_id = repo.create_site(conn, client, "report.fixture")

    run_ids = []
    for promo in (BROKEN_PROMO, GOOD_PROMO):
        server = FixtureSite(_routes(promo)).start()
        try:
            crawl_result = crawl(server.base_url + "/", Tier.T2, budget=FAST)
        finally:
            server.stop()
        result = run_audit(Site(domain="report.fixture"), crawl_result, DIMS, Tier.T2)
        run_id = runs.create_run(conn, site_id, DIMS, "T2", analyst_enabled=True)
        # As the API does on every audit — without it the run has no recorded
        # scope and the report cannot state what the crawl reached.
        from clauditseo.crawler.evidence import snapshot
        runs.store_evidence(conn, run_id, snapshot(crawl_result))
        outcome = run_analyst_layer(conn, run_id, "report.fixture", result, crawl_result,
                                    Settings(), provider=MockAnalyst())
        result.findings.extend(outcome.security_findings)
        result.findings.extend(outcome.findings)
        runs.complete_run(conn, run_id, result)
        run_ids.append(run_id)
    yield conn, run_ids
    conn.close()


@pytest.mark.parametrize("audience", ["client", "internal"])
def test_run_report_passes_both_checks(db_with_runs, audience):
    conn, run_ids = db_with_runs
    report = gen.generate(conn, "run", audience, [run_ids[0]])
    md = report["markdown"]
    assert unsourced_number_lines(md) == []
    assert "[TO CONFIRM:" in md            # keyless CWV/backlinks render honestly
    assert "Analyst insights" in md
    assert "never enter the score" in md
    assert "Prepared" in md                # DD Month YYYY prose date
    if audience == "internal":
        assert "fingerprint" in md
    else:
        assert "fingerprint" not in md


def test_comparison_and_trend_reports_pass_checks(db_with_runs):
    conn, run_ids = db_with_runs
    comparison = gen.generate(conn, "comparison", "internal", run_ids)
    assert unsourced_number_lines(comparison["markdown"]) == []
    assert "Resolved issues" in comparison["markdown"]
    assert "title-missing" in comparison["markdown"]

    trend = gen.generate(conn, "monthly-trend", "client", [run_ids[1]])
    assert unsourced_number_lines(trend["markdown"]) == []
    assert "ISO 8601" in trend["markdown"]


def test_reports_are_persisted(db_with_runs):
    conn, run_ids = db_with_runs
    report = gen.generate(conn, "run", "client", [run_ids[0]])
    row = conn.execute("SELECT * FROM reports WHERE id=?", (report["id"],)).fetchone()
    assert row["template"] == "run"
    assert row["audience"] == "client"
    from pathlib import Path
    assert Path(report["path"]).exists()


def test_unsourced_numbers_are_flagged():
    bad = "# Report\n\nComposite score: 91.9 out of 100.\n"
    flagged = unsourced_number_lines(bad)
    assert flagged and "91.9" in flagged[0]
    good = "Composite: 91.9 (source: engine, confidence: high)"
    assert unsourced_number_lines(good) == []
    exempt = "Prepared 6 August 2026 · run `fd9be548d163` · engine v0.1.0 at 06:15"
    assert unsourced_number_lines(exempt) == []


def test_a_source_tag_is_a_tag_not_a_substring():
    """CQ-55, and demonstrated failure class 3 — a verification gate defeated
    by weak matching.

    The tag test asked `"source:" not in line.lower()` against the **raw**
    line, while the number test ran against `stripped`, the same line with the
    identity spans removed. Two consequences, one root: "source:" is a
    substring of ordinary English ("Resource:", "Open-source:"), and a tag
    found inside a span the checker has already agreed is not a metric counts
    as though it sourced the metric beside it.

    Both shapes below are lines a model can write into a client deliverable
    with a number nothing grounds. The first was reproduced against the
    unfixed function on 19 August 2026: `unsourced_number_lines("Resource: 12
    pages were affected.")` returned `[]`.
    """
    # A tag inside a word is not a tag.
    assert unsourced_number_lines("Resource: 12 pages were affected.") ==         ["Resource: 12 pages were affected."]
    assert unsourced_number_lines("Open-source: 40 of them.") ==         ["Open-source: 40 of them."]
    # A tag inside a span the exemptions have already discounted is not a tag
    # for the rest of the line either.
    assert unsourced_number_lines("See `/open-source:-guide` and 42 pages affected.") ==         ["See `/open-source:-guide` and 42 pages affected."]
    # …and a real tag still reads as one, wherever it sits on the line.
    assert unsourced_number_lines("Composite: 91.9 (source: engine, confidence: high)") == []
    assert unsourced_number_lines("Source: engine. 91.9 composite.") == []


def test_numbers_are_grounded_as_tokens_not_substrings():
    # "43" must NOT be grounded by "1043" hiding in a count or hash.
    assert ungrounded_narrative_numbers("Growth of 43 percent.",
                                        "total_pages: 1043") == ["43"]
    assert ungrounded_narrative_numbers("All 1043 pages audited.",
                                        "total_pages: 1043") == []
    # Thousands separators and trailing decimal zeros normalise.
    assert ungrounded_narrative_numbers("All 1,043 pages audited.",
                                        "total_pages: 1043") == []
    assert ungrounded_narrative_numbers("Score of 75.0 recorded.",
                                        '"score": 75') == []


def test_invented_narrative_numbers_are_flagged_and_block_generation(db_with_runs, monkeypatch):
    conn, run_ids = db_with_runs
    assert ungrounded_narrative_numbers(
        "Expect a 4317 percent lift.", "evidence without that figure") == ["4317"]

    from clauditseo.reporting import render
    original = render.render_run_report

    # Passes everything through, so the double keeps matching the real
    # signature as it grows rather than pinning it to today's arguments.
    def doctored(*args, **kwargs):
        md, _ = original(*args, **kwargs)
        return md, "Traffic will grow 4317 percent."
    monkeypatch.setattr(gen, "render_run_report", doctored)
    with pytest.raises(ReportCheckError, match="4317"):
        gen.generate(conn, "run", "client", [run_ids[0]])


# --- the headline carries the breadth it rests on ---------------------------

@pytest.fixture
def db_with_a_partial_crawl(tmp_path):
    """Two runs whose sitemap declares far more than the crawl fetched — the
    shape of the real audit that prompted this: 6 pages of 272."""
    from clauditseo.crawler.evidence import snapshot

    conn = connect(tmp_path / "partial.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Partial Co")
    site_id = repo.create_site(conn, client, "partial.fixture")

    run_ids = []
    for promo in (BROKEN_PROMO, GOOD_PROMO):
        server = FixtureSite(_routes(promo)).start()
        try:
            crawled = crawl(server.base_url + "/", Tier.T2, budget=FAST)
        finally:
            server.stop()
        result = run_audit(Site(domain="partial.fixture"), crawled, DIMS, Tier.T2)
        run_id = runs.create_run(conn, site_id, DIMS, "T2")
        evidence = snapshot(crawled)
        # The site declares 272 URLs; the crawl reached a handful of them.
        evidence["sitemap_entry_total"] = 272
        runs.store_evidence(conn, run_id, evidence)
        runs.complete_run(conn, run_id, result)
        run_ids.append(run_id)
    yield conn, run_ids
    conn.close()


def test_the_breadth_phrase_states_the_ratio_and_the_share():
    """Both figures, the share, and — since CQ-70 — what each end counted.

    The old assertion was `"6 of 272 discovered pages" in phrase`, which one
    noun over two populations satisfies and which is the defect CQ-70 names.
    Asserted as the three figures plus the two separate nouns instead, so it
    still fails if a figure goes missing and now also fails if they are
    collapsed back under one word.
    """
    from clauditseo.reporting.render import _breadth_phrase

    phrase = _breadth_phrase({"pages_fetched": 6, "discovered": 272,
                              "discovered_basis": "sitemap"})
    assert "6" in phrase and "272" in phrase
    assert "2.2%" in phrase
    assert "6 pages a check could read" in phrase, phrase
    assert "of 272 the sitemap declares" in phrase, phrase
    assert "discovered pages" not in phrase, phrase

    # A scope dict this renderer did not build says nothing about where its
    # denominator came from, so the phrase names no population for it rather
    # than inventing one — `DISCOVERED_BASIS_PHRASE`'s rule, and the same one
    # `_basis_note` follows for the numerator's rung. The numerator's noun is
    # unconditional, so the two ends are still not one word.
    unstated = _breadth_phrase({"pages_fetched": 6, "discovered": 272})
    assert "6 pages a check could read, of 272 (2.2%)" in unstated, unstated


def test_the_breadth_phrase_is_silent_when_it_would_mislead():
    """The scope line's rules, applied to the same facts: no declared total
    means no ratio, and a full crawl is not a caveat. Over-fetching is a
    finding about the sitemap, not coverage above complete."""
    from clauditseo.reporting.render import _breadth_phrase

    for scope in ({"pages_fetched": 6, "discovered": None},
                  {"pages_fetched": 6, "discovered": 0},
                  {"pages_fetched": 12, "discovered": 12},
                  {"pages_fetched": 20, "discovered": 12},
                  None):
        assert _breadth_phrase(scope) == "", scope


@pytest.mark.parametrize("audience", gen.AUDIENCES)
@pytest.mark.parametrize("template", gen.TEMPLATES)
def test_a_composite_states_the_breadth_it_rests_on(db_with_a_partial_crawl,
                                                    template, audience):
    """A composite computed from a fraction of a site read exactly like one
    computed from all of it. The qualifier travels with the figure, on every
    template that states one and for both audiences — the rule that keeps
    getting applied to the run report and forgotten everywhere else.

    The trend template is the exception and is asserted as such: its points
    come from `metric_snapshots`, which stores a value and no scope, so it
    cannot state breadth and must not imply it."""
    conn, run_ids = db_with_a_partial_crawl
    ids = run_ids if template == "comparison" else run_ids[:1]
    md = gen.generate(conn, template, audience, ids)["markdown"]

    composites = [ln for ln in md.splitlines()
                  if ln.startswith("Composite:") or "composite:" in ln.lower()
                  and ln.startswith("- ")]
    if template == "monthly-trend":
        assert "measured across" not in md, (
            "the trend has no per-point scope and must not imply one")
    else:
        assert composites, f"{template} states no composite to qualify"
        for line in composites:
            # CQ-70: the denominator says what it counted, and the numerator
            # has its own noun rather than sharing the denominator's.
            assert "measured across" in line and "of 272 the sitemap declares" in line, line
            assert "pages a check could read" in line, line
    assert unsourced_number_lines(md) == []


# --- the document says what the crawl actually saw --------------------------

@pytest.fixture
def db_with_a_blocked_crawl(tmp_path):
    """A crawl that fetched nothing: a blanket Disallow, a 5xx on robots.txt or
    an unreachable host all produce it, and it is the misconfiguration an SEO
    audit most exists to catch."""
    from clauditseo.crawler.evidence import snapshot
    from clauditseo.crawler.types import CrawlResult

    conn = connect(tmp_path / "blocked.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Blocked Co")
    site_id = repo.create_site(conn, client, "blocked.fixture")

    blocked = CrawlResult(start_url="https://blocked.fixture/", tier=Tier.T2,
                          pages=[], robots_blocked=["https://blocked.fixture/"])
    blocked.stats = {"fetched": 0, "blocked_by_robots": 1}
    dims = ["TEC", "ONP", "CNT"]
    result = run_audit(Site(domain="blocked.fixture"), blocked, dims, Tier.T2)
    run_id = runs.create_run(conn, site_id, dims, "T2")
    runs.store_evidence(conn, run_id, snapshot(blocked))
    runs.complete_run(conn, run_id, result)
    yield conn, run_id
    conn.close()


def test_the_scope_sentence_states_its_provenance_once():
    """Thirteen rounds in the engineering cohort as "scope line carries three
    provenance tags in one sentence".

    The honesty rule is per *line* — `unsourced_number_lines` flags a line
    holding a metric-like number with no tag anywhere on it, so one tag
    discharges the whole sentence. `m()` was applied to each figure anyway,
    and the most-read sentence in the document came out as "6 (source:
    engine, confidence: high) of 272 (source: engine, confidence: high)
    discovered pages fetched, 3 (source: engine, confidence: high) URLs
    blocked by robots.txt." — the same tag three times, for three figures
    that come from one stored crawl evidence row and could not differ.

    `_shared_cause_lines` already settled this for the sentence beside it,
    with a comment saying so: "One tag at the end of the sentence, not four
    inside it." This holds `_scope_lines` to the convention its neighbour
    keeps, across every branch the function has — with and without a declared
    total, with and without an early stop, and the zero-page case whose own
    `[TO CONFIRM: …]` line is a separate claim and is not counted here.
    """
    from clauditseo.reporting.checks import unsourced_number_lines
    from clauditseo.reporting.render import _scope_lines

    shapes = [
        {"pages_fetched": 6, "discovered": 272, "robots_blocked": 3,
         "truncated_by": None},
        {"pages_fetched": 6, "discovered": 272, "robots_blocked": 3,
         "truncated_by": "max_pages"},
        {"pages_fetched": 2, "discovered": None, "robots_blocked": 0,
         "truncated_by": None},
        {"pages_fetched": 12, "discovered": 12, "robots_blocked": 0,
         "truncated_by": None},
        {"pages_fetched": 0, "discovered": 40, "robots_blocked": 2,
         "truncated_by": None},
    ]
    for scope in shapes:
        line = _scope_lines(scope)[0]
        assert line.count("source:") == 1, (
            f"the scope sentence tags its provenance "
            f"{line.count('source:')} times: {line!r}")
        # And the tag it kept still discharges the honesty gate, which is the
        # reason the other two were never needed rather than a second check.
        assert unsourced_number_lines(line) == [], line


def test_the_scope_line_states_the_ratio_not_just_the_count():
    """"6 pages fetched" reads as a small site. On www.acme.com.au it was 6
    of 272 the sitemap declares — 2% — and the sentence gave a client no way
    to tell those apart. The total was in the stored evidence the whole time
    and stopped one function short of the sentence, which is the same shape as
    the scope line's own origin."""
    from clauditseo.reporting.render import _scope_lines

    line = _scope_lines({"pages_fetched": 6, "discovered": 272,
                         "robots_blocked": 0, "truncated_by": "max_pages"})[0]
    assert "6" in line and "272" in line, line
    assert "of 272" in line.replace(" (source: engine, confidence: high)", ""), line
    assert "crawl stopped early (max_pages)" in line
    assert unsourced_number_lines(line) == [], "the new figure needs its source too"


def test_the_scope_line_says_nothing_it_does_not_know():
    """A crawl with no sitemap has no declared total. Saying "6 of 6" would
    assert the site is six pages, which is exactly the false confidence the
    ratio exists to remove."""
    from clauditseo.reporting.render import _scope_lines

    line = _scope_lines({"pages_fetched": 2, "discovered": None,
                         "robots_blocked": 0, "truncated_by": None})[0]
    assert "of" not in line.split("pages fetched")[0].replace("source", ""), line
    assert "2" in line
    assert unsourced_number_lines(line) == []


def test_a_full_crawl_does_not_read_as_partial():
    """Fetching everything the sitemap declares is not a caveat."""
    from clauditseo.reporting.render import _scope_lines

    line = _scope_lines({"pages_fetched": 12, "discovered": 12,
                         "robots_blocked": 0, "truncated_by": None})[0]
    assert "12" in line
    assert "of 12" not in line.replace(" (source: engine, confidence: high)", ""), line


def test_generate_refuses_a_blocked_run_for_a_client_however_it_is_called(
        db_with_a_blocked_crawl):
    """The refusal started in the API route, which is one of three callers.
    `cli.py report` and `scripts/seed_dev_data.py` call `generate()` directly,
    so the CLI produced the exact artefact the API declined. The rule belongs
    where the document is made, not at one of the doors to it.

    Scoped to the client audience, which is the only audience the reasoning
    recorded beside it ever reached: "a deliverable is the artefact that
    leaves the building". An internal document leaves nothing, and the
    companion test below is the other half of this rule."""
    conn, run_id = db_with_a_blocked_crawl
    with pytest.raises(ValueError, match="fetched no pages"):
        gen.generate(conn, "run", "client", [run_id])

    # And through the door, still a 422 carrying the same sentence.
    from fastapi.testclient import TestClient

    from clauditseo.api.app import create_app

    db = Path(conn.execute("PRAGMA database_list").fetchone()[2])
    conn.commit()
    resp = TestClient(create_app(db_path=db)).post(
        "/api/reports",
        json={"template": "run", "audience": "client", "run_ids": [run_id]})
    assert resp.status_code == 422, resp.text
    assert "fetched no pages" in resp.json()["detail"]


def test_a_blocked_run_produces_the_internal_document_that_explains_it(
        db_with_a_blocked_crawl, tmp_path):
    """WF-05, carried twelve rounds. The refusal was unconditional on
    audience, so the one run an operator most needs a written account of was
    the one run that could not produce any account at all — including the one
    saying why. Three such runs are stored on the live service.

    The reasoning recorded beside the refusal is entirely about sending:
    "nothing worth sending", "the artefact that leaves the building". Neither
    reaches `audience="internal"`, which is the operator's own reading copy
    and never leaves. The test below it, `test_the_document_states_what_the
    _crawl_fetched`, had to bypass `generate()` to render exactly this
    document and says so in its own docstring — that bypass is the finding.

    Asserts the document is made *and* that it is honest about the block: a
    document that generated but led with a composite for a site never
    retrieved would be the defect the refusal was protecting against, now
    shipped rather than refused."""
    conn, run_id = db_with_a_blocked_crawl
    out = gen.generate(conn, "run", "internal", [run_id], out_dir=tmp_path)

    md = out["markdown"]
    assert Path(out["path"]).exists()

    # Honest about the block, asserted as the properties rather than as one
    # string: the scope line's counts carry provenance tags, so "0 pages
    # fetched" is not contiguous text. These are the same three properties
    # `test_the_document_states_what_the_crawl_fetched` holds the renderer to
    # one test below — the point here is that `generate()` now reaches them.
    scope = [ln for ln in md.splitlines() if ln.startswith("Crawl scope:")]
    assert scope, "the internal document never states what the crawl fetched"
    assert "0" in scope[0] and "blocked by robots.txt" in scope[0], scope[0]
    assert any("Not assessed" in ln and "no page was fetched" in ln
               for ln in md.splitlines()),         "a crawl that fetched nothing must state that as its own scope limit"

    # Stored like any other deliverable, so it is findable afterwards.
    row = conn.execute("SELECT audience, template FROM reports WHERE id = ?",
                       (out["id"],)).fetchone()
    assert (row["audience"], row["template"]) == ("internal", "run")

    # And through the door the operator actually uses.
    from fastapi.testclient import TestClient

    from clauditseo.api.app import create_app

    db = Path(conn.execute("PRAGMA database_list").fetchone()[2])
    conn.commit()
    resp = TestClient(create_app(db_path=db)).post(
        "/api/reports",
        json={"template": "run", "audience": "internal", "run_ids": [run_id]})
    assert resp.status_code == 201, resp.text


def test_the_document_states_what_the_crawl_fetched(db_with_a_blocked_crawl):
    """The engine stopped scoring an empty crawl, and the document still never
    said one had happened: `snapshot()` persists the counts and `_run_dict`
    reduced the whole blob to a boolean one function short of the renderer.

    Rendered directly rather than through `generate()`, which refuses a
    blocked run for a client. The scope sentence still has to be right: the
    internal audience reads this run on screen, and a blocked run is exactly
    when knowing what was fetched matters most — which is why `generate()`
    now makes the internal document, asserted directly above."""
    from clauditseo.reporting.render import render_run_report

    conn, run_id = db_with_a_blocked_crawl
    run = runs.get_run(conn, run_id)
    site = repo.get_site(conn, run["site_id"])
    md, _ = render_run_report(site, run, "client")

    scope = [ln for ln in md.splitlines() if ln.startswith("Crawl scope:")]
    assert scope, "the report never states what the crawl fetched"
    assert "0" in scope[0], f"scope line does not carry the page count: {scope[0]!r}"
    assert "blocked by robots.txt" in scope[0]
    assert any("Not assessed" in ln and "no page was fetched" in ln
               for ln in md.splitlines()),         "a crawl that fetched nothing must state that as its own scope limit"
    # The new line carries numbers, so it obeys the same rule as every other.
    assert unsourced_number_lines(md) == []


def test_a_report_for_a_normal_crawl_still_states_its_scope(db_with_runs):
    """The scope line is not a special case for failure: a run that fetched
    pages says how many, and no scope-limit sentence is raised."""
    conn, run_ids = db_with_runs
    md = gen.generate(conn, "run", "client", [run_ids[0]])["markdown"]
    scope = [ln for ln in md.splitlines() if ln.startswith("Crawl scope:")]
    assert scope, "every report should say what it saw, not only the blocked ones"
    assert "no page was fetched" not in md
    assert unsourced_number_lines(md) == []


# --- a run with no composite is not a run that scored zero ------------------

#: The shape every surface uses for a fact it could not establish, with the
#: `what` narrowed to the composite. Matching the shape rather than a literal
#: is the point: the reason differs per cause and must, but the sentence a
#: client learns to recognise does not.
COMPOSITE_NOT_ASSESSED = re.compile(
    r"\[TO CONFIRM: Not assessed: (?P<what>[^.\]]*composite[^.\]]*)\. "
    r"Reason: (?P<reason>[^\]]+)\.\]")

@pytest.fixture
def db_with_an_unscorable_run(tmp_path):
    """A11Y carries nominal weight 0.0 by the operator's own decision, so an
    A11Y-only audit has no measurable share and therefore no composite. It is
    selectable from the API and the CLI today."""
    conn = connect(tmp_path / "unscorable.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Unscorable Co")
    site_id = repo.create_site(conn, client, "unscorable.fixture")

    server = FixtureSite(_routes(GOOD_PROMO)).start()
    try:
        crawl_result = crawl(server.base_url + "/", Tier.T2, budget=FAST)
    finally:
        server.stop()
    # Two runs, because the comparison template needs a baseline and a current
    # and both must be unscorable for the assertion to be about the composite
    # rather than about one half of the pair.
    run_ids = []
    for _ in range(2):
        result = run_audit(Site(domain="unscorable.fixture"), crawl_result,
                           ["A11Y"], Tier.T2)
        assert result.composite_score is None, "fixture must produce no composite"
        run_id = runs.create_run(conn, site_id, ["A11Y"], "T2")
        runs.complete_run(conn, run_id, result)
        run_ids.append(run_id)
    yield conn, site_id, run_ids
    conn.close()


@pytest.mark.parametrize("audience", gen.AUDIENCES)
@pytest.mark.parametrize("template", gen.TEMPLATES)
def test_every_template_says_a_missing_composite_the_same_way(
        db_with_an_unscorable_run, template, audience):
    """One fact, one sentence, every surface. A missing composite reached the
    run report as `None (source: engine, confidence: high)` — a null wearing a
    provenance tag that asserted high confidence in it. Fixing that in one
    renderer is what produces the next leak: the vocabulary has to hold across
    every template and both audiences, or the door simply moves."""
    conn, _site_id, run_ids = db_with_an_unscorable_run
    ids = run_ids if template == "comparison" else run_ids[:1]
    md = gen.generate(conn, template, audience, ids)["markdown"]

    # A null rendered as a value, not the word "None" as prose — "- None." is
    # the legitimate placeholder for a comparison section with no issues in it.
    assert "None (source:" not in md, \
        f"a null wearing a provenance tag reached the {audience} {template} document"
    assert not [ln for ln in md.splitlines()
                if "omposite" in ln and "None" in ln], \
        f"a null reached a composite line in the {audience} {template} document"

    # The shape, not the string: each template states its own true reason —
    # a run with no measurable weight and a trend with no scored runs are
    # different facts — but a reader meets one sentence pattern everywhere.
    said = [(ln, match) for ln in md.splitlines()
            if (match := COMPOSITE_NOT_ASSESSED.search(ln))]
    assert said, (f"the {audience} {template} document never says the composite "
                  f"is unassessed in the shared shape")
    for line, match in said:
        assert match.group("reason"), f"a not-assessed sentence with no reason: {line!r}"
        assert "confidence:" not in line, \
            f"a score that was never computed cannot carry a confidence: {line!r}"


def test_a_report_with_no_composite_says_so_rather_than_printing_none(
        db_with_an_unscorable_run):
    """`None` in the headline position is a rendering accident leaking into a
    client's document. The product already has a vocabulary for a number it
    does not have — `[TO CONFIRM: Not assessed: …]` — and a missing composite
    is exactly that, not a null and not a zero."""
    conn, _site_id, run_ids = db_with_an_unscorable_run
    md = gen.generate(conn, "run", "client", run_ids[:1])["markdown"]

    assert "None" not in md, "a null reached the client document"
    headline = [ln for ln in md.splitlines() if ln.startswith("Composite:")]
    assert headline, "the report should still speak about the composite"
    assert "Not assessed: composite score." in headline[0]
    assert "no dimension carried measurable weight" in headline[0]
    # No confidence may be asserted about a measurement that does not exist.
    # Scoped to the headline: other lines legitimately mention the composite
    # while carrying a tag for their own figure (a deduction, a trend point).
    assert "confidence:" not in headline[0], \
        f"a score that was never computed cannot carry a confidence: {headline[0]!r}"


def test_the_chat_summary_does_not_raise_on_a_run_with_no_composite(
        db_with_an_unscorable_run):
    """`f"{score:.1f}"` raises TypeError on None, so the assistant answering
    "what is the latest run" fails outright rather than saying what happened."""
    from clauditseo.api import chat

    conn, site_id, _run_ids = db_with_an_unscorable_run
    for question in ("what is the latest run?", "how is the score trending?"):
        reply = chat.answer(conn, site_id, question)
        assert reply["answer"], question
        assert "None" not in reply["answer"], question


# --- the client is told about their site, not about our plumbing ------------

VENDORS = ("PageSpeed", "CrUX", "Moz", "OpenPageRank", "DataForSEO")


@pytest.mark.parametrize("vendor", VENDORS)
def test_a_client_document_never_names_a_data_provider(db_with_runs, vendor):
    """Which suppliers the operator has keys for is the operator's business.
    A client reading "no PageSpeed or CrUX API key configured" is being shown
    a gap in our tooling dressed as a finding about their site — and they
    cannot act on it. This was closed once for backlinks at 85c86d6; the same
    leak stayed open through the Core Web Vitals door, on the keyless install
    that is the default configuration."""
    conn, run_ids = db_with_runs
    md = gen.generate(conn, "run", "client", [run_ids[0]])["markdown"]
    hit = re.search(rf"\b{re.escape(vendor)}\b", md, re.IGNORECASE)
    assert not hit, (
        f"client document names {vendor}: "
        f"{md.splitlines()[md[:hit.start()].count(chr(10))]!r}")


def test_an_unmeasured_dimension_says_what_and_why_without_naming_anyone(db_with_runs):
    """The replacement sentence still has to carry the two facts the client
    needs — what was not assessed, and why — or suppressing the vendor name
    just makes the report quieter rather than more honest."""
    conn, run_ids = db_with_runs
    md = gen.generate(conn, "run", "client", [run_ids[0]])["markdown"]
    prf = [ln for ln in md.splitlines() if ln.startswith("- PRF:")]
    assert prf, "a keyless run should carry a PRF not-assessed line"
    assert "Not assessed: Core Web Vitals field data." in prf[0]
    assert "no data source is configured for it" in prf[0]


# --- specialist briefs: the table that blocked the whole deliverable --------

BRIEF_FINDING = {"severity": "high", "code": "sitemap-coverage",
                 "summary": "22 indexable pages are absent from the sitemap.",
                 "affected_urls": ["https://report.fixture/a"]}


@pytest.fixture
def db_with_a_brief(db_with_runs):
    """A run carrying a specialist brief whose finding states a figure —
    which is what a brief is for, and the literal example its prompt gives."""
    conn, run_ids = db_with_runs
    runs.store_expert_report(conn, run_ids[0], "crawl",
                             {"model": "m-1", "report": "## SUMMARY\nSee index.",
                              "findings": [BRIEF_FINDING]})
    runs.record_expert_findings(conn, run_ids[0], "crawl", "m-1",
                                [BRIEF_FINDING])
    return conn, run_ids


@pytest.mark.parametrize("audience", ["client", "internal"])
def test_a_brief_finding_carrying_a_number_still_generates(db_with_a_brief, audience):
    """The deliverable the product exists to produce was ungeneratable for
    any run carrying the analysis it charges most for: the briefs table
    printed a model-written summary with no provenance, G7 read the row as an
    untagged number, and generate() raised before writing anything. Retries
    failed identically, so the only way out was editing SQLite by hand."""
    conn, run_ids = db_with_a_brief
    md = gen.generate(conn, "run", audience, [run_ids[0]])["markdown"]
    assert "## Specialist briefs" in md
    assert "22 indexable pages are absent from the sitemap." in md
    assert unsourced_number_lines(md) == []


def test_the_brief_row_says_which_model_wrote_it(db_with_a_brief):
    """The tag is provenance, not padding: a figure a model wrote and one the
    engine measured must not read the same way in a client's document.

    Q-57 hoists the tag: the model is named once under the heading, not on
    every row, so the provenance is still determinable from the document while
    the thirty-times-repeated tag is gone. The row itself no longer repeats
    it — that is the point of the hoist."""
    conn, run_ids = db_with_a_brief
    md = gen.generate(conn, "run", "client", [run_ids[0]])["markdown"]
    briefs = md.split("## Specialist briefs", 1)[1]
    prov = [ln for ln in briefs.splitlines()
            if ln.strip().startswith("_Provenance note")]
    assert any("source: model judgement (m-1)" in ln for ln in prov), briefs
    row = [ln for ln in md.splitlines() if "sitemap-coverage" in ln][0]
    assert "source:" not in row, "a uniform group's row must not repeat the tag"


def test_the_brief_row_does_not_invent_a_confidence(db_with_a_brief):
    """A brief's index block has no confidence column, so the stored 'medium'
    is a placeholder the persistence layer stamps — and records
    `confidence_stated: False` to say so. Asserting it to the client as the
    model's own judgement reads as a figure that has been audited. The hoisted
    provenance (Q-57) says the model stated no confidence, and the invented
    'medium' appears nowhere in the briefs the client reads."""
    conn, run_ids = db_with_a_brief
    md = gen.generate(conn, "run", "client", [run_ids[0]])["markdown"]
    briefs = md.split("## Specialist briefs", 1)[1]
    assert "confidence: not stated by the model" in briefs
    assert "confidence: medium" not in briefs
    # Still sourced — by the hoisted line — so the honesty gate still passes
    # on a group whose rows carry figures.
    assert unsourced_number_lines(md) == []


def test_no_renderer_prints_a_confidence_the_model_never_stated(db_with_a_brief):
    """The provenance invariant, pinned across every renderer at once.

    Not scoped to one section or one function: a finding stored with
    `confidence_stated: False` must not have a confidence asserted for it
    anywhere in the document — table cell, prose bullet or summary line —
    because the deliverable is read as one artefact, not as a set of
    independently-correct sections.
    """
    conn, run_ids = db_with_a_brief
    unstated = [r for r in conn.execute(
        "SELECT check_id, summary, evidence FROM findings WHERE run_id=?",
        (run_ids[0],)).fetchall()
        if json.loads(r["evidence"] or "{}").get("confidence_stated") is False]
    assert unstated, "fixture must carry a finding whose confidence was never stated"

    md = gen.generate(conn, "run", "client", [run_ids[0]])["markdown"]
    for finding in unstated:
        for line in md.splitlines():
            if finding["summary"] not in line and finding["check_id"] not in line:
                continue
            for claimed in re.findall(r"confidence:\s*([^|)\n]+)", line):
                assert claimed.strip() == "not stated by the model", (
                    f"{finding['check_id']} is stored with confidence_stated=False "
                    f"but this line asserts {claimed.strip()!r}:\n  {line}")


def test_a_brief_finding_is_rendered_once_not_twice(db_with_a_brief):
    """A brief finding is stored as model judgement, so it matched
    `_analyst_section` as well as the section built for it and went into the
    client document twice — under Analyst insights carrying the invented
    "confidence: medium", and under Specialist briefs correctly saying the
    model stated none. One finding, two provenances, one document."""
    conn, run_ids = db_with_a_brief
    md = gen.generate(conn, "run", "client", [run_ids[0]])["markdown"]
    hits = [ln for ln in md.splitlines()
            if "22 indexable pages are absent from the sitemap." in ln]
    assert len(hits) == 1, "one finding belongs on one line, in one section"
    # The provenance is hoisted (Q-57): stated once under the briefs heading,
    # not on the finding row. It still says the model stated no confidence.
    briefs = md.split("## Specialist briefs", 1)[1]
    assert "confidence: not stated by the model" in briefs
    # Scoped to the brief, not the whole document: an analyst finding states
    # its own confidence (AnalystFindingDraft.confidence), and "medium" there
    # is the model's own word. Only the brief path stamps a placeholder, and
    # only that placeholder must never reach a client.
    brief_lines = [ln for ln in md.splitlines() if "sitemap-coverage" in ln
                   or "22 indexable pages are absent from the sitemap." in ln]
    assert not any("confidence: medium" in ln for ln in brief_lines)
    insights = md.split("## Analyst insights", 1)[1].split("## ", 1)[0]
    assert "22 indexable pages" not in insights


def test_an_untagged_brief_row_is_still_caught():
    """Pins the regression by its shape rather than its absence — remove the
    provenance cell and this is what comes back."""
    assert unsourced_number_lines(
        "| high | `sitemap-coverage` | 22 indexable pages are absent. |") != []


# --- the scoping sentence, in the artefact the client receives -------------

def test_the_report_carries_the_shared_cause_sentence(tmp_path):
    """The most commercially useful line the product produces — "these
    categories, the same pages, most of the findings, usually one template" —
    lived only on the screen. An auditor quoting it had to retype it, and
    nothing kept the retyped version honest."""
    from clauditseo import anatomy as an

    cause = an.shared_cause(
        {"headings": {"/a", "/b"}, "images": {"/a", "/b"}, "crawl": {"/z"}},
        {"headings": 30, "images": 20, "crawl": 1}, 51)
    assert cause is not None
    assert set(cause["labels"]) == {"Headings", "Images"}
    assert cause["findings"] == 50
    assert cause["share"] == round(50 / 51, 3)


def test_no_cluster_says_nothing_rather_than_something_weak():
    """A claim in a client report has to be one the data carries."""
    from clauditseo import anatomy as an

    assert an.shared_cause({"headings": {"/a"}, "images": {"/b"}},
                           {"headings": 1, "images": 1}, 2) is None
    assert an.shared_cause({}, {}, 0) is None


def test_the_sentence_is_readable_and_still_sourced():
    """Tagging every number turned the one quotable line into something
    nobody could read aloud. The honesty rule is per line, so one tag at the
    end satisfies it and keeps the sentence usable."""
    from clauditseo.reporting.checks import unsourced_number_lines
    from clauditseo.reporting.render import _shared_cause_lines

    lines = _shared_cause_lines({"labels": ["Headings", "Images"], "pages": 99,
                                 "findings": 427, "grand_total": 461,
                                 "share": 0.926})
    body = [ln for ln in lines if "affect the same" in ln][0]
    assert body.count("source:") == 1, "one tag, at the end"
    assert "427 of 461" in body, "the numbers read as numbers"
    assert unsourced_number_lines("\n".join(lines)) == []


def test_a_dimension_excluded_by_choice_reads_differently_from_one_that_went_dark():
    """Two different zeros. A11Y is kept out of the composite deliberately;
    OFP scores nothing when its provider key is missing. Calling both "not
    scored" tells a client that off-page was excluded on purpose."""
    from clauditseo.reporting.render import _score_table

    rows = "\n".join(_score_table({"subscores": {
        "A11Y": {"score": 65.4, "weight": 0.0, "applicable": True,
                 "detail": {"nominal_weight": 0.0}},
        "OFP": {"score": 100.0, "weight": 0.0, "applicable": True,
                "detail": {"nominal_weight": 0.12}},
        "ONP": {"score": 68.0, "weight": 0.27, "applicable": True,
                "detail": {"nominal_weight": 0.22}},
    }}))
    # The distinction this test exists for — a decision against a gap — is
    # unchanged. What changed is the score cell: an unweighted dimension no
    # longer prints a figure that reads as a contribution.
    assert "| A11Y | — | not scored |" in rows
    assert "| OFP | — | not measured this run |" in rows
    assert "| ONP | 68.0 | 27.0% |" in rows


def test_a_dimension_code_with_digits_does_not_read_as_an_untagged_metric():
    """A11Y carries digits, so the header line listing a run's dimensions was
    flagged as an unsourced number and every report for a run including
    accessibility failed to generate."""
    from clauditseo.reporting.checks import unsourced_number_lines

    assert unsourced_number_lines(
        "run `abc12345def6` (T2, dimensions TEC, ONP, A11Y, PRF) · engine v0.5.0"
    ) == []


# --- accessibility, separated rather than hidden ---------------------------

def _report_with(findings, audience="client", subscores=None):
    from clauditseo.reporting.render import render_run_report

    # A hex id, because real run ids are hex and the honesty check exempts
    # them by that shape. A double that does not look like the thing it
    # stands in for fails for reasons that have nothing to do with the test.
    run = {"id": "a1b2c3d4e5f6a7b8", "tier": "T2", "dimensions": ["ONP", "A11Y"],
           "engine_version": "0.5.0", "composite_score": 90.0,
           "finished_at": "2026-08-14T00:00:00+00:00", "subscores": subscores or {},
           "findings": findings}
    return render_run_report({"domain": "x.test"}, run, audience)[0]


def _f(dimension, check_id, severity="medium"):
    return {"dimension": dimension, "check_id": check_id, "severity": severity,
            "source": "deterministic", "confidence": "high",
            "summary": f"{check_id} on a page.", "affected_urls": [],
            "model_id": None, "fingerprint": check_id}


def test_accessibility_is_listed_apart_from_ranking_findings():
    """It is half the open findings on a real client and carries no scoring
    weight. Interleaved by severity, a client reads a document that is half
    accessibility presented identically to the ranking work they are paying
    for — which invites the one response an audit cannot recover from."""
    md = _report_with([_f("ONP", "title-missing"),
                       _f("A11Y", "link-name-missing")])
    assert "## Accessibility" in md
    body, access = md.split("## Accessibility", 1)
    assert "title-missing" in body and "title-missing" not in access
    assert "link-name-missing" in access and "link-name-missing" not in body


def test_the_headline_count_excludes_accessibility_and_says_so():
    """A count that silently includes them overstates the ranking work."""
    md = _report_with([_f("ONP", "title-missing"),
                       _f("A11Y", "link-name-missing"),
                       _f("A11Y", "button-name-missing")])
    # The ranking count stands alone and the accessibility count is stated
    # beside it, so neither is silently folded into the other.
    assert "1 (source: engine, confidence: high) distinct issues" in md
    assert "plus 2 (source: engine, confidence: high) accessibility" in md


def test_the_separation_says_why_rather_than_just_separating():
    """A section with no explanation reads as a demotion. It is not scored
    here, and that is a statement about ranking impact, not about worth."""
    md = _report_with([_f("A11Y", "link-name-missing")])
    assert "do not carry weight in the score" in md
    assert "real defects and worth fixing" in md


def test_a_run_with_no_accessibility_findings_grows_no_empty_section():
    md = _report_with([_f("ONP", "title-missing")])
    assert "## Accessibility" not in md
    assert "accessibility findings listed separately" not in md


def test_the_separated_section_still_passes_the_honesty_check():
    from clauditseo.reporting.checks import unsourced_number_lines

    md = _report_with([_f("ONP", "title-missing"),
                       _f("A11Y", "link-name-missing", "high")])
    assert unsourced_number_lines(md) == []


# --- the deliverable argues its own case ------------------------------------

def test_repeated_findings_become_one_entry_with_a_page_count():
    """A hundred lines reading "N of M images on /X lack alt text" is the
    same finding a hundred times. The document stated "usually one template
    rather than a separate problem in each" and then enumerated all 427
    separately, arguing against its own conclusion for a hundred lines."""
    md = _report_with([
        {**_f("ONP", "img-alt-missing"), "affected_urls": [f"https://x.test/p{i}"]}
        for i in range(40)])
    assert md.count("Img alt missing on 40 pages") == 1
    assert md.count("- **medium**") == 1, "forty findings, one entry"


def test_a_single_instance_keeps_its_own_sentence():
    """The summary carries detail a check name cannot — "24 of 31 images",
    "2 pages share the same meta description"."""
    f = _f("ONP", "meta-desc-duplicate")
    f["summary"] = "2 pages share the same meta description."
    md = _report_with([f])
    assert "2 pages share the same meta description." in md
    assert "Meta desc duplicate on 1 pages" not in md


def test_the_pages_are_listed_until_a_list_stops_helping():
    """Eight paths is a list you act on; a hundred is the enumeration this
    change exists to remove."""
    md = _report_with([
        {**_f("ONP", "img-alt-missing"), "affected_urls": [f"https://x.test/p{i}"]}
        for i in range(30)])
    assert "`/p0`" in md and "`/p7`" in md
    assert "`/p20`" not in md
    assert "and 22 (source: engine, confidence: high) more" in md


def test_the_document_leads_with_what_to_do_first():
    """`biggest_gains` shaped the app and never the document: the report
    stated its conclusion then handed the reader 238 findings with no order
    to work in."""
    md = _report_with([_f("ONP", "img-alt-missing")], subscores={
        "ONP": {"applicable": True, "weight": 0.27, "score": 80.0,
                "detail": {"per_check": {"img-alt-missing": {
                    "deduction": 12.0, "affected": 100, "pages": 99,
                    "eligible": 100, "rate": 1.0}}}}})
    assert "## What to do first" in md
    assert md.index("## What to do first") < md.index("## What we found")
    assert "points on the composite" in md


def test_the_points_are_stated_as_a_ceiling_not_a_promise():
    """The deduction is capped and rate-based. "Up to" is the difference
    between an estimate and a claim."""
    md = _report_with([_f("ONP", "img-alt-missing")], subscores={
        "ONP": {"applicable": True, "weight": 0.27, "score": 80.0,
                "detail": {"per_check": {"img-alt-missing": {
                    "deduction": 12.0, "affected": 100, "pages": 99,
                    "eligible": 100, "rate": 1.0}}}}})
    assert "up to" in md and "The points are a ceiling" in md


def test_a_run_with_no_deductions_grows_no_action_list():
    md = _report_with([_f("ONP", "img-alt-missing")])
    assert "## What to do first" not in md


def test_the_grouped_report_still_passes_the_honesty_check():
    from clauditseo.reporting.checks import unsourced_number_lines

    md = _report_with([
        {**_f("ONP", "img-alt-missing"),
         "affected_urls": [f"https://x.test/blog/eofy-2026-post-{i}"]}
        for i in range(12)])
    assert unsourced_number_lines(md) == []


def test_a_backticked_path_is_not_read_as_a_metric():
    """The report lists the pages a check affects, so a client's own URLs
    read as untagged numbers. A path is an identifier, the same class as a
    run id — but a bare number in backticks still has to say where it came
    from."""
    from clauditseo.reporting.checks import unsourced_number_lines

    assert unsourced_number_lines("- `/blog/eofy-2026-cash-flow`, `/p70k`") == []
    assert unsourced_number_lines("The score was `42` last month.") != []


def test_an_unweighted_dimension_shows_no_number_in_the_score_column():
    """A number in a score column is read as a score. A11Y at 65.4 with a
    "not scored" label beside it was the lowest figure in the table and the
    one most likely to be quoted back — the label was doing all the work of
    preventing a wrong conclusion, and a label loses that argument against a
    number every time."""
    from clauditseo.reporting.render import _score_table

    rows = "\n".join(_score_table({"subscores": {
        "A11Y": {"score": 65.4, "weight": 0.0, "applicable": True,
                 "detail": {"nominal_weight": 0.0}},
        "OFP": {"score": 100.0, "weight": 0.0, "applicable": True,
                "detail": {"nominal_weight": 0.12}},
        "ONP": {"score": 68.0, "weight": 0.27, "applicable": True,
                "detail": {"nominal_weight": 0.22}},
    }}))
    assert "| A11Y | — | not scored |" in rows
    assert "65.4" not in rows, "the figure invites the wrong conclusion"
    assert "| OFP | — | not measured this run |" in rows
    assert "100.0" not in rows
    # A dimension that DOES score keeps its number.
    assert "| ONP | 68.0 | 27.0% |" in rows


def test_an_unweighted_dimension_offers_no_ranked_action():
    """The score table's rule, unapplied one section up.

    `_score_table` already refuses to print a number for a dimension carrying
    no weight — the test above — because "a label loses that argument against
    a number every time". `biggest_gains` multiplies the same dimension's
    deduction by the same zero weight and ranks the product, so the client
    document's action plan led with an item worth `up to 0.0 points on the
    composite`: a number offered as a recoverable gain that cannot be gained.

    Accessibility does not leave the document. It has had its own section
    since F-09 — `test_accessibility_is_listed_apart_from_ranking_findings`
    — and this asserts the finding is still there, so the plan losing the row
    is a correction rather than a deletion.
    """
    md = _report_with([_f("ONP", "img-alt-missing"),
                       _f("A11Y", "link-name-missing")], subscores={
        "ONP": {"applicable": True, "weight": 0.27, "score": 80.0,
                "detail": {"per_check": {"img-alt-missing": {
                    "deduction": 12.0, "affected": 100, "pages": 99,
                    "eligible": 100, "rate": 1.0}}}},
        "A11Y": {"applicable": True, "weight": 0.0, "score": 65.4,
                 "detail": {"per_check": {"link-name-missing": {
                     "deduction": 34.6, "affected": 41, "pages": 40,
                     "eligible": 41, "rate": 1.0}}}}})
    plan = md.split("## What we found", 1)[0]
    assert "## What to do first" in plan
    assert "0.0 points on the composite" not in plan
    # The plan humanises the check id — `_check_label` renders
    # `link-name-missing` as **Link name missing** — so asserting on the raw
    # id here passes whether the row is present or absent. That is a check
    # whose evidence cannot disagree with it, and it is what the first run of
    # this guard actually did.
    assert "Link name missing" not in plan,         "a dimension weighted zero cannot offer points on the composite"
    assert "Img alt missing" in plan
    # Still in the document, in the section F-09 gave it.
    assert "link-name-missing" in md.split("## Accessibility", 1)[1]


def test_the_action_plan_counts_one_page_in_the_singular():
    """`f" across {pages} pages"` had no singular form, so a check touching
    one page read `across 1 pages` in a client-facing document."""
    md = _report_with([_f("ONP", "title-missing")], subscores={
        "ONP": {"applicable": True, "weight": 0.27, "score": 80.0,
                "detail": {"per_check": {"title-missing": {
                    "deduction": 4.0, "affected": 1, "pages": 1,
                    "eligible": 100, "rate": 0.01}}}}})
    assert "across 1 page " in md
    assert "across 1 pages" not in md


def test_a_fabricated_analyst_figure_cannot_reach_a_client_document(db_with_runs):
    """The gate must not be handed the thing it is checking.

    `_evidence_text` serialised `run["findings"]` wholesale — including the
    `source='model-judgement'` rows `_analyst_section` writes the narrative
    from — so `assert_report_honest` compared a text against itself and could
    only ever return clean. Audit 013 reproduced it end to end.

    The `internal` audience refused on an unrelated unsourced-fingerprint
    line, not on the figure, so the audience that ships was the one with no
    working gate. This asserts `client`.
    """
    conn, run_ids = db_with_runs
    conn.execute(
        "INSERT INTO findings (id, run_id, dimension, check_id, severity,"
        " source, model_id, confidence, summary, affected_urls, evidence,"
        " recommendation, fingerprint, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("fab-1", run_ids[-1], "CNT", "analyst-note", "high",
         "model-judgement", "test-model", "medium",
         "Organic sessions fell 47318 percent after the 8 August template "
         "change.", "[]", "{}", "Investigate the template change.",
         "fab-fingerprint-1", "2026-08-16T00:00:00+00:00"))
    conn.commit()

    with pytest.raises(ReportCheckError) as caught:
        gen.generate(conn, "run", "client", [run_ids[-1]])
    assert "47318" in str(caught.value), (
        f"refused, but not for the invented figure: {caught.value}")


def test_a_declared_figure_does_not_ground_an_analyst_narrative(db_with_runs):
    """A brief's declared figure must not license an analyst claim.

    Written to assert a coupling that turned out not to be constructible:
    `_evidence_text` widened the allowed set with the analyst's declared
    figures, justified on the grounds that such a figure "renders carrying
    `ANALYST_FIGURE_NOTE`". It cannot — `narrative` comes from
    `_analyst_section`, which excludes `EXP:*`, and only `EXP:*` findings
    carry declared figures. So the widening admitted brief figures into a
    check over text that can never contain a brief finding.

    The widening is gone rather than repaired, which is why this now reads as
    a refusal: a number the crawl did not measure is ungrounded, and being
    declared by a brief does not change that. The marker still does its work
    where the figures actually render — the specialist-brief table, guarded
    in tests/test_expert_tools.py.
    """
    conn, run_ids = db_with_runs
    # The newest audit: a report built from the Latest View takes the
    # analyst's insights from the newest run of it (item 239 step 7).
    run_id = run_ids[-1]
    figure = "91724"

    # Declared by the analyst, and nowhere in the deterministic evidence.
    runs.store_expert_report(
        conn, run_id, "crawl",
        {"model": "m-1", "report": "## SUMMARY\nSee index.", "findings": [],
         "figures_to_verify": [{"value": figure,
                                "context": f"Lost revenue was {figure} dollars."}]})

    # An analyst finding quoting it, with no `figure_unverified` on its
    # evidence — so `_analyst_section` renders it without the marker. This is
    # the "stripped marker" half; it is the default, not a contrivance.
    conn.execute(
        "INSERT INTO findings (id, run_id, dimension, check_id, severity,"
        " source, model_id, confidence, summary, affected_urls, evidence,"
        " recommendation, fingerprint, created_at)"
        " VALUES ('f-declared', ?, 'CNT', 'revenue-claim', 'high',"
        " 'model-judgement', 'm-1', 'medium', ?, '[]', ?, '',"
        " 'fp-declared', '2026-08-16T00:00:00Z')",
        (run_id, f"The template change cost this site {figure} dollars.",
         json.dumps({"confidence_stated": True})))
    conn.commit()

    with pytest.raises(ReportCheckError) as raised:
        gen.generate(conn, "run", "client", [run_id])
    assert figure in str(raised.value), (
        f"the refusal must name the figure it refused; got {raised.value}")


def _scoped_pair(tmp_path, name):
    """A narrow run and a wide one over paths a real client would have.

    `db_with_runs` above cannot express this defect and its comparison test
    passes anyway: its two runs crawl the same three fixture routes, so no
    finding lands on a page the other run missed, no reason line is ever
    built, and `(+N more)` needs a fourth unfetched page to appear at all.
    A guard whose fixture cannot produce the thing it guards is the shape
    DISCIPLINE rule 5 is about, and this file already carries two of them.

    Digits in the paths on purpose. `unsourced_number_lines` exempts a
    backticked path and nothing else, so `/blog/7-5m-for-smes` is read as an
    untagged metric the moment it appears un-backticked in prose — which is
    what a client's own URLs look like.
    """
    from clauditseo.engine.core import AuditResult
    from clauditseo.engine.types import Confidence, Finding, Severity, Site as ST, Tier

    conn = connect(tmp_path / name)
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Widening Co")
    site_id = repo.create_site(conn, client, "https://wide.test/")

    pages = ["/blog/7-5m-for-smes", "/blog/eofy-2026-checklist",
             "/success-stories/70k-line-of-credit", "/blog/q3-2026-review",
             "/guides/top-10-brokers"]

    def finding(path, *, spans=None):
        """`spans` gives one finding several affected pages.

        The `(+N more)` suffix counts the pages of a *single* finding, not the
        pages that differ between the runs — a distinction this fixture got
        wrong first time and the precondition below caught. Without a finding
        that spans more than three pages the overflow branch never runs, and
        it is the branch carrying the bare number the gate reads as a metric.
        """
        urls = [f"https://wide.test{p}" for p in (spans or [path])]
        return Finding(dimension="ONP", check_id="img-alt-missing",
                       severity=Severity.MEDIUM, summary=f"alt missing on {path}",
                       subject=path, affected_urls=urls,
                       evidence={}, confidence=Confidence.HIGH, recommendation="")

    def store(findings, crawled):
        run_id = runs.create_run(conn, site_id, ["ONP"], "T2")
        runs.complete_run(conn, run_id, AuditResult(
            site=ST(domain="https://wide.test/"), tier=Tier.T2, dimensions=["ONP"],
            findings=findings, crawled_paths=set(crawled)))
        return run_id

    narrow = store([finding(pages[0])], pages[:1])
    wide = store([finding(p) for p in pages]
                 # One check across the four pages the narrow run never
                 # fetched. Four, and none of them `pages[0]`: the reason is
                 # only built when *no* page overlaps what the other run
                 # crawled, so a span including the shared page returns no
                 # reason at all and the overflow branch stays unreached. The
                 # precondition below caught that too.
                 + [finding(pages[1], spans=pages[1:])], pages)
    return conn, narrow, wide


@pytest.mark.parametrize("direction", ["widening", "narrowing"])
def test_a_comparison_document_can_be_generated_in_either_direction(tmp_path, direction):
    """The reason lines have to survive the product's own honesty gate.

    Both buckets state their reason as prose containing the client's paths and
    a `(+N more)` count. Un-backticked, a path with a digit in it reads to
    `unsourced_number_lines` as a metric with no source, and
    `assert_report_honest` raises — so the comparison deliverable could not be
    produced at all, in either direction, and the API answered 500.

    The narrowing half had been broken since renderer 1.13.0 with no test
    generating a comparison from runs of differing scope; the widening half
    was added by the `new_reason` change one commit before this one.
    """
    conn, narrow, wide = _scoped_pair(tmp_path, f"{direction}.db")
    a, b = (narrow, wide) if direction == "widening" else (wide, narrow)

    report = gen.generate(conn, "comparison", "client", [a, b])
    md = report["markdown"]

    assert unsourced_number_lines(md) == [], (
        "the comparison document states a client path or a count with no "
        "source tag, so the product's own gate refuses to release it")
    reasons = [ln for ln in md.splitlines()
               if "not re-checked:" in ln or "new to this record:" in ln]
    assert reasons, "fixture precondition: the pair must produce reason lines"
    assert any("(+" in ln for ln in reasons), (
        "fixture precondition: more than three pages differ, so at least one "
        "reason carries the (+N more) suffix that the gate reads as a metric")
    conn.close()


# --- CQ-130 / CQ-131 -------------------------------------------------------
#
# The honesty gate refused the product's own deliverable for two of the three
# real sites in the live database, and every refusal was an identifier the
# gate had mistaken for a measurement. The suite was green throughout: every
# domain any fixture above renders is alphabetic — `report.fixture`,
# `partial.fixture`, `blocked.fixture`, `unscorable.fixture`, `x.test`,
# `wide.test` — and no fixture renders an internal document carrying a check
# id with a digit in it. The gate had therefore never executed against either
# token class that breaks it in production.
#
# This fixture is the missing input class: a domain with a digit, and a page
# with no `<h1>` so `ONP/h1-missing` renders into the internal document.

NO_H1_PROMO = ("<html><head><title>Promo Page With A Fine Title</title>"
               '<meta name="description" content="A perfectly reasonable promo page.">'
               '<meta name="viewport" content="width=device-width">'
               '<link rel="canonical" href="/promo"></head>'
               "<body><p>Promo, and no heading at all.</p></body></html>")

DIGIT_DOMAIN = "twenty22.fixture"


@pytest.fixture
def db_with_digit_domain(tmp_path):
    """A site whose domain carries a digit, audited over a page with no H1.

    Both halves matter and neither is present anywhere else in this file: the
    domain reaches the title line of *both* audiences (`render.py:745`), and
    the check id reaches the internal document only (`render.py:436`).
    """
    conn = connect(tmp_path / "digit.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Twenty22")
    site_id = repo.create_site(conn, client, DIGIT_DOMAIN)

    server = FixtureSite(_routes(NO_H1_PROMO)).start()
    try:
        crawl_result = crawl(server.base_url + "/", Tier.T2, budget=FAST)
    finally:
        server.stop()
    result = run_audit(Site(domain=DIGIT_DOMAIN), crawl_result, DIMS, Tier.T2)
    run_id = runs.create_run(conn, site_id, DIMS, "T2")
    from clauditseo.crawler.evidence import snapshot
    runs.store_evidence(conn, run_id, snapshot(crawl_result))
    runs.complete_run(conn, run_id, result)
    yield conn, run_id
    conn.close()


@pytest.mark.parametrize("audience", ["client", "internal"])
def test_a_domain_with_a_digit_in_it_can_still_produce_a_document(
        db_with_digit_domain, audience):
    """CQ-130, reproduced as a fixture rather than read.

    Driven read-only over the live database this round, the client document
    generated for 1 of 3 real sites and the internal document for 0 of 3.
    `twenty22.co` failed on its own title line; `www.acme.com.au` failed on
    ``- check `ONP/h1-missing` ``. Both classes are below.
    """
    conn, run_id = db_with_digit_domain
    report = gen.generate(conn, "run", audience, [run_id])
    md = report["markdown"]

    assert unsourced_number_lines(md) == [], (
        "an identifier in the document was read as an untagged metric, so the "
        "product refuses to produce its own deliverable for this site")
    assert f"— {DIGIT_DOMAIN}" in md, (
        "fixture precondition: the domain reaches the title line")
    if audience == "internal":
        assert "`ONP/h1-missing`" in md, (
            "fixture precondition: the internal document names the check id")


def test_widening_the_exemptions_did_not_buy_the_document_with_the_invariant():
    """The negative half of CQ-130, in the same commit as the widening.

    Every entry in `_EXEMPT` is a hole in the one gate the provenance
    invariant rests on, so each of the three classes added is paired here with
    the nearest thing it must NOT swallow.
    """
    # A hostname is exempt; a composite is not, however it is punctuated.
    assert unsourced_number_lines("# SEO audit report — twenty22.co") == []
    assert unsourced_number_lines("Composite: 94.23 out of a possible 100") != []
    assert unsourced_number_lines("We audited 1,489 pages.") != []
    assert unsourced_number_lines("Load time was 3.5s on average.") != []
    # A missing space after a full stop must not read as a hostname and
    # carry the figure in front of it out of the gate's sight.
    assert unsourced_number_lines("The score fell to 12.Then it recovered.") != []

    # A backticked DIM/check-id is exempt; a backticked figure is not — the
    # rule report 059 wrote for backticked paths, applied to check ids.
    assert unsourced_number_lines("  - check `ONP/h1-missing`") == []
    assert unsourced_number_lines("  - check `ONP/h1-multiple`") == []
    assert unsourced_number_lines("The score was `42` last month.") != []
    assert unsourced_number_lines("Affected `4317` of them.") != []

    # A t-prefixed evidence item id is exempt, as f- and x- already are; the
    # three come from one generator each (`analysts/base.py:149,191`,
    # `analysts/tools.py:243`) and only t was missing.
    assert unsourced_number_lines("  - cites evidence items: t1, f3, x7") == []
    assert unsourced_number_lines("It took t1 minutes and 40 seconds.") != []
