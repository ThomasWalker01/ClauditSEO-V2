"""The UA matrix: how the server treats each named crawler's user-agent string
(item 137, brief v18 step AZ, task 4).

Two claims are kept apart on purpose. A robots.txt rule is a *policy the client
set* — `robots.allow`/`disallow` is what the site asks a crawler to do. A 403,
429 or 999 to a crawler's UA string is *server-side filtering* — a CDN or WAF
deciding, often without the client's knowledge, and it is not what the real
crawler (from Google's or OpenAI's own IPs) necessarily experiences. So the
matrix records both columns and says, once, that the status column measures
UA-string treatment on paper, not a real crawler's visit.

`ua-server-refusal` — allowed at the rule, refused by the server — is HELD until
a `cdn_or_waf` is named on the site record, because the fix ("allowlist these
agents at the edge") has no address until the operator says where the edge is.
This module produces the evidence; the crawl brief judges the check, gated on
that field.
"""

from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass, field
from urllib.parse import urlsplit

from .fetch import Fetcher
from .robots import RobotsPolicy

#: Every agent the product names, as (robots token, user-agent string, class),
#: in one place that the automatic checks and the AI-surface analysis both read
#: (item 145 addendum, step BG). The token is what robots.txt matches; the UA
#: string is what the server sees. `None` marks a robots token that is a
#: directive, not a crawler (Google-Extended, Applebot-Extended): it is read in
#: robots.txt and never sent as a UA, because no such agent ever visits.
#:
#: Classes. `search` is organic search (Googlebot, Bingbot): not AI agents, and
#: the only class `ua-server-refusal` covers, but Googlebot feeds AI Overviews
#: and Bingbot feeds Copilot, so neither can be blocked to keep AI out. The four
#: AI classes, and what a block on each costs:
#:   dataset      feeds training corpora; no answer engine's behaviour shows it.
#:   training     vendor-declared model-improvement use.
#:   index        builds an answer engine's own search index ahead of time; a
#:                block removes the site from that engine's results.
#:   answer-time  fetches when a user asks; a block means the assistant could
#:                not look.
#: Cloudflare files Claude-User as an AI crawler; it is user-initiated and is
#: answer-time here.
AGENT_CLASSES = ("search", "dataset", "training", "index", "answer-time")
AI_AGENT_CLASSES = AGENT_CLASSES[1:]

#: What a block on an agent costs, per class, in the words a row states:
#: `ai-crawler-blocked` (robots.txt) and `edge-blocks-ai-ua` (the edge) both. Each
#: says what a block does within its own class and nothing about another's.
BLOCK_CONSEQUENCE = {
    "dataset": "it feeds training corpora, and no answer engine's behaviour shows the block",
    "training": "its vendor declares it for model improvement",
    "index": "it builds that answer engine's own search index, so the site is absent from its results",
    "answer-time": "it fetches when a user asks, so the assistant cannot look at this site",
}

#: Agents the addendum's section 4 rule leaves off the list, and the rule
#: itself. An agent is listed when it showed **demand** (field requests above
#: zero) or has **consequence** (class `index` or `answer-time`). Consequence is
#: read from the class alone: which engines a client's users use is not an
#: input, and no client can answer it today. The rule was applied once, against
#: the operator's Cloudflare per-crawler view of twenty22 (2026-09-14), to prune
#: a vendor taxonomy of 31 agents down to the list below — it is not a filter
#: over rows, and an agent on the list keeps its row whatever its class (channel
#: ruling 20260916-1410). These showed no requests and appear in no engine a
#: client can name, so they are named nowhere in client output.
PRUNED_AGENTS: tuple[str, ...] = (
    "Timpibot", "Novellum", "ProRata", "Terracotta", "Anchor", "TikTok Spider",
    "Google-CloudVertexBot", "ia_archiver",
)

