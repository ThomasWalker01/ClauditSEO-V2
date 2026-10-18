"""Two costs the anatomy view carried on every request, each held by a guard.

`LATEST_FINDING` is a correlated subquery run once per finding state, four
times per anatomy request. Without an index ordered by `created_at` under the
fingerprint, SQLite sorted each fingerprint's rows in a temporary B-tree every
time (migration 0060). And the view parsed every finding's evidence for five
small fields, 334 KB of it on an accessibility coverage row that names none of
them (`_view_evidence`).
"""

import json

from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import runs


def test_the_latest_finding_subquery_uses_the_index_and_sorts_nothing(tmp_path):
    conn = connect(tmp_path / "t.db")
    migrate(conn)
    sql = (f"SELECT f.rowid FROM finding_states fs"
           f" JOIN findings f ON f.rowid = ({runs._latest_finding()})"
           f" WHERE fs.site_id = ?")
    plan = [row[3] for row in conn.execute("EXPLAIN QUERY PLAN " + sql, ("s",))]
    conn.close()
    assert any("idx_findings_fingerprint_created" in step for step in plan), plan
    assert not any("TEMP B-TREE" in step for step in plan), plan


def _fields(ev):
    marks = runs._contract_marks(ev)
    return (repr(runs._outline_index(ev)), repr(runs._evidence_key(ev, "block")),
            repr(marks["contract"]), repr(marks["brief_status"]), repr(marks["brief"]))


def test_the_view_reads_the_same_fields_whether_or_not_it_parses():
    big = json.dumps({"engine": "axe", "text_blocks": ["words " * 50] * 1000})
    cases = [
        None, "", "not json", "[]", "3", "{}", big,
        json.dumps({"outline_index": 2, "contract": 1, "status": "held",
                    "from_brief": "a11y", "block": {"id": 3}}),
        json.dumps({"outline_index": True}), json.dumps({"outline_index": 1.0}),
        json.dumps({"contract": 0, "status": "x"}), json.dumps({"block": None}),
        '{"contract": 1, "contract": 0}', '{"status": NaN, "contract": 1}',
        # A value naming a key is not the key: parsed, and still read right.
        json.dumps({"note": 'the "contract" was absent'}),
    ]
    for evidence in cases:
        assert _fields(runs._view_evidence(evidence)) == \
            _fields(runs._finding_evidence(evidence)), evidence


def test_text_naming_none_of_the_fields_is_not_parsed(monkeypatch):
    def _parse(_):
        raise AssertionError("parsed evidence that names no field the view reads")

    monkeypatch.setattr(runs, "_finding_evidence", _parse)
    assert runs._view_evidence(json.dumps({"text_blocks": ["x"] * 10})) == {}
