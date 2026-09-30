"""The AI surface brief, installed and parsed (item 145, brief v22 step BH).

`ai-surface.md` is installed verbatim but for the header correction channel
20260915-0520 ruled: `TEC/ai-crawler-blocked` moves from `checks:` to `reads:`,
because TEC raises that row and a second emitter would undo 137's one owner.
The parser enforces what the prompt forbids rather than trusting it.
"""

from __future__ import annotations

import json

import clauditseo.modules  # noqa: F401  (register dimensions)
from clauditseo import briefs
from clauditseo.analysts import ai_surface
from clauditseo.analysts.contract import parse
from clauditseo.checks import check_cost, default_severities, sweep_checks

PAGES = ["https://site.test/", "https://site.test/events/conferences"]


def _brief():
    return briefs.by_id()["ai-surface"]


def _block(**over):
    data = {
        "part": "ai-surface", "run_id": "r1", "source": "brief",
        "directives": {"blocked": [{"ua": "GPTBot", "class": "training"}], "noai_pages": 0,
                       "llms_txt": "absent"},
        "edge": {"uas_tested": ["GPTBot"], "uas_blocked": [], "pages_affected": 0},
        "anchor": {"id_page": None},
        "entities": [{"name": "Conferences", "kind": "sub-service"}],
        "rows": [],
        "read_through": [], "absent_reads": [], "conflicts": [
            {"id": "title-framing", "sides": [], "resolved_by": None, "applied_by": None}],
        "not_assessable": [], "declined": [{"item": "CTR", "reason": "not observable"}],
        "assumptions": []}
    data.update(over)
    return "```json\n" + json.dumps(data) + "\n```\n\n### AI surface — assessment\nText."


def _parse(**over):
    b = _brief()
    return parse(_block(**over), list(b.checks), PAGES, defaults=default_severities(),
                 reads=list(b.reads), inputs={"LLMS_TXT_BUILD": "true"})


def _row(check, page, **extra):
    return {"check": check, "page": page, "status": "FAIL", "severity": "MEDIUM",
            "evidence": "e", "replacement": "r", "kind": "text", "note": None, **extra}


# --- install ----------------------------------------------------------------

def test_the_header_reads_the_crawl_row_and_does_not_own_it():
    b = _brief()
    assert "TEC/ai-crawler-blocked" in b.reads
    assert "AIS/ai-crawler-blocked" not in b.checks and "TEC/ai-crawler-blocked" not in b.checks
    assert b.part == "ai-surface" and b.scope == "site"
    assert len(b.reads) == 9


def test_every_check_the_prompt_calls_free_is_raised_by_a_sweep_and_the_rest_cost_a_model():
    text = b_text = _brief().path.read_text(encoding="utf-8")
    free = set()
    for check in _brief().checks:
        at = b_text.find(f"  {check} ")
        if at < 0:
            at = b_text.find(f"  {check}\n")
        assert at >= 0, check
        if "(free)" in text[at:at + 80]:
            free.add(check)
    assert free, "the prompt marks its free checks"
    for check in _brief().checks:
        bare = check.split("/")[1]
        if check in free:
            assert bare in sweep_checks() and check_cost(check) == "free", check
        else:
            assert check_cost(check) == "model", check


