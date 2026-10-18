"""Fixture site with planted TEC and ONP defects, plus the manifest of what a
correct engine must find. Gate G2 asserts every manifest entry is produced
with the expected severity."""

from __future__ import annotations

GOOD_DESC = "A page about reliable plumbing in Melbourne with helpful advice."
DUP_DESC = "The same description reused on two different pages of this site."


def _html(title: str | None, desc: str | None, body: str,
          viewport: bool = True, canonical: str | None = "self",
          robots_meta: str | None = None) -> str:
    head = []
    if title is not None:
        head.append(f"<title>{title}</title>")
    if desc is not None:
        head.append(f'<meta name="description" content="{desc}">')
    if viewport:
        head.append('<meta name="viewport" content="width=device-width, initial-scale=1">')
    if robots_meta:
        head.append(f'<meta name="robots" content="{robots_meta}">')
    if canonical == "self":
        pass  # added per-route below, needs absolute-ish path
    elif canonical:
        head.append(f'<link rel="canonical" href="{canonical}">')
    return f"<html><head>{''.join(head)}</head><body>{body}</body></html>"


def routes() -> dict[str, tuple[int, dict, str]]:
    sitemap = ('<?xml version="1.0"?>'
               '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
               "<url><loc>{base}/</loc></url>"
               "<url><loc>{base}/dup-a</loc></url>"
               "<url><loc>{base}/ghost</loc></url>"
               "</urlset>")
    links = "".join(f'<a href="{p}">{p}</a>' for p in
                    ["/dup-a", "/dup-b", "/no-title", "/bad-headings", "/no-h1",
                     "/no-alt", "/canonical-off", "/bad-jsonld", "/no-viewport",
                     "/noindex", "/missing", "/chain"])
    good_jsonld = ('<script type="application/ld+json">'
                   '{"@context": "https://schema.org", "@type": "LocalBusiness",'
                   ' "name": "Acme Fixture"}</script>')
    bad_jsonld = ('<script type="application/ld+json">'
                  '{"@context": "https://schema.org", "@type": "LocalBusiness",</script>')

    return {
        "/robots.txt": (200, {"Content-Type": "text/plain"}, "User-agent: *\nAllow: /\n"),
        "/sitemap.xml": (200, {"Content-Type": "application/xml"}, sitemap),
        "/": (200, {}, _html(
            "Acme Fixture Home — Plumbing Advice", GOOD_DESC,
            f"<h1>Welcome</h1><h2>Section</h2><img src='/pic.png' alt='A pipe'>"
            f"{links}{good_jsonld}",
            canonical="/")),
        "/dup-a": (200, {}, _html("Duplicate Title Page", DUP_DESC,
                                  "<h1>Alpha</h1>", canonical="/dup-a")),
        "/dup-b": (200, {}, _html("Duplicate Title Page", DUP_DESC,
                                  "<h1>Beta</h1>", canonical="/dup-b")),
        "/no-title": (200, {}, _html(None, GOOD_DESC + " Variant for the untitled page.",
                                     "<h1>Untitled</h1>", canonical=None)),
        "/bad-headings": (200, {}, _html("Heading Hierarchy Fixture Page", "Headings gone wrong on purpose.",
                                         "<h1>One</h1><h1>Two</h1><h2>Sub</h2><h4>Skip</h4>",
                                         canonical="/bad-headings")),
        "/no-h1": (200, {}, _html("No H1 Fixture Page Title Here", None,
                                  "<h2>Straight to two</h2>", canonical="/no-h1")),
        "/no-alt": (200, {}, _html("Image Alt Coverage Fixture", "Images with and without alt text.",
                                   "<h1>Pics</h1><img src='/a.png' alt='Described'>"
                                   "<img src='/b.png'>", canonical="/no-alt")),
        "/canonical-off": (200, {}, _html("Canonical Mismatch Fixture", "Canonical points elsewhere.",
                                          "<h1>Off</h1>", canonical="/somewhere-else")),
        "/bad-jsonld": (200, {}, _html("Broken Structured Data Page", "JSON-LD that will not parse.",
                                       f"<h1>Schema</h1>{bad_jsonld}", canonical="/bad-jsonld")),
        "/no-viewport": (200, {}, _html("Viewport Missing Fixture Page", "No viewport meta here.",
                                        "<h1>Desktop only</h1>", viewport=False,
                                        canonical="/no-viewport")),
        "/noindex": (200, {}, _html("Noindexed Fixture Page Title", "This page asks not to be indexed.",
                                    "<h1>Hidden</h1>", canonical="/noindex",
                                    robots_meta="noindex, nofollow")),
        # /missing intentionally absent -> 404 from the fixture server
        "/chain": (301, {"Location": "/chain2"}, ""),
        "/chain2": (301, {"Location": "/final"}, ""),
        "/final": (200, {}, _html("Redirect Chain Landing Page", "Landed after two hops.",
                                  "<h1>Final</h1>", canonical="/final")),
    }


