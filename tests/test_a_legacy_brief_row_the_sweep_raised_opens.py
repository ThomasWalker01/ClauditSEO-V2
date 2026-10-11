"""A legacy brief's row the automatic checks raised opens on first sight
(item 278, row 10).

The four local briefs file through `record_expert_findings` and are walked by
`recompute_expert_states`, which had no corroboration branch: Local's one row
wore "automatic checks 1" and "candidate" together. Where the automatic
checks raised the same check in the same run, the row is measured, and opens.
A code no automatic check raised still waits as a candidate (item 237).
"""

from __future__ import annotations

import inspect

from clauditseo.persistence import runs


def test_the_walk_reads_the_sweep():
    src = inspect.getsource(runs.recompute_expert_states)
    assert "\"SELECT DISTINCT check_id FROM findings WHERE run_id=? AND source='deterministic'\"" in src
    assert "if present and code in swept_by_run[run]:" in src
    assert '{None: "open", "candidate": "open", "open": "open",' in src
