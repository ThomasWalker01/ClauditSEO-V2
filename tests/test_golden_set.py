"""The golden set, and the guard that keeps it honest.

A labelled corpus rots in a way that is invisible: someone edits the fixture,
the label no longer describes it, and every future score is measured against a
claim that stopped being true. These tests assert the fixture really does
contain what the labels say — and really does NOT contain what the traps say —
by reading the served HTML, not by reading the labels back to themselves.

The scorer tests cover the part that made this possible: matching on the page
rather than on the model's choice of check id.
"""

from __future__ import annotations

import json
import re

import pytest

from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.golden import label_id, score
from clauditseo.persistence import repo, runs
from tests.fixtures.golden_site import LABELS, NAV, VIEWPORT, routes


def _html(path: str) -> str:
    return routes()[path][2]


# --- the fixture contains what the labels claim ----------------------------

def test_the_sitemap_really_does_omit_linked_pages():
    sm = _html("/sitemap.xml")
    assert "/hot-water" not in sm and "/blocked-drains" not in sm
    # And they are genuinely reachable, or the omission would be moot.
    assert "/hot-water" in _html("/") and "/blocked-drains" in _html("/")


def test_the_blocked_drains_page_really_has_no_h1():
    page = _html("/blocked-drains")
    assert "<h1>" not in page
    assert "<h2>Blocked drains</h2>" in page


def test_the_blocked_drains_title_really_duplicates_the_home_page():
    def title(p):
        return p.split("<title>")[1].split("</title>")[0]
    assert title(_html("/blocked-drains")) == title(_html("/"))


def test_the_hot_water_page_really_has_no_meta_description():
    assert 'name="description"' not in _html("/hot-water")
    # Every other page has one, so its absence is a defect and not a style.
    for path in ("/", "/services", "/about", "/contact"):
        assert 'name="description"' in _html(path)


def test_the_about_page_really_contradicts_the_footer():
    about = _html("/about")
    assert "Rosa Street" in about, "the planted misspelling is gone"
    assert "14 Rose Street" in about, "the footer NAP is gone"
    assert "9417 5511" in about and "9417 5500" in about, "phones agree now"


def test_the_services_page_really_carries_a_meta_robots_noindex():
    """And nowhere else, or the label could be satisfied by another page."""
    assert '<meta name="robots" content="noindex">' in _html("/services")
    for path in ("/", "/blocked-drains", "/hot-water", "/about", "/contact"):
        assert 'name="robots"' not in _html(path), f"{path} gained a directive"
    # It has to be a page worth indexing, or the noindex is not a defect.
    assert "/services" in _html("/sitemap.xml") and "/services" in NAV


def test_the_about_page_serves_its_noindex_in_the_headers_and_only_there():
    """The plant that earns its place: a brief reading the HTML and not the
    headers must be able to miss it. If the directive ever appears in the
    body too, the label stops measuring that and nobody would notice."""
    _status, headers, body = routes()["/about"]
    assert headers.get("X-Robots-Tag") == "noindex"
    assert "robots" not in body.lower(), "the directive leaked into the body"
    for path, (_s, h, _b) in routes().items():
        if path != "/about":
            assert "X-Robots-Tag" not in h, f"{path} gained the header"
    # Listed in the sitemap, so it is a contradiction and not an exclusion.
    assert "/about" in _html("/sitemap.xml")


def test_only_the_about_page_lacks_a_viewport():
    """A site-wide absence cannot be scored — a brief that says it once and a
    brief that says it six times both look correct. A divergence can."""
    assert "viewport" not in _html("/about")
    for path in ("/", "/services", "/blocked-drains", "/hot-water", "/contact"):
        assert VIEWPORT in _html(path), f"{path} lost its viewport"
    # Byte-identical on all five, so the only difference is presence.
    assert _html("/").count(VIEWPORT) == 1


# --- and does NOT contain what the traps claim -----------------------------

def test_the_contact_page_is_short_on_purpose_and_otherwise_correct():
    """The trap only works if the page is genuinely fine apart from length."""
    contact = _html("/contact")
    assert "<h1>" in contact and 'name="description"' in contact
    assert "rel=\"canonical\"" in contact
    assert len(contact.split()) < len(_html("/services").split())


