"""URL shape analysis (brief v19 step BB): the deterministic facts about a
URL — its characters, separators, case, depth, length and slug — and the two
site-level tables the URLs & parameters part reads: the pattern table and the
parameter inventory.

Every fact here is derived from strings the crawl already holds (reached page
URLs and the unstripped `href` on each link), so nothing new is stored: the
sweep emitters (`tec._url_checks`), the "now" payload (`runs.urls_now_payload`)
and the brief context (`expert._urls_context`) all read one derivation and
cannot disagree about what the URL space looks like. A leaf module — stdlib
only — so any of those three may import it without a cycle.

Two subtleties the crawler forces, and the reason the parameter inventory is
built from `href` and not from the reached URL set:

- `crawl.normalise_url` strips the tracking keys (`utm_*`, `gclid`, the
  `gad_*`/`gbraid` family) from every crawl identity, so a `utm_source`
  variant is never a distinct fetched page. Reading parameters off the reached
  URLs would therefore never see the very keys the part exists to classify.
  The unstripped `href` in `link_details` keeps them, which is the same source
  `internal-link-tracking-params` reads.
- `normalise_url` preserves the trailing slash and the path case (they can
  address different content), so `/x` and `/x/` can both be reached — which is
  what lets `url-trailing-slash-mixed` see a genuine both-forms duplicate.
"""

from __future__ import annotations

import re
from collections import Counter
from urllib.parse import parse_qsl, unquote, urlsplit

#: Thresholds the sweep applies, overridden per site by the record's fields
#: (`url_max_chars` etc.). Kept here beside the checks that read them so the
#: default and the check that enforces it live in one file.
DEFAULT_URL_MAX_CHARS = 75
DEFAULT_SLUG_MAX_WORDS = 6
DEFAULT_MAX_DEPTH = 3
DEFAULT_RENAME_INLINK_CAP = 20

#: Percent-encoded punctuation the sweep flags: quotes, brackets, braces,
#: angle brackets, comma, pipe, backtick, caret. `%20` (a space) is a
#: *separator* and has its own check, so it is deliberately not here.
_BAD_ENCODED = {"%22", "%27", "%28", "%29", "%5B", "%5D", "%2C", "%7B", "%7D",
                "%3C", "%3E", "%7C", "%60", "%5E"}
_PERCENT = re.compile(r"%[0-9A-Fa-f]{2}")
#: A camelCase seam: a lower/digit followed by an upper letter, joining words.
_CAMEL = re.compile(r"[a-z0-9][A-Z]")
#: A "word" for repeated-token and descriptive-slug purposes: three or more
#: letters. Shorter runs (`of`, `to`, a trailing `s`) are not tokens whose
#: repetition means anything.
_WORD = re.compile(r"[A-Za-z]{3,}")


def _segments(path: str) -> list[str]:
    """The non-empty path segments. `/` is zero segments (depth 0); a trailing
    slash never adds one."""
    return [s for s in (path or "").split("/") if s]


def slug_of(path: str) -> str:
    """The last path segment — the part a rename would change. Empty for the
    root."""
    segs = _segments(path)
    return segs[-1] if segs else ""


def _words(text: str) -> list[str]:
    return _WORD.findall(text or "")


def analyse_url(url: str) -> dict:
    """The per-URL free-check facts, all from the string. `path` keeps its
    exact case and encoding — every flag is about the URL as served, so a
    lower-cased copy would hide the finding."""
    parts = urlsplit(url)
    path = parts.path or "/"
    segs = _segments(path)
    slug = segs[-1] if segs else ""
    query_keys = [k for k, _ in parse_qsl(parts.query, keep_blank_values=True)]

    percent = _PERCENT.findall(path)
    # Separators in the slug: underscore, an encoded space, a plus, or a
    # camelCase seam. `%20` is looked for in the raw slug; a real space, if the
    # markup left one unencoded, counts too.
    slug_has_space = "%20" in slug or "+" in slug or " " in slug
    separator = ("_" in slug or slug_has_space or bool(_CAMEL.search(slug)))

    slug_words = slug.replace("_", "-").split("-") if slug else []
    slug_words = [w for w in slug_words if w]

    # id-only: a slug carrying no real word — pure digits, or a long hash.
    id_only = bool(slug) and not _WORD.search(slug)

    # repeated tokens: one word appearing in two different segments (the
    # /services/plumbing-services/plumbing case), lower-cased so `Plumbing`
    # and `plumbing` are the same token.
    seg_words = [set(w.lower() for w in _words(s)) for s in segs]
    tally: Counter = Counter()
    for ws in seg_words:
        tally.update(ws)
    repeated = sorted(w for w, n in tally.items() if n >= 2)

    return {
        "url": url,
        "path": path,
        "segments": segs,
        "depth": len(segs),
        "slug": slug,
        "slug_word_count": len(slug_words),
        "path_length": len(path),
        "query_keys": query_keys,
        "uppercase": any(c.isupper() for c in path)
        or any(any(c.isupper() for c in k) for k in query_keys),
        "non_ascii": any(ord(c) > 127 for c in path),
        "separator": separator,
        "encoded_chars": sorted({m.upper() for m in percent} & _BAD_ENCODED),
        "id_only": id_only,
        "repeated_tokens": repeated,
    }


