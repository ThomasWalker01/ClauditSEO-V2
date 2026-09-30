"""Re-judge a stored brief's contract under the parser's rules as they now
stand, without a model call (brief v12 step AL).

    python scripts/reparse_contract.py <run_id> <tool_id>

Reads the stored contract's rows back, runs the rules over them (the
`[TO CONFIRM` rows to not_assessable, the alignment rows without their
inputs likewise, the replacements outside bounds or with the wrong
separator dropped with a reason), and rewrites the report row, the
record's findings and the states. Prints what changed.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clauditseo.analysts.expert import reparse_contract      # noqa: E402
from clauditseo.config import settings                       # noqa: E402
from clauditseo.db.connection import connect                 # noqa: E402
from clauditseo.persistence import repo                      # noqa: E402
from clauditseo.persistence.runs import expert_report        # noqa: E402


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    run_id, tool_id = sys.argv[1], sys.argv[2]
    conn = connect(settings().db_path)
    run = conn.execute("SELECT site_id FROM audit_runs WHERE id=?", (run_id,)).fetchone()
    if not run:
        print(f"no run {run_id}")
        return 1
    from clauditseo.api.app import site_of
    site = site_of(repo.site_record(repo.get_site(conn, run["site_id"])))
    before = (expert_report(conn, run_id, tool_id) or {}).get("contract") or {}
    after = reparse_contract(conn, run_id, tool_id, site)
    print(f"{tool_id} on {run_id}")
    print(f"  rows        {len(before.get('rows') or []):4} -> {len(after.get('rows') or []):4}")
    print(f"  dropped     {len(before.get('dropped') or []):4} -> {len(after.get('dropped') or []):4}")
    print(f"  not_assess. {len(before.get('not_assessable') or []):4} -> {len(after.get('not_assessable') or []):4}")
    print(f"  uncovered   {len(before.get('uncovered') or []):4} -> {len(after.get('uncovered') or []):4}")
    for d in after.get("dropped") or []:
        row = d.get("row") or {}
        print(f"  dropped: {d['reason']} :: {row.get('check')} {row.get('page')}")
    for n in after.get("not_assessable") or []:
        print(f"  not assessable: {n.get('check')} {n.get('page')} needs {n.get('needs')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
