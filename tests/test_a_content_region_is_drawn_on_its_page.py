"""Content's regions are drawn on the page they came from (item 245).

The operator, on Content's "This page" tab: "items clickable with no
resulting action". Each region was a button whose press set a class styled
exactly like hover. The regions were built for a picture that was never
drawn: each carries its rect on the rendered page, and the rendered pass
photographs the page.

  - With a screenshot, the page is drawn with a numbered box per region
    (the Accessibility overlay's component); pressing a row outlines its box
    and opens the row's text, and pressing the box again clears it.
  - Without one, the rows are not buttons, and a line says why.
  - The rendered pass reads a region as laid out (`innerText`), so names do
    not run words together, and a region inside another is counted once.
  - A furniture row says which rule made it furniture.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote

import httpx
import pytest

from clauditseo import axe
from clauditseo.db.connection import connect
from clauditseo.modules.cnt import content_hash
from clauditseo.persistence import repo, runs
from tests.needs_build import needs_build

NEEDS_BROWSER = pytest.mark.skipif(not axe.available(),
                                   reason="needs clauditseo[render] and `playwright install chromium`")

MENU = """<!doctype html><html><head><title>Menu</title></head><body>
<nav><ul><li><a href="/webdesign/">Webdesign</a><div>
  <h3>About the Design Process</h3><p>Learn a little about how the design process works</p>