_DATE_YYYY = re.compile(r"^\d{4}$")
_DATE_NN = re.compile(r"^\d{1,2}$")


def derive_pattern(path: str) -> str:
    """The template a path belongs to: the last segment replaced with
    `<slug>`, and a date run (a four-digit year and the one or two numeric
    segments after it) replaced with `YYYY`/`MM`/`DD`. The brief's literal
    rule (v19 step BB) — only the last segment and date segments move, every
    other segment is kept as written, so `/services/plumbing/` and
    `/services/electrical/` are one template and `/blog/2024/03/15/a-post/`
    reads as `/blog/YYYY/MM/DD/<slug>/`.

    The trailing slash is preserved: it is part of the convention the part
    reports, so `/a/` and `/a` are different templates on purpose.
    """
    segs = _segments(path)
    if not segs:
        return "/"
    trailing = path.endswith("/")

    # Date run: the first four-digit segment, then up to two numeric segments.
    out = list(segs)
    for i, seg in enumerate(out):
        if _DATE_YYYY.match(seg):
            out[i] = "YYYY"
            if i + 1 < len(out) and _DATE_NN.match(out[i + 1]):
                out[i + 1] = "MM"
                if i + 2 < len(out) and _DATE_NN.match(out[i + 2]):
                    out[i + 2] = "DD"
            break

    # Last segment -> <slug>, unless the last segment is itself a date token
    # just assigned (a dateless-slug archive URL like /blog/2024/03/).
    if out[-1] not in ("YYYY", "MM", "DD"):
        out[-1] = "<slug>"

    rendered = "/" + "/".join(out)
    return rendered + "/" if trailing else rendered


def pattern_table(urls) -> list[dict]:
    """The site's path templates with a count and depth each, deepest-and-
    biggest concerns first is the reader's job; this returns them by count
    descending, then template, so the derivation is stable. `note` is left to
    the caller/brief — the table here is the fact, not the judgement."""
    seen: Counter = Counter()
    depth: dict[str, int] = {}
    for u in urls:
        path = urlsplit(u).path or "/"
        pat = derive_pattern(path)
        seen[pat] += 1
        depth[pat] = len(_segments(path))
    rows = [{"pattern": pat, "count": n, "depth": depth[pat]}
            for pat, n in seen.items()]
    rows.sort(key=lambda r: (-r["count"], r["pattern"]))
    return rows


def _query_keys(href: str) -> list[str]:
    try:
        return [k for k, _ in parse_qsl(urlsplit(href).query, keep_blank_values=True)]
    except ValueError:
        return []


def parameter_inventory(hrefs, canonical_present) -> list[dict]:
    """The query keys the crawl saw, each with how many distinct URLs carried
    it and how many of those carry a canonical.

    `hrefs` is every link spelling as the markup wrote it (the unstripped
    `href` on each `link_details` entry) — read here, not the reached URL set,
    because `normalise_url` strips the tracking keys and the reached set would
    never show them (module docstring). `canonical_present` is a callable
    `variant_url -> bool`, so this module stays free of the canonical model:
    the caller passes a lookup over Indexability's canonical map, and a key
    whose variants were never fetched (every `utm_*` one) reads as zero.

    `class` is left None here; the site record's `parameter_rules` and the
    brief fill it. The inventory is the fact — key, reach, whether the
    duplicate is already owned by a canonical.
    """
    per_key: dict[str, set] = {}
    for href in hrefs:
        for key in _query_keys(href):
            per_key.setdefault(key, set()).add(href)
    rows = []
    for key, urls in per_key.items():
        present = sum(1 for u in urls if canonical_present(u))
        rows.append({"key": key, "seen": len(urls),
                     "canonical_present": present, "variants": len(urls)})
    rows.sort(key=lambda r: (-r["seen"], r["key"]))
    return rows


def classify(key: str, parameter_rules) -> str | None:
    """The class the site record gives a parameter key, or None when the key
    is unclassified. `parameter_rules` is the record's list of `{key, class}`
    (or a dict `key -> class`); an empty record leaves every key unclassified,
    which is what makes the sweep raise `url-parameter-unclassified` and the
    brief propose a class."""
    if not parameter_rules:
        return None
    if isinstance(parameter_rules, dict):
        return parameter_rules.get(key)
    for rule in parameter_rules:
        if isinstance(rule, dict) and rule.get("key") == key:
            return rule.get("class") or rule.get("cls")
    return None
