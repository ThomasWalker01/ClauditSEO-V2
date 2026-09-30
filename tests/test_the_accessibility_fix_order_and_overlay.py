"""What to fix first, and where on the page it is (brief v16e, item 136f).

Two blocks in one position, chosen by scope. Block 1 orders the site's open
accessibility barriers by the instances each fix removes; Block 2 draws one
page's barriers over the picture the rendered pass took of it.

Both rest on 136j: before it, `evidence` held a sample of hrefs and the real
count lived inside an English sentence, so neither block could have been
built. Every number here is `Σ evidence.count`, never a row count.

**The denominator is the part worth reading twice.** Static checks assess
every crawled page; `axe-*` assesses only what the rendered pass visited — 5
of 12 on Birch, 5 of 227 on Acme. Calling a group "on every page" because
it appeared on the five pages a sampler chose is this block's worst
available lie, so a share is always of the pages *that check* assessed.
"""

from __future__ import annotations

import json

import pytest

from clauditseo.persistence import runs


# --- a site with a known shape -------------------------------------------

def _site(conn):
    from clauditseo.persistence import repo
    op = repo.ensure_default_operator(conn)
    return repo.create_site(conn, repo.create_client(conn, op, "C"), "x.test")


def _finding(conn, run_id, fp, check, urls, instances, count=None,
             severity="high", dimension="A11Y", extra=None):
    ev = {"instances": instances, "count": count if count is not None else len(instances)}
    ev.update(extra or {})
    conn.execute(
        "INSERT INTO findings (run_id, check_id, dimension, severity, summary,"
        " affected_urls, evidence, recommendation, source, fingerprint, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (run_id, check, dimension, severity, f"{check} here", json.dumps(urls),
         json.dumps(ev), "fix", "deterministic", fp, "2026-09-07T00:00:00"))
    conn.execute(
        "INSERT INTO finding_states (site_id, fingerprint, state, changed_by_run,"
        " updated_at) VALUES (?,?,?,?,?)",
        (conn.execute("SELECT id FROM sites LIMIT 1").fetchone()[0], fp, "open",
         run_id, "2026-09-07T00:00:00"))


def _inst(selector, landmark="none", rect=None):
    out = {"selector": selector, "selector_norm": selector,
           "landmark": landmark, "html": f"<a>{selector}</a>"}
    if rect:
        out["rect"] = rect
    return out


@pytest.fixture()
def db(tmp_path):
    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate
    conn = connect(tmp_path / "c.db")
    migrate(conn)
    yield conn
    conn.close()


def _pages(n, prefix="https://x.test/p"):
    return [f"{prefix}{i}" for i in range(n)]


def _sampled(conn, run_id, rendered, crawled):
    """The row that says how much of the crawl the rendered pass read. It is
    the only place the two denominators are recorded together."""
    conn.execute(
        "INSERT INTO findings (run_id, check_id, dimension, severity, summary,"
        " affected_urls, evidence, recommendation, source, fingerprint, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (run_id, "axe-sampled", "A11Y", "info", "sampled", "[]",
         json.dumps({"rendered": rendered, "crawled": crawled}), "", "deterministic",
         "fp-sampled", "2026-09-07T00:00:00"))


# --- Block 1 -------------------------------------------------------------

def test_counts_are_instances_not_rows(db):
    """One row, twelve nameless links, one page. The block must say 12."""
    site = _site(db)
    run = runs.create_run(db, site, ["A11Y"], "T2")
    _sampled(db, run, 4, 4)
    _finding(db, run, "fp1", "link-name-missing", ["https://x.test/"],
             [_inst(f"main > a:nth-of-type({i})") for i in range(12)])
    db.commit()
    order = runs.fix_order_payload(db, site, run)
    assert order["total"] == 12, order["total"]
    assert sum(s["instances"] for s in order["steps"]) == 12


