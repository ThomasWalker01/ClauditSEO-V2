"""The client plan is a generator whose every summary sentence carries a
citation, and whose inputs the engine supplies in full.

Brief v18 step AY. Three things are held here, and each of them is a way
the plan could quietly become the thing it must not be — a model's opinion
printed in the operator's name.

1. **Every placeholder the prompt declares is filled by the engine.**
   `plan.md` conforms, so `render_prompt` raises `BriefInputError` on any
   input the context builder forgot rather than sending `[NOT SUPPLIED]`
   into the prompt. Sixteen placeholders is more than any other brief
   reads, five of them from columns added by `0045_site_plan_fields.sql`,
   and a builder that missed one would be found by a paid run rather than
   here.

2. **A summary sentence with no bracketed citation drops the document.**
   The whole document, not the sentence: a summary with one line silently
   removed still reads as a summary, so the reader has no way to know
   something was cut.

3. **The plan writes no part page.** Its header says `report`, which names
   no sidebar section, so nothing buckets it among the parts and nothing
   reads its empty `rows` as "nothing is wrong here".

The fixture is a site with one completed run and nothing else - no triage
ranking, no findings, no site-record fields. That is the hardest case for
point 1, not the easiest: every input is absent, and absence is exactly
where a builder that returns `""` instead of a stated fallback fails.
"""

from __future__ import annotations

import json

import pytest

from clauditseo.analysts import contract as _contract
from clauditseo.analysts.expert import (EXPERT_TOOLS, build_context,
                                        render_prompt)
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import repo, runs
from clauditseo import briefs

HOME = "https://plan.fixture/"


def _site(conn, site_id):
    """The site as a brief sees it - the route's own builder, so the test
    reads the record through the same parser the product does."""
    from clauditseo.api.app import site_of

    return site_of(repo.site_record(repo.get_site(conn, site_id)))

CITED = (
    "### Executive summary\n"
    "GPTBot and PerplexityBot are denied in robots.txt, so no content work "
    "ranks above lifting that [TEC/ai-crawler-blocked].\n"
    "The site scores 71.2 against 74.0 at the last comparable run, and Images "
    "carries the largest share of what is open [images].\n"
    "Fixing robots.txt unblocks the AI-surface rows behind it [ai-surface].\n"
    "\n"
    "- Blockers: one [crawl]\n"
    "\n"
    "### What is blocking\n"
    "One rule in robots.txt.\n"
)


def _block(**over) -> str:
    data = {"part": "report", "brief": "plan", "run_id": "r1",
            "source": "generator", "document_id": None}
    data.update(over)
    return "```json\n" + json.dumps(data) + "\n```\n\n"


@pytest.fixture
def planted(tmp_path):
    """A site with one completed run and nothing else filled in."""
    db = tmp_path / "plan.db"
    conn = connect(db)
    migrate(conn)
    owner_id = repo.ensure_default_operator(conn, "Plan Operator")
    client_id = repo.create_client(conn, owner_id, "Plan Co")
    site_id = repo.create_site(conn, client_id, "plan.fixture")
    run_id = runs.create_run(conn, site_id, ["ONP", "TEC"], "T2")
    runs.store_evidence(conn, run_id, {
        "start_url": HOME, "started_at": repo.now_iso(),
        "pages": [{"url": HOME, "status": 200, "title": "Plan",
                   "canonical": HOME}]})
    runs.mark_complete(conn, run_id, repo.now_iso())
    conn.commit()
    try:
        yield conn, site_id, run_id
    finally:
        conn.close()


def test_the_engine_fills_every_input_the_plan_declares(planted):
    """A conforming brief's inputs are all the engine's to supply."""
    conn, site_id, run_id = planted
    evidence = runs.get_evidence(conn, run_id)
    site = _site(conn, site_id)
    context = build_context("plan", evidence, site, conn=conn, run_id=run_id)
    # The error the strict path raises names the placeholder, so a failure
    # here reads as "the builder forgot HORIZONS" rather than as a stack.
    prompt = render_prompt("plan", context)
    assert "{{" not in prompt, "a placeholder survived substitution"
    # Absent is legible, and that is the point of the empty fixture: the
    # prompt states its own fallback for each, and it can only do that
    # while it can tell an unset field from a chosen one.
    assert "[NOT SUPPLIED]" in prompt
    # `measure_sources` is the exception, and the difference is the
    # document's: "nothing is connected" is an answer, and it is the answer
    # for every site today.
    assert "MEASURE_SOURCES" not in prompt


