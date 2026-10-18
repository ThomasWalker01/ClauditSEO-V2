"""What every response actually carried, and when that is worth a column.

Brief v16h, item 136i. The block's whole argument is the column rule:
**the column count is the number of template groups that disagree, minimum
one.** A grid drawing one column per group would make a uniform site look
like a table of differences, and a reader would compare eight rows across
three columns to learn there is nothing to compare.

Measured on Acme's stored run (`fe2447ad…`, 227 pages, three groups —
`/blog/` 147, `/success-stories/` 37, everything else 43): every group
agrees on every row, so the real site collapses. The fanned state is
fixtured here, because no stored run has one.
"""

from __future__ import annotations

import json

import pytest

from clauditseo import security_headers as sh
from clauditseo.persistence import runs


# --- the decision, which the check and the grid share --------------------

def test_a_cell_and_its_finding_agree_in_both_directions():
    """SEC's header checks call `cell_state`, so the two cannot disagree about
    the rows they share (`COVERED_BY_CHECK`). `tec`'s `security-headers` did
    this until item 143 step BD moved Security to its own dimension. Asserted
    from the source as well as the behaviour: the agreement is that there is
    ONE function, and a copy that happened to return the same answers today
    would not be."""
    import inspect

    from clauditseo.modules import sec
    src = inspect.getsource(sec)
    assert "sh.cell_state(" in src, (
        "the check decides for itself again, so the grid and the record can "
        "drift apart")
    # Both directions, on the same input.
    have = {"strict-transport-security": "max-age=63072000; includeSubDomains"}
    assert sh.cell_state("strict-transport-security", have, anywhere=True) == sh.SET
    assert sh.cell_state("content-security-policy", have, anywhere=True) == sh.MISSING


def test_absent_everywhere_is_mute_not_bad():
    """A header no page on the site has is a decision not yet taken. Marking
    it as a gap would send an operator to chase two hundred identical cells,
    which is the opposite of what a fix order is for."""
    assert sh.cell_state("referrer-policy", {}, anywhere=False) == sh.ABSENT
    assert sh.cell_state("referrer-policy", {}, anywhere=True) == sh.MISSING


def test_present_but_not_doing_its_job_is_weak():
    """Two cases the brief names. A header that is there and useless is not
    the same claim as one that is missing, and an operator who has 'added
    HSTS' needs to be told which they did."""
    assert sh.cell_state("strict-transport-security",
                         {"strict-transport-security": "max-age=100"},
                         anywhere=True) == sh.WEAK
    assert sh.cell_state("strict-transport-security",
                         {"strict-transport-security": "max-age=31536000; includeSubDomains"},
                         anywhere=True) == sh.SET
    # Brief v20's `SEC/hsts` also names a missing includeSubDomains, and the
    # cell reads the same rule the check does (item 143 step BD).
    assert sh.cell_state("strict-transport-security",
                         {"strict-transport-security": "max-age=31536000"},
                         anywhere=True) == sh.WEAK
    assert sh.cell_state("referrer-policy",
                         {"referrer-policy": "unsafe-url"}, anywhere=True) == sh.WEAK


def test_the_disclosure_row_is_inverted():
    """SET means *not disclosed* on this row, which the brief states and
    which reads backwards unless it is written down. A version banner is the
    defect; a bare vendor name is not, because what matters is a version an
    attacker can look up."""
    assert sh.cell_state("server", {}, anywhere=True) == sh.SET
    assert sh.cell_state("server", {"server": "cloudflare"}, anywhere=True) == sh.SET
    assert sh.cell_state("server", {"server": "nginx/1.18.0"}, anywhere=True) == sh.WEAK
    assert sh.cell_state("server", {"x-powered-by": "PHP/8.1.2"}, anywhere=True) == sh.WEAK


def test_frame_ancestors_satisfies_the_frame_row():
    """The row is named for both. A site that set the modern header and
    dropped the legacy one is protected, and calling that a gap would ask
    for a header it does not need."""
    csp = {"content-security-policy": "frame-ancestors 'self'"}
    assert sh.cell_state("x-frame-options", csp, anywhere=True) == sh.SET


def test_a_route_that_sets_no_cookie_is_not_applicable():
    assert sh.cell_state("set-cookie", {}, anywhere=True, sets_cookies=False) == sh.NA
    assert sh.cell_state("set-cookie", {"set-cookie": "a=1; SameSite=Lax"},
                         anywhere=True) == sh.SET
    assert sh.cell_state("set-cookie", {"set-cookie": "a=1"}, anywhere=True) == sh.MISSING


# --- the grid ------------------------------------------------------------

HEADERS_FULL = {
    "strict-transport-security": "max-age=31536000",
    "content-security-policy": "default-src 'self'; frame-ancestors 'none'",
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "strict-origin-when-cross-origin",
    "permissions-policy": "geolocation=()",
}


