"""Provider keys the operator can set from the admin panel.

Keys used to come only from the environment, which meant a self-hosted tool
could not be configured from its own admin screen: replacing a rejected key
needed a shell, a `setx`, and a restart. That is a poor trade for a product
whose whole shape is "runs on your machine, you own the data".

WHY A FILE AND NOT THE DATABASE

`clauditseo.db` is copied. It is backed up, it is 12 MB of client audit
history, and a future export or hand-off copies it wholesale. Secrets stored
in it would travel with every one of those copies silently. Keeping them in a
separate file means a database backup carries no credentials, which is the
property worth having — the file sits beside the database and is excluded
from git.

WHAT THIS DOES NOT CLAIM

The contents are plaintext. There is no master password to encrypt them
against, and a key encrypted with a key stored next to it is theatre, not
protection. What the file gets is restrictive permissions: 0600 on POSIX, and
on Windows an ACL with inheritance broken so only the owning user can read
it. `harden()` reports whether that succeeded rather than assuming it, and
the admin screen shows the result — an operator told their keys are protected
when they are not is worse off than one told nothing.

PRECEDENCE

The file wins over the environment. The opposite order looks safer and is a
trap: an operator whose environment holds a key the provider now rejects
could type a new one, see it saved, and still watch every request fail,
because the value they could not see was still the one being sent. Whatever
is shown as set has to be what is used. Where a variable is also present in
the environment the screen says so, and says which one is winning.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

#: Deliberately no import of clauditseo.config — config reads this module, so
#: a dependency back would be a cycle. The few environment names needed here
#: are read directly.
ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class ManagedKey:
    """A credential the admin panel may set.

    `name` is the canonical setting name, which is also the environment
    variable an operator can use instead. `provider` matches the label in the
    providers block so the two screens cannot disagree about what is what.
    """

    name: str
    provider: str
    detail: str
    #: Where an operator gets one, as an absolute https URL so the panel can
    #: link straight to it. Empty when there is nowhere to send them — the
    #: DataForSEO password comes with the login, not from a second page.
    obtain: str = ""


#: An allowlist, not "whatever the caller passes". The file is written by an
#: HTTP endpoint, and a store that accepts any name would let a request set
#: the database path or the auth token — settings that are not credentials
#: and have no business being writable from a browser.
MANAGED: tuple[ManagedKey, ...] = (
    ManagedKey("ANTHROPIC_API_KEY", "LLM analyst",
               "the analyst layer, expert analyses and chat",
               "https://console.anthropic.com"),
    ManagedKey("CLAUDITSEO_PAGESPEED_KEY", "PageSpeed",
               "Core Web Vitals lab data",
               "https://developers.google.com/speed/docs/insights/v5/get-started"),
    ManagedKey("CLAUDITSEO_CRUX_KEY", "CrUX",
               "Core Web Vitals field data",
               "https://developer.chrome.com/docs/crux/api"),
    ManagedKey("CLAUDITSEO_OPENPAGERANK_KEY", "OpenPageRank",
               "domain authority and referring domains (free tier). Keys "
               "start opr_live_ — an older domcop.com key is not accepted",
               "https://openpagerank.keywordseverywhere.com"),
    ManagedKey("CLAUDITSEO_MOZ_TOKEN", "Moz", "backlink metrics",
               "https://moz.com/products/api"),
    ManagedKey("CLAUDITSEO_DATAFORSEO_LOGIN", "DataForSEO",
               "backlink summary — login", "https://dataforseo.com"),
    ManagedKey("CLAUDITSEO_DATAFORSEO_PASSWORD", "DataForSEO",
               "backlink summary — password", ""),
    ManagedKey("CLAUDITSEO_BING_KEY", "Bing Webmaster",
               "index coverage and query data",
               "https://www.bing.com/webmasters"),
    ManagedKey("CLAUDITSEO_PLACES_KEY", "Places",
               "Business Profile as Google holds it. Billed per request",
               "https://console.cloud.google.com"),
    ManagedKey("CLAUDITSEO_INDEXNOW_KEY", "IndexNow",
               "submits fixed URLs for recrawl. The key file must be hosted "
               "at the site root",
               "https://www.indexnow.org"),
    ManagedKey("CLAUDITSEO_GOOGLE_SA_FILE", "Search Console",
               "path to a service-account JSON file, not a key",
               "https://console.cloud.google.com"),
)

BY_NAME = {k.name: k for k in MANAGED}


def path() -> Path:
    """Beside the database, overridable so tests never touch a real store."""
    override = os.environ.get("CLAUDITSEO_SECRETS_FILE", "").strip()
    if override:
        return Path(override)
    return ROOT / "data" / "secrets.json"


#: Cache keyed on what the file *is*, not on time. Settings are rebuilt on
#: every request and read ~30 values, so an uncached load would be thirty
#: file reads per request; a time-based cache would mean a saved key does not
#: take effect until it expires, which is the surprise this whole feature is
#: meant to remove. Keyed on (path, mtime_ns, size) it re-reads exactly when
#: the file has changed and never otherwise.
_cache: dict[tuple, dict[str, str]] = {}


def load() -> dict[str, str]:
    """Never raises. A store that cannot be read must not stop the app.

    A corrupt or unreadable file falls back to the environment, which is the
    behaviour that existed before this module — degraded, but running.
    """
    target = path()
    try:
        stamp = target.stat()
    except OSError:
        return {}
    fingerprint = (str(target), stamp.st_mtime_ns, stamp.st_size)
    if fingerprint in _cache:
        return _cache[fingerprint]
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    values = {str(k): str(v) for k, v in raw.items()
              if k in BY_NAME and isinstance(v, str) and v.strip()}
    _cache.clear()
    _cache[fingerprint] = values
    return values


def get(name: str) -> str:
    return load().get(name, "").strip()


def put(name: str, value: str) -> None:
    """Store one key. Unknown names are refused rather than written."""
    if name not in BY_NAME:
        raise KeyError(f"{name} is not a managed key")
    value = value.strip()
    if not value:
        raise ValueError("value is empty")
    current = load()
    current[name] = value
    _write(current)


def drop(name: str) -> bool:
    """Forget one key, falling back to the environment. True if one went."""
    current = load()
    if name not in current:
        return False
    del current[name]
    _write(current)
    return True


def _write(values: dict[str, str]) -> None:
    """Create with restrictive permissions, then replace atomically.

    The mode is passed to `open` rather than chmod'd afterwards: creating a
    readable file and tightening it a moment later leaves a window where the
    keys are exposed, and it is a window that only ever opens on the write
    that adds a new secret.
    """
    target = path()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".json.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(values, fh, indent=2, sort_keys=True)
    harden(tmp)
    os.replace(tmp, target)
    harden(target)


def harden(target: Path | None = None) -> bool:
    """Restrict the file to its owner. Reports success rather than assuming.

    On Windows `chmod` only toggles the read-only flag — it does not restrict
    who may read the file — so the ACL is set with icacls: inheritance broken
    so a permissive parent directory cannot grant access, and the current
    user granted full control. Absence of an error is not evidence it worked,
    so the exit status is checked and returned.
    """
    target = target or path()
    if not target.exists():
        return False
    try:
        os.chmod(target, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        return False
    if sys.platform != "win32":
        return (target.stat().st_mode & 0o077) == 0
    user = os.environ.get("USERNAME", "")
    if not user:
        return False
    # Resolved, not named. A bare name is looked up by CreateProcess, which
    # searches System32 before PATH — the divergence that made a probe in this
    # repo validate one executable while the caller ran another, twice in one
    # day. `icacls` does live in System32, so the lookup would usually find the
    # right one; "usually" is not what this function returns.
    #
    # Unresolvable means the ACL was not set, so this reports False like every
    # other failure here. The docstring's rule is that absence of an error is
    # not evidence it worked, and a program that was never found did not work.
    icacls = shutil.which("icacls")
    if not icacls:
        return False
    try:
        done = subprocess.run(
            [icacls, str(target), "/inheritance:r", "/grant:r", f"{user}:F"],
            capture_output=True, timeout=20, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0


def mask(value: str) -> str:
    """Enough to recognise which key it is, never enough to use it."""
    value = value.strip()
    if len(value) < 8:
        return "•" * 6
    return "•" * 6 + value[-4:]
