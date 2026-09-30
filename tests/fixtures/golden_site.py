"""A site whose defects are true by construction.

The golden harness has always been able to score a brief; what it lacked was
anything to score against, because the labels for a real site are a judgement
only a human can make. This fixture sidesteps that: every defect below is
planted deliberately, so the label is not an opinion about the site — it is a
statement about what was written into it.

What this measures, and what it does not. It measures whether a brief finds
problems that are definitely present and stays quiet about ones that are
definitely absent. That is a floor, not a ceiling: a fixture is small, tidy
and unambiguous, and passing here does not establish that a brief is right
about a real client's site. It does establish that a model change did not
break the basics, and it makes "does the deep tier earn its price" a question
with a number attached.

The traps matter as much as the defects. A brief that raises everything scores
perfectly on catch rate and is useless, so the site deliberately does several
things RIGHT in ways a careless brief tends to flag anyway — a single-locale
site with no hreflang, a deliberately short contact page, a canonical that is
correct, a robots.txt with nothing disallowed at all.
"""

from __future__ import annotations

HOST = "goldenplumbing.test"

#: Real prose, because a brief judging thinness on a page of lorem is judging
#: the fixture rather than the site.
GOOD = (
    "Blocked drains are the most common call-out we take in winter, and the "
    "cause is almost always the same: tree roots finding a hairline crack in "
    "clay pipe. We run a camera down the line before quoting, because the "
    "difference between a root cut and a full relay is several thousand "
    "dollars and you should not have to take our word for which one you "
    "need. The camera footage is yours to keep. If the pipe can be relined "
    "rather than dug up we will say so, even though relining is the cheaper "
    "job for us to sell. Our licence number appears on every quote and you "
    "are welcome to check it against the state register before we start. ")

NAV = ('<nav><a href="/">Home</a><a href="/services">Services</a>'
       '<a href="/blocked-drains">Blocked drains</a>'
       '<a href="/hot-water">Hot water</a><a href="/about">About</a>'
       '<a href="/contact">Contact</a></nav>')


#: What a correct viewport declaration looks like, in one place so the five
#: pages that carry it are byte-identical and the sixth's absence is the only
#: difference between them.
VIEWPORT = '<meta name="viewport" content="width=device-width, initial-scale=1">'


def _page(title: str, desc: str, body: str, *, canonical: str = "",
          extra_head: str = "", viewport: bool = True) -> str:
    head = f"<title>{title}</title>"
    if viewport:
        head += VIEWPORT
    if desc:
        head += f'<meta name="description" content="{desc}">'
    if canonical:
        head += f'<link rel="canonical" href="https://{HOST}{canonical}">'
    head += extra_head
    return (f"<html lang=en><head>{head}</head><body>{NAV}"
            f"<main>{body}</main>"
            '<footer>Golden Plumbing · 14 Rose Street, Fitzroy VIC 3065 · '
            "(03) 9417 5500</footer></body></html>")


