"""Pluggable external-data providers.

Every provider is optional: `available()` says whether it is configured, and
an unavailable provider is simply skipped. Modules consume providers through
the ProviderHub; when nothing is available for a capability, the module
reports the check as not-assessed — never an invented number.

Every value a provider returns carries source + confidence so the merge and
the reports can show where each number came from.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Protocol

#: Any URL in free text, up to the first whitespace or closing quote.
_URL = re.compile(r"(https?://[^\s'\"<>]+)")


def _redact_urls(text: str) -> str:
    """Drop the query string from every URL in a message.

    A provider URL is a credential carrier. `httpx.HTTPStatusError`
    stringifies to include the full request URL, and the PageSpeed call
    carries `key=<39-char Google API key>` — so recording the exception
    verbatim wrote a live key into `findings.evidence`, and from there into
    any whole-database backup. Two rows on run `93bdd2b2` are the measured
    instance, raised as CQ-59.

    The **host and path survive**, because which provider failed and on what
    call is the entire point of the record; only the query goes. Redacting the
    whole URL would have traded one silent failure for another.

    Applied at the point the string is built rather than where it is stored:
    the evidence dict is written by two modules and read by the renderer, the
    dashboard and every backup, and a redaction at any of those is a redaction
    the next writer can forget.
    """
    def strip(m: re.Match) -> str:
        url = m.group(1)
        head, sep, _query = url.partition("?")
        return head + ("?[redacted]" if sep else "")

    return _URL.sub(strip, text)


class NotConfigured(Exception):
    """Raised when a provider is asked to fetch without its key/config."""


@dataclass
class SourcedValue:
    value: Any
    source: str
    confidence: str  # high | medium | low


@dataclass
class BacklinkSnapshot:
    domain: str
    referring_domains: SourcedValue | None = None
    total_backlinks: SourcedValue | None = None
    domain_authority: SourcedValue | None = None
    anchors: dict[str, int] = field(default_factory=dict)  # anchor text -> count
    sources: list[str] = field(default_factory=list)


class BacklinkProvider(Protocol):
    name: str
    confidence: str

    def available(self) -> bool: ...
    def snapshot(self, domain: str) -> BacklinkSnapshot: ...


_CONF_RANK = {"high": 3, "medium": 2, "low": 1}


def merge_backlink_snapshots(snapshots: list[BacklinkSnapshot]) -> BacklinkSnapshot | None:
    """Confidence-weighted merge: for each field, keep the value from the
    highest-confidence source; anchors are summed per source-agnostic text.
    All contributing sources are recorded."""
    snapshots = [s for s in snapshots if s]
    if not snapshots:
        return None
    merged = BacklinkSnapshot(domain=snapshots[0].domain)
    for snap in snapshots:
        merged.sources.extend(s for s in snap.sources if s not in merged.sources)
        for name in ("referring_domains", "total_backlinks", "domain_authority"):
            candidate: SourcedValue | None = getattr(snap, name)
            current: SourcedValue | None = getattr(merged, name)
            if candidate is None:
                continue
            if current is None or _CONF_RANK.get(candidate.confidence, 0) > _CONF_RANK.get(current.confidence, 0):
                setattr(merged, name, candidate)
        for anchor, count in snap.anchors.items():
            merged.anchors[anchor] = merged.anchors.get(anchor, 0) + count
    return merged


class ProviderHub:
    """One object handed to modules via context['providers'].

    Built from settings by default; tests inject fakes. Missing keys mean
    empty provider lists, which modules must treat as not-assessed."""

    def __init__(self, backlink_providers: list[BacklinkProvider] | None = None,
                 cwv_providers: list | None = None,
                 search_providers: list | None = None):
        self.backlink_providers = backlink_providers or []
        self.cwv_providers = cwv_providers or []
        self.search_providers = search_providers or []
        #: Configured providers that were asked and did not answer, by name.
        #: Empty is the normal case and means every provider asked replied —
        #: not that none were asked.
        self.failures: dict[str, dict] = {}

    @classmethod
    def from_settings(cls, cfg) -> "ProviderHub":
        from .backlinks import DataForSEOBacklinks, MozBacklinks, OpenPageRank
        from .google import CruxField, PageSpeedLab

        return cls(
            backlink_providers=[p for p in (MozBacklinks(cfg), DataForSEOBacklinks(cfg),
                                            OpenPageRank(cfg)) if p.available()],
            cwv_providers=[p for p in (CruxField(cfg), PageSpeedLab(cfg)) if p.available()],
        )

    def backlink_snapshot(self, domain: str) -> BacklinkSnapshot | None:
        snaps = []
        for provider in self.backlink_providers:
            try:
                snaps.append(provider.snapshot(domain))
            except NotConfigured:
                continue
            except Exception as exc:   # noqa: BLE001
                # Degrade, never break the run — but remember why. Both
                # branches used to `continue` identically, which made "no key
                # configured" and "the key was rejected with a 403"
                # indistinguishable downstream. The audit then reported "No
                # backlink data provider is configured" for a site where one
                # was configured and answering 403, and Admin showed it green
                # because a key string existed. The operator had two
                # confident messages and neither was the truth.
                self.note_failure(provider, exc)
        return merge_backlink_snapshots(snaps)

    def cwv_metrics(self, url: str) -> dict[str, SourcedValue] | None:
        for provider in self.cwv_providers:
            try:
                metrics = provider.metrics(url)
                if metrics:
                    return metrics
            except NotConfigured:
                continue
            except Exception as exc:   # noqa: BLE001
                # `except (NotConfigured, Exception)` was just `except
                # Exception` with extra words, and it lost the reason the
                # same way the backlink path did.
                self.note_failure(provider, exc)
        return None

    @staticmethod
    def _redact(text: str) -> str:
        """The same, exposed for callers that build their own detail."""
        return _redact_urls(text)

    def note_failure(self, provider, exc: Exception) -> None:
        """Record that a configured provider was asked and did not answer.

        Kept on the hub rather than raised, because one dead provider must
        not stop an audit — but a failure nobody records is a failure the
        operator learns about by noticing a number is missing.
        """
        name = getattr(provider, "name", type(provider).__name__)
        detail = _redact_urls(str(exc).split("\n")[0])[:200]
        status = getattr(getattr(exc, "response", None), "status_code", None)
        self.failures[name] = {
            "provider": name, "error": type(exc).__name__,
            "detail": detail, "status": status,
        }

    def failure_note(self, only: set[str] | None = None) -> str:
        """One sentence naming what was asked and refused, for a finding.

        `only` scopes it to one dimension's own providers. Unscoped, this is
        hub-wide, which is right for a caller that owns the whole hub and
        wrong for a module: a CWV provider refusing made a *backlinks*
        finding claim a backlinks provider was refusing (UX-11).
        """
        failures = (self.failures if only is None else
                    {n: f for n, f in self.failures.items() if n in only})
        if not failures:
            return ""
        parts = []
        for f in failures.values():
            code = f" ({f['status']})" if f.get("status") else ""
            parts.append(f"{f['provider']}{code}")
        return ("The configured provider answered with an error: "
                + ", ".join(sorted(parts)) + ".")
