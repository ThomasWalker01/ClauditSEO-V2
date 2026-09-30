"""A page is one page whether the row spelled it `/about` or `https://…/about`.

The operator's defect, 2026-09-07. The Structured data part page refused
`'/' is not a page of this site — its host '' is not 'beacon.com.au'`,
and under it: `The crawl recorded nothing about this page`. Both came from
one cause. The narrow picker offered Birch's twelve pages **twice**, once as
a path and once as a URL; picking the path set `page = "/"`, and the refresh
route compares hosts while `page_facts` is keyed by URL, so neither could
find anything.

**Where the two spellings come from.** The sweep writes
`affected_urls=[f.url]`, an absolute URL. The legacy expert findings table
(`expert.parse_findings_block`) accepted any cell starting with `http://`,
`https://` **or `/`** and stored it verbatim — so a model writing `/about`
put a path in the same column. The contract parser has resolved a row's page
through the run's page set since brief v10 (`contract.py`, `page_index`);
this reader was the half left behind. Acme has 423 findings and no paths,
which is why it never showed; Birch's 2026-09-06 04:59 run has 52.

**Why the read side is fixed and not only the write side, which is the part
worth keeping.** `anatomy_view` reads OPEN findings site-wide, not one run's
— "a finding raised by an older run and never fixed is still open, and its
page counts here". So a spelling already stored outlives any number of
re-audits, and the operator's re-scan could not have cleared it. Only a
read-side canonicalisation repairs data that exists.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from clauditseo.analysts.expert import parse_findings_block
from clauditseo.persistence import runs


# --- the write side -------------------------------------------------------

REPORT = """Some prose the operator reads.

