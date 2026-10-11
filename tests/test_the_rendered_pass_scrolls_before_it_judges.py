"""The accessibility pass loads what a visitor's scrolling would load.

Operator, 2026-10-01: the a11y screen showed twenty22's home page with empty
frames where its images are. Lazy loaders fill an image only once it scrolls
into view, and a full-page screenshot does not scroll. Script-delay plugins
hold a page's scripts until the first input. So `axe.run_page` now moves the
mouse and walks down the page before axe judges it.

On twenty22 itself the frames are real. Its CSP blocks the `data:` scripts
LiteSpeed serves Bricks' settings in, and `bricksLazyLoad` then fails in any
browser, so the picture there shows what visitors get.
"""

from __future__ import annotations

import pytest

from clauditseo import axe


def test_the_walk_happens_before_axe_judges_the_page():
    """Content a loader adds is content axe has to judge, and a box measured
    before the images take their height is drawn in the wrong place."""
    import inspect
    src = inspect.getsource(axe.run_page)
    assert src.index("_settle(pg)") < src.index("pg.evaluate(_script())"), src[:600]


SVG = ("<svg xmlns='http://www.w3.org/2000/svg' width='40' height='40'>"
       "<rect width='40' height='40' fill='#c00'/></svg>")

#: A script held until the first input, and an image filled only when it
#: scrolls into view, far below the fold.
PAGE = """<html lang=en><head><title>t</title></head><body><main>
<h1>Lazy page</h1>
<div style="height:4000px"></div>
<img id=lazy alt="a red square" data-src="/pic.svg" width=40 height=40
     src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'/%3E">
<p id=seen></p>
<p id=held></p>
<script>
new IntersectionObserver((es, io) => es.forEach(e => {
  if (!e.isIntersecting) return;
  e.target.src = e.target.dataset.src;
  document.getElementById('seen').textContent = 'the lazy image came into view';
  io.disconnect();
})).observe(document.getElementById('lazy'));
const release = () => {
  document.getElementById('held').textContent = 'the held script ran after input';
  removeEventListener('mouseover', release);
};
addEventListener('mouseover', release);
</script>
</main></body></html>"""


@pytest.mark.skipif(not axe.available(),
                    reason="needs clauditseo[render] and `playwright install chromium`")
def test_a_lazy_image_and_a_held_script_are_loaded_before_the_page_is_judged(tmp_path):
    from tests.conftest import FixtureSite

    fixture = FixtureSite({
        "/": (200, {}, PAGE),
        "/pic.svg": (200, {"Content-Type": "image/svg+xml"}, SVG),
    }).start()
    try:
        shot = tmp_path / "shot.png"
        result = axe.run_page(fixture.base_url + "/", screenshot_to=shot)
    finally:
        fixture.stop()

    said = " | ".join(b["text"] for b in result["text_blocks"])
    assert "the lazy image came into view" in said, said
    assert "the held script ran after input" in said, said
    assert "/pic.svg" in fixture.request_log, fixture.request_log
    assert result["settle"]["unloaded_images"] == 0, result["settle"]
    assert shot.is_file()
