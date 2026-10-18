"""CQ-148: an effect that fetches and writes state, with nothing to drop a
response that arrives after the effect has been superseded.

The finding, first raised at report 072 and carried unchanged to report 127.
`dashboard/src/tools.tsx:376` fetches `/api/runs/{runId}/pages` and assigns
`setPages`, `setHomeUrl` and `setPageUrl` from the response. Its dependency is
`runId`. Change the run while that request is in flight and the effect re-runs,
but the first response is not cancelled — it resolves whenever the network
returns it, and whichever of the two lands *last* wins. The picker can therefore
hold the page list of one audit while the Run button names another, and the
brief is then run against pages that do not belong to the run it is filed under.

**The remedy already existed in this codebase, twice, and was not applied here.**
`selection.tsx:124` and `tools.tsx:321` — the effect immediately *above* the
defective one, in the same file — both latch `let live = true`, consult it in
every continuation, and clear it from the effect's cleanup. That is the shape
this test requires, because it is the shape the working sites already use.

**Enumerated from the tree, per DISCIPLINE rule 3.** Report 127 named one site.
A check written against `tools.tsx:376` alone would have been satisfied by
fixing it and would have said nothing about the other ten. Walking every
`useEffect` in every `.ts`/`.tsx` under `dashboard/src` found the class at
**eleven sites across eight files** — `admin.tsx`, `deliverable.tsx`,
`dossier.tsx`, `expert.tsx`, `schedule.tsx`, `selection.tsx`, `tools.tsx`
(three), `views.tsx` and `workbench.tsx` — against four already correct. That
is the "partial fix passes" case rule 3 was written for: the report's list was
one of eleven.

**Why every member of the population is a real defect and not an unmount
warning.** An effect with an empty dependency array runs once, so a late
response can only write to an unmounted component — noisy, not wrong. The
defect this guards is a *superseded* effect: the dependency changed, a second
request went out, and the first one is still coming. So the population is
restricted to effects whose dependency array is non-empty, and at the round that
wrote this every one of the eleven qualified — the deps are `siteId`, `runId`,
`reportId`, `url`, `tick`, `toolId`, `latestRunId` and `siteTick`, all of which
change while the screen is open, none of which is a constant.

**What this check is not.** It confirms a latch is declared, cleared in the
cleanup, and consulted at least once. It does not prove every individual setter
in the body sits behind that consultation — that would need real control-flow
analysis, and a regex claiming to do it would be the weaker-matcher defect the
profile's guard-population invariant names. So this is deliberately
conservative: it catches an effect with no cancellation mechanism at all, which
is the whole of the class found here, and it would not catch one that latched
correctly and then forgot a single branch. Stated rather than implied, because a
reader who assumes the stronger reading would stop checking the branch.
"""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"

#: The request layer every screen goes through (`dashboard/src/api.ts`). A
#: fetch that never reaches component state is not in the class.
CALL = re.compile(r"\bapi\.(?:get|post|put|patch|del|delete)\b")

#: `setPages(`, `setError(` — a React state write. Anchored on the `set` +
#: capital convention the whole directory follows.
SETTER = re.compile(r"\bset[A-Z]\w*\s*\(")

#: `let live = true`, `let cancelled = false`. The latch the working sites use.
LATCH = re.compile(
    r"\blet\s+(live|cancell?ed|ignore[d]?|stale|active)\b\s*=", re.I)


def _sources() -> dict[Path, str]:
    return {p: p.read_text(encoding="utf-8")
            for p in sorted(SRC.rglob("*.ts*")) if p.is_file()}


def _effect_bodies(text: str) -> list[tuple[int, str, str]]:
    """Every `useEffect(...)` body in one file, with its line and dep array.

    Brace-matched rather than regex-delimited: these bodies contain object
    literals, template strings and nested arrow functions, and a non-greedy
    `\\{.*?\\}` stops at the first one of those every time.
    """
    out: list[tuple[int, str, str]] = []
    for m in re.finditer(r"\buseEffect\s*\(", text):
        head = text[m.end():m.end() + 300]
        if "{" not in head:
            continue
        start = m.end() + head.index("{")
        depth = 0
        i = start
        while i < len(text):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        else:
            continue
        # The dependency array is what follows the body, up to the closing
        # paren of the `useEffect(` call itself.
        tail = text[i + 1:i + 200]
        deps = tail.split("]")[0] if "[" in tail else ""
        out.append((text[:start].count("\n") + 1, text[start:i + 1], deps))
    return out


def test_every_fetching_effect_can_drop_a_response_it_no_longer_wants() -> None:
    """A superseded request must not be able to overwrite a current one.

    The failure names every site, because the fix is per-effect and the reader
    has to visit each: latch `live` at the top, consult it in every `.then`,
    `.catch` and `.finally`, and clear it from the returned cleanup — the
    pattern `dashboard/src/selection.tsx:124` already uses.
    """
    sources = _sources()
    assert sources, f"no dashboard sources under {SRC} — the scan found nothing"

    population: list[tuple[Path, int, str]] = []
    for path, text in sources.items():
        for line, body, deps in _effect_bodies(text):
            if not CALL.search(body) or not SETTER.search(body):
                continue
            # A mount-only effect cannot be superseded by a dependency change.
            if not deps.strip():
                continue
            population.append((path, line, body))

    # The population, derived above and asserted here rather than assumed: a
    # pattern that stopped matching would otherwise pass by finding nothing.
    assert len(population) >= 10, (
        "expected at least ten effects under dashboard/src that fetch through "
        f"`api.*` and write state; the scan found {len(population)} across "
        f"{len(sources)} files, so the pattern has probably stopped matching "
        "rather than the code having changed")

    unguarded = []
    for path, line, body in population:
        latch = LATCH.search(body)
        if not latch:
            unguarded.append((path, line, "no latch declared"))
            continue
        name = latch.group(1)
        cleared = re.search(
            rf"return\s*\(\s*\)\s*=>\s*[^;]*?\b{re.escape(name)}\s*=", body,
            re.S)
        if not cleared:
            unguarded.append((path, line, f"`{name}` is never cleared "
                                          "from the effect's cleanup"))
            continue
        # Declaration, cleanup assignment, and at least one consultation.
        if len(re.findall(rf"\b{re.escape(name)}\b", body)) < 3:
            unguarded.append((path, line, f"`{name}` is declared and cleared "
                                          "but never consulted"))

    assert not unguarded, (
        "these effects fetch through `api.*` and write the response into "
        "component state with no way to drop it once the effect has been "
        "superseded, so a slow first response can overwrite a fast second one "
        "and the screen then shows data belonging to a dependency the "
        "operator has already moved off: "
        + "; ".join(
            f"{p.relative_to(SRC.parents[1]).as_posix()}:{line} ({why})"
            for p, line, why in unguarded))
