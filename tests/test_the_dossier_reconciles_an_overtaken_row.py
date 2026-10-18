"""The dossier says when an analysis row was overtaken (screen audits round 3,
dossier AC-01 and run views IP-05).

On twenty22's home page the dossier listed `SEC/cms-user-enumeration` as
"open · analysed 23 Sept" directly above "fixed · measured 2 Oct": the model's
row and the sweep's, each with its own state. The record had already marked
the model row overtaken (`superseded_on`), and the part page said so; the
dossier did not carry the field.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from clauditseo.persistence import runs

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"


def test_the_payload_carries_the_reconciling_fields():
    src = inspect.getsource(runs.page_dossier)
    assert '"superseded_on": st.get("superseded_on")' in src
    assert '"unseen_since": st.get("unseen_since")' in src


def test_the_screen_says_overtaken_not_the_row_s_own_state():
    src = (SRC / "dossier.tsx").read_text(encoding="utf-8")
    assert "overtaken: the automatic checks cleared it {day(f.superseded_on)}" in src
    assert "not seen by the automatic checks since {day(f.unseen_since)}" in src