def test_the_site_really_is_single_locale():
    """Three conditions, because the trap depends on all three and the
    hreflang brief is now handed all three as evidence: no alternate
    annotation, one declared language, and no locale-shaped URL folder. A
    fixture that acquired any one of them would make raising hreflang
    correct, and the trap would be scoring the opposite of what it claims."""
    langs = set()
    for path, (_status, _headers, body) in routes().items():
        assert "hreflang" not in body, f"{path} declares an alternate"
        for token in ("lang=en", 'lang="en"'):
            if token in body:
                langs.add("en")
        first = path.strip("/").split("/")[0]
        assert not re.fullmatch(r"[a-z]{2}(-[a-z]{2})?", first),             f"{path} looks like a locale folder"
    assert langs == {"en"}, "the fixture no longer declares exactly one language"


def test_every_page_really_carries_a_self_canonical():
    for path in ("/", "/services", "/blocked-drains", "/hot-water",
                 "/about", "/contact"):
        assert f'canonical" href="https://goldenplumbing.test{path}"' \
            in _html(path)


def test_robots_txt_really_disallows_nothing():
    """The trap beside the two noindex plants. noindex and robots-disallowed
    are the pair briefs most often confuse, and a fixture that plants one
    without trapping the other cannot tell detection from that confusion."""
    robots = routes()["/robots.txt"][2]
    assert "Allow: /" in robots
    assert "disallow" not in robots.lower(), "the trap is no longer a trap"


def test_no_label_names_a_page_the_fixture_does_not_serve():
    """A label pointing at a page that does not exist can never be caught,
    and would quietly drag the catch rate down forever. Site-scoped labels
    name no page and are exempt."""
    served = set(routes())
    for item in LABELS["expected"] + LABELS["known_absent"]:
        page = item.get("page")
        if page is not None:
            assert page in served, f"{page} is not served"


def test_a_site_level_finding_with_no_url_can_still_be_matched():
    """The bug this cost: a brief's site-level findings carry no URL, so a
    page label could never match one. The hreflang trap scored a clean zero
    while the brief raised eight hreflang findings on a single-locale site —
    a check reporting "clean" because it could not look."""
    from clauditseo.golden import _matches

    rows = [{"check_id": "hreflang-missing-html",
             "summary": "No hreflang annotations were found.", "urls": []}]
    assert _matches({"tool": "hreflang", "mentions": ["hreflang"]}, rows)
    assert not _matches({"tool": "hreflang", "page": "/",
                         "mentions": ["hreflang"]}, rows), (
        "a page label must still require a page; that is what makes it sharp")


def _label(tool: str, words: list[str]) -> dict:
    return next(item for item in LABELS["expected"] + LABELS["known_absent"]
                if item["tool"] == tool and item.get("mentions") == words)


#: Shaped the way run `79a1fc02ab714e1ba132b0bb7ad9d9f0` shaped them, which
#: is the evidence Q-20 was decided on: `indexability` put both plants in the
#: `affected_urls` of one `noindex-page` row, `mobile-viewport` put `/about`
#: in `mobile-viewport-01`'s, and neither summary names the path in prose.
#: A trap that is still site-scoped is here too, because `hreflang` really
#: does raise with an empty `affected_urls` and must keep matching on words.
_AS_THE_RUN_RAISED_THEM = [
    ("indexability", ["noindex", "meta"], "noindex-page",
     "/services carries meta noindex while linked site-wide from indexable"
     " pages (+1 more of the same code: /about carries X-Robots-Tag noindex)",
     ["http://127.0.0.1:60243/services", "http://127.0.0.1:60243/about"]),
    ("indexability", ["noindex", "x-robots"], "noindex-page",
     "/services carries meta noindex while linked site-wide from indexable"
     " pages (+1 more of the same code: /about carries X-Robots-Tag noindex)",
     ["http://127.0.0.1:60243/services", "http://127.0.0.1:60243/about"]),
    ("mobile-viewport", ["viewport"], "mobile-viewport-01",
     "No viewport meta tag present in served HTML, forcing desktop-width"
     " mobile rendering",
     ["http://127.0.0.1:60243/about"]),
    ("indexability", ["disallow"], "robots-disallowed",
     "Two URLs are disallowed in robots.txt and cannot be crawled", []),
]


