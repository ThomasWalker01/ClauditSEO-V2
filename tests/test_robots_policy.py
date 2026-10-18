"""RFC 9309 rule resolution, implemented in RobotsPolicy so politeness never
depends on the interpreter's robotparser vintage (older stdlibs resolve
first-match-wins, letting a broad Allow shadow a narrow Disallow)."""

from __future__ import annotations

from clauditseo.crawler.robots import RobotsPolicy

UA = "ClauditSEOBot/0.1"


def _policy(body: str, status: int = 200) -> RobotsPolicy:
    return RobotsPolicy("http://x.example/robots.txt", status, body)


def test_broad_allow_never_shadows_narrow_disallow():
    # The commonest real-world shape — and the one that breaks first-match
    # resolvers regardless of line order.
    p = _policy("User-agent: *\nAllow: /\nDisallow: /private/\n")
    assert p.allows("http://x.example/", UA)
    assert p.allows("http://x.example/public/page", UA)
    assert not p.allows("http://x.example/private/secret", UA)

    reversed_order = _policy("User-agent: *\nDisallow: /private/\nAllow: /\n")
    assert not reversed_order.allows("http://x.example/private/secret", UA)


def test_longest_match_wins_and_ties_go_to_allow():
    p = _policy("User-agent: *\nDisallow: /p\nAllow: /page\n")
    assert p.allows("http://x.example/page", UA)        # /page (5) beats /p (2)
    assert not p.allows("http://x.example/private", UA)  # only /p matches

    tie = _policy("User-agent: *\nDisallow: /dir\nAllow: /dir\n")
    assert tie.allows("http://x.example/dir/thing", UA)  # equal length -> Allow


def test_wildcards_and_dollar_anchor():
    p = _policy("User-agent: *\nDisallow: /*.pdf$\nDisallow: /tmp/*/draft\n")
    assert not p.allows("http://x.example/files/report.pdf", UA)
    assert p.allows("http://x.example/files/report.pdfx", UA)   # $ anchors
    assert not p.allows("http://x.example/tmp/a/draft", UA)
    assert p.allows("http://x.example/tmp/a/final", UA)


def test_most_specific_agent_group_applies():
    body = ("User-agent: *\nAllow: /\n\n"
            "User-agent: GPTBot\nDisallow: /\n")
    p = _policy(body)
    assert p.allows("http://x.example/page", UA)
    assert not p.allows("http://x.example/page", "GPTBot")
    assert not p.allows("http://x.example/", "GPTBot/1.0")


def test_empty_disallow_means_allow_all():
    p = _policy("User-agent: *\nDisallow:\n")
    assert p.allows("http://x.example/anything", UA)


def test_query_strings_are_matched():
    p = _policy("User-agent: *\nDisallow: /*?session=\n")
    assert not p.allows("http://x.example/page?session=abc", UA)
    assert p.allows("http://x.example/page", UA)


def test_percent_encoded_unreserved_octets_are_decoded_before_matching():
    # RFC 9309 §2.2.2: %76 is 'v' (unreserved) and must decode, so encoding
    # tricks cannot slip past a Disallow.
    p = _policy("User-agent: *\nAllow: /\nDisallow: /private/\n")
    assert not p.allows("http://x.example/pri%76ate/x", UA)
    assert not p.allows("http://x.example/%70rivate/secret", UA)
    # Reserved octets stay encoded: %2F is not a path separator.
    q = _policy("User-agent: *\nDisallow: /a/b\n")
    assert q.allows("http://x.example/a%2Fb", UA)
    # ...but retained encodings compare case-insensitively on both sides.
    r = _policy("User-agent: *\nDisallow: /a%2fb\n")
    assert not r.allows("http://x.example/a%2Fb", UA)


def test_5xx_robots_denies_everything():
    p = _policy("irrelevant", status=503)
    assert not p.allows("http://x.example/", UA)


def test_missing_robots_allows_everything():
    p = RobotsPolicy("http://x.example/robots.txt", 404, "")
    assert p.allows("http://x.example/anything", UA)


def test_sitemaps_still_collected():
    p = _policy("User-agent: *\nAllow: /\nSitemap: https://x.example/sm.xml\n")
    assert p.sitemaps == ["https://x.example/sm.xml"]