</div></li></ul></nav>
<main><p>Our <b>own</b> words about building a website for your business today.</p></main>
</body></html>"""


@pytest.fixture(scope="module")
def menu_site():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            body = MENU.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/"
    finally:
        server.shutdown()


@NEEDS_BROWSER
def test_a_region_inside_another_is_counted_once_and_read_with_its_spaces(menu_site):
    blocks = axe.run_page(menu_site)["text_blocks"]
    texts = [b["text"] for b in blocks]
    nav = [b for b in blocks if b["landmark"] == "nav"]
    assert len(nav) == 1, texts
    assert nav[0]["text"].startswith("Webdesign About the Design Process"), nav[0]["text"]
    assert "WebdesignAbout" not in " ".join(texts), texts
    # Its words once, not again for the heading and paragraph inside it.
    assert nav[0]["words"] == len(nav[0]["text"].split())
    main = [b for b in blocks if b["landmark"] == "main"]
    assert main and "Our own words" in main[0]["text"], texts


# --- the payload and the tab ----------------------------------------------

SITE = "regions.fixture"
PAGE = f"https://{SITE}/webdesign/"
BARE = f"https://{SITE}/bare/"
OTHERS = [f"https://{SITE}/p{n}/" for n in range(9)]
NAV_TEXT = "Webdesign About the Design Process Learn a little about it"
REPEATED = "Call us today for a free quote on your new website design"
OWN = ("A page's own copy about web design, long enough to read as a region "
       "of its own and to be expanded when the reader presses its row.")


def _blk(tag, text, landmark="main", y=0):
    return {"tag": tag, "landmark": landmark, "words": len(text.split()),
            "name": " ".join(text.split()[:6]), "excerpt": text,
            "hash": content_hash(text), "rect": {"x": 10, "y": y, "w": 300, "h": 40}}


def _plant(db, site_id: str) -> str:
    conn = connect(db)
    run_id = runs.create_run(conn, site_id, ["CNT", "A11Y"], "T2")
    pages = [PAGE, BARE, *OTHERS]
    runs.store_evidence(conn, run_id, {"start_url": f"https://{SITE}/", "pages": [
        {"url": u, "status": 200, "content_type": "text/html", "title": "Page",
         "word_count": 120, "opening": "A page's own copy"} for u in pages]})
    blocks = {u: [_blk("li", NAV_TEXT, "nav", 0), _blk("p", REPEATED, "none", 60)]
              for u in pages}
    blocks[PAGE] += [_blk("p", OWN, "main", 120), _blk("p", OWN + " More.", "main", 180)]
    blocks[BARE] += [_blk("p", OWN + " Bare.", "main", 120)]
    with conn:
        conn.execute(
            "INSERT INTO findings (id, run_id, dimension, check_id, severity, source,"
            " summary, affected_urls, fingerprint, created_at, evidence) VALUES (?, ?,"
            " 'A11Y', 'axe-sampled', 'info', 'deterministic', 's', '[]', 'axe-sampled', ?, ?)",
            (repo.create_id(), run_id, repo.now_iso(), json.dumps({
                "rendered": len(pages), "crawled": len(pages), "text_blocks": blocks,
                # A picture of PAGE only: BARE is the no-screenshot case.
                "screens": {PAGE: {"screenshot_path": "x.png", "screenshot_w": 1280,
                                   "screenshot_h": 800}}})))
    # A finding on each page: the page picker reaches only pages a finding
    # names, which is how a narrowed page is opened at all.
    with conn:
        for url in (PAGE, BARE):
            fp = f"thin-{url}"
            conn.execute(
                "INSERT INTO findings (id, run_id, dimension, check_id, severity, source,"
                " summary, affected_urls, fingerprint, created_at, evidence) VALUES (?, ?,"
                " 'CNT', 'thin', 'medium', 'deterministic', 'Thin page', ?, ?, ?, '{}')",
                (repo.create_id(), run_id, json.dumps([url]), fp, repo.now_iso()))
            conn.execute(
                "INSERT INTO finding_states (site_id, fingerprint, state, changed_by_run,"
                " updated_at) VALUES (?, ?, 'open', ?, ?)", (site_id, fp, run_id, repo.now_iso()))
    runs.mark_complete(conn, run_id, repo.now_iso())
    conn.commit()
    conn.close()
    return run_id


def test_the_payload_carries_the_picture_and_why_a_region_is_furniture(tmp_path):
    from clauditseo.db.migrate import migrate
    conn = connect(tmp_path / "r.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site = repo.create_site(conn, repo.create_client(conn, op, "R"), SITE)
    conn.close()
    run_id = _plant(tmp_path / "r.db", site)
    conn = connect(tmp_path / "r.db")
    got = runs.content_blocks_payload(conn, run_id, PAGE)
    assert got["screenshot"] and got["doc"] == {"w": 1280, "h": 800}, got
    why = {b["name"].split()[0]: (b["klass"], b["boilerplate_why"], b["on_pages"])
           for b in got["blocks"]}
    assert why["Webdesign"] == ("boilerplate", "landmark", 11), why
    assert why["Call"] == ("boilerplate", "repeated", 11), why
    assert runs.content_blocks_payload(conn, run_id, BARE)["screenshot"] is None
    conn.close()


@pytest.fixture(scope="module")
def served():
    from tests.test_triage_ranks_the_section_rail import _serve
    server, thread, db, base = _serve("regions")
    try:
        client = httpx.post(f"{base}/api/clients", json={"name": "Regions Co"}, timeout=30).json()
        site = httpx.post(f"{base}/api/clients/{client['id']}/sites",
                          json={"domain": SITE}, timeout=30).json()
        _plant(db, site["id"])
        yield base, site["id"]
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


_JS = """() => ({
  boxes: document.querySelectorAll('.tp-overlay .overlay-box').length,
  selBox: [...document.querySelectorAll('.tp-overlay .overlay-box.is-sel')].map((b) => b.dataset.box),
  selRow: [...document.querySelectorAll('.tp-row.is-sel')].length,
  detail: (document.querySelector('.tp-row.is-sel .tp-excerpt')?.textContent || '').trim(),
  buttons: document.querySelectorAll('.tp-rows button').length,
  noshot: !!document.querySelector('.tp-noshot'),
  notes: [...document.querySelectorAll('.tp-note')].map((n) => n.textContent.trim()),
})"""


def _open(pg, base, site_id, page):
    pg.goto(f"{base}/#/sites/{site_id}?tab=findings&part=content&ctab=page"
            f"&page={quote(page, safe='')}", wait_until="load", timeout=30_000)
    pg.wait_for_selector(".tp-rows", timeout=30_000)


@NEEDS_BROWSER
@needs_build
def test_a_row_outlines_its_box_and_opens_its_text(browser, served):
    base, site_id = served
    pg = browser.new_page(viewport={"width": 1400, "height": 1000})
    try:
        _open(pg, base, site_id, PAGE)
        got = pg.evaluate(_JS)
        assert got["boxes"] == 4 and not got["noshot"], got
        assert any("navigation or footer" in n for n in got["notes"]), got["notes"]
        assert any("repeated on 11 of 11 rendered pages" in n for n in got["notes"]), got["notes"]
        pg.locator(".tp-rows .tp-rowbtn").nth(2).click()
        got = pg.evaluate(_JS)
        assert got["selBox"] == ["3"] and got["selRow"] == 1, got
        assert got["detail"].startswith("A page's own copy"), got
        # Pressing the box again clears both.
        pg.click('.tp-overlay .overlay-box[data-box="3"]')
        got = pg.evaluate(_JS)
        assert got["selBox"] == [] and got["selRow"] == 0, got
    finally:
        pg.close()


@NEEDS_BROWSER
@needs_build
def test_without_a_screenshot_the_rows_are_not_buttons(browser, served):
    base, site_id = served
    pg = browser.new_page(viewport={"width": 1400, "height": 1000})
    try:
        _open(pg, base, site_id, BARE)
        got = pg.evaluate(_JS)
        assert got["buttons"] == 0 and got["noshot"] and got["boxes"] == 0, got
    finally:
        pg.close()
