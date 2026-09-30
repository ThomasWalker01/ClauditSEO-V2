"""Which URL owns a page, drawn as the chain the crawler would follow.

Brief v16g. One block on the Indexability & canonicals part page — the
selected page's own canonical chain at page scope, the site's chains that
are not the healthy case at site scope — and the clauses below are the
item's own test list: a self-canonical page is one node with a loop, a chain
and its finding never disagree, two hops is bad even where the end is fine,
a chain ending on a noindexed page names the reason, a loop stops and is
bad, parameter and slash variants are muted, site scope shows only what is
not healthy worst first, and an all-healthy site is one sentence rather than
a grid of identical loops.

**Why a fixture of its own and not the shared crawl fixture.** The reason
`test_the_headings_outline_blocks_are_drawn.py` gives one file earlier: this
block needs a site carrying every one of the four kinds and every terminal
reason at once — a loop, a two-hop chain, a noindexed end, a 404 end, a
robots-blocked end, a target nobody crawled, an off-host canonical — which
no fixture written for another question happens to contain. Bending
`test_a11y_rendered`'s two-page fixture into that shape would move finding
counts in forty-odd browser tests that have nothing to do with this block.

**The fixture states its own answer, and the code must match it.** `PAGES`
below declares, per page, the kind the chain should draw and the canonical
check the record should hold — written out from the item's four definitions
by hand, not taken from `canonical_chain_state`. The findings planted on the
record come from that declaration and the payload comes from the engine, so
the agreement clause compares two derivations rather than one with itself
(DISCIPLINE rule 5).
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from clauditseo.db.connection import connect
from clauditseo.modules.onp import DEFAULT_SEVERITY, canonical_relation
from clauditseo.persistence import runs
from clauditseo.persistence.repo import create_id, now_iso
from tests.test_a11y_rendered import DIST
from tests.test_triage_ranks_the_section_rail import _serve
from tests.parts import ANATOMY_READY, open_part, open_page_filter

SITE = "chains.test"
BASE_URL = f"https://{SITE}"
#: The host an off-host canonical points at. A separate domain and not a
#: subdomain, because the check compares `netloc` and a subdomain is exactly
#: as different to it as a different registrable domain is.
OTHER = "https://mirror.example"
#: The run that recorded no canonical at all, and the all-healthy run, live
#: on hosts of their own: the pane's page filter narrows against the site it
#: is typed on, so a URL from a neighbouring fixture's domain matches
#: nothing and silently leaves the screen at site scope.
BLANK_URL = f"https://blank.{SITE}"
CLEAN_URL = f"https://clean.{SITE}"


def _url(path: str) -> str:
    return f"{BASE_URL}{path}"


#: `(path, canonical, status, meta_robots, kind, check)`.
#:
#: `canonical` is what the tag says, `...` where the page carries no tag at
#: all. `kind` and `check` are the fixture's own reading of the item's four
#: definitions — ok is one node self-canonical, warn is one hop somewhere
#: real, bad is two hops or an end that cannot be indexed or a loop, mute is
#: a parameter or trailing-slash variant — and `check` is what the canonical
#: checks raise: `canonical-mismatch` on a different path,
#: `canonical-missing` on no tag, and since Q-54 the two variant grades,
#: `canonical-mismatch-trailing-slash` and `canonical-mismatch-parameter`.
#:
#: **`mute` and "raises nothing" came apart at Q-54 and were one column's
#: worth of the same idea before it.** A variant is still drawn quietly; it
#: is no longer silent in the record. Nothing here calls
#: `canonical_chain_state` or `canonical_relation`; that is the point of the
#: file.
NO_TAG = ...

PAGES: list[tuple[str, object, int, str | None, str, str | None]] = [
    # --- the healthy case, three ways of spelling it ---------------------
    ("/", f"{BASE_URL}/", 200, None, "ok", None),
    ("/line-of-credit", f"{BASE_URL}/line-of-credit", 200, None, "ok", None),
    # A page whose canonical is written relative. Same page, same answer.
    ("/apply", "/apply", 200, None, "ok", None),

    # --- warn: one hop to somewhere real ---------------------------------
    ("/blog/what-are-bizcaps-financing-options",
     f"{BASE_URL}/blog/financing-options", 200, None, "warn", "canonical-mismatch"),
    ("/blog/financing-options", f"{BASE_URL}/blog/financing-options", 200,
     None, "ok", None),
    # No canonical tag at all: one node, warn, and the record's own
    # `canonical-missing`. The item's first degradation.
    ("/no-canonical", NO_TAG, 200, None, "warn", "canonical-missing"),
    # An off-host canonical whose path differs too: `canonical-mismatch`
    # fires exactly as it does for any other different path, and the walk
    # stops at the host rather than reporting a page it never read as
    # missing from the crawl. The item's third degradation.
    ("/partner", f"{OTHER}/elsewhere", 200, None, "warn",
     ("canonical-mismatch", "canonical-off-host")),
    # Same path, different host. Answered since Q-55; it raised nothing at
    # all before, which is a page handing its content to another domain
    # with the record silent about it.
    ("/mirror", f"{OTHER}/mirror", 200, None, "warn", "canonical-off-host"),

    # --- mute: a variant, graded since Q-54 ------------------------------
    ("/apply?ref=broker", f"{BASE_URL}/apply", 200, None, "mute",
     "canonical-mismatch-parameter"),
    ("/how-it-works/", f"{BASE_URL}/how-it-works", 200, None, "mute",
     "canonical-mismatch-trailing-slash"),
    ("/how-it-works", f"{BASE_URL}/how-it-works", 200, None, "ok", None),

    # --- bad: two hops, and the end of this one is perfectly indexable ---
    ("/one", f"{BASE_URL}/two", 200, None, "bad", "canonical-mismatch"),
    ("/two", f"{BASE_URL}/three", 200, None, "warn", "canonical-mismatch"),
    ("/three", f"{BASE_URL}/three", 200, None, "ok", None),

    # --- bad: the end cannot be indexed ----------------------------------
    ("/promo", f"{BASE_URL}/promo-old", 200, None, "bad", "canonical-mismatch"),
    ("/promo-old", f"{BASE_URL}/promo-old", 200, "noindex,follow", "ok", None),
    # A dead target is the terminal axis (item 137, brief v18 step BA): the
    # walk ends on a 4xx, so the verdict is canonical-to-404 (TEC), not the
    # relation canonical-mismatch. `/never` (not crawled) and `/forbidden`
    # (robots-blocked) end badly too but on neither a 4xx nor a loop, so they
    # keep canonical-mismatch, as does `/one`'s two-hop chain and `/promo`'s
    # noindex end.
    ("/dead", f"{BASE_URL}/dead-target", 200, None, "bad", "canonical-to-404"),
    ("/never", f"{BASE_URL}/never-crawled", 200, None, "bad", "canonical-mismatch"),
    ("/forbidden", f"{BASE_URL}/blocked", 200, None, "bad", "canonical-mismatch"),

    # --- bad: a loop -> canonical-loop (TEC), the terminal axis -----------
    ("/loop-a", f"{BASE_URL}/loop-b", 200, None, "bad", "canonical-loop"),
    ("/loop-b", f"{BASE_URL}/loop-a", 200, None, "bad", "canonical-loop"),
]

#: The 404 the `/dead` chain ends on. Not in `PAGES`, because the checks run
#: on status-200 HTML alone (`onp.html_pages`) and so does the site-scope
#: list: a page that can never carry a canonical finding may not draw a card
#: that claims one. It is still a *node*, which is how `404` reaches a
#: terminal label.
EXTRA_RECORDS = [(f"{BASE_URL}/dead-target", 404, None, None)]

#: Robots forbade this one, so no page record exists for it at all — it is
#: on the run's `robots_blocked` list and nowhere else, exactly as a crawl
#: leaves it.
BLOCKED = [f"{BASE_URL}/blocked"]

#: One finding from another part, on a page whose canonical is perfect.
#:
#: **Not decoration.** The pane's page filter lists the pages the *record*
#: knows about - `anatomy_view` builds it from the findings' affected URLs -
#: so a page with no finding at all cannot be narrowed to on this screen,
#: whatever its canonical says. That is a pre-existing property of the
#: screen and not this block's to change; but it means the healthy card,
#: which is the shape the item's first clause is about, is only reachable at
#: page scope on a page that carries something. `title-length` is from
#: another part entirely, which is the point: it puts `/line-of-credit` in
#: the list without saying anything about its canonical.
OTHER_FINDINGS = [("/line-of-credit", "title-length")]

#: A site where every page owns itself, for the all-healthy sentence.
CLEAN_PAGES = [(f"/{p}" if p else "/", None, 200, None, "ok", None)
               for p in ("", "about", "apply", "contact")]

#: A site whose only unhealthy chains are variants.
#:
#: **Not a convenience.** On the arranged site above the two mute chains sit
#: past the cap - worst first puts seven bad and one warn in front of them -
#: and they cannot be reached at page scope either, because the pane's page
#: filter lists pages the record holds a finding for and a variant raises
#: none. So this is where the muted card is actually drawn, and the site is
#: worth having on its own terms: a site whose only canonical problem is
#: parameter variants has zero canonical findings and two greyed cards, and
#: a reader looking for the parameter problem has to be able to find it.
VARIANT_URL = f"https://variants.{SITE}"
VARIANT_PAGES: list[tuple[str, object, int, str | None, str, str | None]] = [
    ("/", f"{VARIANT_URL}/", 200, None, "ok", None),
    ("/apply", f"{VARIANT_URL}/apply", 200, None, "ok", None),
    ("/apply?ref=broker", f"{VARIANT_URL}/apply", 200, None, "mute",
     "canonical-mismatch-parameter"),
    ("/how-it-works", f"{VARIANT_URL}/how-it-works", 200, None, "ok", None),
    ("/how-it-works/", f"{VARIANT_URL}/how-it-works", 200, None, "mute",
     "canonical-mismatch-trailing-slash"),
]

NEEDS_BROWSER = pytest.mark.skipif(
    not __import__("clauditseo.axe", fromlist=["axe"]).available(),
    reason="needs clauditseo[render] and `playwright install chromium`")


def _record(path: str, canonical, status: int, robots: str | None,
            *, host: str = BASE_URL, store: bool = True) -> dict:
    """One page record as `crawler.evidence.snapshot` writes it.

    `canonical` is absent from the record entirely where the fixture says
    `NO_TAG`... no: `NO_TAG` is a page that carried no tag, which the crawl
    stores as `canonical: None`. A record with no `canonical` **key** is
    what a run crawled before the field existed leaves, and that is the
    `store=False` fixture below — the two are different answers and the
    block gives them different states.
    """
    page = {"url": f"{host}{path}", "status": status,
            "content_type": "text/html", "title": f"Fixture {path}",
            "word_count": 400}
    if robots is not None:
        page["meta_robots"] = robots
    if store:
        page["canonical"] = None if canonical is NO_TAG else (
            canonical if canonical is None else canonical)
        if canonical is None:
            # The clean fixture: self-canonical, spelled absolutely.
            page["canonical"] = f"{host}{path}"
    return page


def _plant_one(conn, site_id, run_id, host, path, check):
    """One planted finding, from the fixture's declaration and not from the
    engine — the agreement clause is only worth anything if the two sides
    come from two derivations."""
    fp = f"{check}-{path}"
    sev = DEFAULT_SEVERITY.get(check)
    conn.execute(
        "INSERT INTO findings (id, run_id, dimension, check_id,"
        " severity, source, summary, affected_urls, affected_total,"
        " evidence, fingerprint, created_at) VALUES (?, ?, 'ONP',"
        " ?, ?, 'deterministic', ?, ?, 1, ?, ?, ?)",
        (create_id(), run_id, check,
         getattr(sev, "value", None) or "medium",
         f"{check} on {path}.", json.dumps([f"{host}{path}"]),
         json.dumps({}), fp, now_iso()))
    conn.execute(
        "INSERT INTO finding_states (site_id, fingerprint, state,"
        " changed_by_run, updated_at) VALUES (?, ?, 'open', ?, ?)",
        (site_id, fp, run_id, now_iso()))


def _plant(db: Path, site_id: str, pages: list, *, host: str = BASE_URL,
           store: bool = True, extra: list | None = None,
           blocked: list[str] | None = None) -> str:
    conn = connect(db)
    # TEC as well (item 239 step 2): the canonical chains are Indexability's,
    # read from TEC's reference crawl - an ONP-only run never measured them.
    run_id = runs.create_run(conn, site_id, ["ONP", "TEC"], "T3")
    records = [_record(p, c, st, r, host=host, store=store)
               for p, c, st, r, _kind, _check in pages]
    for url, status, ctype, canonical in (extra or []):
        records.append({"url": url, "status": status,
                        "content_type": ctype or "text/html",
                        "canonical": canonical})
    runs.store_evidence(conn, run_id, {
        "start_url": f"{host}/", "pages": records,
        "robots_blocked": blocked or [],
        "sitemap_entries": [r["url"] for r in records]})
    runs.mark_complete(conn, run_id, now_iso())
    # One row per check the fixture says the page raises, planted from the
    # declaration above rather than from the engine: the agreement clause is
    # only worth anything if the two sides come from two derivations.
    with conn:
        for path, _c, _st, _r, _kind, declared in pages:
            if not declared:
                continue
            # A tuple where the page raises more than one, which `/partner`
            # does since Q-55: an off-host canonical to a different path is
            # both `canonical-mismatch` and `canonical-off-host`.
            for check in ((declared,) if isinstance(declared, str) else declared):
                _plant_one(conn, site_id, run_id, host, path, check)
        if host == BASE_URL and store:
            for path, check in OTHER_FINDINGS:
                fp = f"{check}-{path}"
                conn.execute(
                    "INSERT INTO findings (id, run_id, dimension, check_id,"
                    " severity, source, summary, affected_urls, affected_total,"
                    " evidence, fingerprint, created_at) VALUES (?, ?, 'ONP',"
                    " ?, 'low', 'deterministic', ?, ?, 1, ?, ?, ?)",
                    (create_id(), run_id, check, f"{check} on {path}.",
                     json.dumps([f"{host}{path}"]), json.dumps({}), fp,
                     now_iso()))
                conn.execute(
                    "INSERT INTO finding_states (site_id, fingerprint, state,"
                    " changed_by_run, updated_at) VALUES (?, ?, 'open', ?, ?)",
                    (site_id, fp, run_id, now_iso()))
    conn.close()
    return run_id


def _site(base: str, domain: str) -> str:
    client = httpx.post(f"{base}/api/clients", json={"name": "Chains Co"},
                        timeout=30).json()
    return httpx.post(f"{base}/api/clients/{client['id']}/sites",
                      json={"domain": domain}, timeout=30).json()["id"]


@pytest.fixture(scope="module")
def served():
    """Four sites: the arranged one, one whose pages all own themselves, one
    whose run recorded no canonical field at all, and one whose only
    unhealthy chains are parameter and trailing-slash variants."""
    server, thread, db, base = _serve("canonicalchains")
    try:
        full = _site(base, SITE)
        _plant(db, full, PAGES, extra=EXTRA_RECORDS, blocked=BLOCKED)
        clean = _site(base, f"clean.{SITE}")
        _plant(db, clean, CLEAN_PAGES, host=CLEAN_URL)
        blank = _site(base, f"blank.{SITE}")
        _plant(db, blank, CLEAN_PAGES, host=BLANK_URL, store=False)
        variants = _site(base, f"variants.{SITE}")
        _plant(db, variants, VARIANT_PAGES, host=VARIANT_URL)
        yield base, {"full": full, "clean": clean, "blank": blank,
                     "variants": variants}
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def _view(base: str, site_id: str, page: str | None = None) -> dict:
    return httpx.get(f"{base}/api/sites/{site_id}/anatomy",
                     params={"page": page} if page else None, timeout=30).json()


def _part(base: str, site_id: str, page: str | None = None) -> dict:
    return next(c for c in _view(base, site_id, page)["categories"]
                if c["key"] == "indexability")


def _chain(base: str, site_id: str, path: str) -> dict:
    return _view(base, site_id, _url(path))["facts"]["canonical_chain"]


def _raised(base: str, site_id: str) -> dict[str, set[str]]:
    """Which canonical checks the record holds against each page, read the
    way the cards read them — from the site's own states, uncapped."""
    site = httpx.get(f"{base}/api/sites/{site_id}", timeout=30).json()
    out: dict[str, set[str]] = {}
    for s in site["states"]:
        if not s["check_id"].startswith("canonical-"):
            continue
        for url in s["affected_urls"]:
            out.setdefault(url, set()).add(s["check_id"])
    return out


