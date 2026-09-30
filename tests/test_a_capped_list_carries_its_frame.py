"""UX-93: a truncated list of affected URLs says what it was cut from.

Two caps sit between a check and the sentence that describes it, and by the
time the sentence is written they are indistinguishable. An emitter stores the
first N URLs it found; `runs.anatomy_view` cuts that stored list to ten; the
disclosure then states the second cap against the first as though the first
were the total that exists. Driven in Chromium against the running product on
2026-08-29, one row of `www.acme.com.au` read, verbatim:

    summary   "51 of 272 sitemap URL(s) were not reachable from the site's
               internal links or did not resolve"
    PAGES     20
    note      "Showing 10 of 20. This screen's payload caps the URL list it
               carries per finding - the rest are stored and are not
               reachable from here (BACKLOG.md B-30)."

Three counts of one quantity, and the note's last clause is false for 31 of
the 51: `clauditseo/modules/tec.py` stored only the first twenty, so the other
thirty-one were never written anywhere. The guard standing beside the feature
asserted that the URL list is no longer than the count and that the two are
both empty or both not - both derived from the already-cut list, so they
agreed with each other all the way through the defect. That is DISCIPLINE rule
5: a check drawing its evidence from the thing it checks can only ever pass.

`QUESTIONS.md` **Q-26**, answered by the operator on 2026-08-29: **store the
frame**. The pre-truncation count travels with the truncated list, at the
emitter and through storage, so the two caps can be told apart at the point of
display.

**Why this is a file of its own rather than more of
`test_a_count_reaches_what_it_counted.py`, where report 100's remediation
entry asked for it.** That file imports the built-bundle fixture, so
`scripts/prove_fail.py` refuses every test in it - *"runs against
dashboard/dist, which this script does not rebuild"* - and rule 1 could not be
answered for any assertion placed there. Nothing here touches the bundle, so
all four were proven red against the parent commit. The screen half of the
work stays in that file, where the browser fixture already lives, and is
measured against the old bundle in the way `FEATURES.md` F-11 records.
"""

from __future__ import annotations

from clauditseo.persistence import runs


def test_every_emitter_that_caps_a_list_records_what_it_cut():
    """DISCIPLINE rule 3, enumerated from the modules rather than from the
    report's list.

    The audit named two truncation sites (`tec.py:151` and the payload cut in
    `runs.anatomy_view`). Reading the modules for the shape finds **four**
    emitters that cap `affected_urls`, not one - `tec.unreachable`,
    `loc.nap-inconsistent`, `prf.caching-headers` and
    `prf.third-party-scripts` - which is why this walks the syntax tree
    instead of naming them: a fifth added next month is caught by the same
    clause that caught these.

    The rule is narrow on purpose. It binds only where the *emitter* slices,
    because that is the cut nothing downstream can see; a finding that hands
    over its whole list needs no frame, and demanding one everywhere would
    make the field a ritual rather than a fact.
    """
    import ast
    import pathlib

    mods = pathlib.Path(__file__).resolve().parents[1] / "clauditseo" / "modules"
    unframed: list[str] = []
    capped = 0
    for path in sorted(mods.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "Finding"):
                continue
            kw = {k.arg: k.value for k in node.keywords if k.arg}
            urls = kw.get("affected_urls")
            # Any slice anywhere in the expression, not only one applied to
            # the whole list. `prf.caching-headers` spells its cap
            # `[p.url for p in uncached[:5]]` - inside the comprehension - and
            # a check for `Subscript` at the top found three of the four.
            if urls is None or not any(isinstance(n, ast.Slice)
                                       for n in ast.walk(urls)):
                continue
            capped += 1
            if "affected_total" not in kw:
                unframed.append(f"{path.name}:{node.lineno}")

    assert capped >= 4, (
        f"only {capped} emitter caps found - the shape this enumerates has "
        "changed and the test is reading the wrong thing")
    assert not unframed, (
        "these emitters cap `affected_urls` and store no frame beside it, so "
        "a screen reading the stored list cannot tell how much was dropped: "
        + ", ".join(unframed))


