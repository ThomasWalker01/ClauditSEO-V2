"""Bytes for pixels weighs what a visitor would load, and draws one dot per
distinct image (item 241).

Twenty22's Images chart drew one grey dot in both views: the browser pass
read the page's resources once, before any scroll, so the 286 lazy images
below the fold were never fetched and never weighed; the only image weighed
was the header logo, three placements on each of 26 pages, drawn as 78 dots
on one point.

  - The pass scrolls the document before it reads what was fetched, so a
    lazy image below the fold is weighed, from the browser's own record.
  - A same-origin image the page never fetched is weighed by the server's
    size header, and says so (`weight_source: header`).
  - A script lazy loader's image - a `data:` placeholder in `src`, the file in
    `data-lazy-src`, twenty22's WP Rocket markup and 271 of its 366 images -
    is keyed by the file on both sides, so the markup record and the
    measurement meet (the first live audit after the scroll weighed none of
    them: the join was on the placeholder).
  - The payload has one dot per distinct image, carrying the pages it is on:
    a logo on 26 pages is one dot, and a page's view is that page's images.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from clauditseo import imaging
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.persistence import repo, runs

NEEDS_BROWSER = pytest.mark.skipif(not imaging.available(), reason="playwright is not installed")

#: Big enough that `Math.round(bytes / 1024)` is not zero, which the product
#: reads as "not measured".
_PAD = "<!--" + "x" * 3000 + "-->"


def _svg(colour: str) -> bytes:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300">{_PAD}'
            f'<rect width="400" height="300" fill="{colour}"/></svg>').encode()


PAGE = """<!doctype html><html><head><title>Lazy</title></head><body>
<img src="/logo.svg" alt="logo" width="200" height="60">
<div style="height: 5000px">spacer</div>
<img src="/a.svg" alt="a" loading="lazy" width="400" height="300">
<div style="height: 2000px"></div>
<img src="/b.svg" alt="b" loading="lazy" width="400" height="300">
<div style="height: 2000px"></div>
<img src="/c.svg" alt="c" loading="lazy" width="400" height="300">
<div style="display: none"><img src="/hidden.svg" alt="h" loading="lazy"></div>
<div style="height: 2000px"></div>
<img src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
     data-lazy-src="/d.svg" alt="d" class="rocket-lazyload" width="400" height="300">
<script>
  new IntersectionObserver((entries, seen) => {
    for (const e of entries) if (e.isIntersecting) {
      e.target.src = e.target.getAttribute("data-lazy-src"); seen.unobserve(e.target);
    }
  }).observe(document.querySelector(".rocket-lazyload"));
