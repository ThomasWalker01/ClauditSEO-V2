"""Item 183, UI audit 03-6, channel ruling 20260918-0410: one model for what a
scan is, and the registry says what the engine does.

Quick / Standard / Deep had three definitions. The registry defined them by
breadth ("every page the crawl can reach") and stamped each with an engine tier;
the scan grid defines them by judgement, with breadth on its other axis; the
launcher's radios added a fourth word. The ruling: the registry was wrong about
the code. `scanscope.depth_settings` returns `{analyst, model_tier}` and nothing
about pages; `SCOPES` owns the page budget; `tier_for_scope` derives the crawler
tier from the SCOPE. So depth is judgement, scope is breadth, and the tier is the
scope's consequence, never a choice.

These hold the three claims that came out of it: the registry's words are the
module's own strings, the engine tier is recorded against the scope and not the
depth, and no screen that configures or sells a scan offers a tier.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from clauditseo import scanscope

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "dashboard" / "src"
ENTRIES = {e["id"]: e for e in json.loads(
    (ROOT / "clauditseo" / "glossary.json").read_text(encoding="utf-8"))["entries"]}


def test_the_registry_reads_the_modules_own_words():
    """Copied, not paraphrased: one string, one place."""
    for key, d in scanscope.DEPTHS.items():
        e = ENTRIES[f"depth-{key}"]
        assert e["word"] == d["label"], (key, e["word"])
        assert e["full"].startswith(d["what"]), (key, e["full"][:80], d["what"])
    for key, sc in scanscope.SCOPES.items():
        e = ENTRIES[f"scope-{key}"]
        assert e["word"] == sc.label, (key, e["word"])
        # The module's em dash reads as a comma in a sentence; the claim is the
        # same words in the same order.
        assert e["full"].startswith(sc.what.replace(" — ", ", ")), (key, e["full"][:90])


def test_the_engine_tier_is_recorded_against_the_scope_not_the_depth():
    """`tier_for_scope` decides it. A tier on a depth entry is the false mapping
    that produced 03-6, in the field code is most likely to read."""
    for key in scanscope.DEPTHS:
        assert "engine" not in ENTRIES[f"depth-{key}"], key
    for key in scanscope.SCOPES:
        tier = scanscope.tier_for_scope(key)
        assert ENTRIES[f"scope-{key}"]["engine"] == getattr(tier, "value", str(tier)), key


def test_depth_settings_say_nothing_about_pages_and_scopes_say_nothing_about_models():
    """The premise the ruling verified, asserted here so it cannot drift back."""
    for key in scanscope.DEPTHS:
        assert set(scanscope.depth_settings(key)) <= {"analyst", "model_tier"}, key
    for key, sc in scanscope.SCOPES.items():
        assert not hasattr(sc, "model_tier") and not hasattr(sc, "analyst"), key


#: Screens that configure or sell a scan. A tier is a consequence of the scope,
#: so offering one offers a control that does not exist.
SELLING = ("scanmatrix.tsx", "views.tsx", "client_lanes.tsx", "selection.tsx")


def _code(path: Path) -> list[str]:
    text = re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.S)
    return [ln for ln in text.splitlines() if not ln.strip().startswith(("//", "{/*", "*"))]


def test_no_purchase_screen_offers_a_tier_as_a_choice():
    offered = []
    for name in SELLING:
        for ln in _code(SRC / name):
            # A tier drawn as a word a reader chooses by. The tier a request
            # carries is data (`tier: "T2"`), and `tier === "T2"` is code
            # deciding on it; what this refuses is a tier in a label, an option
            # or a heading.
            if re.search(r'>\s*\{?\s*"?T[123]"?\s*\}?\s*<|"\s*T[123]\s*(?:—|-)', ln):
                offered.append(f"{name}: {ln.strip()[:90]}")
    assert not offered, "a screen offers an engine tier as a choice:\n" + "\n".join(offered)


def test_a_stored_run_still_carries_its_tier():
    """Kept as the receipt, for the reason the delta rule needs: a score is
    compared against the previous audit of the same tier."""
    app = (ROOT / "clauditseo" / "api" / "app.py").read_text(encoding="utf-8")
    assert "AND tier=? AND composite_score > 0" in app
    lanes = (SRC / "client_lanes.tsx").read_text(encoding="utf-8")
    assert "run.tier" in lanes or "tier" in lanes
