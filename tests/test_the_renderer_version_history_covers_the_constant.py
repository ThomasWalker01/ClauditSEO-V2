"""The in-source renderer version history covers the version it annotates.

CQ-17 has said since it was raised that *"renderer version history lives in a
comment nothing verifies"*, and CQ-180 is the first time that risk arrived:
`40e45a2`'s successor bumped `RENDERER_VERSION` to `1.24.0` and left the block
immediately above it describing `1.23.0`, while `CHANGELOG.md` carried a full
1.24.0 entry — so the two records of one fact disagreed about whether 1.24.0
existed.

The block is not decoration. `renderer_version` is stamped on every stored
deliverable, and it is the field the Deliverables screen turns into *"written
by an older report renderer"* (WF-93). A maintainer asking what a stored
`1.23.0` document gets wrong reads this block and nothing else; when the block
stops a version short, the newest documents are the ones it cannot answer for.

**Narrow on purpose: the current version, not every version.** Enumerated from
source rather than assumed — the block carries eleven `X.Y.Z:` paragraphs and
the constant has reached 1.24.0, so 1.7.0, 1.10.0 and 1.20.0 among others have
no paragraph and never did. A contiguity assertion would go red on all of them
at once, and the only way to green it would be to write history for versions
nobody can now reconstruct. Inventing a record is the exact failure this block
exists to prevent, so the rule is the one that can be honoured going forward:
*whatever `RENDERER_VERSION` is today, the block says what changed.*

**Non-vacuity is a positive control plus a floor.** The detector is run against
a synthetic block known to breach and one known to be clean, because a check
drawing its evidence from the thing it checks can only ever pass (DISCIPLINE
rule 5); and the real block's paragraph count is floored, because a regex that
stopped matching would make the assertion below true about nothing.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RENDER_PY = ROOT / "clauditseo" / "reporting" / "render.py"

#: A version-history paragraph: a `#:` comment line opening with the version it
#: describes. The block's own convention since 1.1.0, and the shape a reader
#: scans for.
_PARAGRAPH = re.compile(r"^#: (\d+\.\d+\.\d+):", re.M)
_CONSTANT = re.compile(r'^RENDERER_VERSION = "([^"]+)"', re.M)


def _split(source: str) -> tuple[str, str]:
    """The comment block, and the version constant it annotates.

    Split on the constant's own assignment so the block is *everything above
    it* — a paragraph added below the constant would not be found by a reader
    scrolling up to it either.
    """
    match = _CONSTANT.search(source)
    assert match, "RENDERER_VERSION is no longer assigned as a bare string literal"
    return source[: match.start()], match.group(1)


def _documented(block: str) -> list[str]:
    return _PARAGRAPH.findall(block)


def test_the_detector_flags_a_block_that_stops_short():
    """The positive control: CQ-180's own shape, on source this file owns."""
    block, version = _split(
        '#: 1.22.0: something.\n'
        '#: 1.23.0: something else.\n'
        'RENDERER_VERSION = "1.24.0"\n'
    )
    assert version == "1.24.0"
    assert version not in _documented(block), (
        "the detector found a 1.24.0 paragraph in a block that has none")


def test_the_detector_leaves_a_covered_block_alone():
    """The must-not-change direction. The repaired shape has to read clean, or
    the fix cannot land and this guard is a refusal rather than a rule."""
    block, version = _split(
        '#: 1.23.0: something else.\n'
        '#: 1.24.0: the newest thing.\n'
        'RENDERER_VERSION = "1.24.0"\n'
    )
    assert version in _documented(block)


def test_the_block_is_still_being_parsed():
    """The floor. Eleven paragraphs were counted when this guard was written;
    a regex that stopped matching, or a block that moved below the constant,
    would make the assertion below true about nothing."""
    block, _ = _split(RENDER_PY.read_text(encoding="utf-8"))
    found = _documented(block)
    assert len(found) >= 10, (
        f"only {len(found)} version paragraphs were parsed out of "
        f"{RENDER_PY.name} ({found}); the block's convention has changed and "
        "the assertion below is not testing anything"
    )


def test_the_history_says_what_the_current_version_changed():
    """CQ-180, and the mechanism half of CQ-17.

    `renderer_version` is stamped on every stored deliverable and is what the
    Deliverables screen reads to offer a regenerate. A constant the block
    cannot answer for makes that offer unexplainable.
    """
    block, version = _split(RENDER_PY.read_text(encoding="utf-8"))
    documented = _documented(block)
    assert version in documented, (
        f"RENDERER_VERSION is {version} and the version-history block above it "
        f"documents {documented[-1] if documented else 'nothing'} as its "
        "newest - so a maintainer asking what a document written by the "
        "current renderer says differently has nowhere to read it. Add a "
        f"`#: {version}: ...` paragraph stating what documents written by the "
        "previous version get wrong."
    )