def routes() -> dict:
    r: dict = {
        # CORRECT, and a trap: `Allow: /` and not one Disallow line anywhere,
        # so a finding claiming any URL here is robots-blocked is wrong by
        # construction. Adding a Disallow would make that finding correct and
        # turn the trap into the opposite of what it claims.
        "/robots.txt": (200, {"Content-Type": "text/plain"},
                        f"User-agent: *\nAllow: /\n"
                        f"Sitemap: https://{HOST}/sitemap.xml\n"),
        # PLANTED: the sitemap lists three pages and omits /hot-water and
        # /blocked-drains, which are linked from every page in the nav.
        "/sitemap.xml": (200, {"Content-Type": "application/xml"},
                         '<?xml version="1.0" encoding="UTF-8"?>'
                         '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                         + "".join(f"<url><loc>https://{HOST}{p}</loc></url>"
                                   for p in ("/", "/services", "/about"))
                         + "</urlset>"),
    }

    # CORRECT, and a trap: a strong home page with a right canonical.
    r["/"] = (200, {}, _page(
        "Golden Plumbing — licensed plumbers in Fitzroy, Melbourne",
        "Licensed Melbourne plumbers for blocked drains, hot water and "
        "emergency repairs. Camera inspection before every quote.",
        f"<h1>Licensed plumbers in Fitzroy</h1><p>{GOOD * 2}</p>"
        "<h2>What we do</h2><p>" + GOOD + "</p>", canonical="/"))

    # PLANTED: a meta robots noindex in the head of a page that is linked
    # from every nav and listed in the sitemap. It is the highest-stakes check
    # the product ships and it is true by construction — the directive is in
    # the head or it is not.
    r["/services"] = (200, {}, _page(
        "Plumbing services — Golden Plumbing, Fitzroy",
        "Blocked drains, hot water systems, burst pipes and gas fitting "
        "across Melbourne's inner north.",
        f"<h1>Our services</h1><p>{GOOD * 2}</p>", canonical="/services",
        extra_head='<meta name="robots" content="noindex">'))

    # PLANTED: no <h1> at all, and a title that repeats the home page's.
    r["/blocked-drains"] = (200, {}, _page(
        "Golden Plumbing — licensed plumbers in Fitzroy, Melbourne",
        "Blocked drain clearing with camera inspection.",
        f"<h2>Blocked drains</h2><p>{GOOD * 2}</p>",
        canonical="/blocked-drains"))

    # PLANTED: no meta description, and the title is a bare brand word.
    r["/hot-water"] = (200, {}, _page(
        "Hot water", "",
        f"<h1>Hot water systems</h1><p>{GOOD * 2}</p>",
        canonical="/hot-water"))

    # PLANTED three times, and the three are read by three different briefs
    # off three disjoint pieces of evidence — the body, the response headers
    # and the head — so no one of them can mask another.
    #
    # 1. The footer NAP says Rose Street and this page says Rosa Street with
    #    a different phone number. A local brief should catch the
    #    contradiction; it is the whole point of a NAP check.
    # 2. `X-Robots-Tag: noindex` in the response headers and NOWHERE in the
    #    body. This is the plant that earns its place: a brief that reads the
    #    HTML and not the headers misses it while looking like it handled
    #    indexability correctly. On a sitemap-listed page, so it is a
    #    contradiction rather than a deliberate exclusion.
    # 3. No viewport tag, where the other five pages carry an identical
    #    correct one. Planted as a divergence rather than as a site-wide
    #    absence: with all six missing it, a brief that says so once and a
    #    brief that says so six times both look correct and the label cannot
    #    tell them apart.
    r["/about"] = (200, {"X-Robots-Tag": "noindex"}, _page(
        "About Golden Plumbing — 30 years in Melbourne's inner north",
        "Family-run plumbing business serving Fitzroy and Collingwood "
        "since 1994.",
        f"<h1>About us</h1><p>{GOOD * 2}</p>"
        "<address>Golden Plumbing, 14 Rosa Street, Fitzroy VIC 3065. "
        "Phone (03) 9417 5511.</address>", canonical="/about",
        viewport=False))

    # CORRECT, and a trap: a contact page is *meant* to be short. A brief
    # that calls this thin content is wrong, and several do.
    r["/contact"] = (200, {}, _page(
        "Contact Golden Plumbing — Fitzroy, Melbourne",
        "Call (03) 9417 5500 or visit us at 14 Rose Street, Fitzroy.",
        "<h1>Contact us</h1><p>Call (03) 9417 5500. We answer between 7am "
        "and 6pm weekdays, and we run an after-hours line for emergencies. "
        "Our office is at 14 Rose Street, Fitzroy VIC 3065.</p>",
        canonical="/contact"))
    return r


