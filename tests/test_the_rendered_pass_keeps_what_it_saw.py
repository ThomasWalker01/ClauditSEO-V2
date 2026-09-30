"""The rendered pass records where each violation is, and what the page looked like.

Relay item 136j Part B, answering `QUESTIONS.md` Q-53 with "build them".

Neither input existed. `axe.py`'s browser call returned `target`, `html` and
`failureSummary` per node and no bounding rect, and no screenshot was
captured or persisted anywhere in the product — the only `screenshot` in
`clauditseo/` was an ONP filename-pattern regex. 136f Block 2 draws boxes
over a page image and could not be built on either.

**The coverage caveat, recorded against Q-53 and repeated here because this
is the file that would otherwise imply the opposite.** The rendered pass
samples: 5 of 227 pages on the run this was measured against. So a page
having no screenshot is the normal case, not a fault, and every clause below
that asserts absence is asserting the honest state rather than a bug.
"""

from __future__ import annotations

import json

import pytest

from clauditseo import axe


# --- the parts that need no browser --------------------------------------

def test_a_pages_picture_is_named_by_a_hash_of_its_url():
    """A slug of the path would collide (two sites, one `/about`) and can
    contain characters a filesystem refuses. A hash does neither, and is the
    same identity a finding row can compute for itself."""
    a = axe.page_hash("https://x.test/about")
    b = axe.page_hash("https://x.test/about/")
    assert len(a) == 32 and all(c in "0123456789abcdef" for c in a)
    assert a != b, "two different URLs must not share a picture"
    assert axe.page_hash("https://x.test/about") == a, "and it is stable"


def test_a_runs_pictures_live_under_that_run():
    """Retention is `rmtree` of a path the run already knows, which is only
    true while the directory is keyed by run and nothing else."""
    assert axe.screens_dir("abc").name == "abc"
    assert axe.screens_dir("abc").parent == axe.SCREENS


def test_the_evaluate_asks_for_a_rect_and_the_two_page_dimensions():
    """Read from the source: reaching this needs Chromium and the property
    is that the browser is ASKED, which the source settles."""
    import inspect
    src = inspect.getsource(axe.run_page)
    assert "getBoundingClientRect" in src, src[:200]
    assert "window.scrollX" in src and "window.scrollY" in src, (
        "a viewport-relative box is wrong on a full-page screenshot")
    assert "scrollHeight" in src and "innerWidth" in src, (
        "the boxes need the dimensions they are relative to")


def test_a_node_inside_an_iframe_gets_no_box_rather_than_a_guessed_one():
    """`target` is an array because axe walks into frames. Only a
    single-entry target is resolvable from the top document, and a box at
    the wrong coordinates is worse than an absent one."""
    import inspect
    src = inspect.getsource(axe.run_page)
    assert "t.length !== 1" in src, src[src.index("const box"):][:300]


def test_a_zero_area_rect_is_kept():
    """An element clipped to nothing is a real violation at a real position
    — and being invisible is frequently the defect itself, so dropping it
    would delete the finding that matters most."""
    import inspect
    src = inspect.getsource(axe.run_page)
    box = src[src.index("const box"):src.index("return {\n                    violations")]
    assert "width" in box and "height" in box
    assert "b.width > 0" not in box and "if (!b.width" not in box, box


def test_a_rect_reaches_the_finding_and_an_unresolved_one_is_absent():
    """Absent rather than null: 136f draws its absent-data state for a node
    it cannot place, which is a different thing from a box at the origin."""
    result = {"violations": [{
        "id": "color-contrast", "impact": "serious", "help": "h", "tags": [],
        "nodes": [{"target": ["#a"], "html": "<a>", "failureSummary": "f",
                   "rect": {"x": 10, "y": 20, "w": 30, "h": 0}},
                  {"target": ["iframe", "#b"], "html": "<b>",
                   "failureSummary": "f", "rect": None}]}]}
    found = axe.findings_from(result, "https://x.test/", "/")
    inst = found[0].evidence["instances"]
    assert inst[0]["rect"] == {"x": 10, "y": 20, "w": 30, "h": 0}, inst[0]
    assert "rect" not in inst[1], inst[1]
    assert found[0].evidence["count"] == 2, found[0].evidence["count"]


def test_the_screenshot_is_optional_and_its_absence_is_not_an_error():
    """`run_page` is called for every rendered page whether or not the run
    can file pictures. A run with no id — a CLI audit, a test — must behave
    exactly as it did before this item."""
    import inspect
    sig = inspect.signature(axe.run_page)
    assert sig.parameters["screenshot_to"].default is None


# --- retention ------------------------------------------------------------