def test_the_context_fills_every_placeholder_and_sends_a_large_input_once():
    from clauditseo.analysts.expert import build_context, render_prompt
    from clauditseo.crawler.evidence import snapshot
    from clauditseo.crawler.types import CrawlResult, Page
    from clauditseo.engine.types import Site, Tier
    crawl = CrawlResult(start_url="https://site.test/", tier=Tier.T2, robots_status=200,
                        robots_txt="User-agent: GPTBot\nDisallow: /\n")
    body = "<html><head><title>Home</title></head><body><h1>Home</h1>" + "<p>Words here.</p>" * 400 + "</body></html>"
    crawl.pages = [Page(url=f"https://site.test/p{i}", requested_url=f"https://site.test/p{i}",
                        status=200, content=body, content_type="text/html") for i in range(3)]
    ev = snapshot(crawl)
    ctx = build_context("ai-surface", ev, Site(domain="site.test"))
    text = render_prompt("ai-surface", ctx)
    assert "{{" not in text
    assert len(ctx["PAGE_SET"]) > 300
    assert text.count(ctx["PAGE_SET"]) == 1, "the page set is sent once"
    assert "for each page in the PAGE_SET input (under CONTEXT)" in text
    assert "GPTBot (training): block · stated" in ctx["ROBOTS_DIRECTIVES"]
    # `legal_name` read "(the site record has no such field yet)" until
    # migration 0063 gave it a column (item 145 step BH). It is an ordinary
    # empty record field now, and an empty one still states itself.
    assert "- legal_name: [NOT SUPPLIED]" in ctx["SITE_ENTITIES"]
    assert "no such field yet" not in ctx["SITE_ENTITIES"]
    assert "- registered_ids: [NOT SUPPLIED]" in ctx["SITE_ENTITIES"]
    assert "the site record lists no external profiles" in ctx["EXTERNAL_PROFILES"]


#: The briefs that name {{PAGE_SET}} or {{URL_SET}} in TASK and again as the
#: data slot under CONTEXT. Measured on twenty22's run 996557a8: images drops
#: from 400k to 223k characters, structured-data 438k to 248k, headings
#: 290k to 153k.
INPUTS_ONCE = ["urls", "links", "title-desc", "headings", "images", "structured-data",
               "ai-surface", "content-coverage", "content-substance", "content-benchmark"]


def test_no_other_brief_renders_differently():
    from clauditseo.analysts.expert import EXPERT_TOOLS
    assert [t for t, s in EXPERT_TOOLS.items() if s.get("inputs_once")] == INPUTS_ONCE


def test_each_opted_in_brief_places_its_inputs_under_context():
    """The opt-in is safe only when every placeholder's first mention below
    `# CONTEXT` sits inside that section (so the data lands in the slot, not
    in FORMAT), and none is named only above it (that value would never be
    sent once it passed 300 characters)."""
    import re

    from clauditseo.analysts.expert import EXPERT_TOOLS, PROMPT_DIR
    for tool in INPUTS_ONCE:
        text = (PROMPT_DIR / EXPERT_TOOLS[tool]["prompt"]).read_text(encoding="utf-8")
        assert text.count("\n# CONTEXT") == 1, tool
        at = text.find("\n# CONTEXT")
        end = text.find("\n# ", at + 1)
        end = len(text) if end < 0 else end
        above = set(re.findall(r"\{\{([A-Z_]+)\}\}", text[:at]))
        first: dict[str, int] = {}
        for m in re.finditer(r"\{\{([A-Z_]+)\}\}", text[at:]):
            first.setdefault(m.group(1), at + m.start())
        # BYTES_PER_PIXEL is a single figure, never near 300 characters.
        assert above - set(first) <= {"BYTES_PER_PIXEL"}, tool
        assert all(p < end for p in first.values()), tool


# --- the block ----------------------------------------------------------------

def test_a_candidate_with_an_industry_knowledge_source_is_dropped():
    p = _parse(rows=[_row("AIS/entity-enrichment", PAGES[1], candidates=[
        {"entity": "Melbourne", "source": "site record: locations", "place": "first paragraph",
         "sentence": "Birch runs conferences in Melbourne."},
        {"entity": "AV hire", "source": "industry knowledge", "place": "h2", "sentence": "x"},
        {"entity": "Duration", "source": "schema.org: Event.duration", "place": "p", "sentence": "y"}])])
    row, = p.rows
    assert [c["entity"] for c in row.extra["candidates"]] == ["Melbourne", "Duration"]
    assert "1 candidate(s) dropped" in row.note and "industry knowledge" in row.note
    only_bad = _parse(rows=[_row("AIS/entity-enrichment", PAGES[1], candidates=[
        {"entity": "x", "source": "what AI expects", "place": "p", "sentence": "s"}])])
    assert not only_bad.rows and "forbids" in only_bad.dropped[0]["reason"]