```clauditseo-findings
severity | code | summary | urls
high | h1-multiple | two h1s | /about
medium | heading-skip | h2 to h4 | https://x.test/pricing
low | img-filename-generic | img_1234.jpg | /gallery, https://x.test/about
```
"""


def _rows(page_set=None):
    _, found = parse_findings_block(REPORT, page_set)
    return {r["code"]: r["affected_urls"] for r in found}


def test_a_path_the_run_knows_becomes_the_runs_own_url():
    """The fix. Without the page set this reader stored what the model
    typed, and everything downstream that treats `affected_urls` as a URL
    then broke on the difference."""
    pages = ["https://x.test/about", "https://x.test/pricing",
             "https://x.test/gallery"]
    got = _rows(pages)
    assert got["h1-multiple"] == ["https://x.test/about"], got
    assert got["heading-skip"] == ["https://x.test/pricing"], got
    # Both spellings in one cell collapse onto the same page set entry, and
    # the row keeps both pages it named.
    assert got["img-filename-generic"] == ["https://x.test/gallery",
                                        "https://x.test/about"], got


def test_a_path_the_run_does_not_know_is_kept_rather_than_dropped():
    """A finding about a page the crawl never fetched is still a finding.
    Dropping the row to tidy the spelling would lose it, and inventing a
    host would be a guess about which host."""
    got = _rows(["https://x.test/pricing"])
    assert got["h1-multiple"] == ["/about"], got


def test_the_reader_still_works_with_no_page_set_at_all():
    """Called without one — a caller that has no run in hand — it behaves
    exactly as it did before, because a resolver with nothing to resolve
    against must not start dropping rows."""
    got = _rows(None)
    assert got["h1-multiple"] == ["/about"], got
    assert got["heading-skip"] == ["https://x.test/pricing"], got


def test_the_call_site_hands_it_the_runs_pages():
    """The parameter is useless unless the one caller passes it. Read from
    the source rather than exercised, because reaching that line needs a
    model provider."""
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "clauditseo" / "analysts"
           / "expert.py").read_text(encoding="utf-8")
    call = src[src.index("report, raised = parse_findings_block("):]
    call = call[:200]
    assert "evidence" in call and "pages" in call, call


# --- the read side, which is what repairs stored runs ---------------------

SITE: dict[str, str] = {}
RUN: dict[str, str] = {}
NOW = "2026-09-07T00:00:00"

@pytest.fixture()
def site(tmp_path):
    """One site whose findings name the same three pages in both spellings —
    the shape Birch is actually in, built small enough to reason about."""
    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate
    from clauditseo.persistence import repo

    db = tmp_path / "c.db"
    conn = connect(db)
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    client = repo.create_client(conn, op, "C")
    site_id = repo.create_site(conn, client, "x.test")
    run_id = runs.create_run(conn, site_id, ["ONP"], "T2")
    rows = [
        # The sweep's spelling.
        ("title-missing", "ONP", "medium", "deterministic",
         ["https://x.test/", "https://x.test/about"]),
        # A brief's, for one of the same pages and one of its own.
        ("h1-multiple", "ONP", "high", "model-judgement", ["/about"]),
        ("heading-skip", "ONP", "low", "model-judgement", ["/"]),
    ]
    for n, (check, dim, sev, source, urls) in enumerate(rows):
        conn.execute(
            "INSERT INTO findings (run_id, check_id, dimension, severity,"
            " summary, affected_urls, evidence, recommendation, source,"
            " fingerprint, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (run_id, check, dim, sev, f"{check} summary",
             json.dumps(urls), "{}", "fix it", source, f"fp{n}", NOW))
        conn.execute(
            "INSERT INTO finding_states (site_id, fingerprint, state,"
            " changed_by_run, updated_at) VALUES (?,?,?,?,?)",
            (site_id, f"fp{n}", "open", run_id, NOW))
    conn.commit()
    SITE["id"] = site_id
    RUN["id"] = run_id
    yield conn
    conn.close()



def _pages(conn, page=None):
    return runs.anatomy_view(conn, SITE["id"], page)


def test_the_narrow_offers_each_page_once_not_once_per_spelling(site):
    """The visible defect: Birch's twelve pages were offered as twenty-four
    entries, twelve of which could not be acted on."""
    view = _pages(site)
    assert view["pages"] == ["https://x.test/", "https://x.test/about"], view["pages"]
    assert not [u for u in view["pages"] if not u.startswith("http")], (
        "a path in this list is a page the refresh route will refuse and "
        "`page_facts` cannot key on")


def test_the_absolute_spelling_wins_because_that_is_what_consumers_need(site):
    """Not an arbitrary tie-break. The refresh route compares hosts and
    `page_facts` is keyed by URL, so the path form is the one nothing
    downstream can use."""
    assert all(u.startswith("https://") for u in _pages(site)["pages"])


def test_narrowing_by_either_spelling_finds_the_same_findings(site):
    """The half that would have been missed by fixing the picker alone: the
    filter compares by key, so a narrow set from one spelling still matches
    rows written in the other. Before this, narrowing to the URL saw only
    the sweep's rows and reported the page clean of everything a brief had
    said about it."""
    by_url = _pages(site, "https://x.test/about")
    by_path = _pages(site, "/about")
    # `["value"]` since item 156: the count carries its population and the sum
    # wants the figure.
    total = lambda v: sum(c["total"]["value"] for c in v["categories"])
    assert total(by_url) == total(by_path) == 2, (total(by_url), total(by_path))
    # Both spellings resolve the narrow itself, so a stale link or a
    # bookmarked hash lands on the page rather than on nothing.
    assert by_url["page"] == by_path["page"] == "https://x.test/about"


def test_a_page_only_ever_named_by_path_survives(site):
    """No absolute spelling exists for it anywhere, so the path stands.
    Dropping it would delete the finding; inventing a host would be a guess
    about which host."""
    site.execute(
        "INSERT INTO findings (run_id, check_id, dimension, severity, summary,"
        " affected_urls, evidence, recommendation, source, fingerprint,"
        " created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (RUN["id"], "title-long", "ONP", "low", "s",
         json.dumps(["/orphan"]), "{}", "fix", "model-judgement", "fp9", NOW))
    site.execute("INSERT INTO finding_states (site_id, fingerprint, state,"
                 " changed_by_run, updated_at) VALUES (?,?,?,?,?)",
                 (SITE["id"], "fp9", "open", RUN["id"], NOW))
    site.commit()
    assert "/orphan" in _pages(site)["pages"]