@pytest.fixture()
def db(tmp_path):
    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate
    conn = connect(tmp_path / "c.db")
    migrate(conn)
    yield conn
    conn.close()


def _run(conn, pages):
    from clauditseo.persistence import repo
    op = repo.ensure_default_operator(conn)
    site = repo.create_site(conn, repo.create_client(conn, op, "C"), "x.test")
    run_id = runs.create_run(conn, site, ["TEC"], "T2")
    conn.execute("UPDATE audit_runs SET crawl_evidence=? WHERE id=?",
                 (json.dumps({"pages": pages}), run_id))
    conn.commit()
    return run_id


def _page(path, headers=None, status=200, form=False):
    return {"url": f"https://x.test{path}", "status": status,
            "headers": dict(headers if headers is not None else HEADERS_FULL),
            "has_post_form": form}


def _group(prefix, n, headers=None, form=False):
    return [_page(f"{prefix}{i}", headers, form=form) for i in range(n)]


def test_agreeing_routes_collapse_to_one_column(db):
    """Three template groups, all serving the same headers: one column."""
    pages = _group("/blog/p", 12) + _group("/news/p", 12) + _group("/x", 5)
    grid = runs.security_headers_payload(db, _run(db, pages))
    assert grid["recorded"] is True
    assert len(grid["groups"]) == 3, grid["groups"]
    assert grid["fanned"] is False, [r for r in grid["rows"] if not r["agree"]]
    assert grid["columns"] == [], grid["columns"]
    assert all(r["agree"] for r in grid["rows"])


def test_a_disagreeing_header_fans_out_only_the_groups_involved(db):
    """The brief's own fixture: 3 groups, one header missing on one → the
    grid fans that row and leaves the other seven under the divider."""
    short = {k: v for k, v in HEADERS_FULL.items() if k != "referrer-policy"}
    pages = _group("/blog/p", 12) + _group("/news/p", 12) + _group("/checkout", 5, short)
    grid = runs.security_headers_payload(db, _run(db, pages))
    assert grid["fanned"] is True
    fanned = [r for r in grid["rows"] if not r["agree"]]
    assert [r["key"] for r in fanned] == ["referrer-policy"], fanned
    assert len([r for r in grid["rows"] if r["agree"]]) == 7
    # The groups involved plus everything else — not one column per group.
    assert len(grid["columns"]) == 2, grid["columns"]


def test_grid_cells_are_identical_in_both_states(db):
    """One component, two states. The cells a row carries must not depend on
    whether some OTHER row disagreed — if they did, the collapsed view would
    be a different reading of the same site rather than the same one drawn
    in less space."""
    agree = _group("/blog/p", 12) + _group("/news/p", 12)
    short = {k: v for k, v in HEADERS_FULL.items() if k != "referrer-policy"}
    disagree = agree + _group("/checkout", 5, short)

    a = runs.security_headers_payload(db, _run(db, agree))
    b = runs.security_headers_payload(db, _run(db, disagree))
    cells = lambda g, k: {r["key"]: r["cells"][k] for r in g["rows"]}
    # The `/blog/` column says exactly the same thing in both.
    assert cells(a, "/blog/") == {**cells(b, "/blog/")}, (cells(a, "/blog/"),
                                                          cells(b, "/blog/"))
    assert a["fanned"] is False and b["fanned"] is True


def test_the_odd_route_is_named_in_a_sentence(db):
    short = {k: v for k, v in HEADERS_FULL.items() if k != "referrer-policy"}
    pages = _group("/blog/p", 12) + _group("/news/p", 12) + _group("/checkout", 5, short)
    grid = runs.security_headers_payload(db, _run(db, pages))
    assert grid["odd"], grid
    assert grid["odd"]["group"] == "everything else", grid["odd"]
    assert grid["odd"]["lacks"] == ["Referrer-Policy"], grid["odd"]
    assert grid["odd"]["form"] is False


def test_a_form_route_is_the_one_to_fix_first(db):
    """The brief's extra sentence, and it needed a signal nothing recorded:
    the parser now marks a page carrying `<form method=post>`. Runs taken
    before that read as "not a form route", which is why this asserts the
    flag rather than inferring it from the path."""
    short = {k: v for k, v in HEADERS_FULL.items() if k != "referrer-policy"}
    pages = (_group("/blog/p", 12) + _group("/news/p", 12)
             + _group("/checkout", 5, short, form=True))
    grid = runs.security_headers_payload(db, _run(db, pages))
    assert grid["odd"]["form"] is True, grid["odd"]


