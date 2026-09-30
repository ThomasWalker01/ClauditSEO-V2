"""Screaming Frog crawl import.

The built-in crawler is polite and small: 500 pages, no JavaScript. Screaming
Frog does 100k pages and renders JS, and its licence includes a headless CLI —
so the highest-leverage move is not to compete with it but to accept its
export. An imported crawl becomes a run with evidence, and every site-scoped
brief works over it exactly as over a native crawl.

Honesty notes, encoded rather than implied:
- SF's export has no robots.txt body, no sitemap inventory, no NAP capture
  and no JSON-LD blocks. Those evidence keys are simply absent, and the
  briefs already distinguish absent-key ("not captured — no finding may rest
  on this") from present-and-empty ("checked, nothing found").
- Column headers drift across SF versions, so they are matched loosely and
  the importer reports what it could not map instead of guessing.
"""

from __future__ import annotations

import csv
import io
import sqlite3

# Canonical field -> substrings that identify the SF column, tried in order.
COLUMNS = {
    "url": ("address",),
    "status": ("status code",),
    "content_type": ("content type", "content"),
    "title": ("title 1",),
    "meta_description": ("meta description 1",),
    "h1": ("h1-1",),
    "word_count": ("word count",),
    "click_depth": ("crawl depth",),
    "canonical": ("canonical link element 1",),
    "meta_robots": ("meta robots 1",),
    "x_robots_tag": ("x-robots-tag 1",),
    "indexability": ("indexability",),
}

MAX_ROWS = 20_000     # keeps the evidence JSON in the tens of megabytes


def parse_screamingfrog_csv(text: str) -> dict:
    """SF internal export -> the evidence shape the briefs read."""
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    # SF sometimes prefixes a one-cell banner row ("Internal - All") above the
    # real header; the header is the first row containing an Address column.
    header_i = next((i for i, r in enumerate(rows[:5])
                     if any("address" in c.strip().lower() for c in r)), None)
    if header_i is None:
        raise ValueError("no Address column found — is this a Screaming Frog "
                         "internal export?")
    header = [c.strip().lower() for c in rows[header_i]]

    mapping: dict[str, int] = {}
    for field, needles in COLUMNS.items():
        for needle in needles:
            hit = next((i for i, c in enumerate(header) if needle in c), None)
            if hit is not None:
                mapping[field] = hit
                break
    unmapped = sorted(set(COLUMNS) - set(mapping))

    pages = []
    truncated = False
    for raw in rows[header_i + 1:]:
        if len(pages) >= MAX_ROWS:
            truncated = True
            break
        if not raw or not raw[mapping["url"]].strip():
            continue
        page: dict = {}
        for field, i in mapping.items():
            value = raw[i].strip() if i < len(raw) else ""
            if field in ("status", "word_count", "click_depth"):
                page[field] = int(value) if value.isdigit() else None
            else:
                page[field] = value or None
        page["discovered_via"] = "screamingfrog"
        pages.append(page)
    if not pages:
        raise ValueError("the export contained no page rows")

    home = min((p for p in pages if p.get("click_depth") is not None),
               key=lambda p: p["click_depth"], default=pages[0])
    return {
        "source": "screamingfrog",
        "source_note": ("Imported from a Screaming Frog export. This crawl "
                        "may include JavaScript-rendered content the built-in "
                        "crawler cannot see. It carries NO robots.txt body, "
                        "sitemap inventory, JSON-LD or NAP capture — those "
                        "evidence keys are absent, not empty."
                        + (f" Unmapped columns: {', '.join(unmapped)}."
                           if unmapped else "")),
        "start_url": home.get("url"),
        "tier": "import",
        "pages": pages,
        "stats": {"pages": len(pages)},
        "truncated_by": f"importer cap of {MAX_ROWS} rows" if truncated else None,
    }


def collect_drop_folder(conn: sqlite3.Connection, folder) -> list[dict]:
    """Sweep a folder of SF CLI exports into evidence runs.

    The autonomy story: Screaming Frog's headless CLI crawls on the
    operator's schedule and writes CSVs; this collects them on the
    scheduler's tick. File-to-site matching is by filename host
    (www.acme.com.au.csv), because guessing from CSV contents would let one
    site's crawl land on another's history — the one failure mode worse than
    a file left unprocessed. Unmatched or unparseable files move to failed/
    with a .reason file; nothing is deleted and nothing is retried silently.
    """
    from pathlib import Path
    from urllib.parse import urlsplit

    root = Path(folder)
    if not root.is_dir():
        return []
    done, failed = root / "done", root / "failed"

    def host_of(domain: str) -> str:
        netloc = urlsplit(domain if "//" in domain else f"//{domain}").netloc
        return (netloc or domain).lower().strip("/")

    sites = {host_of(r["domain"]): r["id"] for r in conn.execute(
        "SELECT id, domain FROM sites WHERE archived_at IS NULL")}
    # A bare-host file should match a www site and vice versa.
    for host, sid in list(sites.items()):
        if host.startswith("www."):
            sites.setdefault(host[4:], sid)
        else:
            sites.setdefault(f"www.{host}", sid)

    results = []
    for path in sorted(root.glob("*.csv")):
        stem = path.stem.lower()
        site_id = sites.get(stem) or sites.get(stem.replace("_", "."))
        outcome: dict = {"file": path.name}
        try:
            if not site_id:
                raise ValueError(f"no site matches host '{stem}'")
            imported = import_crawl(
                conn, site_id,
                path.read_text(encoding="utf-8-sig", errors="replace"))
            done.mkdir(exist_ok=True)
            path.rename(done / path.name)
            outcome.update(status="imported", **imported)
        except Exception as exc:              # noqa: BLE001 - file quarantined, not lost
            failed.mkdir(exist_ok=True)
            target = failed / path.name
            path.rename(target)
            target.with_suffix(".reason").write_text(str(exc), encoding="utf-8")
            outcome.update(status="failed", reason=str(exc))
        results.append(outcome)
    return results


def import_crawl(conn: sqlite3.Connection, site_id: str, csv_text: str) -> dict:
    """Create a completed, score-less run holding the imported evidence.

    Score-less on purpose: the deterministic modules read fetched page bodies,
    which an import does not carry, and a score computed from different
    machinery would not be comparable with the crawler's. The run exists so
    briefs have evidence to read and the memory has a run to walk.
    """
    from clauditseo.persistence import runs as runs_repo
    from clauditseo.persistence.repo import now_iso

    evidence = parse_screamingfrog_csv(csv_text)
    run_id = runs_repo.create_run(conn, site_id, [], "T3")
    runs_repo.store_evidence(conn, run_id, evidence)
    runs_repo.add_progress(
        conn, run_id, f"Imported {evidence['stats']['pages']} page(s) from "
                      "Screaming Frog — no score is computed for imported "
                      "crawls; expert analyses read this evidence directly")
    with conn:
        # Through the same owner as an audit, with no scores: see
        # runs.mark_complete for why an import must not stamp an engine
        # version. This used to be its own UPDATE, which meant the status
        # column had two writers and any rule added to one missed the other.
        runs_repo.mark_complete(conn, run_id, now_iso())
    return {"run_id": run_id, "pages": evidence["stats"]["pages"],
            "truncated": bool(evidence["truncated_by"]),
            "unmapped_note": evidence["source_note"]}
