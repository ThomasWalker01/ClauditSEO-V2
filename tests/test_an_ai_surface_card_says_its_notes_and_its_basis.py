"""An AI surface card says the model's note and what its criteria read
(screen audits round 4, AI surface US-02, AC-03, IP-05).

The home page's proposed passage named the business "Twenty22", and the
stored note said the brand field is not supplied and the name is a naming
assumption; the card drew `current || note`, so the note never reached the
screen. The four criteria sat under the passage unlabelled and read the
page as it stands ("named subject: no" under a passage that names it). And
the accounting said "15 dropped" beside "20 dropped" on two lines above.
"""
from __future__ import annotations

import inspect
from pathlib import Path

from clauditseo.persistence import runs

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"


def test_the_record_carries_the_models_note():
    src = inspect.getsource(runs.site_states)
    assert 'd["analysis_note"] = note.strip()' in src


def test_the_card_draws_the_note_and_labels_the_passage():
    a = (SRC / "ai_surface.tsx").read_text(encoding="utf-8")
    assert "Analysis note: {fix.analysisNote}" in a
    assert '<span className="fix-lbl">Change: </span>' in a
    assert "The page as it stands:" in a
    p = (SRC / "part_page.tsx").read_text(encoding="utf-8")
    assert 'analysisNote: word === "brief" ? s.analysis_note ?? null : null' in p


def test_the_accounting_states_the_one_dropped_count():
    p = (SRC / "part_page.tsx").read_text(encoding="utf-8")
    assert '{dropped + alsoHeld} dropped' in p
    assert "of them rows for checks it held" in p
