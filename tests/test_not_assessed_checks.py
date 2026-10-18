""""Not assessed" has one definition, computed, not a hand-kept list.

Round 040 (CQ-78, CQ-75). `render.NOT_ASSESSED_CHECKS` was a literal set of
three check ids, maintained by hand beside six modules that each independently
decide whether they emit a `-not-assessed` check. `playbook.py:480` already
computes the same fact from the name — `check.endswith("-not-assessed")` — so
the set was a duplicate of information the check_id itself states, and it had
already drifted: `contrast-not-assessed` (a11y.py) and
`sitemap-coverage-not-assessed` (tec.py) were both missing from it, so a client
document printed each under "What we found", with a fix instruction, rather
than under the not-assessed section it was built for.

`extractability-not-assessed` (ais.py, added by relay 025) carried the same
drift in the other direction: `Severity.LOW`, while every other `-not-assessed`
check is `Severity.INFO`. `CHECK_CEILING[LOW] = 5.0` against `[INFO] = 0.0`
(`scoring.py:46-52`), so the one check this repository added after the pattern
was established was also the one that deducted for a limitation rather than a
defect.
"""

from __future__ import annotations

import re
from pathlib import Path

from clauditseo.reporting.render import NOT_ASSESSED_CHECKS

ROOT = Path(__file__).resolve().parent.parent
MODULES = ROOT / "clauditseo" / "modules"

_CHECK_ID = re.compile(r'check_id="([a-z][a-z-]*-not-assessed)"')
_FINDING_CALL = re.compile(
    r'Finding\(\s*(?:[^()]|\([^()]*\))*?check_id="([a-z][a-z-]*-not-assessed)"'
    r'(?:[^()]|\([^()]*\))*?severity=Severity\.(\w+)', re.S)


def _emitted_ids() -> set[str]:
    """Every `-not-assessed` check_id literally emitted under
    `clauditseo/modules/`. Source-level, not a runtime scan: the modules
    disagree enough in constructor shape (see `test_ais_extractability.py`'s
    own fixtures) that driving all six with real crawls would be the heavier,
    more fragile version of the same fact this file's `check_id="..."` text
    already states."""
    ids = set()
    for path in MODULES.glob("*.py"):
        ids |= set(_CHECK_ID.findall(path.read_text(encoding="utf-8")))
    return ids


def _emitted_severities() -> dict[str, str]:
    """`{check_id: severity name}`, read from the same `Finding(...)` call
    that names the check — not from a second table that could itself drift."""
    out: dict[str, str] = {}
    for path in MODULES.glob("*.py"):
        for check_id, sev in _FINDING_CALL.findall(path.read_text(encoding="utf-8")):
            out[check_id] = sev
    return out


def test_the_collector_finds_something():
    """Guards the enumeration itself — a regex that stopped matching would
    make every assertion below vacuously true."""
    assert len(_emitted_ids()) >= 5, _emitted_ids()


def test_every_not_assessed_check_is_classified_as_one():
    """Every check a module actually emits under the `-not-assessed` name
    must test `in NOT_ASSESSED_CHECKS` — proving the membership object reads
    real emissions, not only the shape of its own predicate."""
    emitted = _emitted_ids()
    assert emitted, "collector found no -not-assessed check_id to check"

    missing = {c for c in emitted if c not in NOT_ASSESSED_CHECKS}
    assert not missing, f"emitted but not in NOT_ASSESSED_CHECKS: {missing}"


def test_a_check_not_ending_not_assessed_is_excluded():
    """The other half of the membership test: a check whose name does not
    make the claim must not be classified as though it had. Real check_ids
    from this codebase, not placeholders."""
    assert "poor-extractability" not in NOT_ASSESSED_CHECKS
    assert "duplicate-content" not in NOT_ASSESSED_CHECKS


def test_every_not_assessed_check_is_info_severity():
    """A `-not-assessed` check states a measurement gap, not a defect —
    `CHECK_CEILING[INFO] == 0.0` is what makes that true in the score.
    A `LOW` (or higher) `-not-assessed` check deducts for a page the crawl
    could not read, which is the exact defect CQ-75 reported."""
    severities = _emitted_severities()
    assert severities, "collector found no Finding(...) call to check"

    wrong = {check: sev for check, sev in severities.items() if sev != "INFO"}
    assert not wrong, f"not-assessed checks not at INFO severity: {wrong}"


def test_not_assessed_checks_matches_the_computable_predicate():
    """`playbook.py:480` derives the same fact independently, reading the
    suffix directly rather than a shared symbol. Pinned to agree so a change
    to either one's string is caught rather than silently diverging again."""
    for check_id in _emitted_ids() | {"poor-extractability", "duplicate-content"}:
        assert (check_id in NOT_ASSESSED_CHECKS) == check_id.endswith("-not-assessed")