def test_steps_sum_to_the_open_instance_count(db):
    """The block's own arithmetic. Bars that do not add up are worse than no
    bars, because the number above them is the one an operator quotes."""
    site = _site(db)
    run = runs.create_run(db, site, ["A11Y"], "T2")
    _sampled(db, run, 6, 6)
    for i, url in enumerate(_pages(6)):
        _finding(db, run, f"fp-a{i}", "link-name-missing", [url],
                 [_inst("footer > a", "footer"), _inst("main > a")])
        _finding(db, run, f"fp-b{i}", "duplicate-id", [url], [_inst("#dup")])
    db.commit()
    order = runs.fix_order_payload(db, site, run)
    assert order["sum"] == order["total"] == 18, (order["sum"], order["total"])


def test_no_instance_lands_in_two_steps(db):
    site = _site(db)
    run = runs.create_run(db, site, ["A11Y"], "T2")
    _sampled(db, run, 4, 4)
    for i, url in enumerate(_pages(4)):
        # The nav link is on every page; the second selector is on one only.
        # A `main` selector on ALL four would be chrome too - by share, not
        # by landmark - which is the rule working and was this clause's own
        # first mistake.
        inst = [_inst("nav > a", "nav")]
        if i == 0:
            inst.append(_inst("main > a:nth-of-type(2)", "main"))
        _finding(db, run, f"fp{i}", "link-name-missing", [url], inst)
    db.commit()
    order = runs.fix_order_payload(db, site, run)
    assert order["sum"] == order["total"] == 5
    # Two distinct kinds, so two steps, and between them every instance once.
    assert sorted(s["kind"] for s in order["steps"]) == ["chrome", "page"]


def test_a_selector_in_the_header_or_footer_is_one_chrome_step(db):
    """The landmark decides it without needing the share. A link in the
    footer of four pages is the site's furniture whether or not the crawl
    reached the rest of the site."""
    site = _site(db)
    run = runs.create_run(db, site, ["A11Y"], "T2")
    _sampled(db, run, 4, 40)
    for i, url in enumerate(_pages(4)):
        _finding(db, run, f"fp{i}", "link-name-missing", [url],
                 [_inst("footer > a", "footer")])
    db.commit()
    step = runs.fix_order_payload(db, site, run)["steps"][0]
    assert step["kind"] == "chrome", step
    assert "footer" in step["label"], step["label"]


def test_a_selector_on_most_of_one_template_is_a_template_step(db):
    """Between the two shares: on enough pages to be a repeat, not enough to
    be the furniture, and not in a furniture region."""
    site = _site(db)
    run = runs.create_run(db, site, ["A11Y"], "T2")
    _sampled(db, run, 10, 10)
    for i, url in enumerate(_pages(7)):
        _finding(db, run, f"fp{i}", "link-name-missing", [url],
                 [_inst("main > article > a", "main")])
    db.commit()
    step = runs.fix_order_payload(db, site, run)["steps"][0]
    assert step["kind"] == "template", step


def test_fewer_than_three_assessed_pages_is_never_a_template(db):
    """Two of two pages is 100% and evidences nothing. The classification is
    a claim about repetition, and three is the least that can support one."""
    site = _site(db)
    run = runs.create_run(db, site, ["A11Y"], "T2")
    _sampled(db, run, 2, 2)
    for i, url in enumerate(_pages(2)):
        _finding(db, run, f"fp{i}", "link-name-missing", [url],
                 [_inst("main > a", "main")])
    db.commit()
    step = runs.fix_order_payload(db, site, run)["steps"][0]
    assert step["kind"] == "page", step


