"""`scripts/run_golden.py` must refuse the operator's *configured* database,
whatever it is called — CQ-220.

The harness creates a client, a site and an audit run every time it is called,
and it once defaulted to the production database: six "Golden fixture" clients
with 127.0.0.1 domains appeared on the operator's home screen beside their real
ones. The refusal added then compared a **filename**::

    if db.name == "clauditseo.db":

A filename standing in for an identity. `clauditseo/config.py` reads the
database path from `CLAUDITSEO_DB`, so "the live db is always named
`clauditseo.db`" is not true, and the guard passes any live database that is
not literally named that. Reproduced 24 August 2026 and again 29 August 2026
without spending: with `CLAUDITSEO_DB` pointing at `live.db`, the harness
accepted `--db <that same live.db>`, connected to it and migrated it, where
`--db data/clauditseo.db` exits 2.

The guard the operator needs is the one they would state themselves: not "is
this file called something", but "is this the file my own data is in".

**Both directions, because a refusal that refuses everything is not a guard.**
The identity comparison must still let a genuine scratch path through — the
whole point of the default `data/golden-scratch.db` is that the instrument
leaves no marks on the thing it measures.

Driven through the command line rather than the predicate. The unit answers
about path arithmetic; this answers about the contract an operator meets, and
it is the operator's own database at stake. Each case exits before any API
call and costs about a second.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _run(db_arg, live: Path, cwd: Path = ROOT):
    """The harness, as an operator runs it, with `live` as their configured
    database. `--estimate` so nothing can be billed even if the guard lets it
    through, and `CLAUDITSEO_NO_ENV_FALLBACK` so the developer's own registry
    value cannot decide what "live" means here."""
    env = dict(os.environ)
    env["CLAUDITSEO_DB"] = str(live)
    env["CLAUDITSEO_NO_ENV_FALLBACK"] = "1"
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_golden.py"),
         "--db", str(db_arg), "--estimate"],
        cwd=str(cwd), capture_output=True, text=True, env=env,
    )


def test_a_live_database_not_named_clauditseo_db_is_refused(tmp_path):
    """The reproduction, exactly: the configured database is `live.db`, and
    the name guard has nothing to catch it with."""
    live = tmp_path / "live.db"
    run = _run(live, live)
    assert run.returncode == 2, (
        "the harness accepted the operator's own database because it is not "
        "named clauditseo.db\n" + run.stdout + run.stderr)
    assert "live database" in run.stderr, run.stderr
    assert not live.exists(), (
        "the harness connected to the live database before refusing it — "
        "connect() creates and migrate() writes")


def test_a_relative_spelling_of_the_live_database_is_refused(tmp_path):
    """Same file, different spelling. A string comparison would pass this;
    the guard resolves both sides first."""
    live = tmp_path / "client-data.db"
    live.write_bytes(b"")
    run = _run(Path("client-data.db"), live, cwd=tmp_path)
    assert run.returncode == 2, (
        "a relative path naming the live database was accepted\n"
        + run.stdout + run.stderr)


def test_the_default_live_database_is_still_refused(tmp_path):
    """The case the original name guard was written for. It is the configured
    path under a default install, so identity catches it too — the fix must
    not trade one direction for the other."""
    run = _run(ROOT / "data" / "clauditseo.db", ROOT / "data" / "clauditseo.db")
    assert run.returncode == 2, run.stdout + run.stderr


def test_a_scratch_path_is_accepted(tmp_path):
    """The other direction. A guard that refuses every path would pass all
    three assertions above and make the instrument unrunnable."""
    live = tmp_path / "live.db"
    run = _run(tmp_path / "golden-scratch.db", live)
    assert run.returncode == 0, (
        "a scratch path was refused\n" + run.stdout + run.stderr)


def test_the_predicate_compares_files_not_names(tmp_path):
    """The unit, for the cases the command line cannot cheaply reach: a live
    database that does not exist yet (a fresh install, where there is nothing
    to `samefile`), and two different files that share a name.

    Imported here rather than at module scope so that the four cases above
    fail on the harness's *behaviour* against the name guard, not on an
    ImportError that says only "the fix is not written yet"."""
    from scripts.run_golden import is_the_live_db

    live = tmp_path / "live.db"
    assert is_the_live_db(live, live)
    assert is_the_live_db(Path(str(live).upper()) if os.name == "nt" else live,
                          live)
    other = tmp_path / "elsewhere"
    other.mkdir()
    assert not is_the_live_db(other / "live.db", live)
    assert not is_the_live_db(tmp_path / "golden-scratch.db", live)