def test_two_groups_disagreeing_in_different_directions_name_no_odd_route(db):
    """A sentence saying "X is served without N headers" is a claim about
    one route. Two groups each lacking something different is not that, and
    naming one would be the block inventing a story."""
    no_ref = {k: v for k, v in HEADERS_FULL.items() if k != "referrer-policy"}
    no_csp = {k: v for k, v in HEADERS_FULL.items() if k != "content-security-policy"}
    pages = (_group("/blog/p", 12, no_ref) + _group("/news/p", 12, no_csp)
             + _group("/x", 5))
    grid = runs.security_headers_payload(db, _run(db, pages))
    assert grid["fanned"] is True
    assert grid["odd"] is None, grid["odd"]


def test_missing_headers_store_is_absent_not_empty(db):
    """A run that stored no headers is a different answer from a site that
    sets none, and an empty grid would say the second."""
    pages = [{"url": "https://x.test/", "status": 200, "headers": {}}]
    grid = runs.security_headers_payload(db, _run(db, pages))
    assert grid["recorded"] is False, grid
    assert grid["rows"] == [] and grid["pages"] == 1


def test_a_run_with_no_crawl_returns_nothing_at_all(db):
    from clauditseo.persistence import repo
    op = repo.ensure_default_operator(db)
    site = repo.create_site(db, repo.create_client(db, op, "C"), "x.test")
    assert runs.security_headers_payload(db, runs.create_run(db, site, ["TEC"], "T2")) is None
    assert runs.security_headers_payload(db, None) is None


def test_redirects_are_counted_and_kept_out_of_the_grid(db):
    """Not pages, and not in this item's grid — HSTS on a redirect is a v20
    check and needs the chain rather than the destination. Counted so the
    report can say how many there were."""
    pages = _group("/blog/p", 12) + [
        {"url": "https://x.test/old", "status": 301, "headers": {}}]
    grid = runs.security_headers_payload(db, _run(db, pages))
    assert grid["pages"] == 12, grid["pages"]
    assert grid["redirects"] == 1, grid["redirects"]


# --- the drawing ---------------------------------------------------------

def _ui() -> str:
    from pathlib import Path
    return (Path(__file__).resolve().parents[1] / "dashboard" / "src"
            / "headers_grid.tsx").read_text(encoding="utf-8")


def test_the_grid_is_drawn_with_no_page_chosen():
    """The block is a claim about every route, so it is drawn at SITE scope.

    Found on the running product, not by this file. `PART_RENDERERS` invokes
    `now` only when a page is chosen - most now-blocks read one page's parse
    and have nothing to say without one - so registering the grid without
    saying otherwise put it behind a page filter that it then, correctly,
    refused to draw under. It rendered nowhere at all: no card at site scope,
    and at page scope the sentence asking the reader to clear the filter.

    **Stated limitation.** This reads the source, so it pins the declaration
    and not the pixels. The clause that would have caught it originally is
    item 136m's `test_no_part_page_block_overflows_its_column`, which renders
    every registered block at three widths with no page chosen; a rendered
    sweep that only ever visits page scope cannot see this class of defect,
    and the one in `test_a11y_rendered.py` picks `/promo` before it walks the
    parts.
    """
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "dashboard" / "src"
           / "part_page.tsx").read_text(encoding="utf-8")

    entry = src[src.index("  security: {"):]
    entry = entry[:entry.index("}")]
    assert "siteScope: true" in entry, (
        "the Security renderer does not declare a site-scoped now block, so "
        f"the grid is drawn only behind a page filter: {entry}")

    # And the gate honours the flag, so the declaration is not decorative.
    assert "render.siteScope" in src, (
        "nothing reads `siteScope`, so declaring it changes nothing")


def test_the_state_is_readable_as_text_and_not_only_as_fill():
    """WCAG 1.4.1, on the Security part, where failing it would be its own
    joke. The brief keeps the SET / MISSING labels for exactly this."""
    src = _ui()
    for word in ("SET", "MISSING", "WEAK", "ABSENT"):
        assert f'"{word}"' in src, word
    # `N/A` was the engine's own token shown to a reader (audit F14). The
    # registry holds the word - `not-applicable`, "does not apply" - and the
    # cell reads that, upper-cased like its neighbours. Asserted through the
    # registry so the test does not become a second definition of it.
    assert 'entry("not-applicable").word.toUpperCase()' in src, (
        "the n/a cell does not read the registry")
    assert '"N/A"' not in src, "the engine's token is still drawn"
    assert "hg-word" in src


def test_absent_takes_the_mute_token_and_missing_the_bad_one():
    src = _ui()
    tone = src[src.index("const TONE"):src.index("const WORD")]
    assert 'absent: "mute"' in tone and 'missing: "bad"' in tone, tone


def test_only_permissions_policy_generates_the_do_not_spend_clause():
    """The brief allows it for that row and no other. A block that decided
    for itself which headers were not worth having would be making a
    recommendation nobody wrote."""
    src = _ui()
    assert 'DO_NOT_SPEND = "Permissions-Policy"' in src
    assert src.count("do not spend on") == 1, "a second clause was invented"
