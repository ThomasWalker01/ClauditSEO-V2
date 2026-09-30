"""One rule for "how many pages", and a headline that agrees with its list.

Two defects reached a client document from the same root. The report headline
counted findings and printed them as pages, so `title-duplicate` — which
raises one finding per group of pages sharing a title — read "on 2 pages"
above a list of thirteen. And the plan section read its count from the engine
while the finding list counted raw URLs, so the same check was 99 pages in
one paragraph and 100 in the next.

Neither number was wrong on its own terms, which is what made them hard to
see: a finding really is a finding, and a URL really is a URL. What was
missing was a single definition of the thing being counted. Both now come
from `page_paths`, and the list a headline sits above is the same sequence
the headline counted — so they cannot drift apart again rather than being
correct for now.
"""

from __future__ import annotations

import re

from clauditseo.engine.scoring import page_paths
from clauditseo.reporting.render import _group_by_check, _group_line

SITE = "https://x.example"


def finding(check: str, urls: list[str], *, dimension: str = "ONP",
            severity: str = "medium", summary: str = "something") -> dict:
    return {"dimension": dimension, "check_id": check, "severity": severity,
            "source": "deterministic", "model_id": None, "confidence": "high",
            "recommendation": "", "summary": summary,
            "affected_urls": [f"{SITE}{u}" for u in urls]}


def test_a_query_string_does_not_make_a_second_page() -> None:
    """The exact pair that split the two counts apart."""
    paths = page_paths([f"{SITE}/apply", f"{SITE}/apply?product_type=loc"])
    assert paths == {"/apply"}


def test_a_trailing_slash_does_not_make_a_second_page() -> None:
    assert page_paths([f"{SITE}/x", f"{SITE}/x"]) == {"/x"}
    assert page_paths([SITE, f"{SITE}/"]) == {"/"}


def test_non_http_subjects_are_not_counted_as_pages() -> None:
    """Some findings name a pair key or a header, not a URL."""
    assert page_paths(["/a|/b", "sitemap", f"{SITE}/real"]) == {"/real"}


def test_the_headline_counts_pages_not_findings() -> None:
    """`title-duplicate` raises one finding per group, not per page.

    Two findings covering six pages must read six, which is the number a
    developer will go and fix.
    """
    group = _group_by_check([
        finding("title-duplicate", ["/a", "/b", "/c"]),
        finding("title-duplicate", ["/d", "/e", "/f"]),
    ])[0]
    assert len(group["findings"]) == 2
    assert group["pages"] == 6
    assert " on 6 pages" in _group_line(group, "client")


def _headline_and_list(group: dict) -> tuple[int, int]:
    """What the rendered line claims, and what it actually shows."""
    lines = _group_line(group, "client").splitlines()
    claimed = int(re.search(r" on (\d+) pages", lines[0]).group(1))
    listed = lines[1].count("`") // 2
    extra = re.search(r"and (\d+) \(source", lines[1])
    return claimed, listed + (int(extra.group(1)) if extra else 0)


def test_the_headline_agrees_with_the_list_beneath_it() -> None:
    """The structural guarantee: both come from one sequence.

    Read off the rendered text, not the group dict. Asserting on `page_list`
    alone passed while the renderer still printed raw URLs beside a count of
    pages — the data was right and the document was not, which is the whole
    defect. Sizes span the display cap, where the line reads "N and M more",
    and include URL variants, without which every list matches trivially.
    """
    for count in (2, 3, 9, 40):
        urls = [f"/page-{i}" for i in range(count)]
        group = _group_by_check([finding("img-alt-missing", [u]) for u in urls])[0]
        claimed, shown = _headline_and_list(group)
        assert claimed == shown, (
            f"{count} pages: headline says {claimed}, list shows {shown}")

    # The case that actually separates URLs from pages. Two findings, not
    # one: a lone finding keeps its own summary instead of a count, so a
    # single-finding group never reaches the branch under test.
    group = _group_by_check([
        finding("img-alt-missing", ["/a", "/a?utm=x", "/b"]),
        finding("img-alt-missing", ["/b?ref=y", "/c"]),
    ])[0]
    claimed, shown = _headline_and_list(group)
    assert claimed == shown == 3


def test_url_variants_of_one_page_are_listed_once() -> None:
    """Otherwise the list contradicts a count that is itself correct."""
    group = _group_by_check([
        finding("img-alt-missing", ["/apply", "/apply?product_type=loc"]),
        finding("img-alt-missing", ["/other"]),
    ])[0]
    assert group["pages"] == 2
    assert group["page_list"] == ["/apply", "/other"]
    # And in the document, which is where it went wrong.
    listed = _group_line(group, "client").splitlines()[1]
    assert "`/apply`" in listed and "`/other`" in listed
    assert "product_type" not in listed
    assert listed.count("`") // 2 == 2


def test_a_check_naming_no_page_does_not_claim_pages() -> None:
    """A site-level finding is real, but it is not "on N pages"."""
    group = _group_by_check([
        finding("robots-missing", [], dimension="TEC"),
        finding("robots-missing", [], dimension="TEC"),
    ])[0]
    assert group["pages"] == 0
    line = _group_line(group, "client")
    assert "pages" not in line.split("(source")[0]
    assert "2 findings" in line


