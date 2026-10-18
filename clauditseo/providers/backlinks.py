"""Backlink / authority providers. Each degrades to unavailable without its
key. Network calls are best-effort with short timeouts; any failure means the
provider contributes nothing rather than breaking the run."""

from __future__ import annotations

import base64

import httpx

from clauditseo.config import Settings

from .base import BacklinkSnapshot, NotConfigured, SourcedValue

TIMEOUT = 20.0


#: OpenPageRank moved off domcop.com and rebuilt its API. The old host still
#: answers, which is the trap: it returns 403 "Invalid API key" to every
#: request, so a correct, current key looked like a rejected one and the
#: obvious reading — "the key is wrong" — was wrong. Nothing about the old
#: shape survived: different host, Bearer instead of a custom header, POST
#: instead of GET, and different field names in the reply.
OPR_ENDPOINT = "https://openpagerank.keywordseverywhere.com/v1/domains/bulk"


class OpenPageRank:
    """Free tier: authority score and referring domains.

    Keys are issued at openpagerank.keywordseverywhere.com and are prefixed
    `opr_live_`. A key from the old domcop service is not accepted here.
    """

    name = "openpagerank"
    confidence = "low"

    def __init__(self, cfg: Settings):
        self._key = cfg.openpagerank_key

    def available(self) -> bool:
        return bool(self._key)

    def snapshot(self, domain: str) -> BacklinkSnapshot:
        if not self.available():
            raise NotConfigured(self.name)
        resp = httpx.post(
            OPR_ENDPOINT,
            # History is a monthly series back to 2018 that nothing here reads.
            json={"domains": [domain], "include_history": False},
            headers={"Authorization": f"Bearer {self._key}"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        results = resp.json().get("results") or [{}]
        entry = results[0] if results else {}
        snap = BacklinkSnapshot(domain=domain, sources=[self.name])
        # `found` false means the domain is not in their index — a real
        # answer, and a different thing from the call having failed. Reading
        # the numbers anyway would report an authority of zero for a domain
        # they simply have nothing on.
        if not entry.get("found"):
            return snap
        if entry.get("open_page_rank") is not None:
            snap.domain_authority = SourcedValue(
                value=float(entry["open_page_rank"]) * 10,  # 0-10 -> 0-100
                source=self.name, confidence=self.confidence)
        # The old API could not answer this at all; the free tier now does.
        if entry.get("referring_domains") is not None:
            snap.referring_domains = SourcedValue(
                value=float(entry["referring_domains"]),
                source=self.name, confidence=self.confidence)
        return snap


class MozBacklinks:
    """Moz Links API (paid tier of a commercial index)."""

    name = "moz"
    confidence = "high"

    def __init__(self, cfg: Settings):
        self._token = cfg.moz_token

    def available(self) -> bool:
        return bool(self._token)

    def snapshot(self, domain: str) -> BacklinkSnapshot:
        if not self.available():
            raise NotConfigured(self.name)
        resp = httpx.post(
            "https://lsapi.seomoz.com/v2/url_metrics",
            json={"targets": [domain]},
            headers={"Authorization": f"Basic {self._token}"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        entry = (resp.json().get("results") or [{}])[0]
        snap = BacklinkSnapshot(domain=domain, sources=[self.name])
        if entry.get("root_domains_to_root_domain") is not None:
            snap.referring_domains = SourcedValue(
                value=int(entry["root_domains_to_root_domain"]),
                source=self.name, confidence=self.confidence)
        if entry.get("external_pages_to_root_domain") is not None:
            snap.total_backlinks = SourcedValue(
                value=int(entry["external_pages_to_root_domain"]),
                source=self.name, confidence=self.confidence)
        if entry.get("domain_authority") is not None:
            snap.domain_authority = SourcedValue(
                value=float(entry["domain_authority"]),
                source=self.name, confidence=self.confidence)
        return snap


class DataForSEOBacklinks:
    """DataForSEO backlinks summary (paid, per-call pricing)."""

    name = "dataforseo"
    confidence = "high"

    def __init__(self, cfg: Settings):
        self._login = cfg.dataforseo_login
        self._password = cfg.dataforseo_password

    def available(self) -> bool:
        return bool(self._login and self._password)

    def snapshot(self, domain: str) -> BacklinkSnapshot:
        if not self.available():
            raise NotConfigured(self.name)
        auth = base64.b64encode(f"{self._login}:{self._password}".encode()).decode()
        resp = httpx.post(
            "https://api.dataforseo.com/v3/backlinks/summary/live",
            json=[{"target": domain, "include_subdomains": True}],
            headers={"Authorization": f"Basic {auth}"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        tasks = resp.json().get("tasks") or []
        item = ((tasks[0].get("result") or [{}])[0]) if tasks else {}
        snap = BacklinkSnapshot(domain=domain, sources=[self.name])
        if item.get("referring_domains") is not None:
            snap.referring_domains = SourcedValue(
                value=int(item["referring_domains"]), source=self.name,
                confidence=self.confidence)
        if item.get("backlinks") is not None:
            snap.total_backlinks = SourcedValue(
                value=int(item["backlinks"]), source=self.name,
                confidence=self.confidence)
        return snap