def test_deleting_a_run_deletes_its_screens(tmp_path, monkeypatch):
    """The only thing this product writes outside the database, so the only
    thing a delete can orphan. A directory of pictures belonging to a run
    that no longer exists is unreachable by every route and invisible to
    every count."""
    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate
    from clauditseo.persistence import repo, runs

    monkeypatch.setattr(axe, "SCREENS", tmp_path / "screens")
    conn = connect(tmp_path / "c.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site = repo.create_site(conn, repo.create_client(conn, op, "C"), "x.test")
    run_id = runs.create_run(conn, site, ["A11Y"], "T2")

    shot = axe.screens_dir(run_id) / f"{axe.page_hash('https://x.test/')}.png"
    shot.parent.mkdir(parents=True)
    shot.write_bytes(b"\x89PNG\r\n\x1a\n")
    assert shot.is_file()

    runs.delete_run(conn, run_id)
    assert not shot.exists(), "the picture outlived the run it belongs to"
    assert not shot.parent.exists(), "and so did its directory"
    conn.close()


def test_a_failed_delete_of_the_pictures_does_not_keep_the_run(tmp_path, monkeypatch):
    """The removal is outside the transaction on purpose. If it were inside,
    a locked file would roll the delete back — leaving the run AND the
    pictures, which is the state this is meant to prevent."""
    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate
    from clauditseo.persistence import repo, runs

    monkeypatch.setattr(axe, "SCREENS", tmp_path / "screens")
    conn = connect(tmp_path / "c.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site = repo.create_site(conn, repo.create_client(conn, op, "C"), "x.test")
    run_id = runs.create_run(conn, site, ["A11Y"], "T2")

    def boom(_):
        raise OSError("locked")

    monkeypatch.setattr(runs, "_drop_screens", boom)
    with pytest.raises(OSError):
        runs.delete_run(conn, run_id)
    assert conn.execute("SELECT 1 FROM audit_runs WHERE id=?",
                        (run_id,)).fetchone() is None, (
        "the run survived a failure to remove its pictures")
    conn.close()


# --- the route ------------------------------------------------------------

@pytest.fixture()
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from clauditseo.api.app import create_app
    monkeypatch.setattr(axe, "SCREENS", tmp_path / "screens")
    app = create_app(db_path=tmp_path / "c.db")
    return TestClient(app)


def test_a_page_the_pass_did_not_visit_has_no_picture_and_says_so(client):
    """404 with a sentence, not an empty body. The absent case is the common
    one — the pass samples — so the reason has to travel with the refusal or
    every blank overlay looks like a bug."""
    r = client.get(f"/api/runs/nosuchrun/screens/{'a' * 32}.png")
    assert r.status_code == 404, r.status_code


def test_the_name_is_validated_before_it_reaches_the_filesystem(client):
    """The one route that serves a file from `data/`, so the one place a
    traversal is reachable at all."""
    for bad in ("../../secrets.png", "..%2f..%2fx.png", "short.png",
                "z" * 32 + ".png", "a" * 32 + ".txt"):
        r = client.get(f"/api/runs/r1/screens/{bad}")
        assert r.status_code in (404, 422), (bad, r.status_code)


def test_the_route_is_behind_the_same_check_as_the_findings():
    """A screenshot of a client's site is client data, and this route would
    otherwise be the one way to read it without the operator check every
    other route makes."""
    import inspect

    from clauditseo.api import app as appmod
    src = inspect.getsource(appmod)
    body = src[src.index('def run_screenshot('):]
    body = body[:body.index("@app.get")]
    assert "check_run(conn, operator, run_id)" in body, body[:400]
    assert "immutable" in body, "a file named by a content hash should be cacheable"


# --- the capture itself, which needs a browser ---------------------------

@pytest.mark.skipif(not axe.available(),
                    reason="needs clauditseo[render] and `playwright install chromium`")
def test_a_screenshot_is_stored_per_rendered_page_and_the_rects_are_real(tmp_path):
    """The one clause here that actually renders. Everything above asserts
    the shape of the arrangement; this asserts that a browser, pointed at a
    page with a known violation, produces a file and a box with area."""
    from tests.conftest import FixtureSite

    body = ("<html lang=en><head><title>t</title></head><body><main>"
            "<h1>h</h1>"
            # Deliberate contrast failure, which axe reports with a node.
            "<p style='color:#eee;background:#fff'>faint</p>"
            "</main></body></html>")
    robots = "User-agent: *\nAllow: /\n"
    fixture = FixtureSite({"/": (200, {}, body),
                           "/robots.txt": (200, {"Content-Type": "text/plain"},
                                           robots)}).start()
    try:
        shot = tmp_path / "screens" / "run1" / "abc.png"
        result = axe.run_page(fixture.base_url + "/", screenshot_to=shot)
    finally:
        fixture.stop()

    assert shot.is_file(), "no picture was written"
    assert shot.read_bytes().startswith(bytes.fromhex("89504e47")), (
        "the file written is not a PNG")
    assert result["screenshot"]["bytes"] == shot.stat().st_size

    # The page dimensions the boxes are relative to.
    assert result["document"]["w"] > 0 and result["document"]["h"] > 0, result["document"]
    assert result["viewport"]["w"] > 0, result["viewport"]

    nodes = [n for v in result["violations"] for n in v["nodes"]]
    assert nodes, "the fixture produced no violation to place"
    placed = [n["rect"] for n in nodes if n.get("rect")]
    assert placed, "every node was unplaceable, so the rect walk found nothing"
    assert any(r["w"] > 0 and r["h"] > 0 for r in placed), placed
