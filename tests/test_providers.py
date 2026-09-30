"""Provider layer: confidence-weighted merge, graceful degradation, and the
OFP module consuming fake providers (no real network calls anywhere)."""

from __future__ import annotations

from clauditseo.config import Settings
from clauditseo.crawler.types import CrawlResult
from clauditseo.engine.types import Site, Tier
from clauditseo.modules.ofp import OffPageModule
from clauditseo.providers.backlinks import DataForSEOBacklinks, MozBacklinks, OpenPageRank
from clauditseo.providers.base import (BacklinkSnapshot, ProviderHub, SourcedValue,
                                      merge_backlink_snapshots)


class FakeProvider:
    def __init__(self, name, snap=None, fail=False):
        self.name = name
        self.confidence = "high"
        self._snap = snap
        self._fail = fail

    def available(self):
        return True

    def snapshot(self, domain):
        if self._fail:
            raise RuntimeError("provider exploded")
        return self._snap


def _snap(domain="x.example", rd=None, conf="low", source="a",
          anchors=None) -> BacklinkSnapshot:
    s = BacklinkSnapshot(domain=domain, sources=[source], anchors=anchors or {})
    if rd is not None:
        s.referring_domains = SourcedValue(value=rd, source=source, confidence=conf)
    return s


def test_merge_prefers_higher_confidence_and_records_all_sources():
    low = _snap(rd=500, conf="low", source="openpagerank")
    high = _snap(rd=120, conf="high", source="moz")
    merged = merge_backlink_snapshots([low, high])
    assert merged.referring_domains.value == 120
    assert merged.referring_domains.source == "moz"
    assert set(merged.sources) == {"openpagerank", "moz"}


def test_merge_sums_anchor_counts():
    a = _snap(source="a", anchors={"brand": 5, "cheap plumber": 3})
    b = _snap(source="b", anchors={"brand": 2})
    merged = merge_backlink_snapshots([a, b])
    assert merged.anchors == {"brand": 7, "cheap plumber": 3}


def test_hub_survives_a_broken_provider():
    good = FakeProvider("good", _snap(rd=50, conf="high", source="good"))
    bad = FakeProvider("bad", fail=True)
    hub = ProviderHub(backlink_providers=[bad, good])
    snap = hub.backlink_snapshot("x.example")
    assert snap and snap.referring_domains.value == 50


def test_unconfigured_real_providers_report_unavailable(monkeypatch):
    for var in ("CLAUDITSEO_MOZ_TOKEN", "CLAUDITSEO_OPENPAGERANK_KEY",
                "CLAUDITSEO_DATAFORSEO_LOGIN", "CLAUDITSEO_DATAFORSEO_PASSWORD"):
        monkeypatch.delenv(var, raising=False)
    cfg = Settings()
    assert not MozBacklinks(cfg).available()
    assert not OpenPageRank(cfg).available()
    assert not DataForSEOBacklinks(cfg).available()
    hub = ProviderHub.from_settings(cfg)
    assert hub.backlink_snapshot("x.example") is None


def _ofp_context(hub):
    return {"crawl": CrawlResult(start_url="https://x.example/", tier=Tier.T2),
            "site": Site(domain="x.example"), "providers": hub}


def test_ofp_flags_toxic_and_overoptimised_anchors():
    snap = _snap(rd=5, conf="high", source="moz",
                 anchors={"best casino bonus": 4, "cheap plumber melbourne": 8,
                          "brand": 2})
    hub = ProviderHub(backlink_providers=[FakeProvider("moz", snap)])
    findings = OffPageModule().run([], Tier.T2, _ofp_context(hub))
    checks = {f.check_id for f in findings}
    assert {"toxic-anchor-pattern", "anchor-overoptimisation",
            "low-referring-domains"} <= checks


def test_ofp_without_providers_is_not_assessed_and_neutral():
    module = OffPageModule()
    findings = module.run([], Tier.T2, {"crawl": CrawlResult(start_url="https://x.example/",
                                                             tier=Tier.T2),
                                        "site": Site(domain="x.example")})
    assert [f.check_id for f in findings] == ["backlinks-not-assessed"]
    assert module.score(findings, {}).score == 100.0  # info: honest, not punitive
