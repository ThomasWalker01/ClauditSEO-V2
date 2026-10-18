"""Fixture site with planted defects for PRF, CNT, OFP, LOC and AIS, plus the
manifest gate G3 asserts against. TEC/ONP noise findings are expected and
ignored — the manifest is a subset check."""

from __future__ import annotations

WORDS_60 = ("Our licensed team repairs burst pipes, blocked drains, leaking taps and "
            "failing hot water systems across the inner suburbs, arriving with parts "
            "stocked so most jobs finish in one visit. We quote before work begins, "
            "explain the cause plainly, guarantee the workmanship in writing and "
            "leave every kitchen, bathroom and laundry cleaner than we found it, "
            "seven days a week.")


def _page(title: str, desc: str, body: str, canonical: str,
          viewport: bool = True) -> str:
    head = (f"<title>{title}</title>"
            f'<meta name="description" content="{desc}">'
            f'<link rel="canonical" href="{canonical}">')
    if viewport:
        head += '<meta name="viewport" content="width=device-width, initial-scale=1">'
    return f"<html><head>{head}</head><body>{body}</body></html>"


def routes() -> dict[str, tuple[int, dict, str]]:
    home_body = (
        "<h1>Fixture Local Services</h1><h2>What we do</h2>"
        f"<p>{WORDS_60}</p><p>{WORDS_60.replace('Our', 'The').replace('We quote', 'They quote')}</p>"
        "<p>Call us on 03 9111 2222 for bookings.</p>"
        + "".join(f'<a href="{p}">{p}</a>' for p in
                  ["/contact", "/locations/melbourne", "/thin", "/copy-a", "/copy-b",
                   "/rambling", "/template", "/heavy", "/slow"])
    )
    rambling = " ".join(["therefore the outcome considered against every angle remains"] * 12)
    template_body = ("<div><div><div>" + "<div class='wrap outer inner pad'></div>" * 80
                     + "</div></div></div><p>Tiny bit of text here.</p>")
    thin_words = "A very short page about drains. " * 6            # ~42 words
    # A block shared by /copy-a and /copy-b ALONE. WORDS_60 is on five of the
    # ten pages, which makes it site template rather than a duplicated pair —
    # true of the fixture and now stated as `template-only-pages`. A
    # duplicate-content gate needs text that really is on just two pages, or
    # it is testing boilerplate detection under another name.
    PAIR_ONLY = (
        "Emergency after hours attendance is available across the northern "
        "suburbs with a fixed call out fee quoted before any work begins and "
        "no charge if we cannot resolve the fault on the first visit, which "
        "we confirm in writing along with the parts used and the warranty "
        "period that applies to the repair we carried out for you today. ")
    location_words = "We service Melbourne homes with care. " * 7  # ~49 words

    return {
        "/robots.txt": (200, {"Content-Type": "text/plain"},
                        "User-agent: *\nAllow: /\n\nUser-agent: GPTBot\nDisallow: /\n"),
        "/sitemap.xml": (200, {"Content-Type": "application/xml"},
                         '<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/'
                         'schemas/sitemap/0.9"><url><loc>{base}/</loc></url></urlset>'),
        "/": (200, {}, _page("Fixture Local Services Home", "A local services fixture site.",
                             home_body, "/")),
        "/contact": (200, {}, _page("Contact The Fixture Team", "How to reach the fixture team.",
                                    "<h1>Contact</h1><p>Ring 03 9111 3333 any time.</p>",
                                    "/contact")),
        "/locations/melbourne": (200, {}, _page(
            "Melbourne Service Area Page", "Fixture location page for Melbourne.",
            f"<h1>Melbourne</h1><p>{location_words}</p>", "/locations/melbourne")),
        "/thin": (200, {}, _page("Thin Content Fixture Page", "A deliberately thin page.",
                                 f"<h1>Drains</h1><p>{thin_words}</p>", "/thin")),
        "/copy-a": (200, {}, _page("Copy Alpha Fixture Page", "First of two identical pages.",
                                   f"<h1>Alpha</h1><p>{WORDS_60}</p><p>{PAIR_ONLY}</p>",
                                   "/copy-a")),
        "/copy-b": (200, {}, _page("Copy Beta Fixture Page", "Second of two identical pages.",
                                   f"<h1>Beta</h1><p>{WORDS_60}</p><p>{PAIR_ONLY}</p>",
                                   "/copy-b")),
        "/rambling": (200, {}, _page("Rambling Sentence Fixture Page", "Sentences that never end.",
                                     f"<h1>Rambling</h1><p>{rambling}. {rambling}. {rambling}.</p>",
                                     "/rambling")),
        "/template": (200, {}, _page("Template Heavy Fixture Page", "Markup far outweighing text.",
                                     f"<h1>Template</h1>{template_body}", "/template")),
        "/heavy": (200, {}, _page("Heavy Page Weight Fixture", "An oversized HTML document.",
                                  "<h1>Heavy</h1><div data-blob='" + "x" * 250_000 + "'></div>"
                                  f"<p>{WORDS_60}</p>", "/heavy")),
        "/slow": (200, {"X-Fixture-Delay": "1.3"},
                  _page("Slow Response Fixture Page", "This page answers slowly.",
                        f"<h1>Slow</h1><p>{WORDS_60}</p>", "/slow")),
    }


MANIFEST: list[tuple[str, str, str, str]] = [
    ("PRF", "cwv-not-assessed", "cwv", "info"),
    # `slow-response`, the HTML-bytes `page-weight` and `caching-headers` were
    # planted here and are retired (migration 0054). PRF's page-naming checks
    # are the trace's now, and this corpus takes no trace -- the fixture's
    # `/slow`, `/heavy` and no-cache routes are left in place because they are
    # a plausible site, not because anything still reads them.
    #
    # So PRF plants exactly one defect here, and it is a scope statement. If a
    # trace-fed corpus is ever wanted, it needs a renderer in the fixture,
    # which is a different decision (`conftest` sets CLAUDITSEO_TRACE_PERF=0).
    ("CNT", "thin-content", "/thin", "medium"),
    ("CNT", "duplicate-content", "/copy-a|/copy-b", "medium"),
    ("CNT", "readability-long-sentences", "/rambling", "low"),
    ("CNT", "low-text-ratio", "/template", "low"),
    ("OFP", "backlinks-not-assessed", "backlinks", "info"),
    ("LOC", "nap-inconsistent", "nap-phone", "medium"),
    ("LOC", "localbusiness-schema-missing", "localbusiness-schema", "medium"),
    ("LOC", "thin-location-page", "/locations/melbourne", "low"),
    ("TEC", "ai-crawler-blocked", "ai-crawler-access:GPTBot", "high"),  # one row per agent (145 BG)
    ("AIS", "llms-txt-missing", "llms-txt", "info"),
]


def routes_with_base(base_url: str) -> dict[str, tuple[int, dict, str]]:
    return {path: (status, headers, body.replace("{base}", base_url))
            for path, (status, headers, body) in routes().items()}