def test_a_passage_over_sixty_words_is_truncated_and_noted():
    long = " ".join(f"w{i}" for i in range(75))
    row, = _parse(rows=[_row("AIS/answer-liftable", PAGES[1], passage=long,
                             criteria={"named_subject": False}, place="first paragraph")]).rows
    assert len(row.extra["passage"].split()) == 60
    assert "truncated from 75 to 60 words" in row.note


def test_a_needs_value_outside_the_enum_is_held_with_a_reason():
    p = _parse(absent_reads=[{"check": "INT/lang-en-absent", "part": "international",
                              "needs": "International has not been purchased"}])
    entry, = p.ai_surface["absent_reads"]
    assert entry["held"] == "unrecognised needs value"


def test_an_analysis_tier_absence_is_distinguishable_from_an_unrun_part():
    p = _parse(absent_reads=[
        {"check": "INT/lang-en-absent", "part": "international", "needs": "part has not run"},
        {"check": "ONP/heading-answer-delayed", "part": "headings",
         "needs": "part ran free-only, this check is analysis"}])
    needs = {e["check"]: e["needs"] for e in p.ai_surface["absent_reads"]}
    assert needs["INT/lang-en-absent"] != needs["ONP/heading-answer-delayed"]
    assert not any("held" in e for e in p.ai_surface["absent_reads"])


def test_not_assessable_needs_is_still_free_text():
    p = _parse(not_assessable=[{"check": "AIS/entity-type-generic", "page": None,
                                "needs": "gbp_primary_category on the site record is empty"}])
    assert p.not_assessable[0]["needs"] == "gbp_primary_category on the site record is empty"


def test_a_read_through_entry_for_a_check_this_brief_owns_is_rejected():
    p = _parse(read_through=[
        {"check": "AIS/entity-unnamed", "page": None, "payload": {}, "source_run": "r1"},
        {"check": "TEC/links-behind-js", "page": "/", "payload": {"render_only": 3}, "source_run": "r1"}])
    assert [r["check"] for r in p.ai_surface["read_through"]] == ["TEC/links-behind-js"]
    assert "which this analysis owns" in p.dropped[0]["reason"]


def test_a_site_scoped_read_never_takes_a_per_page_row():
    p = _parse(read_through=[
        {"check": "INT/lang-en-absent", "page": None, "payload": {"alternate": False}, "source_run": "r1"},
        {"check": "CNT/answer-first", "page": "/events", "payload": {}, "source_run": "r1"}])
    scopes = {r["check"]: (r["scope"], r["page"]) for r in p.ai_surface["read_through"]}
    assert scopes["INT/lang-en-absent"] == ("site", None)
    assert scopes["CNT/answer-first"] == ("page", "/events")


def test_a_site_row_and_the_unmeasured_info_row_are_stored_and_markers_counted():
    p = _parse(rows=[
        _row("AIS/id-page-absent", None, severity="HIGH", note="raised: entity-unresolvable fired",
             required_sections=[{"section": "Registered identifiers",
                                 "held": "[client to supply] — registered_ids is empty"}]),
        {"check": "AIS/llms-txt-authored", "page": None, "status": "INFO",
         "severity": "INFO", "evidence": "Block 3 carries a file", "replacement": None,
         "kind": "info", "note": "never scored"},
        _row("AIS/answer-liftable", PAGES[1], passage="Birch runs [client to supply] events.")])
    checks = {r.check: r for r in p.rows}
    assert checks["AIS/id-page-absent"].page == PAGES[0] and checks["AIS/id-page-absent"].severity == "high"
    assert checks["AIS/llms-txt-authored"].severity == "info"
    assert p.ai_surface["client_to_supply"] == 2
    stored = p.as_dict()
    assert stored["ai_surface"]["now"]["directives"]["blocked"][0]["ua"] == "GPTBot"
    assert stored["ai_surface"]["conflicts"][0]["id"] == "title-framing"