def test_the_denominator_is_the_pages_that_check_assessed(db):
    """The clause this block would be dishonest without. Two checks, the same
    two pages, one crawl: the static check is on 2 of 40 and the axe check is
    on 2 of 2 — because the rendered pass only read two."""
    site = _site(db)
    run = runs.create_run(db, site, ["A11Y"], "T2")
    _sampled(db, run, 2, 40)
    for i, url in enumerate(_pages(2)):
        _finding(db, run, f"fs{i}", "link-name-missing", [url], [_inst("main > a", "main")])
        _finding(db, run, f"fa{i}", "axe-color-contrast", [url], [_inst("main > p", "main")])
    db.commit()
    by = {s["check"]: s for s in runs.fix_order_payload(db, site, run)["steps"]}
    assert by["link-name-missing"]["assessed"] == 40, by["link-name-missing"]
    assert by["axe-color-contrast"]["assessed"] == 2, by["axe-color-contrast"]
    # And the classification follows the denominator, not the page count.
    assert by["link-name-missing"]["kind"] == "page"
    assert by["axe-color-contrast"]["kind"] == "page", (
        "two assessed pages is under the template floor, whatever the share")


def test_the_step_label_counts_selectors_not_instances(db):
    """What an operator touches is the selector; how often is the instance
    count, which is the bar's height. A literal reading of the item drew six
    bars all reading "Make the 1 id unique in the nav" — measured on Acme
    before the steps were merged by (check, kind)."""
    site = _site(db)
    run = runs.create_run(db, site, ["A11Y"], "T2")
    _sampled(db, run, 4, 4)
    for i, url in enumerate(_pages(4)):
        _finding(db, run, f"fp{i}", "duplicate-id", [url],
                 [_inst("#a", "nav"), _inst("#b", "nav"), _inst("#c", "nav")])
    db.commit()
    steps = runs.fix_order_payload(db, site, run)["steps"]
    assert len(steps) == 1, [s["label"] for s in steps]
    assert steps[0]["instances"] == 12, steps[0]
    assert "3 ids" in steps[0]["label"], steps[0]["label"]


def test_an_empty_site_says_nothing_rather_than_drawing_zero(db):
    site = _site(db)
    run = runs.create_run(db, site, ["A11Y"], "T2")
    db.commit()
    assert runs.fix_order_payload(db, site, run) is None


# --- Block 2 -------------------------------------------------------------

def test_an_unrendered_page_reports_the_sample_rather_than_drawing(db):
    """The common case: the pass samples, so most pages have no picture. The
    payload carries both counts so the screen can say which run and tier
    decided it instead of showing an empty canvas."""
    site = _site(db)
    run = runs.create_run(db, site, ["A11Y"], "T2")
    _sampled(db, run, 5, 227)
    db.commit()
    got = runs.a11y_page_payload(db, site, run, "https://x.test/unseen")
    assert got["screenshot"] is None, got
    assert got["rendered"] == 5 and got["crawled"] == 227, got
    assert got["barriers"] == []


def test_a_rendered_page_carries_its_picture_and_its_boxes(db):
    site = _site(db)
    run = runs.create_run(db, site, ["A11Y"], "T2")
    url = "https://x.test/"
    db.execute(
        "INSERT INTO findings (run_id, check_id, dimension, severity, summary,"
        " affected_urls, evidence, recommendation, source, fingerprint, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (run, "axe-sampled", "A11Y", "info", "sampled", "[]",
         json.dumps({"rendered": 1, "crawled": 4, "screens": {url: {
             "screenshot_path": "data/screens/x/y.png",
             "screenshot_w": 1280, "screenshot_h": 4000}}}),
         "", "deterministic", "fp-s", "2026-09-07T00:00:00"))
    _finding(db, run, "fp1", "axe-color-contrast", [url],
             [_inst("main > p", "main", {"x": 10, "y": 20, "w": 100, "h": 18})])
    _finding(db, run, "fp2", "link-name-missing", [url], [_inst("footer > a", "footer")])
    db.commit()
    got = runs.a11y_page_payload(db, site, run, url)
    assert got["screenshot"] == f"/api/runs/{run}/screens/" + got["screenshot"].split("/")[-1]
    assert got["screenshot"].endswith(".png")
    assert got["doc"] == {"w": 1280, "h": 4000}, got["doc"]
    assert len(got["barriers"]) == 2
    # Placed first, so the numbering runs down the picture before it runs
    # down the list of things that have no position.
    assert got["barriers"][0].get("rect"), got["barriers"][0]
    assert not got["barriers"][1].get("rect"), got["barriers"][1]
    assert [b["n"] for b in got["barriers"]] == [1, 2]


