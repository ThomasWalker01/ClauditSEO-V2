"""A check the sweep tests only in part is not certified clean (screen
audits round 3, Security AC-01).

Security's clean line read "31 checks clean on every reading across the
site" and named `cert-chain`, which the sweep raises only for expiry inside
14 days, and three CMS probes it raises only on an answer of 200, while the
same page's analysis held each as not assessable ("full chain/OCSP-stapling
scan", "403 challenge page"). `sweepOutranks` let the newer sweep's silence
overrule those holds.
"""

from __future__ import annotations

from pathlib import Path

from clauditseo.modules import sec

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"


def test_the_partial_checks_are_the_sweeps_own():
    assert set(sec.PARTLY_MEASURED) == {
        "cert-chain", "cms-xmlrpc", "cms-login-exposed", "cms-registration-open"}
    assert set(sec.PARTLY_MEASURED) <= set(sec.DEFAULT_SEVERITY)
    assert all(why.strip() for why in sec.PARTLY_MEASURED.values())


def test_the_api_carries_them_on_the_security_part():
    app = (Path(sec.__file__).parents[1] / "api" / "app.py").read_text(encoding="utf-8")
    assert 'cat["partly_measured"] = _sec_partly' in app


def test_the_sweep_does_not_outrank_a_hold_on_one():
    src = (SRC / "part_page.tsx").read_text(encoding="utf-8")
    body = src.split("export function sweepOutranks", 1)[1].split("\n}\n", 1)[0]
    assert "!part.partly_measured?.[checkId]" in body


def test_the_clean_line_says_what_was_not_tested():
    src = (SRC / "part_page.tsx").read_text(encoding="utf-8")
    assert "&& !byOrder(r) && !spotlessDropped.includes(r) && !partly(r)" in src
    assert "only as far as the automatic checks test them" in src
