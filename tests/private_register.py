"""Whether this checkout carries the operator's private register.

Item 187 excluded the operator's working record from the public tree - the
audit reports under `audits/`, and `OPERATOR_ACTIONS.md`, `QUESTIONS.md`,
`NEXT_UP.md`, `BACKLOG.md` and `TIMINGS.md` - and `PUBLIC_EXCLUDE.txt` records
why: they are saturated with client detail and they are a working record rather
than product.

A guard that READS one of those cannot run in an exported tree, and the first
export proved that the failure mode is worse than a red test:

    ERROR collecting tests/test_reconcile_findings.py
    FileNotFoundError: ...\\public-root\\audits\\038-2026-08-17.md
    Interrupted: 1 error during collection

One absent file aborted collection of the whole suite. Not twenty failures -
nothing ran at all. So the rule here has two halves, and the second matters as
much as the first:

1. **Skip, with a reason a stranger can read.** The operator chose skipping
   over excluding these files from the export (2026-09-21), and the argument
   for it is that a suite which tells you what it is not checking is better
   than one that quietly omits it. A public clone shows these as skips naming
   the register they wanted.

2. **Never read at import time.** A module-level `read_text` of an absent path
   raises during collection, where a skip marker has not been consulted yet
   and cannot save it. Either read inside the test, or call `skip_module()`
   before the read. `HAVE_REGISTER` is a cheap `is_dir()`/`is_file()` check and
   is safe at module scope; the CONTENT is not.

This is not a way to make a failing guard quiet. Everything here is still
enforced in the repository that keeps the register, which is the repository
where a change to it can be made.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

#: The paths `PUBLIC_EXCLUDE.txt` keeps out of the export. Listed rather than
#: parsed from the manifest on purpose: this is a test-support module and a
#: parser here would be a second reader of that file's format, which
#: `test_no_client_data_ships.py` already holds. If the manifest grows a path a
#: guard reads, that guard's own skip names it.
AUDITS = ROOT / "audits"
OPERATOR_ACTIONS = ROOT / "OPERATOR_ACTIONS.md"
TIMINGS = ROOT / "TIMINGS.md"
NEXT_UP = ROOT / "NEXT_UP.md"
QUESTIONS = ROOT / "QUESTIONS.md"
BACKLOG = ROOT / "BACKLOG.md"

#: Does this checkout carry the register at all? `audits/` is the marker
#: because it is the largest of them and the one no public export will ever
#: carry - a tree with it has the rest.
HAVE_REGISTER = AUDITS.is_dir()

REASON = ("the operator's private register is not in this tree (item 187: "
          "`audits/` and the working record do not ship). This guard runs in "
          "the repository that keeps them.")

#: For a clause that reads the register inside its own body.
needs_register = pytest.mark.skipif(not HAVE_REGISTER, reason=REASON)


def skip_module() -> None:
    """Skip a whole module before it reads the register at import time.

    Call this ABOVE the module-level read, not below it: the point is to leave
    before the `read_text` that would otherwise abort collection for every
    other file in the suite.
    """
    if not HAVE_REGISTER:
        pytest.skip(REASON, allow_module_level=True)


def have(path: Path) -> bool:
    """Is this particular register file here? For a guard that reads one of
    them rather than the audit reports - the manifest excludes them together,
    but a checkout could in principle carry one and not another, and a guard
    should say which one it wanted."""
    return path.exists()
