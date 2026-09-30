"""CNT's eight free checks (brief v17 step AX).

Content had five deterministic checks and four briefs, and the four
briefs did all the work an operator actually read. Eight of the questions
they were being paid to answer are arithmetic on a page the crawl already
holds: how long it is against the floor for its kind, how many facts it
carries per hundred words, whether it names an author, whether the
questions it asks itself are answered, and whether two of its pages have
the same title.

**Two of the eight are narrower than the brief specifies, and both say
so.**

`stale` is defined - in the brief and in `content-substance.md` alike - as
an old date *and* a page unchanged across the last two crawls. A module is
handed one crawl. This reports the age and says so; the prompt's own
caution ("decline is not decay") is what the model applies on top.

`question-unanswered` is the structural half of what
`ONP/h2-question-unanswered` asks. That check is brief-only and stays so:
whether a page answers a question *in substance* is a reading. Whether
anything at all follows the heading is not, and it is the half that
catches an FAQ block with empty answers.
"""

from __future__ import annotations

import pytest

from clauditseo.crawler.types import CrawlResult, Page
from clauditseo.engine.types import Site, Tier
from clauditseo.modules.cnt import ContentModule

BASE = "https://content.test"
FILLER = ("The team works across the state and has done so for a long time. "
          "We care about the work and about the people who ask us to do it. ") * 30


def _page(path: str, body: str) -> Page:
    return Page(url=BASE + path, requested_url=BASE + path, status=200,
                content_type="text/html; charset=utf-8",
                content=f"<html><head><title>{path}</title></head>"
                        f"<body><main>{body}</main></body></html>")


def _run(pages: list[Page], prior: dict | None = None, **site_fields):
    crawl = CrawlResult(start_url=BASE + "/", tier=Tier.T2)
    crawl.pages.extend(pages)
    site = Site(domain="content.test")
    for k, v in site_fields.items():
        setattr(site, k, v)
    return ContentModule().run(list(crawl.pages), Tier.T2,
                               {"crawl": crawl, "site": site,
                                "prior_pages": prior})


def _unchanged(pages: list[Page]) -> dict:
    """The previous crawl, having recorded exactly these words.

    `stale` asks two things - the date is old, and nobody has touched the
    page since - and the second is the caller's to answer. A fixture that
    supplied no prior crawl would be testing the first condition alone,
    which is the over-firing the second exists to stop.
    """
    from clauditseo.modules.cnt import content_hash
    from clauditseo.modules.pagefacts import extract_facts

    return {p.url: content_hash(extract_facts(p).text) for p in pages}


def _ids(findings) -> set[str]:
    return {f.check_id for f in findings}


TYPES = {"/service": "service", "/article": "article"}


def test_a_short_service_page_is_thin_against_its_own_floor():
    short = _page("/service", "<h1>Service</h1><p>We do the thing.</p>")
    got = _run([short], page_types=TYPES)
    thin = [f for f in got if f.check_id == "thin"]
    assert thin, _ids(got)
    assert "300-word floor" in thin[0].summary, thin[0].summary


def test_a_page_whose_kind_nobody_set_gets_no_floor_and_no_finding():
    """The rule `schema-missing-for-type` set: a check about what a kind of
    page owes cannot run on a page whose kind nobody stated, and guessing
    the kind would invent the finding with it."""
    short = _page("/whatever", "<h1>Whatever</h1><p>We do the thing.</p>")
    got = _run([short])
    assert "thin" not in _ids(got), [f.summary for f in got]


def test_the_site_record_overrides_the_placeholder_floor():
    short = _page("/service", "<h1>Service</h1><p>" + "word " * 350 + "</p>")
    assert "thin" not in _ids(_run([short], page_types=TYPES))
    got = _run([short], page_types=TYPES, word_floors={"service": 400})
    assert "thin" in _ids(got), [f.summary for f in got]


def test_a_page_of_words_with_no_facts_in_them():
    vague = _page("/service", "<h1>Service</h1><p>" + FILLER + "</p>")
    got = [f for f in _run([vague], page_types=TYPES) if f.check_id == "fact-density"]
    assert got, "a page of pure assertion is not reported"
    assert "per 100 words" in got[0].summary, got[0].summary