@pytest.mark.parametrize("tool,words,check_id,summary,urls",
                         _AS_THE_RUN_RAISED_THEM)
def test_each_label_can_actually_be_matched(tool, words, check_id, summary,
                                            urls):
    """A label that can never match is indistinguishable from a brief that
    was clean, and that is how the `hreflang` trap scored a perfect zero
    while the brief raised eight of them.

    This asserted the opposite until Q-20: that these three labels were
    site-scoped, fed rows with no URL. The premise was that a brief declaring
    `scope: site` never names one, and the paid run falsified it for two of
    the three tools — so the rows here are the ones that run actually raised.
    An untripped trap in a paid run means nothing on its own. This is what
    says the trap was armed."""
    from clauditseo.golden import _matches

    label = _label(tool, words)
    assert _matches(label, [{"check_id": check_id, "summary": summary,
                             "urls": urls}])


def test_the_two_noindex_labels_do_not_answer_for_each_other():
    """They are on different pages and delivered by different mechanisms, so
    catching one must not score the other. Otherwise a brief that reads only
    the HTML scores both and the header plant measures nothing.

    Both are page labels since Q-20, so this is now checked in both
    directions — a page can no more answer for the other page than a
    mechanism can for the other mechanism."""
    from clauditseo.golden import _matches

    header_only = [{"check_id": "noindex-page",
                    "summary": "About page serves X-Robots-Tag: noindex",
                    "urls": ["http://127.0.0.1:60243/about"]}]
    assert _matches(_label("indexability", ["noindex", "x-robots"]),
                    header_only)
    assert not _matches(_label("indexability", ["noindex", "meta"]),
                        header_only)
    # The mirror: the right words on the wrong page is not a hit either.
    wrong_page = [{"check_id": "noindex-page",
                   "summary": "Services page serves X-Robots-Tag: noindex",
                   "urls": ["http://127.0.0.1:60243/services"]}]
    assert not _matches(_label("indexability", ["noindex", "x-robots"]),
                        wrong_page)


def test_a_label_with_no_words_matches_nothing():
    """Otherwise an empty label matches every finding the tool raised and
    scores a perfect catch rate for saying nothing."""
    from clauditseo.golden import _matches

    rows = [{"check_id": "x", "summary": "y", "urls": []}]
    assert not _matches({"tool": "t"}, rows)
    assert not _matches({"tool": "t", "mentions": []}, rows)


def test_every_label_carries_a_note_saying_why():
    """A label without its reason cannot be re-judged when a brief disputes
    it, and the first thing a disputed label needs is its own argument."""
    for item in LABELS["expected"] + LABELS["known_absent"]:
        assert item.get("note"), f"{label_id(item)} has no note"


# --- the scorer -------------------------------------------------------------

@pytest.fixture
def scored(tmp_path):
    """One run whose findings are written by hand, so the scorer is measured
    rather than the model."""
    conn = connect(tmp_path / "golden.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site = repo.create_site(conn, repo.create_client(conn, op, "G"),
                            "goldenplumbing.test")
    run_id = runs.create_run(conn, site, ["TEC"], "T2")

    def raise_finding(tool, check_id, summary, url):
        conn.execute(
            "INSERT INTO findings (id, run_id, dimension, check_id, severity,"
            " source, confidence, summary, affected_urls, fingerprint,"
            " created_at) VALUES (?, ?, ?, ?, 'medium', 'model-judgement', 'medium',"
            " ?, ?, ?, datetime('now'))",
            (f"f{check_id}{url}", run_id, f"EXP:{tool}", check_id, summary,
             json.dumps([f"https://goldenplumbing.test{url}"]),
             f"fp{check_id}{url}"))

    def report(tool):
        runs.store_expert_report(conn, run_id, tool,
                                 {"model": "m", "report": "r", "tokens": 1})
    return conn, run_id, raise_finding, report