#: The labels, written from the plant above rather than from a reading of the
#: output. `page` labels throughout, because expert briefs name their own
#: checks and scoring on the model's choice of words would measure vocabulary
#: rather than detection.
LABELS: dict = {
    "site": f"https://{HOST}/",
    "labelled_by": "fixture (true by construction)",
    #: Context a crawl cannot supply, for the briefs that ask for it. Without
    #: these a page-scoped brief has nothing to judge relevance against.
    "inputs": {"PAGE_TOPIC_OR_TARGET_QUERY": "emergency plumber Fitzroy",
               "BRAND_NAME": "Golden Plumbing"},
    "expected": [
        # The sitemap omits two pages that are linked from every page.
        # Site-scoped: the brief raised `sitemap-coverage` and
        # `sitemap-missing` and named no URL on either, so the first version
        # of this label scored a correct finding as a miss. The label was
        # wrong, not the brief.
        {"tool": "crawl", "mentions": ["sitemap"],
         "note": "lists 3 of 6 pages; /hot-water and /blocked-drains missing"},
        # /blocked-drains has no h1 and duplicates the home page title.
        {"tool": "onpage-hygiene", "page": "/blocked-drains",
         "mentions": ["h1"], "note": "h2 opens the page; no h1 exists"},
        {"tool": "onpage-hygiene", "page": "/blocked-drains",
         "mentions": ["title"], "note": "byte-identical title to the home page"},
        # /hot-water has no meta description.
        {"tool": "onpage-hygiene", "page": "/hot-water",
         "mentions": ["description"], "note": "meta description absent"},
        # The about page contradicts the footer on both street and phone.
        {"tool": "citations-nap", "page": "/about", "mentions": ["address"],
         "note": "Rosa Street vs Rose Street in the footer"},
        # Indexability, and both of these carry a page as well as their
        # words. They were site-scoped between 8a6d3da and Q-20 on the theory
        # that a brief declaring `scope: site` never names a URL. The paid
        # run `79a1fc02…` falsified it: `indexability` put BOTH plants in the
        # `affected_urls` of one `noindex-page` row, and `mobile-viewport`
        # put `/about` in its own. Scope is what a brief is asked to look at;
        # it says nothing about where the brief writes the URL down.
        #
        # The words stay, and they are what keeps the two apart. One
        # directive is a tag in the head and the other is a response header,
        # and those are different code paths in the brief as well as in the
        # fixture — so `meta` and `x-robots` are the two words that are true
        # by construction about which plant was found. Page AND words, so
        # neither a different problem on the page nor the same problem on
        # another page can score a hit.
        {"tool": "indexability", "page": "/services",
         "mentions": ["noindex", "meta"],
         "note": "meta robots noindex in the head of /services, a page linked "
                 "from every nav and listed in the sitemap"},
        # The one that earns its place. A brief that reads the HTML and not
        # the headers misses this while looking like it handled indexability
        # correctly, which is exactly the failure a golden set exists to
        # expose.
        {"tool": "indexability", "page": "/about",
         "mentions": ["noindex", "x-robots"],
         "note": "X-Robots-Tag: noindex on /about, in the response headers "
                 "and nowhere in the body"},
        # `/about` is the only page with no viewport tag; the other five
        # carry a byte-identical correct one. The page is a `page` and not a
        # word in `mentions`: the brief put `/about` in `affected_urls` and
        # said only "No viewport meta tag present in served HTML" in the
        # summary, so the words-only version scored 0.0 for a brief that was
        # exactly right. It also has to be the page rather than the word for
        # a second reason — `mobile-viewport-02`, a complaint that the raw
        # head markup was not supplied, carries "viewport" and all six URLs,
        # so a words-only label would score a catch off a data-completeness
        # note. Page and word together are what make this detection.
        {"tool": "mobile-viewport", "page": "/about", "mentions": ["viewport"],
         "note": "five pages declare width=device-width, initial-scale=1; "
                 "/about declares no viewport at all"},
    ],
    "known_absent": [
        # A brief that flags a deliberately short contact page is wrong.
        {"tool": "onpage-hygiene", "page": "/contact", "mentions": ["thin"],
         "note": "a contact page is meant to be short; flagging it is noise"},
        # Single-locale site. Raising hreflang here is a false positive.
        # Site-scoped deliberately: this brief's findings carry no URL, so a
        # page label silently never matched and the trap scored a clean zero
        # while the brief raised eight of them.
        {"tool": "hreflang", "mentions": ["hreflang"],
         "note": "one locale, no alternates — nothing to declare"},
        # Every page carries a correct self-canonical.
        {"tool": "crawl", "page": "/", "mentions": ["canonical"],
         "note": "self-canonical is present and correct on every page"},
        # robots.txt is `Allow: /` and nothing else, so no URL on this site
        # is robots-blocked and a finding saying one is has been invented.
        # It sits beside the two noindex plants on purpose: noindex and
        # robots-disallowed are the two things briefs most often confuse, and
        # a fixture that plants one without trapping the other cannot tell
        # detection from that confusion.
        {"tool": "indexability", "mentions": ["disallow"],
         "note": "robots.txt carries Allow: / and no Disallow line at all"},
    ],
}