def test_an_article_with_no_author_is_reported_and_a_service_page_is_not():
    article = _page("/article", "<h1>Article</h1><p>" + FILLER + "</p>")
    assert "no-author" in _ids(_run([article], page_types=TYPES))
    # The same page with a byline says who wrote it.
    signed = _page("/article", "<h1>Article</h1><p>By Jane Smith. " + FILLER + "</p>")
    assert "no-author" not in _ids(_run([signed], page_types=TYPES))
    # And a service page owes no author at all.
    service = _page("/service", "<h1>Service</h1><p>" + FILLER + "</p>")
    assert "no-author" not in _ids(_run([service], page_types=TYPES))


def test_a_question_heading_with_nothing_under_it():
    page = _page("/service",
                 "<h1>Service</h1>"
                 "<h2>What does it cost?</h2>"
                 "<h2>How long does it take?</h2><p>About two weeks, "
                 "depending on the size of the job and the access.</p>"
                 "<p>" + FILLER + "</p>")
    got = _run([page], page_types=TYPES)
    unanswered = [f for f in got if f.check_id == "question-unanswered"]
    assert unanswered, _ids(got)
    assert "What does it cost?" in unanswered[0].summary, unanswered[0].summary
    assert "How long" not in unanswered[0].summary, unanswered[0].summary


def test_a_question_answered_after_the_detail_rather_than_before_it():
    page = _page("/service",
                 "<h1>Service</h1><h2>What does it cost?</h2><p>It depends.</p>"
                 "<p>" + FILLER + "</p>")
    got = [f for f in _run([page], page_types=TYPES) if f.check_id == "answer-first"]
    assert got, "three words under a question heading is not an answer"


def test_a_shared_title_is_one_group_over_n_pages_not_n_squared_pairs():
    """The unit, measured on a real corpus.

    Pairs read well on a twelve-page site and produced **25,651 across
    227 pages** on a 260-page one whose blog shares a title template -
    a number no operator can act on, and the same fact squared. Grouped,
    that corpus reports seven groups over sixty-nine pages, the largest
    being forty-five pages titled "Acme 2024": a template nobody filled
    in, which is a finding somebody can fix in one place.
    """
    pages = [_page(f"/post-{i}", "<h1>Acme 2024</h1><p>" + FILLER + "</p>")
             for i in range(6)]
    got = [f for f in _run(pages) if f.check_id == "title-overlap"]
    assert len(got) == 1, [f.summary for f in got]
    assert "1 group" in got[0].summary, got[0].summary
    assert "over 6 pages" in got[0].summary, got[0].summary
    assert len(got[0].affected_urls) == 6, got[0].affected_urls


def test_two_pages_with_one_title_are_reported():
    same = [_page("/a", "<h1>Emergency plumbing services</h1><p>" + FILLER + "</p>"),
            _page("/b", "<h1>Emergency plumbing services</h1><p>" + FILLER + "</p>")]
    assert "title-overlap" in _ids(_run(same))


def test_two_suburbs_of_one_service_are_the_exempt_pattern():
    """The pair this check must never fire on.

    `Emergency plumbing Richmond` and `Emergency plumbing Hawthorn` are
    two pages doing their job. One subject, two places: the remainders
    match and the location entities differ, which is the exemption.
    """
    places = ["Richmond", "Hawthorn"]     # the record's own suburbs
    suburbs = [_page("/richmond", "<h1>Emergency plumbing Richmond</h1><p>" + FILLER + "</p>"),
               _page("/hawthorn", "<h1>Emergency plumbing Hawthorn</h1><p>" + FILLER + "</p>")]
    got = _run(suburbs, neighbourhoods=places)
    assert "title-overlap" not in _ids(got), (
        "two location pages doing their job are reported as duplicates")