# --- the walk the drawing is made from ------------------------------------

def test_a_self_canonical_page_is_one_ok_node_with_a_loop(served):
    """The healthy case, and it is a shape and not only a colour: one node,
    no hops, nothing to say about a terminal, and the note the item's
    mockup carries."""
    base, sites = served
    for path in ("/", "/line-of-credit", "/apply"):
        chain = _chain(base, sites["full"], path)
        assert chain["kind"] == "ok", path
        assert chain["hops"] == 0 and len(chain["nodes"]) == 1, path
        assert chain["terminal"] is None and chain["check"] is None, path
        assert chain["note"] == "Canonical is the page itself. Nothing to do."
        # One node with nothing after it is what the client draws the loop
        # from, so the title has to say so in words for a reader who cannot
        # see the loop.
        assert "0 hops, canonicalises to itself" in _title(chain), path


def _title(chain: dict) -> str:
    """The accessible name the client builds, rebuilt here from the payload
    it is built from — `titleOf` in `canonical_chains.tsx`. Not read off the
    DOM, because this half of the file runs without a browser."""
    hops = f"{chain['hops']} hop{'' if chain['hops'] == 1 else 's'}"
    end = (f"ends on {chain['terminal']}" if chain["terminal"]
           else f"ends on {chain['external_host']}" if chain["external_host"]
           else "canonicalises to itself" if chain["hops"] == 0
           else "ends on an indexable page")
    return f"canonical chain for {chain['label']}, {hops}, {end}"


