"""`ai_crawler_policy` on the site record, and one `ai-crawler-blocked` row per
agent with its class (item 145, brief v22 step BG, step 2).

Channel ruling 20260915-0520: severity lives where the row is raised. Not
stated, or `allow`, keeps 137's HIGH blocker (a block nothing says was chosen);
`block` makes the block the policy working, LOW and not a blocker. The agent
and its class ride on TEC's row, so the AI surface reads them rather than
classifying.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

import clauditseo.modules  # noqa: F401  (register dimensions)
from clauditseo.api.app import create_app
from clauditseo.crawler.types import CrawlResult
from clauditseo.crawler.ua_matrix import (PRUNED_AGENTS, UA_MATRIX_AGENTS,
                                         agent_class)
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.engine.types import Severity, Site, Tier
from clauditseo.modules.tec import AI_CRAWLERS, TechnicalModule
from clauditseo.persistence import repo

#: twenty22's shape from the addendum: the training agents told no in
#: robots.txt, the index agents not named at all.
_ROBOTS = ("User-agent: *\nAllow: /\n\n"
           + "".join(f"User-agent: {a}\nDisallow: /\n\n" for a in
                     ("GPTBot", "ClaudeBot", "CCBot", "Bytespider",
                      "Meta-ExternalAgent", "Amazonbot", "PetalBot")))


def _rows(policy=None):
    crawl = CrawlResult(start_url="https://twenty22.test/", tier=Tier.T2,
                        robots_txt=_ROBOTS, robots_status=200)
    site = Site(domain="twenty22.test", ai_crawler_policy=policy)
    return [f for f in TechnicalModule()._site_checks(crawl, site)
            if f.check_id == "ai-crawler-blocked"]


def test_one_row_per_blocked_agent_with_its_class():
    rows = _rows()
    by = {f.evidence["agent"]: f for f in rows}
    assert set(by) == {"GPTBot", "ClaudeBot", "CCBot", "Bytespider",
                       "Meta-ExternalAgent", "Amazonbot", "PetalBot"}
    assert by["CCBot"].evidence["class"] == "dataset"
    assert by["GPTBot"].evidence["class"] == "training"
    assert len({f.fingerprint for f in rows}) == len(rows), "one row each, not one row for all"
    assert all(f.evidence["agent"] in f.summary and f.evidence["class"] in f.summary for f in rows)


def test_an_agent_with_no_demand_and_no_consequence_is_not_in_client_output():
    """The addendum's section 4 rule, and where it lives (channel ruling
    20260916-1410).

    The rule prunes the *list*, once, against the operator's Cloudflare view:
    an agent is listed when it showed demand or has consequence. It is not a
    filter over rows — a listed agent keeps its row whatever its class, which
    is the other half asserted here. Without that half the test would pass on
    an engine that had quietly stopped reporting training agents at all.
    """
    listed = {t for t, _ua, _c in UA_MATRIX_AGENTS}
    disallow = "".join(f"User-agent: {a}\nDisallow: /\n\n" for a in PRUNED_AGENTS)
    crawl = CrawlResult(start_url="https://twenty22.test/", tier=Tier.T2,
                        robots_txt="User-agent: *\nAllow: /\n\n" + disallow,
                        robots_status=200)
    rows = [f for f in TechnicalModule()._site_checks(
        crawl, Site(domain="twenty22.test")) if f.check_id == "ai-crawler-blocked"]
    for name in PRUNED_AGENTS:
        assert name not in listed, name
        assert agent_class(name) is None, name
        assert name not in AI_CRAWLERS, name
        assert not any(f.evidence["agent"] == name for f in rows), name
    assert rows == [], "robots.txt named nothing the product reads"

    # The positive half: an agent that showed demand is on the list and its
    # block is a finding, class stated. 39 refused ClaudeBot requests is the
    # addendum's own worked example of a block that costs something.
    kept = _rows()
    assert any(f.evidence["agent"] == "ClaudeBot"
               and f.evidence["class"] == "training" for f in kept), kept


def test_the_check_reads_every_non_search_agent_and_no_search_agent():
    assert set(AI_CRAWLERS) == {t for t, _ua, c in UA_MATRIX_AGENTS if c != "search"}
    assert "Googlebot" not in AI_CRAWLERS and "Bingbot" not in AI_CRAWLERS
    assert "Google-Extended" in AI_CRAWLERS, "a robots token is read in robots.txt"


def test_not_stated_or_allow_keeps_the_high_blocker():
    for policy in (None, "allow"):
        rows = _rows(policy)
        assert rows and all(f.severity is Severity.HIGH for f in rows), policy
        assert all(f.evidence["blocker"] is True for f in rows), policy
    assert "states no AI crawler policy" in _rows(None)[0].summary
    assert "contradicts" in _rows("allow")[0].summary


def test_a_stated_block_is_low_and_not_a_blocker():
    rows = _rows("block")
    assert len(rows) == 7
    assert all(f.severity is Severity.LOW and f.evidence["blocker"] is False for f in rows)
    assert all(f.evidence["ai_crawler_policy"] == "block" for f in rows)
    assert "policy working" in rows[0].summary


def _open_row(conn, site_id, run_id, blocker):
    import json

    from clauditseo.persistence.repo import create_id, now_iso
    with conn:
        conn.execute(
            "INSERT INTO findings (id, run_id, dimension, check_id, severity, source,"
            " summary, affected_urls, fingerprint, created_at, evidence) VALUES (?, ?, 'TEC',"
            " 'ai-crawler-blocked', 'low', 'deterministic', 's', '[]', 'fp1', ?, ?)",
            (create_id(), run_id, now_iso(), json.dumps({"agent": "GPTBot", "blocker": blocker})))
        conn.execute(
            "INSERT INTO finding_states (site_id, fingerprint, state, changed_by_run,"
            " updated_at) VALUES (?, 'fp1', 'open', ?, ?)", (site_id, run_id, now_iso()))

def test_the_policy_is_stored_through_the_site_route_and_refuses_other_words(tmp_path):
    db = tmp_path / "p.db"
    conn = connect(db)
    migrate(conn)
    repo.seed_demo(conn)
    conn.close()
    api = TestClient(create_app(db_path=db))
    client = api.post("/api/clients", json={"name": "C"}).json()
    site_id = api.post(f"/api/clients/{client['id']}/sites", json={"domain": "twenty22.test"}).json()["id"]

    r = api.put(f"/api/sites/{site_id}", json={"ai_crawler_policy": "block",
                                               "ai_field_data_source": "cloudflare"})
    assert r.status_code == 200, r.text
    got = api.get(f"/api/sites/{site_id}").json()
    assert got["ai_crawler_policy"] == "block" and got["ai_field_data_source"] == "cloudflare"
    assert api.put(f"/api/sites/{site_id}", json={"ai_crawler_policy": "maybe"}).status_code == 422
    conn = connect(db)
    from clauditseo.api.app import site_of
    assert site_of(repo.get_site(conn, site_id)).ai_crawler_policy == "block"
    conn.close()


def test_admin_sites_offers_the_policy_as_a_choice():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "dashboard" / "src" / "admin.tsx").read_text(encoding="utf-8")
    at = src.index('value={f.ai_crawler_policy}')
    block = src[at:at + 600]
    for v in ('value=""', 'value="allow"', 'value="block"'):
        assert v in block, v
    assert "ai_field_data_source" in src


def test_every_path_that_runs_the_checks_hands_them_the_whole_site_record(tmp_path):
    """Item 145 BG's twenty22 acceptance run raised HIGH under a stated `block`
    policy: the audit worker built a Site from four fields, so every record
    input the checks read arrived as its default. Verify and section refresh
    built theirs from two."""
    import inspect

    from clauditseo.api import app as _app
    src = inspect.getsource(_app)
    run_audits = src.count("run_audit(")
    assert "site = site_of(repo.site_record(site_row))" in inspect.getsource(_app._execute_run)
    assert src.count("site_of(repo.site_record(site_row)),") == 2, "verify and section refresh"
    assert run_audits >= 3
    # And the record's inputs survive `site_of`, which is what those paths use.
    conn = connect(tmp_path / "s.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site_id = repo.create_site(conn, repo.create_client(conn, op, "T"), "t.test")
    repo.update_site(conn, site_id, ai_crawler_policy="block", url_max_chars="90")
    site = _app.site_of(repo.site_record(repo.get_site(conn, site_id)))
    conn.close()
    assert site.ai_crawler_policy == "block" and site.url_max_chars == "90"


def test_a_scoped_audit_crawl_asks_for_the_ua_matrix():
    import inspect

    from clauditseo.api import app as _app
    assert "ua_matrix=True" in inspect.getsource(_app._execute_run)


def test_the_edge_declaration_names_only_agents_the_matrix_sends(tmp_path):
    db = tmp_path / "e.db"
    conn = connect(db)
    migrate(conn)
    repo.seed_demo(conn)
    conn.close()
    api = TestClient(create_app(db_path=db))
    client = api.post("/api/clients", json={"name": "C"}).json()
    site_id = api.post(f"/api/clients/{client['id']}/sites", json={"domain": "twenty22.test"}).json()["id"]
    record = api.get(f"/api/sites/{site_id}/record").json()
    offered = {a["agent"] for a in record["edge_agents"]}
    assert "ClaudeBot" in offered and "OAI-SearchBot" in offered
    assert "Googlebot" not in offered, "a search agent is not an AI edge block"
    assert "Google-Extended" not in offered, "a robots token is never sent, so no edge refuses it"
    ok = api.put(f"/api/sites/{site_id}", json={"ai_edge_blocked_agents": "ClaudeBot,CCBot"})
    assert ok.status_code == 200, ok.text
    assert api.get(f"/api/sites/{site_id}/record").json()["ai_edge_blocked_agents"] == "ClaudeBot,CCBot"
    for bad in ("Googlebot", "Google-Extended", "NotABot"):
        assert api.put(f"/api/sites/{site_id}", json={"ai_edge_blocked_agents": bad}).status_code == 422, bad


def test_admin_sites_offers_the_edge_declaration_from_the_server_list():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "dashboard" / "src" / "admin.tsx").read_text(encoding="utf-8")
    at = src.index("Blocked at the firewall on purpose")
    block = src[at:at + 1200]
    assert "site.edge_agents" in block and 'type="checkbox"' in block
    assert "OAI-SearchBot" not in src, "the screen keeps no copy of the agent list"