def test_a_contract_briefs_sweep_corroboration_is_attributed_to_the_brief(tmp_path):
    """Item 137 (brief v18 step AZ). A contract brief that corroborates a sweep
    check stores the finding under the sweep's own dimension (`TEC/sitemap-
    invalid`) with `evidence.from_brief` naming the brief, not under `EXP:<tool>`
    — the Q-56 rule. `_raised_rows` must credit the brief for it anyway, and must
    credit each physical row EXACTLY ONCE: an `EXP:` row carries `from_brief`
    too, so a naive dimension-OR-from_brief union would count it twice.
    """
    from clauditseo.golden import _raised_rows

    conn = connect(tmp_path / "attr.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site = repo.create_site(conn, repo.create_client(conn, op, "G"),
                            "goldenplumbing.test")
    run_id = runs.create_run(conn, site, ["TEC"], "T2")

    def insert(dimension, check_id, evidence):
        conn.execute(
            "INSERT INTO findings (id, run_id, dimension, check_id, severity,"
            " source, confidence, summary, affected_urls, evidence, fingerprint,"
            " created_at) VALUES (?, ?, ?, ?, 'medium', 'model-judgement', 'medium',"
            " 's', '[]', ?, ?, datetime('now'))",
            (f"f{dimension}{check_id}", run_id, dimension, check_id,
             json.dumps(evidence) if evidence is not None else None,
             f"fp{dimension}{check_id}"))

    # A crawl corroboration under the sweep dimension; a crawl brief-only check
    # under EXP:crawl (which ALSO carries from_brief); and a pure sweep row the
    # brief did not produce.
    insert("TEC", "sitemap-invalid", {"from_brief": "crawl"})
    insert("EXP:crawl", "crawl-budget-waste", {"from_brief": "crawl"})
    insert("TEC", "robots-missing", None)
    conn.commit()

    rows = _raised_rows(conn, run_id)
    crawl_checks = sorted(r["check_id"] for r in rows.get("crawl", []))
    assert crawl_checks == ["crawl-budget-waste", "sitemap-invalid"], crawl_checks
    assert len(rows.get("crawl", [])) == 2, "a row was attributed more than once"
    # The pure sweep row belongs to no brief: it has no from_brief and is not
    # under EXP:, so it is not selected at all.
    assert "robots-missing" not in {r["check_id"] for rs in rows.values() for r in rs}
    conn.close()


def test_a_finding_on_the_right_page_counts_however_it_is_named(scored):
    """The point of the page label. The model called it
    `heading-structure-broken`; no label could have guessed that."""
    conn, run_id, raise_finding, report = scored
    report("onpage-hygiene")
    raise_finding("onpage-hygiene", "heading-structure-broken",
                  "The page opens with an h1 missing entirely.",
                  "/blocked-drains")
    conn.commit()
    out = score(conn, run_id, LABELS)
    assert "/blocked-drains[h1]" in out["tools"]["onpage-hygiene"]["caught"]


def test_a_different_problem_on_the_same_page_is_not_a_hit(scored):
    """Otherwise any finding anywhere on the page scores, and the label
    measures presence rather than detection."""
    conn, run_id, raise_finding, report = scored
    report("onpage-hygiene")
    raise_finding("onpage-hygiene", "image-alt-missing",
                  "Two images on this page have no alt text.",
                  "/blocked-drains")
    conn.commit()
    out = score(conn, run_id, LABELS)
    tool = out["tools"]["onpage-hygiene"]
    assert "/blocked-drains[h1]" in tool["missed"]
    assert "image-alt-missing" in tool["unlabelled_raised"]


def test_raising_a_trap_counts_against_the_brief(scored):
    """A brief that flags everything scores full marks on catch rate and is
    useless. The traps are what stop that."""
    conn, run_id, raise_finding, report = scored
    report("onpage-hygiene")
    raise_finding("onpage-hygiene", "thin-content",
                  "This page is thin and should be expanded.", "/contact")
    conn.commit()
    out = score(conn, run_id, LABELS)
    assert "/contact[thin]" in out["tools"]["onpage-hygiene"]["false_positives"]
    assert out["total_false_positives"] >= 1


