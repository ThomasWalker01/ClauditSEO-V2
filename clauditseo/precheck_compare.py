"""The precheck compared with the one before it, and what that suggests.

Brief v4 Item 2 (`_plans/site-screen-brief-v4-2026-09-03.md`). The precheck
was three numbers and a timestamp; the operator had to remember last time's
numbers to know whether anything moved. This puts the prior beside the now,
as sets rather than counts - the URLs the precheck already stores in its
payload - and turns the difference into the one decision the precheck
exists to inform: which scan to run, if any.

The suggestion is a rule over the counts, not a model: free, explainable,
and it names the scan-matrix cell so the Audit pane can pre-select it.

**What the stored payload cannot say, said here.** The precheck stores one
list for navigation and footer together - the crawler's link extraction
keeps a URL once, under whichever region saw it first - so "moved between
nav and footer" is not observable and is not reported. The sitemap list is
capped at `PICKER_LIMIT` (500) and says so in `page_urls_capped`; a diff
over a capped list is a diff over its first 500, and the payload says
`capped` when that is what it is.
"""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlsplit

from clauditseo.precheck import _diff_key

#: Added plus removed sitemap pages, as a share of what the prior check
#: published, at or above which a Full scan is suggested ...
SUGGEST_MIN_SHARE = 0.10
#: ... and never for fewer pages than this, whatever the share: on a
#: ten-page site one page is ten per cent.
SUGGEST_MIN_PAGES = 3


def instant(iso: str | None) -> datetime | None:
    """A stored stamp as a moment, so two can be ordered (item 254).

    A precheck is stamped in local time with its offset and a run in UTC, so
    ordering the two as text is wrong by the offset: on a UTC+10 machine a
    check made nine hours before an audit sorted after it. A stamp with no
    offset is read as UTC, which is what the run columns hold."""
    if not iso:
        return None
    try:
        at = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    return at if at.tzinfo else at.replace(tzinfo=timezone.utc)


def later(a: str | None, b: str | None) -> bool:
    """Whether `a` is a later moment than `b`; False where either is unread."""
    x, y = instant(a), instant(b)
    return bool(x and y and x > y)


def path_key(u: str) -> str:
    """One identity for a precheck URL and an audit's stored path.

    The precheck holds absolute URLs and `audit_runs.crawled_paths` holds
    paths; both are compared as a path with its query, trailing slash
    dropped the way `precheck._diff_key` drops it, so a sitemap and a crawl
    that disagree about the slash still name one page.
    """
    if "://" in u:
        parts = urlsplit(_diff_key(u))
        path = parts.path or "/"
        return path + (f"?{parts.query}" if parts.query else "")
    path, _, query = u.partition("?")
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    return (path or "/") + (f"?{query}" if query else "")


def sets_of(payload: dict) -> tuple[set[str], set[str] | None]:
    """The nav set and the sitemap set of one stored precheck. The sitemap
    set is None whenever the sitemap could not be read: no set, not an
    empty one, so a diff against it is not "everything removed"."""
    nav = {path_key(u) for u in payload.get("nav_urls") or []}
    full = ({path_key(u) for u in payload.get("page_urls") or []}
            if payload.get("sitemap_state") == "ok" else None)
    return nav, full


def diff(now: set[str] | None, prior: set[str] | None) -> dict:
    if now is None or prior is None:
        return {"added": [], "removed": [], "known": False}
    return {"added": sorted(now - prior), "removed": sorted(prior - now), "known": True}


