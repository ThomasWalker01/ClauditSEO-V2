"""History chat: a read-only conversational view over the API's own queries.

Deliberately deterministic in v1 — the question routes to real queries
(regressions, trend, latest run) and the answer is composed from their
results, citing the runs it drew from. It can never mutate data, and every
claim is grounded in a query result. An LLM-phrased upgrade can wrap this
later without changing the grounding.
"""

from __future__ import annotations

import sqlite3

from clauditseo.persistence import runs


def answer(conn: sqlite3.Connection, site_id: str, question: str) -> dict:
    q = question.lower()
    if "regress" in q:
        return _regressions(conn, site_id)
    if "trend" in q or "score" in q or "improv" in q:
        return _trend(conn, site_id)
    if "open" in q or "outstanding" in q or "issues" in q:
        return _open_issues(conn, site_id)
    return _latest(conn, site_id)


def _regressions(conn, site_id) -> dict:
    states = [s for s in runs.site_states(conn, site_id) if s["state"] == "regressed"]
    if not states:
        return {"answer": "No regressions on record for this site — nothing previously "
                          "fixed has reappeared.", "cited_runs": []}
    cited = sorted({s["changed_by_run"] for s in states if s["changed_by_run"]})
    lines = [f"{len(states)} regression(s) on record:"]
    for s in states:
        lines.append(f"- [{s['severity']}] {s['dimension']}/{s['check_id']}: "
                     f"{s['summary']} (reappeared in run {s['changed_by_run'][:8]}, "
                     f"{s['updated_at'][:10]})")
    return {"answer": "\n".join(lines), "cited_runs": cited}


def _trend(conn, site_id) -> dict:
    trend = runs.site_trend(conn, site_id)
    # `site_readings`, because the sentence built below puts a run count and
    # `complete[0]`'s score beside `site_trend`, and only audits write to the
    # trend. Reading the whole history here made the two halves of one answer
    # describe different populations.
    all_runs = runs.site_readings(conn, site_id)
    complete = [r for r in all_runs if r["status"] in runs.AUDITED_STATUSES]
    if not trend or not complete:
        return {"answer": "No completed runs yet, so there is no trend to report.",
                "cited_runs": []}
    first, last = trend[0], trend[-1]
    direction = ("improved" if last["value"] > first["value"]
                 else "declined" if last["value"] < first["value"] else "held steady")
    # The latest run can have no composite even when the trend has points:
    # trend rows come from scored runs only, so an unscorable run sits at the
    # head of `complete` with nothing to format. `:.1f` raised TypeError here.
    from clauditseo.reporting.render import composite_phrase

    latest_score = complete[0]["composite_score"]
    latest = (f"Latest run {complete[0]['id'][:8]} scored "
              f"{composite_phrase(latest_score)}." if latest_score is not None
              else f"Latest run {complete[0]['id'][:8]}: "
                   f"{composite_phrase(latest_score)}")
    return {
        "answer": (f"Across {len(trend)} run(s) the composite score {direction}: "
                   f"{first['value']:.1f} ({first['captured_at'][:10]}) to "
                   f"{last['value']:.1f} ({last['captured_at'][:10]}). "
                   + latest),
        "cited_runs": [complete[-1]["id"], complete[0]["id"]],
    }


def _open_issues(conn, site_id) -> dict:
    states = [s for s in runs.site_states(conn, site_id)
              if s["state"] in ("open", "regressed")]
    if not states:
        return {"answer": "No open findings — everything previously found is fixed or "
                          "accepted.", "cited_runs": []}
    cited = sorted({s["changed_by_run"] for s in states if s["changed_by_run"]})
    by_sev: dict[str, int] = {}
    for s in states:
        by_sev[s["severity"]] = by_sev.get(s["severity"], 0) + 1
    parts = ", ".join(f"{n} {sev}" for sev, n in sorted(by_sev.items()))
    return {"answer": f"{len(states)} open finding(s): {parts}.", "cited_runs": cited}


def _latest(conn, site_id) -> dict:
    # "What is the latest run" is a question about the site, so the answer is
    # the latest run that speaks for it. Reproduced against the live database
    # before this line changed: the History chat answered "Latest run d4474b38
    # scored 86.2" for a site whose newest audit scored 70.52.
    complete = [r for r in runs.site_readings(conn, site_id)
                if r["status"] in runs.AUDITED_STATUSES]
    if not complete:
        return {"answer": "No completed runs for this site yet.", "cited_runs": []}
    from clauditseo.reporting.render import composite_phrase

    r = complete[0]
    score = r["composite_score"]
    tail = (f"with composite score {composite_phrase(score)}."
            if score is not None else f"with {composite_phrase(score)}")
    return {
        "answer": (f"Latest run {r['id'][:8]} ({r['tier']}, "
                   f"{', '.join(r['dimensions'])}) finished {r['finished_at'][:10]} "
                   + tail),
        "cited_runs": [r["id"]],
    }
