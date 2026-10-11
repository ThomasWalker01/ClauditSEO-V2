"""The Analyses shop says one price per row and one state per part (screen
audits round 3, shop AC-02, IP-02, IP-03, UI-01).

- AC-02: the Est. column showed the estimate at the model that would run
  (`est_cost_default`) and the run control quoted the median of past runs at
  whatever ran them (`est_cost`): USD 0.04 against ~0.08 on Indexability, and
  so on for all twenty rows.
- IP-02: "seen once" on the part headers counted the candidates that wait for
  the operator too: 76 rows the Record offers Confirm on.
- IP-03: a header's dot said "analysed" over rows saying "not read" when the
  analysis read an earlier audit.
- UI-01: the dots drew as 4 px slivers inside table cells.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from clauditseo.persistence import runs

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"


def test_the_control_quotes_the_column_s_figure():
    src = (SRC / "catalogue.tsx").read_text(encoding="utf-8")
    assert src.count("<SpendButton price={x.est_cost_default ?? x.est_cost ?? null}") == 2
    assert "x.est_cost ?? x.est_cost_default" not in src


def test_seen_once_and_to_confirm_are_counted_apart():
    src = inspect.getsource(runs.anatomy_view)
    assert 'if r["fingerprint"] in awaiting:' in src
    assert '"to_confirm": count(to_confirm.get(c.key, 0), "record"),' in src
    shop = (SRC / "catalogue.tsx").read_text(encoding="utf-8")
    assert "pops={a.data?.populations ?? null} /> to confirm</>" in shop


def test_a_row_read_on_an_earlier_audit_says_so():
    src = (SRC / "catalogue.tsx").read_text(encoding="utf-8")
    assert "audit${earlier.audits_since === 1 ? \"\" : \"s\"} ago`" in src


def test_the_dot_is_a_block_inside_a_cell():
    css = (SRC / "styles.css").read_text(encoding="utf-8")
    assert ".cat-dot { display: inline-block; width: 10px; height: 10px;" in css
