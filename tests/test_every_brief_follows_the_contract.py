"""Every conforming brief follows the contract's layout (brief v11 step AH,
`clauditseo/prompts/_CONTRACT.md`): a header with id, name, part, scope,
tier and checks; a `## Block 1 — findings` section before `## Block 2 —
readable`; Block 2's five headings in order; and none of the things a
prompt never says - a clarifier gate, "stop and wait", phase narration, a
closing offer. A legacy prompt, one whose header lists no checks, is
exempt until it is rewritten, and says so by name.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from clauditseo import briefs

PROMPTS = Path(__file__).resolve().parents[1] / "clauditseo" / "prompts"
FILES = sorted(p for p in PROMPTS.glob("*.md") if not p.name.startswith("_"))

BLOCK_1 = re.compile(r"^## Block 1 — findings", re.M)
BLOCK_2 = re.compile(r"^## Block 2 — readable", re.M)
HEADINGS = ("— assessment", "— patterns only", "### Patterns", "### Not assessable", "### Out of scope")
NEVER = ("CLARIFY", "stop and wait", "Phase 1", "Want me to")


def test_the_contract_file_is_installed_and_is_not_a_brief():
    assert (PROMPTS / "_CONTRACT.md").is_file()
    assert "_CONTRACT" not in {b.id for b in briefs.catalogue()}
    assert not any(p.name.startswith("_") for p in FILES)


@pytest.mark.parametrize("path", FILES, ids=[p.stem for p in FILES])
def test_a_brief_with_checks_follows_the_layout(path: Path):
    header, body = briefs.split_front_matter(path.read_text(encoding="utf-8"))
    assert header is not None, f"{path.name}: no front matter"
    for key in ("id", "name", "part", "scope", "tier", "checks"):
        assert key in header, f"{path.name}: header lacks `{key}`"
    if not header["checks"]:
        pytest.skip(f"{path.name} is a legacy prompt: its header lists no checks, so it is "
                    "exempt from the contract until it is rewritten")
    one = BLOCK_1.search(body)
    two = BLOCK_2.search(body)
    assert one and two and one.start() < two.start(), (
        f"{path.name}: Block 1 — findings must precede Block 2 — readable")
    tail = body[two.start():]
    positions = [tail.find(h) for h in HEADINGS]
    assert all(p >= 0 for p in positions), (
        f"{path.name}: Block 2 lacks {[h for h, p in zip(HEADINGS, positions) if p < 0]}")
    assert positions == sorted(positions), f"{path.name}: Block 2's headings are out of order"
    for word in NEVER:
        assert word not in body, f"{path.name} says {word!r}, which a conforming brief never does"
    assert "```json" in body, f"{path.name}: Block 1 is not a fenced JSON block"