# (dimension, check_id, subject, severity) — subjects as the modules normalise them.
MANIFEST: list[tuple[str, str, str, str]] = [
    # `TEC/not-https` and `TEC/security-headers` were planted here until item
    # 143 step BD moved Security & transport to SEC; this manifest is audited
    # over TEC and ONP, and SEC's own rows are planted in
    # `test_security_is_its_own_dimension.py`.
    # The sitemap declares /, /dup-a and /ghost while the site serves a dozen
    # pages, so item 137 (brief v18 step AZ) splits the old single coverage row
    # in two: /ghost is declared but never reached (`unreachable`), and the many
    # reached pages the sitemap omits are `sitemap-coverage` (now the reverse
    # sense — reached pages absent from the sitemap, MEDIUM, site-scoped).
    ("TEC", "unreachable", "unreachable", "medium"),
    ("TEC", "sitemap-coverage", "site", "medium"),
    ("TEC", "http-status-error", "/missing", "high"),
    ("TEC", "redirect-chain", "/chain", "medium"),
    # Item 147 (brief v20): `mobile-viewport` is `viewport-missing` and HIGH —
    # a page with no viewport tag does not render responsively at all, which
    # was never a MEDIUM.
    ("TEC", "viewport-missing", "/no-viewport", "high"),
    # /noindex is reached, carries a noindex directive, is linked from only the
    # home page (one inlink) and is not in the sitemap — so under the item-137
    # split of noindex-page (brief v18 step BA) it fires NEITHER noindex-linked
    # (needs >= 3 inlinks) nor noindex-in-sitemap. That is the split working: a
    # stray noindex page nobody points at was the false HIGH the old check
    # raised. The two new checks are gate-tested in
    # test_the_noindex_split.py, which plants a linked one.
    ("ONP", "title-missing", "/no-title", "high"),
    # One row per member page since brief v11 step AH: the subject is the
    # page, and the shared string is the row's `group`.
    ("ONP", "title-duplicate", "/dup-a", "medium"),
    ("ONP", "meta-desc-duplicate", "/dup-a", "low"),
    ("ONP", "meta-desc-missing", "/no-h1", "medium"),
    ("ONP", "h1-missing", "/no-h1", "medium"),
    ("ONP", "h1-multiple", "/bad-headings", "low"),
    ("ONP", "heading-skip", "/bad-headings", "medium"),   # raised at brief v11 step AI
    ("ONP", "img-alt-missing", "/no-alt", "medium"),
    ("ONP", "canonical-missing", "/no-title", "low"),
    ("ONP", "canonical-mismatch", "/canonical-off", "medium"),
    ("ONP", "jsonld-invalid", "/bad-jsonld", "medium"),
]


def routes_with_base(base_url: str) -> dict[str, tuple[int, dict, str]]:
    """Substitute the fixture server's real origin into the sitemap."""
    out = {}
    for path, (status, headers, body) in routes().items():
        out[path] = (status, headers, body.replace("{base}", base_url))
    return out
