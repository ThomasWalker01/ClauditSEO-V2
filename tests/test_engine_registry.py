from clauditseo.engine import registry
from clauditseo.engine.types import Confidence, Finding, Severity, Site, SubScore, Tier, fingerprint


class ToyModule:
    code = "TOY"
    name = "Toy"
    default_weight = 0.0

    def applicable(self, site: Site) -> bool:
        return True

    def run(self, pages, tier, context):
        return [Finding(dimension="TOY", check_id="toy-check", severity=Severity.INFO,
                        summary="toy", subject="/")]

    def score(self, findings, context) -> SubScore:
        return SubScore(dimension="TOY", score=100.0, weight=0.0)


def test_register_and_run_module_without_engine_changes():
    mod = ToyModule()
    registry.register(mod)
    try:
        assert registry.get("TOY") is mod
        assert isinstance(mod, registry.AuditModule)
        findings = mod.run([], Tier.T1, {})
        assert findings[0].fingerprint == fingerprint("TOY", "toy-check", "/")
    finally:
        registry.unregister("TOY")


def test_fingerprint_is_stable_and_normalised():
    a = fingerprint("TEC", "canonical-missing", "/About/")
    b = fingerprint("TEC", "canonical-missing", "/about")
    assert a == b
    assert a != fingerprint("TEC", "canonical-missing", "/contact")


def test_finding_defaults_are_deterministic_source():
    f = Finding(dimension="TEC", check_id="x", severity=Severity.LOW, summary="s", subject="/")
    assert f.source == "deterministic"
    assert f.confidence == Confidence.HIGH