def test_a_chain_and_its_finding_agree(served):
    """The item's rule, in both directions and at the page level, which is
    the level at which the two are the same claim.

    Forward: every page the record holds an open canonical finding against
    draws something other than `ok`. Backward: every `warn` or `bad` chain
    has one. `mute` is excluded from the backward half **by name and not by
    accident** — it is the one kind the item defines as the case no check
    raises, and `test_parameter_and_slash_variants_are_mute` below is what
    holds it to that.
    """
    base, sites = served
    raised = _raised(base, sites["full"])
    for path, _c, _st, _r, kind, _check in PAGES:
        chain = _chain(base, sites["full"], path)
        has = raised.get(_url(path), set())
        if has:
            assert chain["kind"] != "ok", (path, has)
        if chain["kind"] in ("warn", "bad"):
            # `/mirror` was the one documented exception until Q-55 — a
            # `warn` chain the record said nothing about. It raises
            # `canonical-off-host` now, so there is no exception left and
            # the loop makes no special case for any path.
            assert has, path
            assert chain["check"] in has, (path, chain["check"], has)
        if chain["kind"] == "ok":
            assert not has, (path, has)
        assert chain["kind"] == kind, (path, chain["kind"], kind)


def test_a_two_hop_chain_is_bad_even_when_the_end_is_indexable(served):
    """A hop is a hop. `/one` -> `/two` -> `/three`, and `/three` is a
    perfectly ordinary self-canonical 200 — so nothing at the end of this
    chain is wrong, and the chain still is."""
    base, sites = served
    chain = _chain(base, sites["full"], "/one")
    assert chain["kind"] == "bad" and chain["hops"] == 2
    assert [n["path"] for n in chain["nodes"]] == ["/one", "/two", "/three"]
    # No terminal reason, because there is nothing wrong with where it ends.
    assert chain["terminal"] is None
    assert "2 hops before a page owns itself" in chain["note"]
    assert "The end is indexable" in chain["note"]
    # And the middle of the chain, read on its own, is one hop and warn —
    # which is the same walk seen from one node further along.
    middle = _chain(base, sites["full"], "/two")
    assert middle["kind"] == "warn" and middle["hops"] == 1