def test_a_page_label_miss_says_the_brief_named_no_such_page(scored):
    """Q-20's amendment, first kind. The brief raised something for this tool
    and none of it was on the labelled page — an honest miss the brief
    earned, and the rate is already saying so."""
    conn, run_id, raise_finding, report = scored
    report("mobile-viewport")
    raise_finding("mobile-viewport", "viewport-missing",
                  "No viewport meta tag present in served HTML.", "/contact")
    conn.commit()
    tool = score(conn, run_id, LABELS)["tools"]["mobile-viewport"]

    assert tool["missed"] == ["/about[viewport]"]
    why = tool["missed_because"]["/about[viewport]"]
    assert "no finding named /about" in why
    assert "none on that page" in why


def test_a_page_label_miss_says_when_the_words_and_not_the_finding_failed(
        scored):
    """Q-20's amendment, second kind, and the reason page labels were
    affordable at all.

    A page label is sharper than a site-scoped one and degrades to a false
    negative: on the day a brief reports the same defect without naming the
    URL — or names it and words it differently — the label stops matching and
    reads as a clean miss. `hreflang`'s trap comment records that failure
    costing eight raised findings scored as a perfect zero. The operator
    accepted that cost on the condition that a miss names its own reason, so
    a miss where a finding DID name the page is reported as the label
    drifting from the brief's vocabulary and not as the model missing it.

    It is also carried out of the terminal: this is the class the register
    row has to name, or a later reader comparing two rates compares one
    model against another model's label set."""
    conn, run_id, raise_finding, report = scored
    report("mobile-viewport")
    raise_finding("mobile-viewport", "head-markup-unavailable",
                  "Injection source and platform stack not supplied.",
                  "/about")
    conn.commit()
    out = score(conn, run_id, LABELS)
    tool = out["tools"]["mobile-viewport"]

    assert tool["missed"] == ["/about[viewport]"]
    why = tool["missed_because"]["/about[viewport]"]
    assert "named /about" in why, "the page WAS named; say so"
    assert "none carried viewport" in why
    assert "head-markup-unavailable" in why, "name the finding to look at"
    # Separated from the honest kind, so the two never read the same.
    assert "no finding named" not in why
    assert out["labels_missed_on_a_named_page"] == [
        "mobile-viewport:/about[viewport]"]


def test_a_site_scoped_miss_says_it_read_no_url(scored):
    """The trap kind. `hreflang` stays site-scoped because that brief really
    does raise with an empty `affected_urls`, and its misses must not be
    explained as if a page had been looked for."""
    from clauditseo.golden import _miss_reason

    kind, why = _miss_reason({"tool": "hreflang", "mentions": ["hreflang"]},
                             [{"check_id": "x", "summary": "y", "urls": []}])
    assert kind == "site-words"
    assert "site-scoped label" in why and "hreflang" in why


def test_a_brief_that_did_not_run_is_not_scored_as_a_miss(scored):
    """It has not missed anything; scoring it would punish the operator's
    tool choice rather than the model."""
    conn, run_id, _raise, _report = scored
    conn.commit()
    out = score(conn, run_id, LABELS)
    assert out["tools"]["onpage-hygiene"]["scored"] is False


def test_an_exact_code_label_still_works(scored):
    """Where a brief does emit a fixed vocabulary, the old label kind is
    still the sharper instrument."""
    conn, run_id, raise_finding, report = scored
    report("crawl")
    raise_finding("crawl", "sitemap-coverage", "3 of 6 pages listed.",
                  "/sitemap.xml")
    conn.commit()
    out = score(conn, run_id, {"expected": [
        {"tool": "crawl", "code": "sitemap-coverage"}]})
    assert out["tools"]["crawl"]["caught"] == ["sitemap-coverage"]
    assert out["overall_catch_rate"] == 1.0
