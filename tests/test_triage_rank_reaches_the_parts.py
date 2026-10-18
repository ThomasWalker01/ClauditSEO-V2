"""The ranked fixture: a site whose audit carries the five checks WF-07 named.

**The name is historical**, like the rail file beside it. This guarded that
triage's five ranked checks reached the five parts they were about, after the
rail read "-" on every part because triage invented check ids the part
registry did not know. Item 196 retired the purchased ranking: the order is
computed from the record now, so every id in it is one the registry knows and
that defect cannot recur in that form.

What survives is what `test_the_four_destinations` imports - `EXPECTED` and
the `served` fixture, a site with an audit carrying those five checks. The
claim the clauses made is carried forward by
`test_the_audit_ranks_its_own_work.py`: every ranked row names the part it
belongs to, which is what the rail needs in order to place anything at all.

Not renamed, for the reason the rail file records: an import that moves is an
import that can fail at collection, and collection is the worst place to be
wrong.
ranking panel names each check's part with what is open there.

Brief v2 step C (`_plans/site-screen-brief-v2-2026-09-03.md`, WF-07). On
the operator's site the rail read "–" on every part under "Ranked 5 checks
against this audit": triage names checks of its own - `sitemap-coverage-regressed`,
`duplicate-content-regressed`, `img-alt-missing-fix-incomplete`,
`link-name-missing-scale`, `heading-skip-multiple` - and the server's
part-of-check registry knows only the sweep's ids, so its answer was null
for all five. The join is by check-id family against the checks open in
each part; the acceptance the brief sets, with those five, is Crawl &
sitemaps 1, Content 2, Images 3, Accessibility 4, Headings 5.

**The fixture.** The sweep fixture's audit has `img-alt-missing` and
`heading-skip` open; three findings are added to the result before it is
stored - `sitemap-coverage` (TEC), `duplicate-content` (CNT),
`link-name-missing` (A11Y) - so every family has a check open in its part,
as the operator's site has. Then triage's report is stored with the five
checks in the brief's order.
"""

from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

import pytest

from clauditseo.db.connection import connect
from clauditseo.persistence import runs
from tests.test_a11y_rendered import DIST

NEEDS_BROWSER = pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("playwright")
    is None, reason="playwright is not installed")

pytestmark = [
    NEEDS_BROWSER,
    pytest.mark.skipif(not (DIST / "index.html").is_file(),
                       reason="dashboard not built (npm run build in dashboard/)"),
]

RANKED = [
    # A triage cluster name the sweep registry does not know, so the server
    # cannot place it and the client-side family join is what this test
    # exercises. `sitemap-regression` was that name until item 137 (brief v18
    # step AZ) made it a real registered check filed under `crawl`; a
    # registered check the server places itself, which defeats the precondition
    # below. `sitemap-coverage-regressed` is unregistered and still family-joins
    # to Crawl via the open `sitemap-coverage`.
    ("sitemap-coverage-regressed", "high", "Declared sitemap entries collapsed from 272 to 50"),
    ("duplicate-content-regressed", "high", "Five duplicate-content regressions in CNT"),
    ("img-alt-missing-fix-incomplete", "high", "Prior fix did not persist; root cause unknown"),
    ("link-name-missing-scale", "medium", "100+ instances, compliance risk"),
    ("heading-skip-multiple", "medium", "Template-fixable"),
]
EXPECTED = {"Crawl & sitemaps": "1", "Content": "2", "Images": "3",
            "Accessibility": "4", "Headings": "5"}

_JS = """() => ({
  // The rank digit stands on the shop's part header since brief v24 step BO.
  ranks: Object.fromEntries([...document.querySelectorAll('.catalogue-shop .crow-part')].map((li) => [
    (li.querySelector('.crow-part-link')?.textContent || '').trim(),
    (li.querySelector('.anat-rank')?.textContent || '').trim()])),
  note: (document.querySelector('.anat-rail-note')?.textContent || '').trim(),
  table: [...document.querySelectorAll('.tri-table tbody tr')].map((tr) => ({
    n: tr.querySelector('td')?.textContent.trim(),
    check: tr.querySelector('code')?.textContent.trim(),
    part: (tr.querySelector('.tri-part')?.textContent || '').trim(),
    open: (tr.querySelector('td:last-child')?.textContent || '').trim(),
  })),
  open: (document.querySelector('.anat-pane h2.part-h2')?.textContent || '').trim(),
  partRank: (document.querySelector('.anat-pane .part-rank')?.textContent || '').trim(),
})"""


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def served():
    import tempfile

    import httpx
    import uvicorn

    from clauditseo.api.app import create_app
    from clauditseo.engine.types import Finding, Severity
    from tests.test_coverage import DIMS, _Hub, _run

    tmp = Path(tempfile.mkdtemp(prefix="triagejoin"))
    db = tmp / "clauditseo.db"
    app = create_app(db_path=db)
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port,
                                           log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 30
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    if not server.started:
        pytest.fail("server did not start")
    base = f"http://127.0.0.1:{port}"
    try:
        client = httpx.post(f"{base}/api/clients", json={"name": "Join Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": "join.fixture"}, timeout=30).json()
        conn = connect(db)
        result = _run(_Hub())
        # Five families, one check open in each part, as the operator's site has.
        result.findings.extend([
            Finding(dimension="ONP", check_id="img-alt-missing", severity=Severity.MEDIUM,
                    summary="19 of 42 images lack alt text.",
                    subject="images", affected_urls=["https://x.test/"]),
            Finding(dimension="ONP", check_id="heading-skip", severity=Severity.LOW,
                    summary="Heading level jumps H1 to H3.",
                    subject="headings", affected_urls=["https://x.test/"]),
            Finding(dimension="TEC", check_id="sitemap-coverage", severity=Severity.HIGH,
                    summary="The sitemap declares 272 pages; the crawl reached 50.",
                    subject="sitemap", affected_urls=["https://x.test/sitemap.xml"]),
            Finding(dimension="CNT", check_id="duplicate-content", severity=Severity.HIGH,
                    summary="Two pages carry the same body copy.",
                    subject="/a|/b", affected_urls=["https://x.test/a", "https://x.test/b"]),
            Finding(dimension="A11Y", check_id="link-name-missing", severity=Severity.MEDIUM,
                    summary="41 links have no accessible name.",
                    subject="links", affected_urls=["https://x.test/"]),
        ])
        run_id = runs.create_run(conn, site["id"], DIMS, "T2")
        runs.complete_run(conn, run_id, result)
        runs.store_expert_report(
            conn, run_id, "triage",
            {"model": "test-model", "report": "# Triage\n\nRanked five.",
             "findings": [{"code": c, "severity": s, "summary": w} for c, s, w in RANKED]})
        conn.close()
        yield base, site["id"], run_id
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            yield b
        finally:
            b.close()