def suggest(full_added: int, full_removed: int, prior_full: int | None,
            nav_changed: int, *, min_share: float = SUGGEST_MIN_SHARE,
            min_pages: int = SUGGEST_MIN_PAGES, basis: str = "precheck") -> dict:
    """Which scan the difference calls for.

    Full · Quick when the sitemap gained or lost at least `min_share` of
    what the prior published **and** at least `min_pages` pages; Nav · Quick
    when only the navigation changed; otherwise nothing to run. Both
    thresholds fire at exactly the line, not above it.
    """
    changed = full_added + full_removed
    share = (changed / prior_full) if prior_full else None
    if (basis == "crawl" and prior_full and share is not None
            and share >= min_share and changed >= min_pages):
        # Against a crawl nothing is "added or removed" (item 254): the
        # sitemap declares pages the last crawl did not read.
        return {"cell": "full:quick", "changed": changed, "share": share,
                "reason": f"{changed} page{'s' if changed != 1 else ''} the sitemap "
                          f"declares {'were' if changed != 1 else 'was'} not in the last "
                          f"crawl, {round(share * 100)}% of the {prior_full} it read, "
                          f"over the {round(min_share * 100)}% line"}
    if prior_full and share is not None and share >= min_share and changed >= min_pages:
        return {"cell": "full:quick", "changed": changed, "share": share,
                "reason": f"{changed} page{'s' if changed != 1 else ''} added or removed "
                          f"is {round(share * 100)}% of the {prior_full} published before, "
                          f"over the {round(min_share * 100)}% line"}
    if nav_changed:
        return {"cell": "nav:quick", "changed": changed, "share": share,
                "reason": f"only the navigation changed ({nav_changed} page"
                          f"{'s' if nav_changed != 1 else ''}), and a Nav scan covers it"}
    return {"cell": None, "changed": changed, "share": share,
            "reason": ("nothing to run: " + (
                f"{changed} page{'s' if changed != 1 else ''} changed, under the "
                f"{round(min_share * 100)}% line and the {min_pages}-page floor"
                if changed else "nothing published moved since the prior check"))}


#: Why a first check has nothing beside it when a crawl exists (item 254).
CRAWL_IS_NEWER = "the last crawl is newer than this check; re-run the precheck"


def compare(now: dict, prior: dict | None, *, prior_kind: str,
            prior_at: str | None, before_audit: dict | None,
            audit_paths: list[str] | None = None,
            prior_reason: str | None = None,
            newest_audit_at: str | None = None) -> dict:
    """The comparison payload the pane renders.

    `prior` is the previous precheck's payload, or None when the prior is
    an audit's crawl (`audit_paths`) - the first check has no predecessor
    and diffs against the newest audit's `crawled_paths`, labelled `crawl`.

    **A crawl prior is not a prior check (item 254).** Its two lists are
    "declared, not crawled" and "crawled, not declared": a page the crawl
    read and the sitemap does not list is live, not removed. The payload
    keeps the `added` / `removed` keys so one shape serves both kinds, the
    pane words them by `prior.kind`, and only a `precheck` prior's `removed`
    may mark findings "on pages gone". The suggestion counts the first list
    alone, since nothing in the second calls for a scan.

    `stale` names the newest audit where it started after this check: the
    counts are then older than a crawl of the same site, and the pane says so.
    """
    now_nav, now_full = sets_of(now)
    if prior is not None:
        prior_nav, prior_full = sets_of(prior)
    else:
        prior_nav = None
        prior_full = {path_key(p) for p in (audit_paths or [])} or None
    nav = diff(now_nav, prior_nav)
    full = diff(now_full, prior_full)
    prior_full_n = len(prior_full) if prior_full is not None else None
    crawl = prior_kind == "crawl"
    sug = suggest(len(full["added"]), 0 if crawl else len(full["removed"]), prior_full_n,
                  len(nav["added"]) + len(nav["removed"]),
                  basis="crawl" if crawl else "precheck")
    checked = now.get("checked_at")
    stale = {"audit_at": newest_audit_at} if later(newest_audit_at, checked) else None
    return {
        "now": {"checked_at": now.get("checked_at"), "nav": len(now_nav),
                "full": len(now_full) if now_full is not None else None,
                "full_capped": bool(now.get("page_urls_capped")),
                "sitemap_files": now.get("sitemap_files"),
                "sitemap_state": now.get("sitemap_state")},
        "stale": stale,
        "prior": {"kind": prior_kind, "at": prior_at,
                  # Why there is no prior where one might be expected.
                  "reason": prior_reason,
                  "before_audit": before_audit,
                  "nav": len(prior_nav) if prior_nav is not None else None,
                  "full": prior_full_n,
                  "full_capped": bool(prior.get("page_urls_capped")) if prior else False,
                  "sitemap_files": prior.get("sitemap_files") if prior else None,
                  "sitemap_state": prior.get("sitemap_state") if prior else None},
        "diff": {"nav": nav, "full": full,
                 "capped": bool(now.get("page_urls_capped"))
                           or bool(prior and prior.get("page_urls_capped"))},
        "suggestion": {**sug, "min_share": SUGGEST_MIN_SHARE,
                       "min_pages": SUGGEST_MIN_PAGES},
    }
