"""The well-known path sweep: one ordinary GET per path, once per site (item 143,
brief v20 step BD).

**Passive, and disclosed.** Every request here is a plain GET with the
crawler's own user agent, the same request a browser makes for a page. Nothing
logs in, posts, guesses a credential or follows up on what it finds. The
operator's ruling (143 addendum, 2026-09-07): these stay in the free sweep and
are NOT gated behind `active_probing_authorised`, but a client's WAF may log
them as probing, so the client report discloses the count, examples, user agent
and date - which is why the list actually fetched is returned, not just what it
found.

**A 200 is not an exposure.** Many sites answer every path with their own
styled page and status 200. So each response is kept with its status, type,
length and first bytes, beside one request for a path that cannot exist - the
site's own not-found answer - and the checks in `modules/sec.py` require a
content signature (a `.git/HEAD` that starts `ref:`, a listing titled
`Index of`), never the status alone.
"""

from __future__ import annotations

import time
import uuid
from urllib.parse import urljoin

from .types import USER_AGENT

#: What is fetched, and why. Fixed by the brief; nothing is added without one.
PATHS: tuple[tuple[str, str], ...] = (
    ("/.git/HEAD", "exposed-file"),
    ("/.env", "exposed-file"),
    ("/.svn/entries", "exposed-file"),
    ("/wp-config.php.bak", "exposed-file"),
    ("/wp-config.php.old", "exposed-file"),
    ("/wp-config.php.save", "exposed-file"),
    ("/phpinfo.php", "exposed-file"),
    ("/debug.log", "exposed-file"),
    ("/wp-content/debug.log", "exposed-file"),
    ("/error_log", "exposed-file"),
    ("/backup.zip", "exposed-file"),
    ("/backup.tar.gz", "exposed-file"),
    ("/.DS_Store", "exposed-file"),
    ("/composer.json", "exposed-file"),
    ("/package.json", "exposed-file"),
    ("/.htpasswd", "exposed-file"),
    ("/readme.html", "cms-fingerprint"),
    ("/xmlrpc.php", "cms-xmlrpc"),
    ("/wp-login.php", "cms-login-exposed"),
    ("/wp-login.php?action=register", "cms-registration-open"),
    ("/wp-json/wp/v2/users", "cms-user-enumeration"),
    ("/?author=1", "cms-user-enumeration"),
    ("/.well-known/security.txt", "security-txt"),
    ("/wp-content/uploads/", "directory-listing"),
    ("/wp-content/plugins/", "directory-listing"),
    ("/wp-includes/", "directory-listing"),
    ("/vendor/", "directory-listing"),
)

#: How much of a body is kept. Enough for every signature the checks read; a
#: backup archive's bytes are never stored beyond its first line.
HEAD_BYTES = 2500
TIMEOUT = 8.0


def sweep(start_url: str, client=None) -> dict:
    """Fetch every path once, plus one path that cannot exist.

    Returns `{"fetched": [...], "not_found": {...}, "user_agent", "at"}`. Each
    fetched row is `{path, purpose, status, final_url, content_type, length,
    head}`; a request that failed is kept with `error` and no status, because a
    path we could not ask about is not a path that is safe.
    """
    import httpx

    own = client is None
    if own:
        client = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT,
                              follow_redirects=True, verify=True)
    try:
        def get(path: str, purpose: str) -> dict:
            url = urljoin(start_url, path)
            row = {"path": path, "purpose": purpose, "url": url}
            try:
                resp = client.get(url)
                body = resp.content[:HEAD_BYTES]
                row.update({
                    "status": resp.status_code,
                    "final_url": str(resp.url),
                    "content_type": resp.headers.get("content-type", ""),
                    "length": len(resp.content),
                    "head": body.decode("utf-8", errors="replace"),
                })
            except Exception as exc:
                row["error"] = f"{type(exc).__name__}: {exc}"
            return row

        fetched = [get(path, purpose) for path, purpose in PATHS]
        not_found = get(f"/clauditseo-not-found-{uuid.uuid4().hex[:12]}", "error-leak")
        return {"fetched": fetched, "not_found": not_found,
                "user_agent": USER_AGENT,
                "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    finally:
        if own:
            client.close()
