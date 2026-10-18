"""The client report, split the way the screen is (brief v17 step AV6).

**AV6 asks for something the report does not have.** "Each part section
is split the same way" - the deliverable has no part sections. It groups
findings by check inside severity bands, then Accessibility, Not
assessed, Security notes, Analyst insights and Specialist briefs. There
is nothing here shaped like Title & description.

What the document *does* already have is the split itself, unnamed: every
finding in the graded sections is `source == "deterministic"`, and the two
model sections at the foot are the paid half. A reader was never told
which was which, so the one argument this whole brief is about - here is
what we found for nothing, and here is what the specialist read - was
being made by the app and not by the artefact that leaves the building.

So: the sections say what they are, in the same two words the part pages
use, and `run-free` is the template that stops after the free half.

A fourth template rather than a flag, because the choice has to survive
the document. The filename is the register's key and the artefact's
identity; a `free only` that lived only in a column would produce two
files a client could not tell apart, and the reindexer that reads
documents back off disk would have to guess.
"""

from __future__ import annotations

import pytest

from clauditseo.reporting import generate as gen


def test_the_free_only_template_is_a_template_the_product_knows():
    assert "run-free" in gen.TEMPLATES, gen.TEMPLATES
    # And the filename carries it, because the file is the artefact.
    # The matcher reads the stem: the caller strips `.md` before asking.
    m = gen._DOCUMENT_NAME.match(
        "birch-com-au-run-free-client-2026-09-06-a1b2c3d4")
    assert m and m.group("template") == "run-free", m and m.groupdict()
    # `run` still parses as `run` beside it: `.+` is greedy and backtracks,
    # and a slug ending in the word would be the way to break this.
    m = gen._DOCUMENT_NAME.match("birch-run-free-run-client-2026-09-06-a1b2c3d4")
    assert m and m.group("template") == "run" and m.group("slug") == "birch-run-free", \
        m and m.groupdict()


@pytest.fixture(scope="module")
def g7(tmp_path_factory):
    """One audit with both halves: deterministic findings and a stored
    analyst layer. Built the way `test_reporting_g7` builds it - a real
    crawl of the fixture site, a real audit over it - because what this
    file is about is which sections a document ends up with, and a hand-
    planted finding would not produce the sections."""
    import clauditseo.modules  # noqa: F401
    from clauditseo.analysts.layer import run_analyst_layer
    from clauditseo.analysts.mock import MockAnalyst
    from clauditseo.config import Settings
    from clauditseo.crawler.crawl import crawl
    from clauditseo.crawler.evidence import snapshot
    from clauditseo.crawler.types import TierBudget
    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate
    from clauditseo.engine.core import run_audit
    from clauditseo.engine.types import Site, Tier
    from clauditseo.persistence import repo, runs
    from tests.conftest import FixtureSite
    from tests.test_history_g4 import GOOD_PROMO, _routes

    dims = ["TEC", "ONP", "PRF", "OFP"]
    conn = connect(tmp_path_factory.mktemp("av6") / "av6.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "Free Half Co")
    site_id = repo.create_site(conn, client, "report.fixture")
    server = FixtureSite(_routes(GOOD_PROMO)).start()
    try:
        crawled = crawl(server.base_url + "/", Tier.T2,
                        budget=TierBudget(max_pages=20, request_timeout_s=5,
                                          wall_clock_s=30, delay_s=0))
    finally:
        server.stop()
    result = run_audit(Site(domain="report.fixture"), crawled, dims, Tier.T2)
    run_id = runs.create_run(conn, site_id, dims, "T2", analyst_enabled=True)
    runs.store_evidence(conn, run_id, snapshot(crawled))
    outcome = run_analyst_layer(conn, run_id, "report.fixture", result, crawled,
                                Settings(), provider=MockAnalyst())
    result.findings.extend(outcome.security_findings)
    result.findings.extend(outcome.findings)
    runs.complete_run(conn, run_id, result)
    # A stored brief as well, so the document has BOTH model sections:
    # `Analyst insights` is the analyst layer's, `Specialist briefs` is a
    # brief's, and they are written by two different functions. A fixture
    # with one of them would have let the other go on being printed.
    runs.store_expert_report(conn, run_id, "title-desc", {
        "model": "claude-sonnet-5", "cost": 0.08,
        "report": "## Title & description — assessment\n\nOne sentence.\n",
        "findings": []})
    runs.record_expert_findings(
        conn, run_id, "title-desc", "claude-sonnet-5",
        [{"code": "title-entity-alignment", "severity": "medium",
          "summary": "The home page title names no entity.",
          "affected_urls": [], "recommendation": "Name the business."}])
    yield conn, [run_id]
    conn.close()


def test_the_document_names_which_half_is_which(g7):
    conn, run_ids = g7
    md = gen.generate(conn, "run", "client", [run_ids[0]])["markdown"]
    # The free half, said where the count is: a client reading "31 distinct
    # issues" is owed the fact that none of it cost anything to find.
    assert "without a model" in md, md[:2000]
    # And the paid half, in the word the part pages head their second
    # section with.
    assert "Analyst insights" in md and "Specialist briefs" in md


def test_run_free_stops_after_the_free_half(g7):
    conn, run_ids = g7
    full = gen.generate(conn, "run", "client", [run_ids[0]])["markdown"]
    free = gen.generate(conn, "run-free", "client", [run_ids[0]])["markdown"]
    assert "Analyst insights" in full and "Specialist briefs" in full
    assert "Analyst insights" not in free, free[-3000:]
    assert "Specialist briefs" not in free, free[-3000:]
    # It is the same document otherwise - the scores, the findings and the
    # accessibility section are the audit's, and the audit is unchanged.
    for head in ("## Overall score", "## What we found", "## Accessibility"):
        if head in full:
            assert head in free, head
    # And it says what it left out, rather than quietly being shorter. A
    # client comparing two documents from one audit must be able to tell
    # which one is the whole answer.
    assert "free checks only" in free.lower(), free[:2500]


def test_the_register_records_the_template_it_was_asked_for(g7):
    conn, run_ids = g7
    report = gen.generate(conn, "run-free", "internal", [run_ids[0]])
    row = conn.execute("SELECT template FROM reports WHERE id=?",
                       (report["id"],)).fetchone()
    assert row["template"] == "run-free", dict(row)
    assert "-run-free-internal-" in report["path"], report["path"]
