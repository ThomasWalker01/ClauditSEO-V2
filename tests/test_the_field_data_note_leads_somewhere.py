"""The Speed part's field-data note names a step that exists, and links it.

Screen audits round 3, Speed US-02 (High): the note said "connect CrUX or
Search Console on Admin › Sites", while the code beside it said no provider
serves that source and the Sites form has no such control. The one action that
would make the vitals real did nothing. What exists is the CrUX key, on
Admin › Provider keys, which gives the vitals their real-user p75.
"""
from __future__ import annotations

import inspect
from pathlib import Path

from clauditseo import secrets
from clauditseo.modules import prf
from clauditseo.persistence import runs

SRC = Path(__file__).resolve().parent.parent / "dashboard" / "src"


def test_the_note_names_the_key_and_carries_its_door():
    src = inspect.getsource(runs)
    assert "\"not connected — connect CrUX or Search Console on \"" not in src
    assert "A CrUX key on Admin › Provider " in src
    assert '"action": {"label": "Provider keys", "href": "#/admin?tab=keys"}' in src
    speed = (SRC / "speed_now.tsx").read_text(encoding="utf-8")
    assert "field.action && (" in speed and "goHandler(field.action.href)" in speed


def test_no_advice_sends_the_reader_to_a_field_source_on_sites():
    assert "connected on \"\n" not in inspect.getsource(prf)
    assert "Admin > Sites (no provider here reads one yet)" not in inspect.getsource(prf)
    # And the key's own line no longer names the retired chat.
    assert all("chat" not in k.purpose for k in secrets.MANAGED if hasattr(k, "purpose"))