def test_a_capped_list_records_the_total_its_own_summary_states():
    """The emitter half, driven rather than read.

    Report 100's remediation entry asks for the count to be asserted *against
    the summary's own figure* and not only against the list beside it. The
    summary is written from `missing` before anything is sliced, so it is the
    one figure in the finding that can disagree with the frame - which is the
    whole of why it is the thing asserted against.
    """
    from clauditseo.crawler.types import CrawlResult, Page
    from clauditseo.engine.types import Tier
    from clauditseo.modules.tec import TechnicalModule

    start = "https://x.test/"
    pages = [Page(url=start, requested_url=start, status=200,
                  content="<html><body>home</body></html>",
                  content_type="text/html")]
    ghosts = [f"https://x.test/ghost{i}" for i in range(51)]
    crawl = CrawlResult(start_url=start, tier=Tier.T2, pages=pages,
                        sitemap_entries=[start, *ghosts])

    found = TechnicalModule().run(pages, Tier.T2, {"crawl": crawl})
    cov = next(f for f in found if f.check_id == "unreachable")

    assert "51 of 52" in cov.summary, (
        f"the fixture no longer produces the case this asserts: {cov.summary!r}")
    assert len(cov.affected_urls) == 20, (
        f"the emitter stored {len(cov.affected_urls)} URLs - this test exists "
        "because it stores fewer than it counted")
    assert cov.affected_total == 51, (
        f"the summary states 51 and the finding carries {cov.affected_total!r} "
        "as its frame, so the 31 it dropped are dropped silently")


def _framed(tmp_path):
    """A stored site whose one finding was cut by its emitter.

    Built through `complete_run` rather than by writing the row, so the
    column, the insert and the read are all exercised by the thing the
    product actually calls.
    """
    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate
    from clauditseo.engine.core import AuditResult
    from clauditseo.engine.types import Finding, Severity, Site, Tier
    from clauditseo.persistence import repo

    conn = connect(tmp_path / "frame.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site = repo.create_site(conn, repo.create_client(conn, op, "Co"), "x.test")
    run = runs.create_run(conn, site, ["TEC"], "T2")
    ghosts = [f"https://x.test/ghost{i}" for i in range(51)]
    runs.complete_run(conn, run, AuditResult(
        site=Site(domain="https://x.test/"), tier=Tier.T2, dimensions=["TEC"],
        findings=[Finding(
            dimension="TEC", check_id="unreachable", severity=Severity.MEDIUM,
            summary="51 of 52 sitemap URL(s) are published but the crawl "
                    "could not reach them.",
            subject="unreachable", affected_urls=ghosts[:20],
            affected_total=51, evidence={"unreached_count": 51})]))
    return conn, site


def _only(view: dict) -> dict:
    found = [f for c in view["categories"] for f in c["findings"]]
    assert len(found) == 1, f"expected one finding, got {len(found)}"
    return found[0]


def test_the_frame_survives_storage_and_reaches_the_payload(tmp_path):
    """All three numbers on the wire, and each one distinguishable.

    `total` is what the check found, `pages` is what the emitter kept, and
    `urls` is what the payload carries. Before this they were two numbers
    describing one cut, and the screen had to guess which cut it was
    describing.
    """
    conn, site = _framed(tmp_path)
    try:
        f = _only(runs.anatomy_view(conn, site))
        assert f["total"] == 51, (
            f"the stored frame did not survive the round trip: {f.get('total')!r}")
        assert f["pages"] == 20, f"the emitter's cap moved: {f['pages']}"
        assert len(f["urls"]) == 10, (
            f"the payload's cap moved: {len(f['urls'])}")
    finally:
        conn.close()


def test_a_row_stored_before_the_frame_existed_asserts_no_total(tmp_path):
    """The tolerated null, asserted rather than assumed.

    Every row written before migration 0030 carries no frame, and no frame is
    not a frame of zero and not "the list is whole": it is *unknown*. The
    payload has to say so, because the alternative - defaulting to the stored
    length - reinstates the exact claim this work removed, on the rows least
    able to support it.
    """
    conn, site = _framed(tmp_path)
    try:
        with conn:
            conn.execute("UPDATE findings SET affected_total = NULL")
        f = _only(runs.anatomy_view(conn, site))
        assert f["total"] is None, (
            f"a row with no stored frame reports a total of {f['total']!r}, "
            "which is a number nothing measured")
        assert f["pages"] == 20, "the stored list is still what it was"
    finally:
        conn.close()