def test_a_chain_ending_on_noindex_names_the_reason(served):
    """`noindex` on the terminal node, in words, on the node — not a colour
    and not a tooltip."""
    base, sites = served
    chain = _chain(base, sites["full"], "/promo")
    assert chain["kind"] == "bad" and chain["terminal"] == "noindex"
    assert chain["nodes"][-1]["noindex"] is True
    assert "a noindexed page" in chain["note"]
    assert "ends on noindex" in _title(chain)
    # The other three terminal reasons the item names, each read off the
    # node the walk actually stopped on.
    for path, reason in (("/dead", "404"), ("/never", "not crawled"),
                         ("/forbidden", "robots-blocked")):
        other = _chain(base, sites["full"], path)
        assert other["kind"] == "bad", path
        assert other["terminal"] == reason, (path, other["terminal"])
    # A URL robots forbade is `robots-blocked` and not `not crawled`: the
    # crawl knows about it and declined it, which is a different
    # instruction to the reader from never having heard of it.
    assert _chain(base, sites["full"], "/forbidden")["nodes"][-1][
        "robots_blocked"] is True
    assert _chain(base, sites["full"], "/never")["nodes"][-1]["in_crawl"] is False


def test_a_loop_stops_and_is_bad(served):
    """`/loop-a` -> `/loop-b` -> `/loop-a`. The walk stops the second time
    it meets a URL, and the chain is bad because it never reaches a page
    that owns itself."""
    base, sites = served
    chain = _chain(base, sites["full"], "/loop-a")
    assert chain["kind"] == "bad" and chain["terminal"] == "loop"
    assert [n["path"] for n in chain["nodes"]] == ["/loop-a", "/loop-b", "/loop-a"]
    # Stopped, not merely capped: a walk that ran the full five hops would
    # have six nodes.
    assert chain["hops"] == 2
    assert "comes back to a URL it has already been through" in chain["note"]