def test_the_engine_says_which_absence_a_read_is():
    import tempfile
    from pathlib import Path

    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate
    from clauditseo.persistence import repo, runs
    conn = connect(Path(tempfile.mkdtemp()) / "t.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site_id = repo.create_site(conn, repo.create_client(conn, op, "T"), "t.test")
    run_id = runs.create_run(conn, site_id, ["TEC", "CNT"], "T2")
    assert ai_surface.absent_needs(conn, site_id, run_id, "INT/lang-en-absent") == ai_surface.NEEDS_UNRUN
    assert ai_surface.absent_needs(conn, site_id, run_id, "CNT/eeat") == ai_surface.NEEDS_FREE_ONLY
    assert ai_surface.absent_needs(conn, site_id, run_id, "TEC/links-behind-js").startswith("blocked: ")
    conn.close()


def test_a_rows_payload_survives_the_store_and_reaches_the_record():
    import tempfile
    from pathlib import Path

    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate
    from clauditseo.persistence import repo, runs
    conn = connect(Path(tempfile.mkdtemp()) / "t.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site_id = repo.create_site(conn, repo.create_client(conn, op, "T"), "site.test")
    run_id = runs.create_run(conn, site_id, ["AIS"], "T2")
    p = _parse(rows=[
        _row("AIS/entity-enrichment", PAGES[1], candidates=[
            {"entity": "Melbourne", "source": "site record: locations", "place": "first paragraph",
             "sentence": "Birch runs conferences in Melbourne."}]),
        _row("AIS/answer-liftable", PAGES[1], passage="Birch runs conferences.",
             place="first paragraph under the H1", criteria={"named_subject": True})])
    runs.mark_complete(conn, run_id, repo.now_iso())
    from clauditseo.analysts.expert import _store_contract
    runs.store_expert_report(conn, run_id, "ai-surface",
                             {"status": "ok", "report": "", "model": "m", "tokens": 0})
    _store_contract(conn, run_id, "ai-surface", "m", p.as_dict())
    got = {s["check_id"]: s for s in runs.site_states(conn, site_id)}
    conn.close()
    assert got["entity-enrichment"]["payload"]["candidates"][0]["sentence"].startswith("Birch runs")
    lift = got["answer-liftable"]["payload"]
    assert lift["passage"] == "Birch runs conferences." and lift["criteria"] == {"named_subject": True}
    assert lift["place"] == "first paragraph under the H1"


# --- the part page's reachability "now" ---------------------------------------

def _reach_run(tmp_path, *, declared=None, field=None):
    from clauditseo.crawler.types import CrawlResult
    from clauditseo.crawler.evidence import snapshot
    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate
    from clauditseo.engine.types import Site, Tier
    from clauditseo.persistence import repo, runs
    conn = connect(tmp_path / "r.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site_id = repo.create_site(conn, repo.create_client(conn, op, "T"), "site.test")
    run_id = runs.create_run(conn, site_id, ["AIS"], "T2")
    ev = snapshot(CrawlResult(start_url="https://site.test/", tier=Tier.T2, robots_status=200,
                              robots_txt="User-agent: GPTBot\nDisallow: /\n"))
    ev["ua_matrix"] = [
        {"agent": "ClaudeBot", "agent_class": "training", "sent": True, "robots": "allow",
         "home_status": 403, "probe_status": []},
        {"agent": "OAI-SearchBot", "agent_class": "index", "sent": True, "robots": "allow",
         "home_status": 403, "probe_status": []},
        {"agent": "Applebot", "agent_class": "index", "sent": True, "robots": "allow",
         "home_status": 200, "probe_status": [200]},
        {"agent": "Google-Extended", "agent_class": "training", "sent": False, "robots": "allow"}]
    runs.store_evidence(conn, run_id, ev)
    with conn:
        for agent in ("ClaudeBot", "OAI-SearchBot"):
            conn.execute(
                "INSERT INTO findings (id, run_id, dimension, check_id, severity, source, summary,"
                " affected_urls, fingerprint, created_at, evidence) VALUES (?, ?, 'AIS',"
                " 'edge-blocks-ai-ua', 'high', 'deterministic', 's', '[]', ?, ?, ?)",
                (repo.create_id(), run_id, f"fp-{agent}", repo.now_iso(),
                 json.dumps({"agent": agent, "responses": [{"status": 403, "url": "https://site.test/"}]})))
    site = Site(domain="site.test", ai_edge_blocked_agents=declared, ai_field_data_source=field)
    return conn, run_id, site


def test_the_reachability_rows_tell_a_chosen_block_from_an_unstated_one(tmp_path):
    conn, run_id, site = _reach_run(tmp_path, declared="ClaudeBot")
    now = ai_surface.reachability_payload(conn, run_id, site)
    conn.close()
    by = {r["agent"]: r for r in now["rows"]}
    assert by["GPTBot"]["state"] == "stated" and by["GPTBot"]["got"] == "n/a"
    assert by["ClaudeBot"]["state"] == "edge policy" and by["ClaudeBot"]["got"] == "403"
    assert by["OAI-SearchBot"]["state"] == "unstated block"
    assert by["Applebot"]["state"] == "reachable" and by["Applebot"]["shown"] == "same"
    assert by["Google-Extended"]["robots_token"] and by["Google-Extended"]["state"] == "unstated"
    # An agent the matrix did not ask as is not assessed, never reachable.
    assert by["PerplexityBot"]["state"] == "not assessed"
    assert "Googlebot" not in by, "the search agents are not AI agents"


def test_the_field_columns_render_only_when_the_source_is_set(tmp_path):
    from pathlib import Path
    conn, run_id, site = _reach_run(tmp_path)
    assert ai_surface.reachability_payload(conn, run_id, site)["field_source"] is None
    conn.close()
    conn, run_id, site = _reach_run(tmp_path / "f" if (tmp_path / "f").mkdir() is None else tmp_path,
                                    field="cloudflare")
    assert ai_surface.reachability_payload(conn, run_id, site)["field_source"] == "cloudflare"
    conn.close()
    src = (Path(__file__).resolve().parents[1] / "dashboard" / "src" / "ai_surface.tsx").read_text(encoding="utf-8")
    assert "{field && <th" in src and "{field && <td" in src


# --- what twenty22's first paid run showed (996557a8, 2026-09-15) -----------

def test_a_brief_row_for_a_per_agent_free_check_is_dropped():
    p = _parse(rows=[_row("AIS/edge-blocks-ai-ua", None, severity="HIGH", uas=["CCBot", "ClaudeBot"])])
    assert not p.rows and "raised per crawler by the automatic checks" in p.dropped[0]["reason"]


def test_llms_txt_authored_needs_the_build_input_true():
    b = _brief()
    row = {"check": "AIS/llms-txt-authored", "page": None, "status": "INFO", "severity": "INFO",
           "evidence": "Block 3 carries a file", "replacement": None, "kind": "info", "note": None}
    off = parse(_block(rows=[row]), list(b.checks), PAGES, defaults=default_severities(),
                reads=list(b.reads), inputs={"LLMS_TXT_BUILD": "false"})
    assert not off.rows and "LLMS_TXT_BUILD" in off.dropped[0]["reason"]
    on = parse(_block(rows=[row]), list(b.checks), PAGES, defaults=default_severities(),
               reads=list(b.reads), inputs={"LLMS_TXT_BUILD": "true"})
    assert [r.check for r in on.rows] == ["AIS/llms-txt-authored"]


def test_an_enrichment_row_the_record_cannot_feed_is_held_not_dropped():
    p = _parse(rows=[_row("AIS/entity-enrichment", PAGES[1], candidates=[],
                          note="populating sub_services on Admin › Sites would unlock candidates")])
    assert not p.rows and not p.dropped
    held, = p.not_assessable
    assert held["check"] == "AIS/entity-enrichment" and "sub_services" in held["needs"]


def test_the_page_set_gives_the_words_under_the_h1_not_the_navigation():
    from clauditseo.engine.types import Site
    page = {"url": "https://site.test/", "status": 200, "content_type": "text/html",
            "title": "Home", "h1": "SEO and Website Designs",
            "opening": "About the Design Process Learn a little about",
            "outline": [[1, "SEO and Website Designs", True, "Twenty22 designs websites in Bendigo."]]}
    text = ai_surface.page_set({"pages": [page]}, Site(domain="site.test"), [], {})
    assert "first words under the H1 (initial HTML, main region): Twenty22 designs websites" in text
    assert "About the Design Process" not in text


def test_a_candidate_held_on_an_empty_record_field_is_a_hold_not_a_forbidden_source():
    p = _parse(rows=[_row("AIS/entity-enrichment", PAGES[1], note="locations is empty", candidates=[
        {"entity": "service area", "source": "site record: locations · [NOT SUPPLIED]",
         "place": "first paragraph", "note": "cannot emit a sentence"}])])
    assert not p.rows and not p.dropped
    assert p.not_assessable[0]["check"] == "AIS/entity-enrichment"


# --- Block 3: /llms.txt (step BI) ----------------------------------------------

_LLMS_EV = {"pages": [
    {"url": "https://site.test/", "status": 200},
    {"url": "https://site.test/events/conferences", "status": 200},
    {"url": "https://site.test/old", "status": 200, "canonical": "https://site.test/new"},
    {"url": "https://site.test/private", "status": 200, "meta_robots": "noindex"}]}
_FILE = ("# Birch\n\n> Events in Melbourne.\n\n## Services\n\n"
         "- [Home](https://site.test/): the home page\n"
         "- [Conferences](https://site.test/events/conferences): corporate conferences in Melbourne\n"
         "- [Old](https://site.test/old): an old page\n"
         "- [Private](https://site.test/private): hidden\n"
         "- [Guessed](https://site.test/events/gala-dinners): a page the crawl never reached\n")


def _with_file(build):
    p = _parse()
    p.body = p.body + "\n\n## Block 3\n```markdown\n" + _FILE + "```\n"
    ai_surface.police_llms_file(p, _LLMS_EV, build)
    return p


def test_the_llms_txt_file_holds_only_crawled_indexable_self_canonical_urls():
    f = _with_file(True).ai_surface["llms_txt_file"]
    assert "https://site.test/events/conferences" in f["text"] and f["urls"] == 2
    refused = {r["url"].removeprefix("https://site.test"): r["reason"] for r in f["refused"]}
    assert refused == {"/old": "canonicalises to https://site.test/new", "/private": "is noindex",
                       "/events/gala-dinners": "is not in this audit's crawl"}
    assert "gala-dinners" not in f["text"]
    assert f["sections"] == 1 and not any("H1" in s for s in f["shape"])


def test_a_file_authored_without_the_build_input_is_not_kept():
    p = _with_file(False)
    assert "llms_txt_file" not in p.ai_surface
    assert "```markdown" not in p.body
    assert "LLMS_TXT_BUILD false" in p.dropped[-1]["reason"]


# --- channel 20260915-2045: entity-unresolvable, and free rows are the sweep's --

def test_a_brief_row_on_a_free_check_is_dropped():
    p = _parse(rows=[_row("AIS/entity-unresolvable", None, severity="HIGH"),
                     _row("AIS/id-page-absent", None, severity="HIGH")])
    assert [r.check for r in p.rows] == ["AIS/id-page-absent"]
    assert "free check; the automatic checks measure it" in p.dropped[0]["reason"]
