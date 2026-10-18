"""Generate shows what the generator asks to be checked before sending
(screen audits round 3, Reports UX-01).

`generate()` returns `warnings` - "this report carries the product name...
because no operator name is set", and the plan's refusal - and the Generate
card read `{ id?, path? }` and dropped them. Item 256 had retired the only
other screen that drew them.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from clauditseo.reporting import generate

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"


def test_the_generator_returns_them():
    assert '"warnings": warnings}' in inspect.getsource(generate.generate)


def test_the_card_reads_and_draws_them():
    src = (SRC / "reports.tsx").read_text(encoding="utf-8")
    assert "setWarnings(resp.warnings ?? []);" in src
    assert "<strong>Before you send this:</strong>" in src
    assert ".report-gen-warnings {" in (SRC / "styles.css").read_text(encoding="utf-8")