def test_parameter_and_slash_variants_are_mute(served):
    """Still greyed, and no longer silent.

    Both spellings: a query the canonical drops, and a trailing slash it
    drops. Neither raised a check until Q-54 — the comparison the check made
    was `urlsplit(...).path` with `rstrip("/")` on both sides, so neither
    difference reached it — and the block drew them greyed so that a reader
    looking for the parameter problem would find it here and not conclude
    the site has none.

    Q-54 grades them apart and gives each a row. **`mute` survives that**,
    which is the point of this clause: the colour is about how loud the
    chain is, not about whether anything was recorded, and collapsing the
    two would make a scored slash variant shout.
    """
    base, sites = served
    raised = _raised(base, sites["full"])
    expected = {"/apply?ref=broker": "canonical-mismatch-parameter",
                "/how-it-works/": "canonical-mismatch-trailing-slash"}
    for path, check in expected.items():
        chain = _chain(base, sites["full"], path)
        assert chain["kind"] == "mute", path
        assert chain["check"] == check, (path, chain["check"])
        assert check in raised.get(_url(path), set()), path
        # The sentence names the grade, because the two carry different
        # findings and "variant" alone would not say which row to look for.
        assert "No check fires on it" not in chain["note"], path
    assert "not deducted from the score" in _chain(
        base, sites["full"], "/apply?ref=broker")["note"]
    # And the two nodes are told apart on the drawing, which is the whole
    # point of the card: `/apply` twice would be a picture of nothing.
    variant = _chain(base, sites["full"], "/apply?ref=broker")
    assert [n["label"] for n in variant["nodes"]] == ["/apply?ref=broker", "/apply"]


def test_an_off_host_canonical_is_answered_on_both_shapes(served):
    """Q-55. Retired the clause that wrote down the gap and asserts the
    rule that closed it.

    This was `test_an_off_host_canonical_is_the_one_kind_no_check_answers`,
    which existed to say in a test what the record could not say at all: a
    page declaring another domain's URL as its canonical hands its content
    away, and nothing fired. `canonical_relation` compared paths and only
    then hosts, so `canon_path.rstrip("/") != f.path.rstrip("/")` never
    reached `netloc`.

    **Both shapes fire, and the different-path shape fires BOTH checks**
    (operator, 2026-09-07). `canonical-mismatch` is untouched by this item
    in the literal sense: no row it used to raise stops being raised. Had
    off-host been made a branch of the relation instead, every existing
    `canonical-mismatch` on a page whose canonical left the host would have
    silently resolved.
    """
    base, sites = served
    raised = _raised(base, sites["full"])
    mirror = _chain(base, sites["full"], "/mirror")
    assert mirror["kind"] == "warn"
    assert mirror["relation"] == "off-host"
    assert mirror["external_host"] == "mirror.example"
    assert mirror["check"] == "canonical-off-host"
    assert "canonical-off-host" in raised.get(_url("/mirror"), set())
    # The node names the host, because "not crawled" would be true and would
    # send the reader looking for a page on their own site.
    assert mirror["nodes"][-1]["external"] is True
    assert "mirror.example" in mirror["note"]
    # The different-path case: two findings on one page, which is the
    # ruling. The chain names `canonical-mismatch` because that is what its
    # relation is; the off-host fact is on the card as the external host and
    # in the record as its own row.
    partner = _chain(base, sites["full"], "/partner")
    assert partner["external_host"] == "mirror.example"
    assert partner["check"] == "canonical-mismatch"
    assert raised.get(_url("/partner"), set()) >= {
        "canonical-mismatch", "canonical-off-host"}, raised.get(_url("/partner"))


def test_the_apex_and_its_www_are_one_site(served):
    """The rule Q-55 asks to answer FIRST, and the reason it must be.

    A canonical from `example.com/x` to `www.example.com/x` is the single
    most common correct canonical there is. Without the equivalence the new
    check would fire on it, and `canonical-off-host` would be MEDIUM and
    scored on a site doing exactly the right thing.

    Asserted on the function rather than through a fixture site, because
    what is being pinned is the predicate the check and the chain drawing
    both read — a second implementation of "is this the same host" is how
    the card and the finding come to disagree.
    """
    from clauditseo.modules.onp import canonical_off_host, same_site_host

    assert same_site_host("example.com", "www.example.com")
    assert same_site_host("www.example.com", "example.com")
    assert same_site_host("example.com:8443", "example.com")
    assert not same_site_host("example.com", "mirror.example")
    # A sub-domain is NOT the apex: `blog.example.com` is a different host
    # and a canonical across it is a real off-host canonical.
    assert not same_site_host("blog.example.com", "example.com")

    assert canonical_off_host("https://example.com/x",
                              "https://www.example.com/x") is None
    assert canonical_off_host("https://example.com/x", "/x") is None
    assert canonical_off_host("https://example.com/x",
                              "https://mirror.example/x") == "mirror.example"