def test_the_report_and_the_engine_count_the_same_way() -> None:
    """The plan and the finding list are rendered from different sources.

    The engine's per-check `pages` feeds "What to do first"; the group feeds
    the list below it. Same findings in, same number out, or one paragraph
    contradicts the next.
    """
    from clauditseo.engine.scoring import _pages_touched
    from clauditseo.engine.types import Finding

    urls = [f"{SITE}/apply", f"{SITE}/apply?x=1", f"{SITE}/b", f"{SITE}/c"]
    engine_side = [Finding(dimension="ONP", check_id="img-alt-missing",
                           severity="medium", summary="s", subject=u,
                           affected_urls=[u]) for u in urls]
    report_side = _group_by_check([finding("img-alt-missing", ["/apply"]),
                                   finding("img-alt-missing", ["/apply?x=1"]),
                                   finding("img-alt-missing", ["/b"]),
                                   finding("img-alt-missing", ["/c"])])[0]
    assert _pages_touched(engine_side) == report_side["pages"] == 3


# --- what a client is told about a gap ----------------------------------------


def _not_assessed(**evidence) -> dict:
    return {"dimension": "OFP", "check_id": "backlinks-not-assessed",
            "severity": "info", "source": "deterministic", "model_id": None,
            "confidence": "low", "recommendation": "",
            "summary": "Not assessed: anchor text distribution. The configured "
                       "provider (moz, openpagerank) does not supply it.",
            "affected_urls": [], "evidence": evidence}


def test_a_client_is_never_shown_the_provider_that_refused() -> None:
    from clauditseo.reporting.render import _not_assessed_line
    f = _not_assessed(unmeasured=["referring domains"],
                      providers_failing=[{"provider": "openpagerank",
                                          "status": 403}])
    line = _not_assessed_line(f, "client")
    assert "openpagerank" not in line and "403" not in line
    assert "referring domains" in line
    assert "unavailable during this run" in line


def test_a_client_is_never_shown_a_provider_that_answered_either() -> None:
    """The branch the first fix missed.

    Only refusal was handled, because that was what the run in front of me
    was doing. Once the keys worked, a different sentence put the same vendor
    names into a client document.
    """
    from clauditseo.reporting.render import _not_assessed_line
    f = _not_assessed(unmeasured=["anchor text distribution"],
                      providers_answering=["moz", "openpagerank"])
    line = _not_assessed_line(f, "client")
    assert "moz" not in line and "openpagerank" not in line
    assert "anchor text distribution" in line
    assert "do not report it" in line


def test_the_operator_still_gets_the_provider_and_the_status() -> None:
    """The gap is the client's business; the cause is the operator's."""
    from clauditseo.reporting.render import _not_assessed_line
    f = _not_assessed(unmeasured=["referring domains"],
                      providers_failing=[{"provider": "openpagerank",
                                          "status": 403}])
    assert "openpagerank" in _not_assessed_line(f, "internal")


def test_a_reason_is_not_invented_when_none_was_recorded() -> None:
    """"no data source available" was appended unconditionally, so it landed
    under a sentence that had just named the source which answered."""
    from clauditseo.reporting.render import _not_assessed_line
    line = _not_assessed_line(_not_assessed(providers_answering=["moz"]),
                              "internal")
    assert "no data source available" not in line


def test_a_crawl_that_fetched_nothing_is_not_blamed_on_the_tier() -> None:
    """Two silences, one flag, and the document picked the wrong one.

    `tier_permits_external = tier is not Tier.T1 and bool(crawl.pages)` put two
    conditions under a name claiming one, and the renderer mapped its false
    value to a single definite cause: "this audit tier does not call external
    data sources". True at T1. False at T2 or T3 whose crawl fetched no page —
    where the tier *does* call out and the reason is that there was nothing to
    measure.

    Live on the operator's own data at the time of writing: run `d02919eb` is
    `tier=T2, status=blocked` and carries `tier_permits_external=False`, beside
    `1b1da5e5` at `tier=T1` carrying the same value. One sentence is true and
    the other is not, and the stored evidence could not tell them apart.

    Nineteen rounds on the cohort register, and the impact is a false definite
    cause in a client document on every blocked crawl.
    """
    from clauditseo.reporting.render import _not_assessed_line

    blocked = _not_assessed(unmeasured=["Core Web Vitals field data"],
                            tier_calls_external=True, pages_fetched=False)
    line = _not_assessed_line(blocked, "client")
    assert "this audit tier does not call external data sources" not in line, (
        "a T2 crawl that fetched nothing was blamed on the tier: " + line)
    assert "no page" in line or "nothing to measure" in line, (
        "the reason must name the real cause — no page was fetched: " + line)


def test_a_tier_that_makes_no_external_call_still_says_so() -> None:
    """The other half, so the fix cannot be a blanket rewording.

    At T1 the sentence was always right, and it outranks the others: with no
    call made, what is configured and whether it would have answered are both
    unknown, and any sentence about them is a claim the run cannot support.
    """
    from clauditseo.reporting.render import _not_assessed_line

    t1 = _not_assessed(unmeasured=["Core Web Vitals field data"],
                       tier_calls_external=False, pages_fetched=False)
    assert ("this audit tier does not call external data sources"
            in _not_assessed_line(t1, "client"))


def test_a_stored_finding_from_before_the_split_still_renders_its_cause() -> None:
    """Five findings in the operator's database carry the old single flag.

    Re-rendering one must not change what its document said. The old key is
    still read where the new pair is absent, which is the only way a stored
    deliverable and a fresh one can be compared at all.
    """
    from clauditseo.reporting.render import _not_assessed_line

    old = _not_assessed(unmeasured=["Core Web Vitals field data"])
    old["evidence"]["tier_permits_external"] = False
    assert ("this audit tier does not call external data sources"
            in _not_assessed_line(old, "client"))