def test_a_summary_sentence_citing_nothing_drops_the_whole_plan(planted):
    parsed = _contract.parse(_block() + CITED, [], [])
    assert parsed.generator is not None, parsed.dropped
    assert not parsed.dropped

    uncited = CITED.replace(" [images]", "")
    parsed = _contract.parse(_block() + uncited, [], [])
    assert parsed.generator is None, "an uncited summary produced a document"
    assert len(parsed.dropped) == 1
    reason = parsed.dropped[0]["reason"]
    assert "citing no check or part" in reason
    # The reason carries the sentence, so the operator can see which line
    # failed without opening the stored report.
    assert "Images" in reason


def test_the_rule_reaches_only_the_plans_own_summary(planted):
    """A generator that is not the plan, and prose outside the summary, are
    both left alone.

    The plan is the only document whose summary a client reads on its own.
    `content-brief` is a commissioning document for a writer, its headings
    are not these, and applying a citation rule to it would drop every
    brief it ever wrote.
    """
    body = CITED.replace(" [images]", "")
    parsed = _contract.parse(_block(brief="content-brief") + body, [], [])
    assert parsed.generator is not None
    assert not parsed.dropped

    # Uncited prose under a later heading is not a summary sentence.
    later = CITED + "\nThe roadmap is sequenced by horizon and nothing else.\n"
    parsed = _contract.parse(_block() + later, [], [])
    assert parsed.generator is not None, parsed.dropped


def test_the_plan_writes_the_document_and_no_part_page():
    from clauditseo.anatomy import CATEGORIES, TOOL_CATEGORIES

    plan = briefs.by_id()["plan"]
    assert plan.kind == "generator"
    assert plan.checks == (), "a generator emits no rows"
    assert plan.part == briefs.REPORT_PART
    assert plan.part in briefs.PARTLESS
    # No sidebar section is named `report`, so no part page is registered
    # for it and no bucket collects its rows.
    assert briefs.REPORT_PART not in {c.key for c in CATEGORIES}
    # Item 238: under no part at all - its one door is Reports' "Generate".
    assert "plan" not in TOOL_CATEGORIES
    assert EXPERT_TOOLS["plan"]["scope"] == "site"
    assert EXPERT_TOOLS["plan"]["inputs"] == [], (
        "an input the operator types at run time is an assumption the "
        "document could not honestly list")


def test_the_five_plan_fields_round_trip_on_the_site_record(planted):
    conn, site_id, _ = planted
    repo.update_site(conn, site_id,
                     optimisation_ratio="70-80",
                     horizons=["30 days", "60 days", "90 days"],
                     workstreams=["content", "technical"],
                     capacity="12 hours a sprint",
                     measure_sources=["GSC"])
    site = _site(conn, site_id)
    assert site.optimisation_ratio == "70-80"
    assert site.horizons == ["30 days", "60 days", "90 days"]
    assert site.workstreams == ["content", "technical"]
    assert site.capacity == "12 hours a sprint"
    assert site.measure_sources == ["GSC"]


# --- the plan in the deliverable, and on the rail ---------------------------

def _store_plan(conn, run_id, *, body, contract):
    """One stored plan report, through the product's own writer."""
    from clauditseo.persistence.runs import store_expert_report

    store_expert_report(conn, run_id, "plan", {
        "model": "claude-opus-5", "report": body, "findings": [],
        "contract": contract})


def test_a_refused_plan_says_so_in_the_document_rather_than_vanishing(planted):
    """The three endings of `_plan_section` are three different documents.

    A plan that was never run leaves the document as it was. A plan that
    was refused says so, because a client reading a report with no summary
    has no way to tell "we chose not to" from "it was rejected". A plan
    that was accepted is the front of the document.
    """
    from clauditseo.reporting.generate import PLAN_REFUSED, _plan_section

    conn, _, run_id = planted
    evidence = "{}"

    front, narrative, warning = _plan_section(conn, run_id, evidence)
    assert (front, narrative, warning) == ("", "", None), "no plan ran"

    _store_plan(conn, run_id, body=CITED,
                contract={"status": "read", "generator": None,
                          "dropped": [{"row": None, "reason": "the executive "
                                       "summary has 1 sentence(s) citing no "
                                       "check or part"}]})
    front, narrative, warning = _plan_section(conn, run_id, evidence)
    assert front == PLAN_REFUSED
    assert narrative == ""
    assert warning and "citing no check or part" in warning


