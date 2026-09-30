"""A lazy-loaded image is checked, weighed and shown as its file (item 246).

On twenty22's `/website-blogs/` the Bytes-for-pixels chart drew two thumbnails
amber - 102 KB and 97 KB at 300x224 - while the wall said "0 over budget",
the page card said "webp · 4 KB" for both, `img-heavy` was in the clean line
and Fixes had no card. The chart read the item 241 path, keyed on the file a
lazy loader swaps in; everything else keyed on `src`, which for WP Rocket's
markup is one `data:` SVG shared by every 300x300 thumbnail:

  - the sweep dropped every `data:` row, so no image check ever read a lazy
    image, and looked measurements up by `src`;
  - the Latest View filed each page's image weights under `src`, so the
    shared placeholder held one weight for all of them;
  - the template rule keyed images on `src` too.

One image is one file, everywhere.
"""

from __future__ import annotations

import json

from clauditseo.crawler.types import Page
from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.modules.onp import OnPageModule
from clauditseo.modules.pagefacts import extract_facts, position_key
from clauditseo.persistence import latest_view, repo, runs

HOME = "https://lazy.fixture/website-blogs/"
PLACEHOLDER = ("data:image/svg+xml,%3Csvg%20xmlns='http://www.w3.org/2000/svg'%20"
               "viewBox='0%200%20300%20300'%3E%3C/svg%3E")
CHECKLIST = "/wp-content/uploads/General-SEO-robot_checklist2-300x300.webp"
MAP = "/wp-content/uploads/Local-SEO-robot_looking-at-map-300x300.webp"
SMALL = "/wp-content/uploads/small-300x300.webp"

HTML = f"""<!doctype html><html><head><title>Blogs</title></head><body><main>
<h1>Blogs</h1>
<img src="{PLACEHOLDER}" data-lazy-src="{CHECKLIST}" alt="Checklist robot" width="300" height="300">
<img src="{PLACEHOLDER}" data-lazy-src="{MAP}" alt="Map robot" width="300" height="300">
<img src="{PLACEHOLDER}" data-lazy-src="{SMALL}" alt="Small robot" width="300" height="300">
</main></body></html>"""


def _shot(kb: int) -> dict:
    return {"rendered": {"1440": [300, 224]}, "intrinsic_w": 300, "intrinsic_h": 300,
            "weight_kb": kb, "weight_source": "header", "lcp_candidate": False,
            "above_fold": False}


#: What the image pass measured, keyed as `imaging` keys it: by the file.
MEASURED = {HOME: {CHECKLIST: _shot(102), MAP: _shot(97), SMALL: _shot(6)}}


def _facts():
    return extract_facts(Page(url=HOME, requested_url=HOME, status=200,
                              content_type="text/html", content=HTML))


def test_the_sweep_checks_a_lazy_image_as_its_file_and_says_how_it_was_weighed():
    found = OnPageModule()._image_checks([_facts()], MEASURED, (200, 1000))
    heavy = [f for f in found if f.check_id == "img-heavy"]
    # One finding for the page (the operator's ruling a), naming both images
    # with each one's own weight - not the first alone.
    assert len(heavy) == 1, [f.summary for f in heavy]
    f = heavy[0]
    assert f.evidence["images"] == [CHECKLIST, MAP], f.evidence["images"]
    assert sorted(e["weight_kb"] for e in f.evidence["per_image"]) == [97, 102]
    assert f.summary.startswith("2 images: ") and "General-SEO" in f.summary \
        and "Local-SEO" in f.summary, f.summary
    assert "data:" not in f.summary, f.summary
    for e in f.evidence["per_image"]:
        assert e["weight_source"] == "header"
        assert "server's size header" in e["basis"], e["basis"]
    # No finding of any image check names the placeholder as an image.
    assert not [f for f in found if "data:image" in f.summary], [f.summary for f in found]


def test_the_template_rule_keys_a_lazy_image_on_its_file():
    rows = [i for i in _facts().image_details if i.get("tag") == "img"]
    assert len({position_key(i) for i in rows}) == 3, [position_key(i) for i in rows]


