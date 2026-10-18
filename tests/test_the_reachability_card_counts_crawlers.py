"""The reachability card counts crawlers, and captions classes from the
registry (item 267, row 12).

"17 of 19 AI crawlers measured" counted two robots tokens, which nothing
visits under; the classes carried a caption of their own beside a legend
defining the same words. The lead now reads "17 of 17 crawlers measured · 2
robots tokens", and each class's caption is its glossary entry's first
sentence.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "dashboard" / "src" / "ai_surface.tsx"


def test_tokens_are_not_crawlers():
    src = SRC.read_text(encoding="utf-8")
    assert "const crawlers = now.rows.filter((r) => !r.robots_token);" in src
    assert "robots token${tokens === 1 ? \"\" : \"s\"}" in src


def test_every_class_caption_is_a_registry_sentence():
    src = SRC.read_text(encoding="utf-8")
    assert "{short(entry(`agent-${cls}`))}" in src
    ids = {e["id"] for e in json.loads((ROOT / "clauditseo" / "glossary.json").read_text(
        encoding="utf-8"))["entries"]}
    for cls in ("dataset", "training", "index", "answer-time"):
        assert f"agent-{cls}" in ids, cls
