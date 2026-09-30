"""Reopen the analysis rows an audit closed without reading them (item 223).

`_apply_states` cleared every open row of an audited dimension whose
fingerprint the run did not emit. A brief row's fingerprint is its own
(`brief_fingerprint`) and no sweep emits it, so every audit that did not run
the brief closed that brief's rows - on twenty22 the ONP-only T2 of
2026-09-23 moved 36 title-desc rows to `fixed` while re-raising the same
check on the same pages, and the part page lost their replacements.

The rule is corrected in `_apply_states`. This repairs what it already wrote,
and only that: a `fixed` analysis row is reopened when the run that closed it
did not run its brief AND either the check is one only a model can raise, or
that run's own sweep raised the same check on the row's page. A row a sweep
closed because it stopped raising the check there - the corroborating reading
gone - is what the corrected rule would still close, so it is left.

`open`, because only open and regressed rows reach the clearing pass and
which of the two it was is not recorded; `changed_by_run` is the brief run
that wrote the row, so the state still reads as a run's and not the
operator's. Idempotent: a reopened row is no longer `fixed`.
"""

import json
import logging

log = logging.getLogger(__name__)


def apply(conn) -> None:
    from clauditseo.persistence.runs import _check_cost, _page_key

    rows = conn.execute(
        "SELECT s.site_id, s.fingerprint, s.changed_by_run, f.run_id, f.dimension,"
        " f.check_id, f.affected_urls, json_extract(f.evidence, '$.from_brief') AS tool"
        " FROM finding_states s JOIN findings f ON f.fingerprint = s.fingerprint"
        " JOIN audit_runs a ON a.id = f.run_id AND a.site_id = s.site_id"
        " WHERE s.state = 'fixed' AND f.source = 'model-judgement'"
        " AND json_extract(f.evidence, '$.contract') = 1"
        " AND s.changed_by_run IS NOT NULL AND s.changed_by_run != f.run_id").fetchall()
    swept: dict[str, set] = {}
    reopened = 0
    for r in rows:
        closer = r["changed_by_run"]
        if conn.execute("SELECT 1 FROM expert_reports WHERE run_id=? AND tool_id=?",
                        (closer, r["tool"])).fetchone():
            continue
        if closer not in swept:
            swept[closer] = {
                (f["check_id"], _page_key(u))
                for f in conn.execute("SELECT check_id, affected_urls FROM findings"
                                      " WHERE run_id=? AND source='deterministic'", (closer,))
                for u in json.loads(f["affected_urls"] or "[]")}
        urls = json.loads(r["affected_urls"] or "[]")
        model_only = _check_cost(f"{r['dimension']}/{r['check_id']}") != "free"
        re_raised = any((r["check_id"], _page_key(u)) in swept[closer] for u in urls)
        if not (model_only or re_raised):
            continue
        conn.execute("UPDATE finding_states SET state='open', changed_by_run=?"
                     " WHERE site_id=? AND fingerprint=? AND state='fixed'",
                     (r["run_id"], r["site_id"], r["fingerprint"]))
        reopened += 1
    log.info("0065: reopened %d analysis rows an audit closed without reading them", reopened)