def test_two_pages_for_one_service_in_one_suburb_are_the_finding():
    """The pair this check exists for, and the one a naive fix loses.

    `Plumbing Melbourne` and `Plumbing services Melbourne` carry the same
    location entity and the same subject; the remainders are `{plumbing}`
    and `{plumbing, services}`, which no similarity measure calls equal
    and which are plainly one subject twice. Containment is what catches
    it, and comparing whole titles - the first fix for the suburb pair -
    is what missed it.
    """
    pages = [_page("/plumbing-melbourne",
                   "<h1>Plumbing Melbourne</h1><p>" + FILLER + "</p>"),
             _page("/plumbing-services-melbourne",
                   "<h1>Plumbing services Melbourne</h1><p>" + FILLER + "</p>")]
    got = _run(pages, neighbourhoods=["Melbourne"])
    assert "title-overlap" in _ids(got), (
        "one service, one suburb, two pages - and the check said nothing")


def test_a_page_whose_own_date_is_old():
    old = _page("/article",
                '<h1>Article</h1><script type="application/ld+json">'
                '{"@type":"Article","dateModified":"2019-01-01"}</script>'
                "<p>" + FILLER + "</p>")
    got = [f for f in _run([old], prior=_unchanged([old]), page_types=TYPES)
           if f.check_id == "stale"]
    assert got, "an article dated 2019, unchanged since the last crawl, is not reported"
    assert "2019-01-01" in got[0].summary, got[0].summary
    # And the recommendation carries the caution the prompt gives the model.
    assert "not automatically a wrong one" in got[0].recommendation


def test_an_old_date_on_a_page_somebody_edited_is_not_stale():
    """The half a date alone gets wrong.

    A CMS nobody configured leaves `dateModified` at first publication, so
    a page rewritten last week reads as four years old. `stale` is two
    conditions and this is the second: the previous crawl recorded
    different words, so somebody has touched it.
    """
    old = _page("/article",
                '<h1>Article</h1><script type="application/ld+json">'
                '{"@type":"Article","dateModified":"2019-01-01"}</script>'
                "<p>" + FILLER + "</p>")
    edited = _page("/article",
                   '<h1>Article</h1><script type="application/ld+json">'
                   '{"@type":"Article","dateModified":"2019-01-01"}</script>'
                   "<p>Rewritten last week. " + FILLER + "</p>")
    got = [f for f in _run([edited], prior=_unchanged([old]), page_types=TYPES)
           if f.check_id == "stale"]
    assert not got, "a page edited since the last crawl is reported as stale"


def test_a_first_crawl_says_nothing_about_staleness():
    """Two conditions, one answerable: the check answers neither.

    Reporting "old" while unable to say "and untouched" is half a rule
    presented as the whole, which is the over-firing the second condition
    exists to stop.
    """
    old = _page("/article",
                '<h1>Article</h1><script type="application/ld+json">'
                '{"@type":"Article","dateModified":"2019-01-01"}</script>'
                "<p>" + FILLER + "</p>")
    assert "stale" not in _ids(_run([old], prior=None, page_types=TYPES))


# --- the registry --------------------------------------------------------

FREE = ("thin", "stale", "no-author", "question-unanswered", "duplicate-content",
        "title-overlap", "fact-density", "answer-first")
MODEL = ("gap", "format-gap", "intent-gap", "topic-drift", "eeat", "substance",
         "answer-surface", "retrieval-cost", "cannibalisation", "term-density",
         "vocabulary-gap", "demand-gap", "optimisation-ratio")


def test_every_content_check_has_a_cost_and_a_part():
    from clauditseo import anatomy
    from clauditseo.checks import check_costs

    costs = check_costs()
    for check in FREE:
        assert costs.get(f"CNT/{check}") == "free", (check, costs.get(f"CNT/{check}"))
        assert anatomy.categorise(check, "CNT") == "content", check
    for check in MODEL:
        assert costs.get(f"CNT/{check}") == "model", (check, costs.get(f"CNT/{check}"))
        assert anatomy.categorise(check, "CNT") == "content", check


def test_topic_drift_is_analysis_and_the_reason_is_written_down():
    """It sits in a prompt's check list beside two the prompt marks
    `(free, read only)`, and it is not one of them: whether a page's
    subject has a path to the topical map is a judgement about a map the
    engine does not hold."""
    from clauditseo.modules.cnt import BRIEF_ONLY_CHECKS

    assert "topic-drift" in BRIEF_ONLY_CHECKS
    assert "thin" not in BRIEF_ONLY_CHECKS and "title-overlap" not in BRIEF_ONLY_CHECKS
