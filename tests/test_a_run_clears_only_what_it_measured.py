"""Item 240: a run clears only what it measured.

The ledger marked findings `fixed` that the run never looked for, and a
fixed state reaches the client report. Three instruments were missing from
the clearing rule, each with its own false "fixed":

  - an analysis's rows: the ONP-only T2 of 2026-09-23 ran no analysis and
    cleared 48 of a paid analysis's rows on twenty22;
  - cross-page checks: a one-page refresh "fixed" a `title-duplicate`, which
    one page cannot have, and the next audit raised a false regression;
  - the image pass: a verify, which weighs no images, could clear `img-heavy`.

One predicate decides now (`runs.measured`), and only `clean` clears. A full
reading of the site that raises neither the cross-page nor the image check
still clears both - the rule withholds a clearing, it does not stop one. An
analysis's row is cleared only by its analysis.
"""

from __future__ import annotations

from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.engine.core import AuditResult
from clauditseo.engine.types import Finding, Severity, Site, Tier
from clauditseo.persistence import repo, runs

BASE = "https://measured.test"
PAGES = [f"{BASE}/p{n}/" for n in range(60)]
PATHS = {f"/p{n}/" for n in range(60)}
PAGE = PAGES[0]


def _f(check, url=PAGE, dim="ONP", source="deterministic"):
    return Finding(dimension=dim, check_id=check, severity=Severity.MEDIUM,
                   summary=f"{check} on {url}", subject=f"{check}:{url}",
                   affected_urls=[url], source=source)


def _run(conn, site, findings, kind="audit", paths=PATHS, imaged=frozenset(), dims=("ONP",)):
    run = runs.create_run(conn, site, list(dims), "T2", kind=kind,
                          scan_scope="site" if kind == "audit" else "page")
    runs.complete_run(conn, run, AuditResult(
        site=Site(domain=BASE + "/"), tier=Tier.T2, dimensions=list(dims), findings=findings,
        crawled_paths=set(paths), imaged_paths=set(imaged)))
    return run


def _state(conn, site, check):
    return conn.execute(
        "SELECT s.state FROM finding_states s JOIN findings f ON f.fingerprint=s.fingerprint"
        " WHERE s.site_id=? AND f.check_id=? LIMIT 1", (site, check)).fetchone()[0]


def _db(tmp_path):
    conn = connect(tmp_path / "c.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    return conn, repo.create_site(conn, repo.create_client(conn, op, "C"), "measured.test")


def test_an_audit_that_ran_no_analysis_leaves_an_analysis_row_open(tmp_path):
    """The live case: the analysis's row opens on an audit that corroborates
    it; a later audit that runs no analysis - and does not raise the check on
    that page either - leaves it open. (Item 223 let that second audit clear
    it; 240 makes an analysis's row its analysis's alone.)"""
    from tests.test_an_audit_does_not_close_the_analysis_it_did_not_run import (
        A, B, _audit, _brief, _row, _states, _sweep)
    conn, site = _db(tmp_path)
    first = _audit(conn, site, [_sweep("meta-desc-length", A), _sweep("meta-desc-length", B)])
    _brief(conn, site, first, [_row("meta-desc-length", A)])
    assert _states(conn, site)[("meta-desc-length", A)] == "open"
    _audit(conn, site, [_sweep("meta-desc-length", B)])
    assert _states(conn, site)[("meta-desc-length", A)] == "open"


def test_a_refresh_of_one_page_leaves_a_cross_page_check_open(tmp_path):
    conn, site = _db(tmp_path)
    _run(conn, site, [_f("title-duplicate")])
    _run(conn, site, [], kind="refresh", paths={"/p0/"})
    assert _state(conn, site, "title-duplicate") == "open"


def test_a_verify_with_no_image_pass_leaves_an_image_check_open(tmp_path):
    conn, site = _db(tmp_path)
    _run(conn, site, [_f("img-heavy")], imaged=PATHS)
    _run(conn, site, [], kind="verify", paths={"/p0/"})
    assert _state(conn, site, "img-heavy") == "open"


def test_a_full_reading_that_raises_neither_clears_both(tmp_path):
    conn, site = _db(tmp_path)
    _run(conn, site, [_f("title-duplicate"), _f("img-heavy")], imaged=PATHS)
    _run(conn, site, [], imaged=PATHS)
    assert _state(conn, site, "title-duplicate") == "fixed"
    assert _state(conn, site, "img-heavy") == "fixed"


def test_the_predicate_says_why():
    reading = runs.Reading("r", frozenset({"ONP"}), frozenset({"/p0/"}), frozenset(),
                           frozenset(), site_reading=False)
    assert runs.measured(reading, "ONP", "title-duplicate", [PAGE]) == (
        "unmeasured", "a cross-page check needs a reading of the whole site")
    assert runs.measured(reading, "ONP", "img-heavy", [PAGE])[0] == "unmeasured"
    assert runs.measured(reading, "ONP", "title-missing", [PAGE]) == ("clean", "")
    assert runs.measured(reading, "ONP", "title-missing", [PAGE], raised=True)[0] == "raised"
    assert runs.measured(reading, "TEC", "title-missing", [PAGE])[0] == "unmeasured"
