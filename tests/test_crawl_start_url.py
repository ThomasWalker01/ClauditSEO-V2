"""CQ-95: one place where a stored domain becomes a URL the crawler can use.

`launch_audit` builds `https://{domain}/` from a bare stored domain before it
crawls. The two narrow-run entry points added later — `verify_findings` and
`refresh_section` — handed `site_row["domain"]` to the crawler raw. On the
five of six live sites that hold a bare authority, `normalise_url` turns
`www.acme.com.au` into `http:www.acme.com.au` — no `//`, so the netloc is
empty — from which `robots_url_for` builds `http:///robots.txt` and the
sitemap URL `http:/sitemap.xml`. Nothing is fetched, and TEC reports the
absence it manufactured as `The site is not served over HTTPS.` at
`confidence: high` into the site's standing record. Two such findings were
open in `data/clauditseo.db` when this file was written.

**Asserted on the URL handed to the crawler, not on a live 200.** The fixture
server speaks plain HTTP on loopback and the rule being restored defaults a
schemeless domain to `https://` — so an end-to-end reachability assertion here
would go red for a second, unrelated reason and teach nothing about CQ-95.
What went wrong is the *shape* of the URL, and that is what these assert. The
counter-assertion at the bottom covers reachability, on the domain shape that
can be reached.

The enumeration guard is derived from **every crawl call in the module**, not
from the call sites that already build a scheme. CQ-97 records what the other
derivation costs: round 051's kind-filter guard listed the readers that
already carried the filter, so the reader that did not was never in the set.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from urllib.parse import urlsplit

from fastapi.testclient import TestClient

import clauditseo.modules  # noqa: F401  (registers the dimensions)
from clauditseo.api.app import create_app
from tests.conftest import FixtureSite
from tests.test_verify import _routes, _seeded

ROOT = Path(__file__).resolve().parents[1]


def _bare(site) -> str:
    """The shape five of the six live `sites` rows hold.

    `FixtureSite.base_url` is `http://127.0.0.1:PORT`; stripping the scheme
    gives `127.0.0.1:PORT`, which `normalise_url` mangles exactly as it
    mangles `www.acme.com.au` — both come back with an empty netloc.
    """
    return site.base_url.split("://", 1)[1]


# --- the rule itself -------------------------------------------------------

def test_a_bare_domain_becomes_an_absolute_url_and_a_scheme_survives():
    from clauditseo.crawler.crawl import crawl_start_url

    assert crawl_start_url("www.acme.com.au") == "https://www.acme.com.au/"
    assert crawl_start_url("  www.acme.com.au  ") == "https://www.acme.com.au/"
    # A domain that already carries a scheme is handed back untouched: the
    # operator typed it, and http:// on a staging target is a choice.
    assert crawl_start_url("http://127.0.0.1:8123/") == "http://127.0.0.1:8123/"
    assert crawl_start_url("https://www.13acme.com.au/") == "https://www.13acme.com.au/"
    # A scheme is `http://`, not the four characters `http`. `httpwatch.com`
    # is a real domain, and `startswith("http")` — the test `launch_audit`
    # has always used and the one this helper inherited — hands it to the
    # crawler bare, which is CQ-95 again through a narrower door.
    assert crawl_start_url("httpwatch.com") == "https://httpwatch.com/"
    assert crawl_start_url("https.example.com") == "https://https.example.com/"
    # A scheme is case-insensitive, so the test for one must be too (CQ-102).
    # `startswith(("http://", "https://"))` reads `HTTPS://x` as a bare domain
    # and returns `https://HTTPS://x/` — whose netloc is `HTTPS:` and whose
    # hostname is `https`. That is *non-empty*, so the unaddressable-authority
    # assertion below cannot see it: this is a crawl of a host that does not
    # exist rather than a crawl of no host at all, and it needs its own
    # assertion. Returned untouched rather than lower-cased, per the rule
    # above — `normalise_url` already folds the scheme downstream.
    assert crawl_start_url("HTTPS://www.example.com/") == "HTTPS://www.example.com/"
    assert crawl_start_url("Http://127.0.0.1:8123/") == "Http://127.0.0.1:8123/"


def test_the_crawler_never_receives_an_authority_it_cannot_address():
    """The mechanism, stated as the thing that must not be producible.

    `urlsplit("http:www.acme.com.au").netloc` is empty, and every URL the
    crawl derives from the start URL — robots.txt, the sitemap, llms.txt —
    inherits that emptiness.
    """
    from clauditseo.crawler.crawl import crawl_start_url, normalise_url
    from clauditseo.crawler.robots import robots_url_for

    for stored in ("www.acme.com.au", "127.0.0.1:8123", "example.test"):
        url = normalise_url(crawl_start_url(stored))
        assert urlsplit(url).netloc, f"{stored!r} produced {url!r}, no host"
        assert urlsplit(robots_url_for(url)).netloc, \
            f"{stored!r} produced an unaddressable robots URL"


def test_a_crawl_refuses_a_start_url_it_cannot_address():
    """CQ-103: close the class in the room, not at the doors.

    `crawl_site` is `crawl` aliased — `api/app.py:31` and `cli.py:115` both
    import it that way — so this one function is the choke point for every
    crawl the product launches: `adaptive.py:59,121`, `app.py:1423,1559,2476`
    and `cli.py:168`, enumerated by grep rather than from a report's list.
    Guarding the doors leaves the room open, and round 051 guarded three doors
    while `normalise_url` went on manufacturing the URL: a fourth entry point
    reproduces CQ-95 in full.

    **The dead end, recorded so it is not walked again.** Report 052 (CQ-100)
    prescribes rewriting the AST guard below to assert that every crawl call's
    first argument is literally a `crawl_start_url(...)` call. That predicate
    cannot be made both precise and general: four of the six call sites pass
    the URL through a local name (`cli.py:168`, `app.py:2476`) or through a
    function parameter (`adaptive.py:59,121`), and each of those is correct.
    An AST check strict enough to catch the defect flags all four; one loose
    enough to pass them catches nothing. So the refusal below is the net, and
    the AST guard keeps only what it can honestly assert.

    Refused rather than repaired. `crawl()` cannot know whether a caller that
    handed it `www.acme.com.au` meant https or a scheme the operator chose,
    and guessing is what `crawl_start_url` exists to do one layer up with the
    stored domain in hand. A crawl that cannot name a host has nothing to say
    about a site, and saying so loudly is the difference between a failed run
    and a `confidence: high` finding that the site is not served over HTTPS.
    """
    import pytest

    from clauditseo.crawler.crawl import crawl
    from clauditseo.crawler.types import Tier

    for stored in ("www.acme.com.au", "example.test", "13acme.com.au"):
        with pytest.raises(ValueError) as raised:
            crawl(stored, Tier.T1)
        assert stored in str(raised.value),             f"the refusal for {stored!r} must name what it was handed"


# --- every crawl the API launches ------------------------------------------

def test_no_crawl_in_the_api_is_launched_from_a_stored_domain_directly():
    """Enumerated from the crawl calls, not from the ones already correct.

    The set is every call to the crawler in `clauditseo/api/app.py` — the
    question — rather than every call that already passes through the helper,
    which is the answer and would have been satisfied by two of the three
    call sites on the day CQ-95 shipped.
    """
    # CQ-101: anchored on this file, not on the working directory, which is
    # what every other source-reading module here does — `test_ci_bounds.py:24`,
    # `test_anatomy.py:19`, `test_dashboard_a11y.py:36` among them. Read
    # cwd-relative, the one test that keeps a Critical closed goes red for a
    # reason that has nothing to do with the product.
    src = (ROOT / "clauditseo" / "api" / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    crawls = [n for n in ast.walk(tree)
              if isinstance(n, ast.Call)
              and isinstance(n.func, ast.Name)
              and n.func.id in {"crawl_site", "crawl"}
              and n.args]
    assert len(crawls) >= 3, \
        f"expected the module's crawl calls to be found; got {len(crawls)}"

    offenders = []
    for call in crawls:
        first = call.args[0]
        # `site_row["domain"]` / `site["domain"]` handed over as-is.
        if (isinstance(first, ast.Subscript)
                and isinstance(first.slice, ast.Constant)
                and first.slice.value == "domain"):
            offenders.append(f"{ast.unparse(first)} (line {call.lineno})")
    assert not offenders, (
        "a stored domain reached the crawler without being made into a URL: "
        + "; ".join(offenders)
        + " — use crawl_start_url(), the one place that rule lives")


# --- the two endpoints, driven ---------------------------------------------

def _evidence(conn, run_id: str) -> dict:
    row = conn.execute("SELECT crawl_evidence FROM audit_runs WHERE id=?",
                       (run_id,)).fetchone()
    return json.loads(row["crawl_evidence"])


def test_a_verification_of_a_site_stored_bare_crawls_an_addressable_url(tmp_path):
    site = FixtureSite(_routes()).start()
    try:
        db, conn, site_id, fps = _seeded(tmp_path, site, domain=_bare(site))
        client = TestClient(create_app(db_path=db))
        resp = client.post(f"/api/sites/{site_id}/verify",
                           json={"fingerprints": fps})
        assert resp.status_code == 200, resp.text
        start = _evidence(conn, resp.json()["run_id"])["start_url"]
        assert urlsplit(start).netloc, \
            f"the verification crawled {start!r}, which addresses no host"
    finally:
        site.stop()


# `refresh_section` has no behavioural twin here, and the reason is worth more
# than the test would have been. Driven the same way — a site seeded at a bare
# `127.0.0.1:PORT`, then `POST /api/sites/{id}/refresh` — the endpoint answers
# **422** before it ever reaches the crawl:
#
#     'http://127.0.0.1:55881/' is not a page of this site
#     — a refresh re-reads a page the audit already crawled
#
# That was not CQ-95. It was `_host_matches_site` (`api/app.py:586-641`), which
# compares a URL's *host* against the stored *domain* and never stripped a port:
# with `127.0.0.1:55881` in the `sites` row, `host == domain` was false, both
# `endswith` clauses were false, and the refresh was refused. So a site stored
# as `host:port` could not be section-refreshed at all, whatever this file does.
# This paragraph said it "lives one call site away from CQ-98's suffix-match
# defect and belongs to that fix, not this one", and round 138 took CQ-98 and
# took it: `_comparable_host` strips the port (and the IPv6 brackets a stored
# authority carries and `urlsplit().hostname` does not) for the comparison
# alone, leaving `site_host` untouched because `_probe_target` dials what that
# returns. The refusal above is also no longer the sentence quoted — it named a
# check the route does not make and now names the two hosts it compared.
# `tests/test_a_public_suffix_is_not_a_site_of_its_own.py` is where both halves
# are asserted; the paragraph is kept rather than deleted because the reasoning
# for *why* there is still no driven twin here is unchanged.
#
# The refresh call site is still guarded: the AST enumeration above named
# `site_row['domain'] (line 1484)` as an offender before the fix, and it is the
# assertion that fails if a later change puts a bare domain back.


# --- the counter-assertion -------------------------------------------------

def test_a_site_stored_with_a_scheme_is_unchanged(tmp_path):
    """The shape every existing test uses. It reached robots.txt before this
    change and must still reach it after — the fix is for the other shape,
    not a new behaviour for this one.
    """
    site = FixtureSite(_routes()).start()
    try:
        db, conn, site_id, fps = _seeded(tmp_path, site)
        client = TestClient(create_app(db_path=db))
        resp = client.post(f"/api/sites/{site_id}/verify",
                           json={"fingerprints": fps})
        assert resp.status_code == 200, resp.text
        ev = _evidence(conn, resp.json()["run_id"])
        assert urlsplit(ev["start_url"]).netloc
        assert ev["robots_status"] == 200, \
            "the absolute-URL shape stopped reaching robots.txt"
    finally:
        site.stop()


# --- one reader of a stored domain, enumerated (CQ-132) --------------------

def test_a_scheme_is_two_slashes_and_not_the_four_characters_http():
    """`site_host` is the other half of `crawl_start_url`, and CQ-132 is what
    happened while only one half existed.

    The rule was diagnosed in `crawl_start_url`'s docstring, by name and with
    this exact input, and the fix stayed in that function. Four call sites
    went on testing `domain.startswith("http")`: `_host_matches_site`,
    `_probe_target` and `_validate_start_url` in `api/app.py`, and the
    deliverable's filename slug in `reporting/generate.py`.

    The `""` cases are the fallback, unified. Three of the four fell back with
    `or domain` and one with `or ""`; with the scheme test wrong that
    difference decided whether a call site mangled the host or lost it, which
    is luck rather than a rule.
    """
    from clauditseo.crawler.crawl import site_host

    # A real domain that begins with the four characters. `httpwatch.com` is
    # the input `crawl_start_url`'s docstring names; `httpsecure.com.au` is
    # the shape an Australian client record would hold.
    assert site_host("httpwatch.com") == "httpwatch.com"
    assert site_host("httpsecure.com.au") == "httpsecure.com.au"
    assert site_host("https.example.com") == "https.example.com"
    # A scheme is case-insensitive, for the reason CQ-102 records.
    assert site_host("HTTPS://X.COM/") == "x.com"
    assert site_host("https://www.13acme.com.au/") == "www.13acme.com.au"
    assert site_host("  www.acme.com.au  ") == "www.acme.com.au"
    # A bare authority comes back whole, port included: `_probe_target`'s
    # answer is what `probes._host_port` dials, so dropping the port here
    # would move a probe of `example.com:8443` onto 443 without saying so.
    assert site_host("127.0.0.1:443") == "127.0.0.1:443"
    # A scheme with no authority names no host. `or domain` would hand back
    # `https://` as though it were one.
    assert site_host("https://") == ""
    assert site_host("") == ""
    # And it never raises: `urlsplit` answers `ValueError: Invalid IPv6 URL`
    # for an unbalanced bracket, which is CQ-120 at the route above it.
    assert site_host("https://a]b") == ""
    assert site_host("a]b") == "a]b"


def test_no_module_re_derives_how_to_read_a_host_out_of_a_stored_domain():
    """Enumerated from the predicate, not from the four call sites fixed.

    The set is every `startswith("http")` under `clauditseo/` — the shape of
    the defect — narrowed to the ones testing a *domain* rather than a URL.
    A test listing the four known copies would pass the moment a fifth is
    written, which is exactly how these four came to exist after the defect
    was diagnosed and fixed in `crawl.py`.

    `scoring.py` and `runs.py` are excluded by the name they test, not by an
    allowlist: `u.startswith("http")` there asks "is this crawled URL
    absolute", a different question with a different right answer.
    """
    offenders = []
    for path in sorted((ROOT / "clauditseo").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "startswith"
                    and len(node.args) == 1
                    and getattr(node.args[0], "value", None) == "http"):
                continue
            if "domain" not in ast.unparse(node.func.value):
                continue
            offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}: "
                             f"{ast.unparse(node)}")
    assert not offenders, (
        "a scheme is `http://` or `https://`, not the four characters `http` "
        "- call crawl.site_host(), the one place that rule lives:\n  "
        + "\n  ".join(offenders))
