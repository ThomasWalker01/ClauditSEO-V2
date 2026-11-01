"""Three false readings the blocked audit of 31 Oct showed up.

`http-redirect` counted the URLs of a redirect chain, so the one clean redirect
every HTTPS site has read as two hops. `cert-san` asked one certificate about
two names, on a platform that gives each name its own. And a crawl a firewall
answered reached `watch_changes` as a critical change to robots.txt, while the
header called a site with a scored nav scan one with no scored audit.
"""
from __future__ import annotations

import json
import sqlite3

from clauditseo.crawler import transport
from clauditseo.crawler.types import CrawlResult, Page, TransportProbe
from clauditseo.engine.types import Tier
from clauditseo.modules import sec
from clauditseo.persistence import runs

START = "https://www.shop.test/"


def _sec(probe):
    page = Page(url=START, requested_url=START, status=200, headers={},
                content="<html></html>", content_type="text/html")
    crawl = CrawlResult(start_url=START, tier=Tier.T2, pages=[page])
    crawl.transport = probe
    return {f.check_id: f for f in sec.SecurityModule().run([], Tier.T2,
                                                           {"crawl": crawl, "site": None})}


def test_one_redirect_is_one_hop():
    probe = TransportProbe(host="www.shop.test", http_redirects_to_https=True,
                           http_redirect_chain=["http://www.shop.test/", START])
    assert "http-redirect" not in _sec(probe)


def test_two_redirects_are_two_hops():
    probe = TransportProbe(host="shop.test", http_redirects_to_https=True,
                           http_redirect_chain=["http://shop.test/", "https://shop.test/", START])
    assert "in 2 hops, not one" in _sec(probe)["http-redirect"].summary


def test_a_name_with_its_own_certificate_is_covered():
    probe = TransportProbe(host="www.shop.test", cert_subject_alt_names=["www.shop.test"],
                           cert_own_hosts=["shop.test"])
    assert "cert-san" not in _sec(probe)


def test_a_name_with_no_certificate_of_its_own_stays_uncovered():
    probe = TransportProbe(host="www.shop.test", cert_subject_alt_names=["www.shop.test"])
    assert _sec(probe)["cert-san"].evidence["uncovered"] == ["shop.test"]


def test_only_the_name_left_out_is_asked(monkeypatch):
    asked = []
    monkeypatch.setattr(transport, "_own_certificate",
                        lambda host, port: asked.append(host) or True)
    probe = TransportProbe(host="www.shop.test", cert_subject_alt_names=["www.shop.test"])
    transport._sibling_certificates("www.shop.test", 443, probe)
    assert asked == ["shop.test"] and probe.cert_own_hosts == ["shop.test"]

    asked.clear()
    both = TransportProbe(host="www.shop.test",
                          cert_subject_alt_names=["shop.test", "*.shop.test"])
    transport._sibling_certificates("www.shop.test", 443, both)
    assert asked == [] and both.cert_own_hosts == []


def _db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE audit_runs (id TEXT, site_id TEXT, kind TEXT, status TEXT,"
                 " tier TEXT, composite_score REAL, started_at TEXT, crawl_evidence TEXT,"
                 " crawled_paths TEXT)")
    return conn


def _run(conn, run_id, day, status="complete", score=70.0, **evidence):
    conn.execute("INSERT INTO audit_runs VALUES (?, 's', 'audit', ?, 'T2', ?, ?, ?, ?)",
                 (run_id, status, score, f"2026-10-{day:02d}T08:00:00+00:00",
                  json.dumps({"robots_status": 200, "robots_txt": "User-agent: *", **evidence}),
                  json.dumps(["/", "/a"])))


CHECKPOINT = {"vendor": "Vercel", "title": "Vercel Security Checkpoint", "status": 403,
              "url": START, "at": "robots"}


def test_a_firewall_answer_is_no_change_to_robots():
    conn = _db()
    _run(conn, "good", 1)
    _run(conn, "refused", 2, status="blocked", robots_status=403, robots_txt="",
         edge_challenge=CHECKPOINT)
    assert runs.watch_changes(conn, "s") == []


def test_the_crawls_either_side_of_a_firewall_answer_are_compared():
    conn = _db()
    _run(conn, "before", 1)
    _run(conn, "refused", 2, status="blocked", robots_status=403, edge_challenge=CHECKPOINT)
    _run(conn, "after", 3, robots_status=404)
    assert [a["what"] for a in runs.watch_changes(conn, "s")] == ["robots.txt HTTP status"]


def test_a_blocked_run_with_no_firewall_still_alerts():
    conn = _db()
    _run(conn, "good", 1)
    _run(conn, "shut", 2, status="blocked", robots_status=503)
    assert [a["severity"] for a in runs.watch_changes(conn, "s")] == ["critical"]


def test_the_header_is_told_of_the_scored_audit_and_the_refusal():
    conn = _db()
    _run(conn, "nav", 1)
    _run(conn, "refused", 2, status="blocked", score=82.0)
    got = runs.audit_standing(conn, "s")
    assert got["newest_blocked"] is True
    assert got["narrow_audit"]["run_id"] == "nav" and got["narrow_audit"]["pages"] == 2


def test_a_site_with_no_audit_has_nothing_to_tell():
    assert runs.audit_standing(_db(), "s") == {"newest_blocked": False, "narrow_audit": None}
