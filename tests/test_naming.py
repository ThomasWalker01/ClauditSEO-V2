"""The retired `AUDITDECK_` prefix is gone from everything that ships.

The product was renamed on 14 August 2026 and the old prefix was kept as a
second lookup so a working install would keep working. That compatibility
window is closed: every setting is `CLAUDITSEO_` and nothing reads the old
name. These two guards are what stop it drifting back.

They are deliberately different in kind. The first reads shipped text, which
catches a stale row in the README. The second drives the app, which is the
only thing that can show the *lookup* is gone — source can be clean while a
fallback still resolves, and this repository has shipped exactly that shape
more than once.

Files that document the rename keep the word on purpose and are excused by
name below: the case a rule carries is the reason the rule survives, which is
why `.gitattributes` and `.gitignore` still say what they were renamed from.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from clauditseo.api.app import create_app
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import repo

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "clauditseo" / "config.py"
RETIRED = "AUDITDECK_"

#: Text that exists to record the rename, or is the historical record itself.
#: Excused by path, so a new file cannot join this list by accident.
DOCUMENTS_THE_RENAME = {
    ".gitattributes",                       # names the path it was renamed from
    ".gitignore",                           # ditto, for the build artefact
    "tests/test_axe.py",                    # the case for the .gitattributes rule
    "tests/test_packaging.py",              # the case for the ignore rule
    "tests/test_naming.py",                 # this file
    "clauditseo/db/migrations/0001_initial.sql",  # an applied migration
}


def _shipped_files() -> list[Path]:
    """Everything an operator can read or run, enumerated from the tree.

    Not a hand-kept list: a new module or screen is covered the moment it
    exists, which is the difference between this and the guard it replaces.
    """
    paths = [ROOT / "README.md", ROOT / "ARCHITECTURE.md", ROOT / "LICENCE"]
    paths += sorted((ROOT / "clauditseo").rglob("*.py"))
    paths += sorted((ROOT / "dashboard" / "src").glob("*.ts"))
    paths += sorted((ROOT / "dashboard" / "src").glob("*.tsx"))
    paths += sorted((ROOT / "tests").glob("*.py"))
    return [p for p in paths
            if p.relative_to(ROOT).as_posix() not in DOCUMENTS_THE_RENAME]


def test_the_setting_names_are_all_current():
    """Derive the vocabulary from `config.py` rather than restating it."""
    source = CONFIG.read_text(encoding="utf-8")
    names = set(re.findall(r'_env\("([A-Z][A-Z0-9_]*)"', source))
    assert len(names) >= 15, f"suspiciously few settings parsed: {sorted(names)}"

    stale = sorted(n for n in names if n.startswith(RETIRED))
    assert not stale, f"config.py still defines settings under the old prefix: {stale}"


#: Files that must NAME the retired prefix in order to refuse it, with the
#: number of times each is allowed to. Bounded rather than excused: an
#: allowlist by path would let a stray reference in the same file ride along
#: unnoticed, which is the shape of every partial fix in this repository.
#: Raising a number here is a deliberate act with a reason, not a side effect.
DETECTS_THE_RENAME = {
    # `LEGACY_TOKEN_ENV`, and the sentence the refusal shows the operator.
    "clauditseo/config.py": 2,
    # One clause in the auth paragraph, describing the refusal.
    "ARCHITECTURE.md": 1,
}


def test_nothing_that_ships_names_the_retired_prefix():
    offenders: dict[str, list[int]] = {}
    for path in _shipped_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        rel = path.relative_to(ROOT).as_posix()
        hits = [i + 1 for i, line in enumerate(text.splitlines())
                if RETIRED in line or "auditdeck" in line.lower()]
        allowed = DETECTS_THE_RENAME.get(rel, 0)
        if len(hits) > allowed:
            offenders[rel] = hits
    assert not offenders, (
        "the retired prefix still ships in: "
        + "; ".join(f"{f} lines {ls}" for f, ls in sorted(offenders.items())))


def test_the_detection_allowance_is_not_slack():
    """Every allowance must be used, or it is a hole rather than a budget.

    A count left higher than the file needs is indistinguishable from an
    exemption, and would silently absorb the next stray reference.
    """
    for rel, allowed in DETECTS_THE_RENAME.items():
        text = (ROOT / rel).read_text(encoding="utf-8")
        used = sum(1 for line in text.splitlines()
                   if RETIRED in line or "auditdeck" in line.lower())
        assert used == allowed, (
            f"{rel} is allowed {allowed} reference(s) to the retired prefix "
            f"and uses {used}; change the allowance deliberately or remove it")


def test_a_stale_legacy_token_does_not_open_the_api(tmp_path, monkeypatch):
    """Removing a lookup must not remove an access control.

    This test asserted the opposite and was wrong. It required
    `/api/clients` to answer 200 with only `AUDITDECK_TOKEN` set, on the
    reasoning that the old name should no longer resolve. It should not — but
    the consequence is that `settings().api_token` is empty, `auth` falls
    through `if cfg_token or any_operator_tokens` and returns None, and an
    install that required a credential before the upgrade requires none
    after it. The failing direction was chosen without asking what failing
    open would mean.

    Fail closed instead: the old name still does not authenticate anybody,
    and its presence is treated as a misconfigured install rather than as an
    absent one. Recovery is a rename, which the refusal has to name, because
    `CLAUDITSEO_TOKEN` is deliberately outside `secrets.MANAGED` and the
    admin panel cannot set it.
    """
    monkeypatch.delenv("CLAUDITSEO_TOKEN", raising=False)
    monkeypatch.setenv("AUDITDECK_TOKEN", "legacy-secret")

    db = tmp_path / "legacy.db"
    conn = connect(db)
    migrate(conn)
    conn.close()
    api = TestClient(create_app(db_path=db))

    refused = api.get("/api/clients")
    assert refused.status_code == 401, (
        "a stale AUDITDECK_TOKEN left the API open — an access control "
        "disappeared on upgrade")
    assert "CLAUDITSEO_TOKEN" in refused.text, (
        "the refusal must name the variable to rename; the admin panel "
        f"cannot set this one. Got: {refused.text!r}")

    # The old secret is still not a credential.
    assert api.get("/api/clients",
                   headers={"Authorization": "Bearer legacy-secret"}
                   ).status_code == 401

    # And renaming it restores service, which is what makes the refusal a
    # remedy rather than a wall.
    monkeypatch.delenv("AUDITDECK_TOKEN", raising=False)
    monkeypatch.setenv("CLAUDITSEO_TOKEN", "legacy-secret")
    fixed = TestClient(create_app(db_path=db))
    assert fixed.get("/api/clients",
                     headers={"Authorization": "Bearer legacy-secret"}
                     ).status_code == 200


def test_the_design_record_does_not_describe_a_removed_fallback():
    """A blanket rename can turn a true sentence into a false one.

    `ARCHITECTURE.md` read "legacy `AUDITDECK_TOKEN` retained" — accurate
    until the window closed. The rename rewrote the variable and left the
    claim, so the design record now asserted a legacy path on the release
    that removed it. `test_nothing_that_ships_names_the_retired_prefix`
    cannot see this: it searches for the retired *word*.
    """
    text = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    offenders = [i + 1 for i, line in enumerate(text.splitlines())
                 if "CLAUDITSEO_TOKEN" in line
                 and re.search(r"\blegacy\b|\bretained\b|\bfallback\b", line, re.I)]
    assert not offenders, (
        "ARCHITECTURE.md describes the canonical token as a legacy or "
        f"retained path, at line(s) {offenders}")


def test_the_current_token_still_gates(tmp_path, monkeypatch):
    """The half the suite never proved: that `CLAUDITSEO_TOKEN` works."""
    monkeypatch.delenv("AUDITDECK_TOKEN", raising=False)
    monkeypatch.setenv("CLAUDITSEO_TOKEN", "current-secret")

    db = tmp_path / "current.db"
    conn = connect(db)
    migrate(conn)
    repo.create_operator(conn, "Member", role="member")
    conn.close()
    api = TestClient(create_app(db_path=db))

    assert api.get("/api/clients").status_code == 401
    assert api.get("/api/clients",
                   headers={"Authorization": "Bearer current-secret"}
                   ).status_code == 200


def test_a_provider_key_under_the_retired_prefix_reads_as_unconfigured(
        tmp_path, monkeypatch):
    """Moved here from test_secrets.py, inverted.

    It asserted `test_the_legacy_prefix_is_still_honoured` — an install
    configured before the rename kept working. That window is closed, so the
    same input must now read as unconfigured. The panel must still be able to
    set it, because that is the recovery path such an operator is sent to.
    """
    from clauditseo import secrets as store
    from clauditseo.config import settings

    canonical = "CLAUDITSEO_OPENPAGERANK_KEY"
    monkeypatch.setenv("CLAUDITSEO_SECRETS_FILE", str(tmp_path / "secrets.json"))
    monkeypatch.setenv("CLAUDITSEO_NO_ENV_FALLBACK", "1")
    monkeypatch.delenv(canonical, raising=False)
    monkeypatch.setenv("AUDITDECK_OPENPAGERANK_KEY", "set-before-the-rename")
    store._cache.clear()
    try:
        assert settings().openpagerank_key == "", (
            "a key under the retired prefix still resolves")
        store.put(canonical, "typed-into-the-panel")
        assert settings().openpagerank_key == "typed-into-the-panel"
    finally:
        store._cache.clear()