def test_the_relation_reproduces_the_check_it_replaced(served):
    """`canonical_relation` moved a comparison; it did not change one.

    The condition it replaced, character for character, was

        f.canonical is None                                  -> missing
        canon_path.rstrip("/") != f.path.rstrip("/")
            and f.canonical.strip()                          -> mismatch

    and this walks a table of the awkward spellings against it. Without
    this the refactor is a claim; with it, it is a measurement — and it is
    the test that would catch the tempting one-line "improvement" of
    comparing hosts, which is exactly the change the item stops before.
    """
    from urllib.parse import urlsplit
    cases = [
        ("/a", None, "https://h/a"),
        ("/a", "", "https://h/a"),
        ("/a", "   ", "https://h/a"),
        ("/a", "https://h/a", "https://h/a"),
        ("/a", "https://h/a/", "https://h/a"),
        ("/a", "/a", "https://h/a"),
        ("/a", "https://h/b", "https://h/a"),
        ("/a", "https://other/a", "https://h/a"),
        ("/a", "https://other/b", "https://h/a"),
        ("/", "https://h", "https://h/"),
        ("/a", "https://h/a?x=1", "https://h/a"),
        ("/a", "https://h/a", "https://h/a?x=1"),
    ]
    for path, canonical, url in cases:
        # The old branch, rewritten here and nowhere else.
        if canonical is None:
            was = "canonical-missing"
        else:
            canon_path = urlsplit(canonical).path or "/"
            was = ("canonical-mismatch"
                   if canon_path.rstrip("/") != path.rstrip("/")
                   and canonical.strip() else None)
        now = {"missing": "canonical-missing",
               "elsewhere": "canonical-mismatch"}.get(
                   canonical_relation(path, canonical, url))
        assert now == was, (path, canonical, url, now, was)


# --- the site's own list --------------------------------------------------

def test_site_scope_shows_only_non_healthy_chains_worst_first(served):
    """`ok` never reaches the list, and what does is ordered bad, then
    warn, then mute — longest chain first inside a kind, so the shape a
    reader most needs to see is the one at the top."""
    base, sites = served
    payload = _part(base, sites["full"])["chains"]
    assert payload["recorded"] is True
    kinds = [c["kind"] for c in payload["chains"]]
    assert "ok" not in kinds
    order = {"bad": 0, "warn": 1, "mute": 2}
    assert kinds == sorted(kinds, key=lambda k: order[k]), kinds
    # Longest first inside a kind.
    bad = [c for c in payload["chains"] if c["kind"] == "bad"]
    assert [c["hops"] for c in bad] == sorted((c["hops"] for c in bad),
                                              reverse=True)
    # The count the cap is measured against is the run's, not the list's:
    # the block draws eight and says how many pages it walked.
    declared = {p: k for p, _c, _st, _r, k, _ch in PAGES}
    assert payload["total"] == len(PAGES)
    assert payload["healthy"] == sum(1 for k in declared.values() if k == "ok")
    assert payload["cap"] == runs.CANONICAL_CHAINS_CAP
    unhealthy = sum(1 for k in declared.values() if k != "ok")
    assert len(payload["chains"]) == min(unhealthy, payload["cap"])
    assert payload["more"] == max(unhealthy - payload["cap"], 0)
    assert payload["more"] > 0, "the fixture is meant to exercise the cap"
    # The 404 is a node and never a card: the checks run on status-200 HTML
    # alone, so a page that can carry no canonical finding may not draw a
    # card claiming one.
    assert all(c["path"] != "/dead-target" for c in payload["chains"])


def test_all_healthy_is_one_sentence_not_a_grid(served):
    """The item's second degradation. Four self-canonical pages produce no
    chains at all, and the client's own branch on that is a sentence — do
    not draw 260 loops."""
    base, sites = served
    payload = _part(base, sites["clean"])["chains"]
    assert payload["recorded"] is True
    assert payload["chains"] == []
    assert payload["healthy"] == payload["total"] == len(CLEAN_PAGES)
    assert payload["more"] == 0


def test_a_run_that_recorded_no_canonical_says_so(served):
    """Absent, not clean. An empty list would say every page owns itself,
    which is a measurement this run never made."""
    base, sites = served
    payload = _part(base, sites["blank"])["chains"]
    assert payload["recorded"] is False
    assert payload["chains"] == [] and payload["total"] == 0
    assert payload["crawled"] == len(CLEAN_PAGES)


# --- the drawing ----------------------------------------------------------

@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        try:
            yield b
        finally:
            b.close()