def test_one_image_on_two_pages_is_a_finding_on_each():
    """Not a template image, so each page is fixed on its own: fixing the
    file on one page does not fix it on the other (the operator,
    2026-09-27)."""
    other = HOME.replace("website-blogs", "about")
    page = extract_facts(Page(url=other, requested_url=other, status=200,
                              content_type="text/html", content=HTML))
    found = OnPageModule()._image_checks([_facts(), page],
                                         {**MEASURED, other: MEASURED[HOME]}, (200, 1000))
    heavy = [f for f in found if f.check_id == "img-heavy"]
    assert sorted(f.affected_urls[0] for f in heavy) == sorted([HOME, other]), \
        [(f.affected_urls, f.evidence.get("template")) for f in heavy]


def _stored(tmp_path):
    conn = connect(tmp_path / "lazy.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site = repo.create_site(conn, repo.create_client(conn, op, "Lazy Co"), "lazy.fixture")
    run = runs.create_run(conn, site, ["ONP"], "T3")
    facts = _facts()
    inventory = [{**{k: v for k, v in i.items() if k != "css_class"},
                  **MEASURED[HOME].get(i.get("lazy_src") or i.get("src") or "", {})}
                 for i in facts.image_details]
    runs.store_evidence(conn, run, {"start_url": HOME, "pages": [
        {"url": HOME, "status": 200, "content_type": "text/html", "title": "Blogs",
         "image_inventory": inventory}]})
    runs.mark_complete(conn, run, "2026-09-25T00:00:00+00:00")
    return conn, site, run


def test_the_page_card_reads_each_lazy_images_own_weight(tmp_path):
    conn, site, _run = _stored(tmp_path)
    inventory = runs.page_facts(conn, site, HOME)["image_inventory"]
    weights = {i["lazy_src"]: i.get("weight_kb") for i in inventory}
    assert weights == {CHECKLIST: 102, MAP: 97, SMALL: 6}, weights
    stored = latest_view._get(conn, site, "page", "/website-blogs/")["image_weights"]["value"]
    assert PLACEHOLDER not in stored and set(stored) == {CHECKLIST, MAP, SMALL}, list(stored)
    conn.close()


def test_the_charts_amber_dots_are_the_checks_findings(tmp_path):
    """The invariant the item asks for: a dot drawn over budget on a page is
    a finding the sweep raises there, and the other way round."""
    conn, site, run = _stored(tmp_path)
    dots = runs.image_budget_payload(conn, run)["dots"]
    amber = {d["src"] for d in dots if d["state"] in ("warn", "bad")}
    heavy = {im for f in OnPageModule()._image_checks([_facts()], MEASURED, (200, 1000))
             if f.check_id == "img-heavy" for im in f.evidence.get("images") or [f.evidence["image"]]}
    assert amber == heavy == {CHECKLIST, MAP}, (amber, heavy)
    conn.close()
    _ = json


def test_a_finding_whose_images_is_a_count_does_not_break_the_site(tmp_path):
    """`img-duplicate-links` has always carried `images` as a count. Read as
    a list of files by the ruling-a change, it made `/api/sites/<id>` a 500
    on every site with one (twenty22, 2026-09-29)."""
    conn, site, run = _stored(tmp_path)
    with conn:
        conn.execute(
            "INSERT INTO findings (id, run_id, dimension, check_id, severity, source, summary,"
            " affected_urls, fingerprint, created_at, evidence) VALUES (?, ?, 'ONP',"
            " 'img-duplicate-links', 'medium', 'deterministic', '2 images link to /x', ?,"
            " 'dup', '2026-09-25T00:00:00+00:00', ?)",
            (repo.create_id(), run, json.dumps([HOME]), json.dumps({"href": "/x", "images": 2})))
        conn.execute("INSERT INTO finding_states (site_id, fingerprint, state, changed_by_run,"
                     " updated_at) VALUES (?, 'dup', 'open', ?, '2026-09-25T00:00:00+00:00')",
                     (site, run))
    got = {s["fingerprint"]: s for s in runs.site_states(conn, site)}
    assert got["dup"]["images"] == [], got["dup"]["images"]
    conn.close()