def test_an_accepted_plans_numbers_are_tagged_or_caveated_line_by_line(planted):
    """Gate G7's rule, applied to the plan's prose.

    The deliverable's measured evidence is one run's deterministic
    findings; the plan writes about the Record, which spans runs. So a
    plan sentence quoting a count this document cannot ground says so on
    its own line, and one carrying no number at all is left alone.
    """
    from clauditseo.reporting.generate import _plan_section
    from clauditseo.reporting.checks import unsourced_number_lines

    conn, _, run_id = planted
    _store_plan(conn, run_id, body=CITED,
                contract={"status": "read",
                          "generator": {"brief": "plan", "page": "",
                                        "document_id": None}})
    front, narrative, warning = _plan_section(conn, run_id, '{"measured": []}')
    assert warning is None
    assert front, "an accepted plan produced no front section"
    # The whole point: the document this becomes must pass the gate.
    assert unsourced_number_lines(front) == []
    # 71.2 and 74.0 are not in an empty evidence set, so that line is
    # caveated rather than tagged.
    caveated = [ln for ln in front.splitlines() if "[TO CONFIRM" in ln]
    assert any("71.2" in ln for ln in caveated), front
    # A sentence with no number is left exactly as the model wrote it.
    assert any(ln.endswith("[ai-surface].") for ln in front.splitlines()), front
    assert narrative, "the gate is handed nothing to ground"


GROUNDED = (
    "### Executive summary\n"
    "Images carries the largest share of what is open, 14 rows [images].\n"
    "Fixing robots.txt unblocks the AI-surface rows behind it [ai-surface].\n"
)


def test_the_plan_states_its_provenance_once_not_on_every_line(planted):
    """Q-57. The plan's provenance is one line under its heading, not the same
    tag on every one of its number-bearing lines.

    A grounded count — one this document's evidence contains — carries no
    per-line tag any more: it is sourced by the hoisted line above it. The
    hoisted line names the model, and the honesty gate still passes because it
    reads that line as sourcing the plan block beneath it.
    """
    from clauditseo.reporting.generate import _plan_section
    from clauditseo.reporting.checks import unsourced_number_lines

    conn, _, run_id = planted
    _store_plan(conn, run_id, body=GROUNDED,
                contract={"status": "read",
                          "generator": {"brief": "plan", "page": "",
                                        "document_id": None}})
    # 14 is in the evidence, so the line is grounded, not caveated.
    front, narrative, warning = _plan_section(conn, run_id, '{"open_rows": 14}')
    assert warning is None

    prov = [ln for ln in front.splitlines()
            if ln.strip().startswith("_Provenance note")]
    assert len(prov) == 1, front
    assert "source: model judgement (claude-opus-5)" in prov[0]
    assert "not stated by the model" in prov[0]

    # The grounded line is sourced by the hoist, so it carries neither a tag
    # of its own nor a caveat — and the gate passes on the whole front.
    grounded = [ln for ln in front.splitlines() if "14 rows" in ln][0]
    assert "source:" not in grounded
    assert "[TO CONFIRM" not in grounded
    assert unsourced_number_lines(front) == []
    # The tag is stated once, not thirty times.
    assert front.count("source:") == 1, front


def test_the_rail_reports_the_plan_and_what_has_moved_under_it(planted):
    """`plan · generated <time>` against `plan predates <n> rows`.

    The count is the server's because the screen cannot compare a
    timestamp against every row; a refused plan is not a generated one, so
    the tile does not point at a document that does not exist.
    """
    from clauditseo.persistence.runs import current_state

    conn, site_id, run_id = planted
    state = current_state(conn, site_id)
    assert state["plan_generated_at"] is None
    assert state["plan_stale_rows"] == 0

    _store_plan(conn, run_id, body=CITED,
                contract={"status": "read", "generator": None,
                          "dropped": [{"row": None, "reason": "uncited"}]})
    state = current_state(conn, site_id)
    assert state["plan_generated_at"] is None, (
        "a refused plan is not a generated one")

    _store_plan(conn, run_id, body=CITED,
                contract={"status": "read",
                          "generator": {"brief": "plan", "page": "",
                                        "document_id": None}})
    state = current_state(conn, site_id)
    assert state["plan_generated_at"], "an accepted plan is not reported"
    assert state["plan_stale_rows"] == 0

    # A row that moves after the plan was written is a row the plan has
    # not read.
    with conn:
        conn.execute(
            "INSERT INTO finding_states (site_id, fingerprint, state,"
            " updated_at) VALUES (?, ?, 'open', ?)",
            (site_id, "later-row", "2099-01-01T00:00:00Z"))
    assert current_state(conn, site_id)["plan_stale_rows"] == 1


def test_the_specialist_sections_are_in_sidebar_order():
    """The document meets the parts in the order the app does.

    Severity order put the same audit in a different sequence every run,
    so two documents about one site could not be compared by eye. The
    order is the catalogue's, which is the sidebar's.
    """
    from clauditseo import briefs as _b

    order = [b.id for b in _b.catalogue() if b.part not in _b.PARTLESS]
    assert order.index("title-desc") < order.index("indexability"), order
    assert order.index("headings") < order.index("crawl"), order