</script>
</body></html>"""

ROUTES = {"/": (b"text/html; charset=utf-8", PAGE.encode()),
          **{f"/{n}.svg": (b"image/svg+xml", _svg(c)) for n, c in
             (("logo", "red"), ("a", "green"), ("b", "blue"), ("c", "gray"), ("hidden", "black"),
              ("d", "white"))}}


@pytest.fixture(scope="module")
def site():
    class Handler(BaseHTTPRequestHandler):
        def _send(self, body: bool):
            entry = ROUTES.get(self.path)
            if entry is None:
                self.send_response(404)
                self.end_headers()
                return
            ctype, payload = entry
            self.send_response(200)
            self.send_header("Content-Type", ctype.decode())
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            if body:
                self.wfile.write(payload)

        def do_GET(self):  # noqa: N802
            self._send(True)

        def do_HEAD(self):  # noqa: N802
            self._send(False)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/"
    finally:
        server.shutdown()


@NEEDS_BROWSER
def test_lazy_images_below_the_fold_are_weighed_and_a_never_fetched_one_by_its_header(site):
    got = imaging.measure([site], breakpoints=(1024,))[site]
    for src in ("/logo.svg", "/a.svg", "/b.svg", "/c.svg"):
        assert got[src]["weight_kb"] and got[src]["weight_source"] == "resource", (src, got[src])
    hidden = got["/hidden.svg"]
    assert hidden["weight_kb"] and hidden["weight_source"] == "header", hidden
    # Keyed by the file the loader swapped in, not by the placeholder.
    assert not [k for k in got if k.startswith("data:")], list(got)
    swapped = got["/d.svg"]
    assert swapped["weight_kb"] and swapped["weight_source"] == "resource", swapped


def test_the_markup_record_carries_the_file_a_lazy_loader_holds():
    from clauditseo.modules.pagefacts import _lazy_src
    assert _lazy_src({"src": "data:image/gif;base64,x", "data-lazy-src": "/d.svg"}) == "/d.svg"
    assert _lazy_src({"data-src": "data:image/gif;base64,x"}) is None
    assert _lazy_src({"src": "/plain.jpg"}) is None


def _image(src, w, h, kb=40):
    return {"src": src, "resolved": f"https://logo.fixture{src}", "alt": "x",
            "rendered": {"1440": [w, h]}, "weight_kb": kb, "weight_source": "resource"}


def test_a_logo_on_26_pages_is_one_dot_and_a_page_shows_its_own(tmp_path):
    conn = connect(tmp_path / "d.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site = repo.create_site(conn, repo.create_client(conn, op, "C"), "logo.fixture")
    run = runs.create_run(conn, site, ["ONP"], "T3")
    pages = [{"url": f"https://logo.fixture/p{n}/", "status": 200, "content_type": "text/html",
              "image_inventory": [_image("/logo.svg", 256, 176, 2)] * 3
              + ([_image("/hero.jpg", 1200, 600, 400)] if n == 0 else [])}
             for n in range(26)]
    runs.store_evidence(conn, run, {"start_url": "https://logo.fixture/", "pages": pages})
    got = runs.image_budget_payload(conn, run)
    logo = [d for d in got["dots"] if d["src"] == "/logo.svg"]
    assert len(logo) == 1 and len(logo[0]["paths"]) == 26 and logo[0]["placements"] == 78, logo
    assert len(got["dots"]) == 2, got["dots"]
    assert got["placements"] == 79 and got["weighed_pages"] == 26, got
    # A page's view is its own distinct images: the logo and, on /p0/, the hero.
    on_p0 = [d["src"] for d in got["dots"] if "/p0/" in d["paths"]]
    on_p5 = [d["src"] for d in got["dots"] if "/p5/" in d["paths"]]
    assert sorted(on_p0) == ["/hero.jpg", "/logo.svg"] and on_p5 == ["/logo.svg"]


@NEEDS_BROWSER
def test_the_stored_record_of_a_lazy_loaded_image_carries_its_weight(site):
    """The live path end to end: crawl the page, measure it in a browser,
    write the evidence. The markup record's `src` is the placeholder; its
    weight arrives only if the two sides are joined on the file."""
    from clauditseo.crawler.crawl import crawl
    from clauditseo.crawler.evidence import snapshot
    from clauditseo.crawler.types import TierBudget
    from clauditseo.engine.types import Tier
    result = crawl(site, Tier.T2, budget=TierBudget(max_pages=1, request_timeout_s=5,
                                                    wall_clock_s=30, delay_s=0))
    measured = imaging.measure([site], breakpoints=(1024,))
    page = next(p for p in snapshot(result, image_measurements=measured)["pages"]
                if p["url"].rstrip("/") == site.rstrip("/"))
    lazy = [r for r in page["image_inventory"] if r.get("lazy_src") == "/d.svg"]
    assert lazy and lazy[0]["src"].startswith("data:"), page["image_inventory"]
    assert lazy[0].get("weight_kb") and lazy[0].get("weight_source") == "resource", lazy[0]


def test_the_crawler_asks_for_a_page_as_a_browser_does():
    """A page that varies on `Accept` hands the crawler the variant a browser
    gets, so the markup and the image pass's measurements are of one page.
    Twenty22 served `.png` to the crawler and `.png.webp` to Chromium, from
    two cached copies, and none of the robots on its home page joined."""
    from clauditseo.crawler.fetch import Fetcher

    class Varies(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            webp = "image/webp" in (self.headers.get("Accept") or "")
            body = (f'<img data-lazy-src="/robot.png{".webp" if webp else ""}">').encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Varies)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        page = Fetcher(5).fetch(f"http://127.0.0.1:{server.server_address[1]}/")
    finally:
        server.shutdown()
    assert "/robot.png.webp" in page.content, page.content



def test_a_dot_weighed_by_its_header_is_drawn():
    """A hollow dot is a ring in its state's colour. Drawn with `fill: none`
    and no stroke, seven of the nine dots on twenty22's home page were not
    drawn at all, and the chart looked as empty as before the fix."""
    import re
    from pathlib import Path
    css = (Path(__file__).resolve().parents[1] / "dashboard/src/images_budget.css").read_text(encoding="utf-8")
    for state in ("ok", "warn", "bad", "mute"):
        rule = re.search(r"\.ib-header\.ib-" + state + r"\s*\{([^}]*)\}", css)
        assert rule and re.search(r"\bstroke\s*:\s*var\(--", rule.group(1)), state
