"""The Pages pane says which pages carry the problems.

Screen audits round 3, Pages US-01 (High): the pane was a URL filter and a
dropdown of 45 URLs. The endpoint returned title, words and depth and nothing
drew them, and no count of findings per page existed, so "which pages carry
the problems" took 45 dossiers to answer.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from clauditseo.persistence import runs

ROOT = Path(__file__).resolve().parent.parent


def test_open_findings_are_counted_per_page_at_their_worst(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE rows (affected_urls TEXT, severity TEXT)")
    conn.executemany("INSERT INTO rows VALUES (?, ?)", [
        (json.dumps(["https://gate-six.test/", "https://gate-six.test/a/"]), "medium"),
        (json.dumps(["https://gate-six.test/"]), "critical"),
        (json.dumps(["https://gate-six.test/a/?utm=x"]), "low"),
    ])
    real = conn.execute

    class Conn:
        row_factory = sqlite3.Row

        def execute(self, sql, params=()):
            assert "state IN ('open','regressed')" in sql and "NOT " in sql
            return real("SELECT affected_urls, severity FROM rows")

    got = runs.open_by_page(Conn(), "site")
    assert got == {"/": {"open": 2, "worst": "critical"},
                   "/a/": {"open": 2, "worst": "medium"}}, got


def test_the_route_carries_the_counts_and_the_pane_draws_them():
    app = (ROOT / "clauditseo" / "api" / "app.py").read_text(encoding="utf-8")
    route = app[app.index('@app.get("/api/runs/{run_id}/pages")'):]
    route = route[:route.index("@app.", 1)]
    assert "runs.open_by_page(conn, run[\"site_id\"])" in route
    assert 'p["open"] = got.get("open", 0)' in route
    views = (ROOT / "dashboard" / "src" / "views.tsx").read_text(encoding="utf-8")
    assert "<h4 className=\"pages-table-head\">Pages by open findings</h4>" in views
    for col in ("<th>Title</th>", '<th className="num">Words</th>',
                '<th className="num">Depth</th>', '<th className="num">Open</th>'):
        assert col in views, col
    assert "(b.open ?? 0) - (a.open ?? 0)" in views