def test_a_static_instance_is_listed_without_a_box_rather_than_dropped(db):
    """It has a selector and no rect — nothing measured it. The item forbids
    re-rendering to find one, because boxes from a second render would be a
    second page's positions drawn over the first page's picture."""
    site = _site(db)
    run = runs.create_run(db, site, ["A11Y"], "T2")
    url = "https://x.test/"
    _sampled(db, run, 1, 1)
    _finding(db, run, "fp1", "duplicate-id", [url], [_inst("#dup", "main")])
    db.commit()
    got = runs.a11y_page_payload(db, site, run, url)
    assert len(got["barriers"]) == 1
    assert "rect" not in got["barriers"][0], got["barriers"][0]


def test_a_chrome_group_is_marked_on_the_row(db):
    """So a row can say "on every page" without the screen recomputing the
    classification Block 1 already made."""
    site = _site(db)
    run = runs.create_run(db, site, ["A11Y"], "T2")
    _sampled(db, run, 4, 4)
    for i, u in enumerate(_pages(4)):
        _finding(db, run, f"fp{i}", "link-name-missing", [u], [_inst("footer > a", "footer")])
    db.commit()
    order = runs.fix_order_payload(db, site, run)
    got = runs.a11y_page_payload(db, site, run, "https://x.test/p0", order)
    assert got["barriers"][0]["chrome"] is True, got["barriers"][0]


# --- the drawing ---------------------------------------------------------

def _ui() -> str:
    from pathlib import Path
    return (Path(__file__).resolve().parents[1] / "dashboard" / "src"
            / "a11y_fixorder.tsx").read_text(encoding="utf-8")


def test_boxes_are_scaled_by_the_document_width_they_were_measured_against():
    """A rect is in document pixels and the image is drawn at whatever width
    the column gives it. Scaling by anything but their ratio puts every box
    somewhere else."""
    src = _ui()
    assert "el.clientWidth / docW" in src, src[:0] or "no scale derived from docW"
    for axis in ("left", "top", "width", "height"):
        assert f"{axis}: `${{" in src, axis


def test_a_zero_area_node_gets_a_marker_rather_than_nothing():
    """An element clipped to nothing is a real violation at a real position,
    and a box of zero pixels is invisible — so it draws at a floor."""
    src = _ui()
    assert "overlay-zero" in src and "zero ? 12 : 1" in src, src[:0] or "no floor"
    assert "not visible on the page" in src


def test_a_box_and_its_row_share_one_selection():
    src = _ui()
    assert src.count("onSelect(selected === b.n ? null : b.n)") == 2, (
        "the box and the row must both toggle the same selection")
    assert "is-sel" in src and "aria-current" in src


def test_every_box_has_an_accessible_name():
    """The gate the item names: this is an accessibility feature and it may
    not itself be a set of unlabelled buttons."""
    src = _ui()
    assert "violation ${b.n}" in src and "aria-label" in src, src[:0] or "unnamed"


def test_smaller_boxes_are_drawn_last_so_they_stay_reachable():
    src = _ui()
    # In `ShotBoxes` since item 245, shared by Accessibility and Content.
    assert "(b.rect.w * b.rect.h) - (a.rect.w * a.rect.h)" in src, (
        "a large box drawn over a small one makes the small one unclickable")


def test_the_axis_says_it_is_counting_instances():
    """The whole point of 136j, and the one sentence that stops a reader
    taking the bars for rows."""
    src = _ui()
    assert "instances removed, not rows" in src


def test_the_block_says_when_its_own_steps_do_not_add_up():
    """`fix_order_payload` carries both numbers so the screen can report a
    disagreement rather than drawing bars that quietly do not sum."""
    src = _ui()
    assert "order.sum !== order.total" in src, src[:0] or "no drift note"