_JS = """() => {
  const cards = [...document.querySelectorAll('.cc-card')];
  const text = (sel) => (document.querySelector(sel) || {}).textContent || '';
  const attr = (el, a) => (el && el.getAttribute) ? el.getAttribute(a) : '';
  return {
    cards: cards.length,
    kinds: cards.map((c) => [...c.classList].find(
      (k) => k === 'cc-ok' || k === 'cc-warn' || k === 'cc-bad'
             || k === 'cc-mute') || ''),
    titles: cards.map((c) => (c.querySelector('.cc-title') || {}).textContent || ''),
    svgTitles: cards.map((c) => (c.querySelector('.cc-svg title') || {}).textContent || ''),
    svgRoles: cards.map((c) => attr(c.querySelector('.cc-svg'), 'role')),
    paths: cards.map((c) => [...c.querySelectorAll('.cc-path')].map(
      (t) => t.textContent)),
    dots: cards.map((c) => c.querySelectorAll('.cc-dot').length),
    nodeRoles: cards.map((c) => [...c.querySelectorAll('.cc-node')].map(
      (g) => attr(g, 'role'))),
    nodeNames: cards.map((c) => [...c.querySelectorAll('.cc-node')].map(
      (g) => attr(g, 'aria-label'))),
    notes: cards.map((c) => (c.querySelector('.cc-note') || {}).textContent || ''),
    loops: cards.map((c) => c.querySelectorAll('.cc-loop').length),
    itself: cards.map((c) => (c.querySelector('.cc-itself') || {}).textContent || ''),
    checks: cards.map((c) => (c.querySelector('.cc-check') || {}).textContent || ''),
    legend: [...document.querySelectorAll('.cc-legend .cc-key')].map(
      (s) => s.textContent),
    clean: text('.cc-clean'),
    absent: text('.cc-absent'),
    more: text('.cc-more'),
    tally: text('.cc-tally'),
  };
}"""


def _open(pg, base, site_id, page: str | None = None):
    """The Indexability part, and then the page filter if one is named — in
    that order, which is `test_a11y_rendered`'s third reveal pass's order
    and for its reason: a category clicked while the pane refetches loses
    the press."""
    pg.goto(f"{base}/#/sites/{site_id}?tab=findings", wait_until="load",
            timeout=30_000)
    pg.wait_for_selector(ANATOMY_READY, timeout=30_000)
    open_part(pg, 'Indexability')
    # On the three-block layout since brief v25 step BP.
    pg.wait_for_selector(".part-page .cc-root", timeout=15_000)
    if page is not None:
        open_page_filter(pg)
        pg.fill(".page-find", page)
        # The card is the page's own block, so a drawn node is the signal
        # that the narrowed payload has arrived; a fixed wait would pass
        # against a screen that never refetched.
        pg.wait_for_selector(".cc-page .cc-card .cc-dot", timeout=15_000)


def _read(browser, base, site_id, page: str | None = None) -> dict:
    """One screen, read once, on a page of its own — navigating to the same
    hash does not reload, so two states means two browser pages."""
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    try:
        _open(pg, base, site_id, page)
        return pg.evaluate(_JS)
    finally:
        pg.close()


BROWSER = [NEEDS_BROWSER,
           pytest.mark.skipif(not (DIST / "index.html").is_file(),
                              reason="dashboard not built")]


def _mark(fn):
    for m in BROWSER:
        fn = m(fn)
    return fn


@_mark
def test_the_healthy_card_is_one_dot_with_a_loop_back_to_itself(browser, served):
    base, sites = served
    got = _read(browser, base, sites["full"], _url("/line-of-credit"))
    assert got["cards"] == 1
    assert got["kinds"] == ["cc-ok"]
    assert got["dots"] == [1]
    # The loop, and the word beside it — the mockup's "itself".
    assert got["loops"] == [1]
    assert got["itself"] == ["itself"]
    assert got["svgRoles"] == ["group"]
    assert "healthy" in got["titles"][0]
    assert got["notes"] == ["Canonical is the page itself. Nothing to do."]


@_mark
def test_every_node_carries_its_path_as_real_text(browser, served):
    """The item's rendered-axe clause. A coloured dot and an arrow are not
    there at all for a screen reader, so each node's path is text under it
    and the drawing as a whole has a title of the stated form."""
    base, sites = served
    got = _read(browser, base, sites["full"], _url("/promo"))
    assert got["paths"] == [["/promo", "/promo-old  · noindex"]]
    assert got["svgTitles"] == [
        "canonical chain for /promo, 1 hop, ends on noindex"]
    # And the nodes the crawl read are controls, named for what pressing
    # them does.
    assert got["nodeRoles"] == [["button", "button"]]
    assert all("open this page" in n for n in got["nodeNames"][0])


@_mark
def test_the_two_hop_card_draws_three_dots_and_says_why_it_is_bad(browser, served):
    base, sites = served
    got = _read(browser, base, sites["full"], _url("/one"))
    assert got["kinds"] == ["cc-bad"] and got["dots"] == [3]
    assert got["paths"] == [["/one", "/two", "/three"]]
    assert got["svgTitles"] == [
        "canonical chain for /one, 2 hops, ends on an indexable page"]
    assert "2 hops before a page owns itself" in got["notes"][0]
    # The check id is the control that narrows the record.
    assert got["checks"] == ["open · canonical-mismatch"]


