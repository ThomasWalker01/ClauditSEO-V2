"""One tone per meaning (item 140).

The dashboard used to bind a colour to a component: the same amber meant
severity Medium, state open and an open count; the same green meant free,
enabled and a run button. Item 140 made the colour follow the *meaning* — a
`Pill` takes a `tone`, the tones live in one `--tone-*` block, and no screen
writes a raw `pill-*`/`chip-*`/`sev-*`/`src-*`/`state-*`/`badge-*` tone class
any more. This guard is the thing that keeps it that way: it fails the moment a
new pill is written in the old vocabulary, or a second colour is smuggled onto
a meaning.

Three clauses, each a way the discipline could rot:

1. No legacy tone class survives in a screen. Every tone-bearing class is now
   `<Pill tone="…">`; the only file allowed to name the classes is `pill.tsx`.
   A short allowlist covers non-tone *layout* classes that happen to share a
   forbidden prefix (`state-col` is a column width, not a state).

2. No selector is defined twice in `styles.css`. The audit that opened 140
   found `.sev*` defined twice with disagreeing values and the cascade quietly
   picking a winner; a single-class selector that reappears is that smell.

3. Amber / red / yellow *fills* belong only to `.tone-sev-*` and `.tone-count-*`.
   This is scoped to the tone system on purpose: a regression banner, a
   delete-on-hover and the data-viz bars (`.strip-bar.tone-bad`, …) legitimately
   paint red and are a different axis; the rule is that no *pill tone* other
   than a level or a count carries a level/count fill.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"
STYLES = SRC / "styles.css"

# A class token starts after a quote, brace, backtick or space, and never
# mid-word — so `fix-src-page`, `img-chip-logo` and `seq-badge-live` (the
# prefix is not at a token boundary) are not matches, only a real token like
# `src-brief` is. The tone NAMES reuse these prefixes on purpose (a Pill's
# `tone="sev-high"` is the whole point), so this is applied only to `className`
# text — never to a `tone=` prop or a comment — see `_class_strings`.
FORBIDDEN = re.compile(r"(?<![\w-])(pill|chip|sev|src|state|badge)-[a-z]")

# Every string literal that sits inside a `className=…` (both `className="…"`
# and `className={ … "…" … }`). Only these are class lists; a `tone="sev-high"`
# prop or a code comment naming an old class is not a class and is not scanned.
_CLASSNAME = re.compile(r"className\s*=\s*(\"[^\"]*\"|'[^']*'|\{)")
_STR_LIT = re.compile(r"\"([^\"]*)\"|'([^']*)'|`([^`]*)`")


def _class_strings(text: str) -> list[tuple[int, str]]:
    """(offset, class-list-text) for every className value in the source."""
    out: list[tuple[int, str]] = []
    for m in _CLASSNAME.finditer(text):
        val = m.group(1)
        if val[0] in "\"'":
            out.append((m.start(1), val[1:-1]))
            continue
        # className={ … } — take the balanced brace body, then every string
        # literal inside it (ternary arms, template chunks).
        depth, i = 1, m.end(1)
        while i < len(text) and depth:
            depth += (text[i] == "{") - (text[i] == "}")
            i += 1
        body = text[m.end(1):i - 1]
        for s in _STR_LIT.finditer(body):
            lit = s.group(1) or s.group(2) or s.group(3) or ""
            out.append((m.end(1) + s.start(), lit))
    return out

# Non-tone layout classes that share a forbidden prefix. These carry no colour
# meaning — they are widths, filter containers and copy captions — so they are
# not part of the tone system 140 unified. Kept explicit so a new tone class
# cannot hide behind the allowance.
LAYOUT_ALLOW = {
    "state-col", "state-why", "state-filters", "state-based",
}


def _tsx_files() -> list[Path]:
    return sorted(p for p in SRC.glob("*.tsx") if p.name != "pill.tsx")


def test_no_screen_writes_a_legacy_tone_class() -> None:
    offences: list[str] = []
    for path in _tsx_files():
        text = path.read_text(encoding="utf-8")
        for offset, classes in _class_strings(text):
            for tok in classes.split():
                if not FORBIDDEN.match(tok):
                    continue
                if tok in LAYOUT_ALLOW:
                    continue
                line = text.count("\n", 0, offset) + 1
                offences.append(f"{path.name}:{line}: {tok}")
    assert not offences, (
        "legacy tone classes survive; use <Pill tone=…> (pill.tsx):\n  "
        + "\n  ".join(offences)
    )


def test_styles_defines_no_selector_twice() -> None:
    text = STYLES.read_text(encoding="utf-8")
    # Strip @media/@supports bodies so a class restyled under a breakpoint is
    # not counted as a duplicate of its base rule.
    depth = 0
    top: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("@media") or stripped.startswith("@supports"):
            depth += 1
            continue
        if depth:
            depth += line.count("{") - line.count("}")
            if depth < 0:
                depth = 0
            continue
        top.append(line)
    body = "\n".join(top)
    # A single simple class selector heading a rule block: `.foo {` or
    # `.foo-bar {`, not a compound (`.a .b`), pseudo (`:hover`) or list.
    seen: dict[str, int] = {}
    for m in re.finditer(r"(?m)^\s*(\.[a-z][a-z0-9-]*)\s*\{", body):
        sel = m.group(1)
        seen[sel] = seen.get(sel, 0) + 1
    dupes = sorted(s for s, n in seen.items() if n > 1)
    assert not dupes, f"selector defined twice in styles.css: {dupes}"


# Warm hues (amber/red/yellow) named by palette token or by literal. A blue
# (`--accent*`), grey (`--surface*`, `--border*`), green (`--good*`) or violet
# (`--an-*`) fill is allowed on any tone; only a *level or count* hue is
# restricted to the sev/count tones.
_WARM = re.compile(r"--warn|--danger|#b3261e|#d9730d|#e0a800|#f\w{2}[0-9a-f]{0,3}\b", re.I)


def test_only_severity_and_count_pills_carry_a_level_fill() -> None:
    text = STYLES.read_text(encoding="utf-8")
    offences: list[str] = []
    # Each `.tone-<name> { … }` rule (single tone class heading a block).
    for m in re.finditer(r"(?m)^\s*\.tone-([a-z0-9-]+)\s*\{([^}]*)\}", text):
        name, block = m.group(1), m.group(2)
        bg = re.search(r"\bbackground(?:-color)?\s*:\s*([^;]+);", block)
        if not bg:
            continue
        if _WARM.search(bg.group(1)) and not (
            name.startswith("sev-") or name.startswith("count-")
        ):
            offences.append(f".tone-{name}: {bg.group(1).strip()}")
    assert not offences, (
        "a non-severity, non-count pill tone carries a level/count fill:\n  "
        + "\n  ".join(offences)
    )
