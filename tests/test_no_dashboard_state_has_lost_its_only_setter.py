"""CQ-239: a `useState` in `dashboard/src` whose setter nothing ever calls.

The finding, raised at report 120. `dashboard/src/tools.tsx:197` declared
`const [ran, setRan] = useState<"all" | "done" | "todo">("all")`, and commit
`763c68c` (12 August 2026) deleted the only caller of `setRan` — a three-button
segment filter — replacing it with a `ConfirmRun` modal that answers the same
operator choice at click time. The declaration stayed. For nineteen days `ran`
was permanently `"all"`, while six sites went on reading it as though it could
be one of three: `ranMatches`, `RUN_LABEL.done`/`.todo`, the tool-list
empty-state text's `ran === "done"` branch, and `RUN_BLOCKED_EMPTY.done`/`.todo`
— the last of these added by round 119's *own* fix, which extended a branch the
running product can never enter without noticing.

**Why this is a scan and not a driven test.** The defect is not something the
product does; it is a state the product cannot reach. A browser cannot observe
the absence of a transition — no fixture can arrange `ran === "done"`, which is
the whole finding — so there is no rendered evidence to assert against. What can
be observed is the source property that makes the branch unreachable: a setter
returned by `useState` and called nowhere. That is checkable exactly, over every
file at once, and rule 4's objection does not apply: the evidence is the call
graph, not a comment claiming the state is live.

**Enumerated from the tree rather than from a list**, per DISCIPLINE rule 3.
Report 120 named one variable; a hard-coded check for `setRan` would have been
satisfied by deleting it and would say nothing about the next one. This walks
every `.ts`/`.tsx` under `dashboard/src` and every `const [x, setX] = useState`
in them, so a state that loses its last setter in any component is caught by the
same assertion. Measured at the round that wrote it: **212 pairs across 18
files, one violation** — the one report 120 named.

**Why the search is over the whole directory and not per file.** A setter is
routinely passed down as a prop or handed to a context, so `setSiteId` declared
in `App.tsx` is called in `tools.tsx`. Searching one file at a time would call
every such setter dead. The union of all sources is the smallest scope that
cannot produce that false positive; the cost is that a setter passed to a
component that never invokes it still counts as used, which makes this check
conservative rather than complete — it finds states with *no* caller anywhere,
which is the class report 120 found.
"""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"

#: `const [ran, setRan] = useState<...>(...)`. Anchored on `useState` so a
#: destructured context value — `const { sites, siteId, setSiteId } = ...` at
#: `tools.tsx:219` — is not read as a state pair it is not.
PAIR = re.compile(
    r"\bconst\s*\[\s*([A-Za-z_$][\w$]*)\s*,\s*([A-Za-z_$][\w$]*)\s*\]"
    r"\s*=\s*useState")


def _sources() -> dict[Path, str]:
    return {p: p.read_text(encoding="utf-8")
            for p in sorted(SRC.rglob("*.ts*")) if p.is_file()}


def test_every_dashboard_state_still_has_something_that_can_set_it() -> None:
    """A setter called nowhere means every read of its getter is a constant.

    The failure message names the file, the line and both halves of the pair,
    because the remedy differs by case and the reader has to choose: delete the
    state and fold its readers onto the one value it can hold, or restore the
    control that was meant to set it. Report 120's `ran` was the first — the
    control it belonged to had been deliberately replaced, and the readers were
    residue.
    """
    sources = _sources()
    assert sources, f"no dashboard sources under {SRC} — the scan found nothing"
    everything = "\n".join(sources.values())

    pairs = [(path, text[:m.start()].count("\n") + 1, m.group(1), m.group(2))
             for path, text in sources.items() for m in PAIR.finditer(text)]
    # The population, asserted rather than assumed: a regex that stopped
    # matching would otherwise pass this test by finding nothing to check.
    assert len(pairs) > 100, (
        "expected the dashboard to declare well over a hundred state pairs; "
        f"the scan found {len(pairs)} across {len(sources)} files, so the "
        "pattern has probably stopped matching rather than the code changed")

    dead = [(path, line, getter, setter)
            for path, line, getter, setter in pairs
            if len(re.findall(rf"\b{re.escape(setter)}\b", everything)) <= 1]

    assert not dead, (
        "these `useState` setters are declared and called nowhere in "
        "dashboard/src, so their getters are permanently their initial value "
        "and every branch keyed on any other value is unreachable: "
        + "; ".join(
            f"{p.relative_to(SRC.parents[1]).as_posix()}:{line} "
            f"{getter}/{setter}" for p, line, getter, setter in dead))