#: The list, pruned by that rule. A blocked agent here is a finding whatever its
#: class: what a block costs is the class's own sentence in `BLOCK_CONSEQUENCE`,
#: and the reader weighs it. The seven dataset and training agents are on the
#: list because they showed demand on the acceptance site — 39 refused ClaudeBot
#: requests is an agent that keeps coming, and a block on it is a decision with
#: a cost.
UA_MATRIX_AGENTS: tuple[tuple[str, str | None, str], ...] = (
    ("Googlebot", "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)", "search"),
    ("Bingbot", "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)", "search"),
    ("CCBot", "CCBot/2.0 (https://commoncrawl.org/faq/)", "dataset"),
    ("GPTBot", "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; GPTBot/1.1; +https://openai.com/gptbot)", "training"),
    ("ClaudeBot", "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; ClaudeBot/1.0; +claudebot@anthropic.com)", "training"),
    ("Bytespider", "Mozilla/5.0 (Linux; Android 5.0) AppleWebKit/537.36 (KHTML, like Gecko) Mobile Safari/537.36 (compatible; Bytespider; spider-feedback@bytedance.com)", "training"),
    ("Meta-ExternalAgent", "meta-externalagent/1.1 (+https://developers.facebook.com/docs/sharing/webmasters/crawler)", "training"),
    ("Amazonbot", "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Amazonbot/0.1; +https://developer.amazon.com/support/amazonbot) Chrome/119.0.6045.214 Safari/537.36", "training"),
    ("PetalBot", "Mozilla/5.0 (compatible;PetalBot;+https://webmaster.petalsearch.com/site/petalbot)", "training"),
    ("Google-Extended", None, "training"),
    ("Applebot-Extended", None, "training"),
    ("OAI-SearchBot", "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; OAI-SearchBot/1.0; +https://openai.com/searchbot", "index"),
    ("Claude-SearchBot", "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Claude-SearchBot/1.0; +https://www.anthropic.com)", "index"),
    ("Applebot", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15 (Applebot/0.1; +http://www.apple.com/go/applebot)", "index"),
    ("PerplexityBot", "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; PerplexityBot/1.0; +https://perplexity.ai/perplexitybot)", "index"),
    ("ChatGPT-User", "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; ChatGPT-User/1.0; +https://openai.com/bot", "answer-time"),
    ("Claude-User", "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Claude-User/1.0; +Claude-User@anthropic.com)", "answer-time"),
    ("Perplexity-User", "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Perplexity-User/1.0; +https://perplexity.ai/perplexity-user)", "answer-time"),
    ("MistralAI-User", "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; MistralAI-User/1.0; +https://docs.mistral.ai/robots)", "answer-time"),
    ("DuckAssistBot", "DuckAssistBot/1.1; (+http://duckduckgo.com/duckassistbot.html)", "answer-time"),
    ("Meta-ExternalFetcher", "meta-externalfetcher/1.1 (+https://developers.facebook.com/docs/sharing/webmasters/crawler)", "answer-time"),
)

def agent_class(token: str) -> str | None:
    """The class of a named agent, or None for a token this product does not
    name (a stored row from before the list grew still resolves by name)."""
    return next((c for t, _ua, c in UA_MATRIX_AGENTS if t.lower() == (token or "").lower()), None)


def agents_of(*classes: str) -> tuple[str, ...]:
    """The robots tokens of every agent in the given classes, in list order."""
    return tuple(t for t, _ua, c in UA_MATRIX_AGENTS if c in classes)


#: Statuses that read as a server-side refusal rather than a normal response:
#: 403 forbidden, 429 rate-limited, and 999 (LinkedIn/edge "no thanks").
REFUSAL_STATUSES = (403, 429, 999)

#: Response headers that hint a CDN or WAF sits in front of the origin — the
#: "where is the rule" the operator confirms before `ua-server-refusal` opens.
#: Recorded verbatim from the home response so the brief can name the vendor.
CDN_HEADER_HINTS = ("server", "via", "cf-ray", "cf-cache-status", "x-cache",
                    "x-served-by", "x-sucuri-id", "x-akamai-transformed",
                    "x-amz-cf-id", "x-cdn", "fastly-debug-digest")

#: Headers kept beside the hints as the response's signature: what a refusal
#: looked like (Cloudflare's `cf-mitigated: challenge`, a `retry-after`), and
#: what was served, so an `edge-blocks-ai-ua` row can quote the response rather
#: than only its status (145 BG: status and retained headers per UA).
SIGNATURE_HEADERS = ("content-type", "content-length", "cf-mitigated",
                     "retry-after", "x-datadome", "x-sucuri-block",
                     "akamai-grn", "x-deny-reason")
RETAINED_HEADERS = CDN_HEADER_HINTS + SIGNATURE_HEADERS

#: How many probe pages beyond home each agent is fetched against. Bounded so
#: the whole matrix is at most (agents sent) * (1 + PROBE_PAGES) fetches.
PROBE_PAGES = 2

#: The agent whose bodies are fingerprinted for SEC/cloaking (item 143 step
#: BD). Cloaking serves Google something other than what a visitor gets, so
#: Googlebot's bodies are compared with the crawl's own fetch of the same URLs.
FINGERPRINT_AGENT = "Googlebot"

_TITLE = re.compile(r"<title[^>]*>(.*?)</title\s*>", re.I | re.S)
_TAGS = re.compile(r"<script\b.*?</script\s*>|<style\b.*?</style\s*>|<[^>]+>", re.I | re.S)
_LINK_HOST = re.compile(r"<a\b[^>]*\bhref\s*=\s*[\"']https?://([^/\"':?#]+)", re.I)


def fingerprint(html: str) -> dict:
    """What a cloaking comparison needs from a body, and nothing more: the
    title, the visible text length, and the hosts its links point to. Small
    enough to travel in the evidence snapshot, which keeps no page bodies."""
    html = html or ""
    t = _TITLE.search(html)
    text = re.sub(r"\s+", " ", _TAGS.sub(" ", html)).strip()
    return {"title": re.sub(r"\s+", " ", t.group(1)).strip()[:200] if t else "",
            "text_len": len(text),
            "link_hosts": sorted({h.lower() for h in _LINK_HOST.findall(html)})[:200]}


@dataclass
class UAMatrixRow:
    agent: str
    robots: str                                  # "allow" | "disallow"
    home_status: int | None = None
    probe_status: list[int | None] = field(default_factory=list)
    #: RETAINED_HEADERS present on the home response.
    headers: dict[str, str] = field(default_factory=dict)
    error: str | None = None
    #: url -> fingerprint(), on the FINGERPRINT_AGENT row only.
    bodies: dict[str, dict] = field(default_factory=dict)
    #: The agent's class (AGENT_CLASSES); None only on a hand-built row.
    agent_class: str | None = None
    #: False for a robots token that is never sent as a UA: its row carries the
    #: robots verdict and no status, which reads as not fetched, not as a pass.
    sent: bool = True
    #: Bytes of text body per response, home then probes. A 200 carrying a
    #: challenge page is a refusal a status column alone cannot see.
    home_body_len: int | None = None
    probe_body_len: list[int | None] = field(default_factory=list)
    #: RETAINED_HEADERS per probe response, in probe order.
    probe_headers: list[dict[str, str]] = field(default_factory=list)
    #: url -> `parity.document()` of each response this agent got: status,
    #: title, words, main-region hash and the rest, no body. What
    #: `AIS/ua-sensitive` compares with the crawl's own fetch (item 145 BG).
    docs: dict[str, dict] = field(default_factory=dict)

    @property
    def refusal_check(self) -> str:
        """Which check a refusal to this agent is (channel 20260915-0520): the
        search agents' is `TEC/ua-server-refusal`, held on `cdn_or_waf`; every
        other agent's is `AIS/edge-blocks-ai-ua`. One refusal, one row."""
        return "TEC/ua-server-refusal" if self.agent_class == "search" else "AIS/edge-blocks-ai-ua"

    @property
    def refused(self) -> bool:
        """Allowed at the rule, but the server answered a refusal status to at
        least one URL. The `ua-server-refusal` signal, before the HELD gate."""
        if self.robots != "allow":
            return False
        seen = [self.home_status, *self.probe_status]
        return any(s in REFUSAL_STATUSES for s in seen if s is not None)


def probe_urls(start_url: str, pages) -> list[str]:
    """Up to `PROBE_PAGES` reached, same-host HTML pages other than home, for
    the matrix's status columns. Same-host so a third party's 403 is not read as
    this site's, and reached so a URL that already 404s does not read as a
    refusal for every agent."""
    host = urlsplit(start_url).netloc.lower()
    home_path = (urlsplit(start_url).path or "/").rstrip("/") or "/"
    out: list[str] = []
    for p in pages:
        url = getattr(p, "url", None) or ""
        if getattr(p, "status", 0) != 200:
            continue
        if not str(getattr(p, "content_type", "")).startswith("text/html"):
            continue
        split = urlsplit(url)
        if split.netloc.lower() != host:
            continue
        if ((split.path or "/").rstrip("/") or "/") == home_path:
            continue
        out.append(url)
        if len(out) >= PROBE_PAGES:
            break
    return out


def _retained(result) -> dict[str, str]:
    return {h: result.headers[h] for h in RETAINED_HEADERS if result.headers.get(h)}


def _document(result) -> dict:
    from .parity import document
    try:
        return document(result)
    except Exception:  # a document the parser chokes on is not a crawl failure
        return {"status": result.status or None, "error": "unreadable"}


def _body_len(result) -> int | None:
    """Text body bytes, or None where nothing came back to measure."""
    if not result.status:
        return None
    return len((result.content or "").encode("utf-8"))


def build_ua_matrix(start_url: str, pages, policy: RobotsPolicy,
                    timeout_s: float, deadline: float,
                    delay_s: float = 0.0) -> list[dict]:
    """Fetch home and the probe pages as each named agent that has a UA,
    recording the robots verdict, the class, and per response the status, the
    retained headers and the body length. A robots-only token gets its verdict
    and no fetch.

    Returns plain dicts (not dataclasses) because this travels straight into the
    crawl evidence snapshot, which is JSON. Stops early on the wall-clock
    deadline rather than overrunning a crawl's budget on the matrix."""
    probes = probe_urls(start_url, pages)
    rows: list[dict] = []
    for token, ua, klass in UA_MATRIX_AGENTS:
        if time.monotonic() > deadline:
            break
        verdict = "allow" if policy.allows(start_url, token) else "disallow"
        row = UAMatrixRow(agent=token, robots=verdict, agent_class=klass,
                          sent=ua is not None)
        if ua is None:
            rows.append(asdict(row))
            continue
        with Fetcher(timeout_s, user_agent=ua) as fetcher:
            home = fetcher.fetch(start_url)
            keep = token == FINGERPRINT_AGENT
            if keep and home.status == 200:
                row.bodies[start_url] = fingerprint(home.content)
            row.home_status = home.status or None
            row.home_body_len = _body_len(home)
            row.docs[start_url] = _document(home)
            row.error = home.error
            row.headers = _retained(home)
            for u in probes:
                if time.monotonic() > deadline:
                    break
                if delay_s:
                    time.sleep(delay_s)
                got = fetcher.fetch(u)
                if keep and got.status == 200:
                    row.bodies[u] = fingerprint(got.content)
                row.probe_status.append(got.status or None)
                row.probe_body_len.append(_body_len(got))
                row.probe_headers.append(_retained(got))
                row.docs[u] = _document(got)
        rows.append(asdict(row))
        if delay_s:
            time.sleep(delay_s)
    return rows