@_mark
def test_site_scope_draws_the_grid_and_page_scope_draws_one_card(browser, served):
    base, sites = served
    site = _read(browser, base, sites["full"])
    assert site["cards"] == runs.CANONICAL_CHAINS_CAP
    assert site["kinds"][0] == "cc-bad"
    assert "more chain" in site["more"]
    assert "canonicalise to themselves" in site["tally"]
    assert site["legend"] == [
        "self-canonical — as it should be",
        "points elsewhere — check it is intended",
        "ends on a page that cannot be indexed",
        "parameter or slash variant"]
    # The mute chains, read off the site grid. Until Q-54 they could only
    # be read there: the pane's page filter lists the pages the record
    # knows about, and a variant raised nothing, so it was in no filter.
    # Both grades now carry a check, so a mute chain is a page the filter
    # offers like any other — and `mute` went on meaning what it always
    # meant, which is how loud the chain is drawn and not whether anything
    # was recorded about it.
    variants = _read(browser, base, sites["variants"])
    mutes = [i for i, k in enumerate(variants["kinds"]) if k == "cc-mute"]
    assert variants["kinds"] == ["cc-mute", "cc-mute"], variants["kinds"]
    # Containment, not equality: the cell renders the finding's state
    # beside the id ("open · <check>").
    named = " ".join(variants["checks"][i] for i in mutes)
    assert "canonical-mismatch-parameter" in named, named
    assert "canonical-mismatch-trailing-slash" in named, named
    for i in mutes:
        # And the sentence no longer says nothing fires, which it did until
        # this item and would have gone on reading as true.
        assert "No check fires on it" not in variants["notes"][i]
    one = _read(browser, base, sites["full"], _url("/one"))
    assert one["cards"] == 1 and one["kinds"] == ["cc-bad"]


@_mark
def test_pressing_a_node_opens_that_page_in_scope(browser, served):
    """The item's "clicking a node opens that page in scope". Pressed on
    the *second* node, which is the one the fix is about — the reader has
    already seen the page they came from."""
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    base, sites = served
    try:
        _open(pg, base, sites["full"], _url("/one"))
        # On the node's own press target, which is the invisible circle and
        # not the `<g>`: a group's box spans the dot AND the path text under
        # it, so its centre is empty space and a click there lands on the
        # `<svg>` behind. That is where a real press goes too.
        pg.click(".cc-card .cc-node:nth-of-type(2) .cc-hit")
        # The pane's scope moves to that page, which the block redrawing for
        # it is the evidence of. Not the filter field's value: that holds
        # what was *typed* until it is retyped — two pieces of state on
        # purpose, per the note above the input — so a press that moves the
        # scope correctly leaves the box reading what the test filled it
        # with, and asserting on it would be asserting the wrong thing.
        pg.wait_for_function(
            """() => (document.querySelector('.cc-card .cc-title') || {})
                 .textContent?.startsWith('/two')""",
            timeout=10_000)
        assert pg.eval_on_selector_all(".cc-card", "els => els.length") == 1
    finally:
        pg.close()


@_mark
def test_a_node_is_a_target_big_enough_to_press(browser, served):
    """WCAG 2.2 AA 2.5.8: 24 CSS px, measured on the rendered figure rather
    than argued from the viewBox.

    The drawing is scaled to the card, so the dot's 12 viewBox units are
    about eight pixels on a two-card grid — which is why the press target is
    a circle of its own and why this test measures the page instead of
    trusting the arithmetic in `HIT_R`'s comment.
    """
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    base, sites = served
    try:
        _open(pg, base, sites["full"])
        boxes = pg.eval_on_selector_all(
            ".cc-card .cc-hit",
            "els => els.map(e => { const b = e.getBoundingClientRect();"
            " return [b.width, b.height]; })")
        assert boxes, "no pressable node on the site grid"
        for w, h in boxes:
            assert w >= 24 and h >= 24, (w, h)
    finally:
        pg.close()


@_mark
def test_pressing_the_check_id_narrows_the_record(browser, served):
    """The item's "clicking the check id in the sub-line narrows the
    record". On the three-block layout (brief v25 step BP) the check id writes
    `?check=` and the fix cards narrow to that check, with the narrow stated;
    pressing it again clears it."""
    pg = browser.new_page(viewport={"width": 1568, "height": 1080})
    base, sites = served
    try:
        _open(pg, base, sites["full"])
        check = pg.get_attribute(".cc-card button.cc-check", "data-check") \
            or pg.inner_text(".cc-card button.cc-check").strip()
        pg.click(".cc-card button.cc-check")
        pg.wait_for_function("() => location.hash.includes('check=')", timeout=10_000)
        pg.wait_for_selector(".narrow-line", timeout=10_000)
        got = pg.evaluate("""() => ({
          hash: location.hash,
          line: document.querySelector('.narrow-line').textContent,
          cards: [...document.querySelectorAll('.part-page [data-fix-check]')].map((e) => e.dataset.fixCheck) })""")
        pg.click(".narrow-clear")
        pg.wait_for_function("() => !location.hash.includes('check=')", timeout=10_000)
    finally:
        pg.close()
    from urllib.parse import parse_qs
    pressed = parse_qs(got["hash"].split("?", 1)[1])["check"][0]
    assert got["line"].startswith(f"Showing {pressed}:"), got
    assert got["cards"] and all(c == pressed.split("/")[-1] for c in got["cards"]), got["cards"]


@_mark
def test_an_all_healthy_site_is_a_sentence_and_a_run_with_no_canonical_says_so(
        browser, served):
    base, sites = served
    clean = _read(browser, base, sites["clean"])
    assert clean["cards"] == 0
    assert "Every page canonicalises to itself" in clean["clean"]
    blank = _read(browser, base, sites["blank"])
    assert blank["cards"] == 0
    assert "recorded no canonical tag" in blank["absent"]
    assert "not the same as their all owning themselves" in blank["absent"]
