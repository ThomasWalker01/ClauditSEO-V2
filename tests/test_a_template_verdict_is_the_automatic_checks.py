"""A template's verdict is the automatic checks' reading of its pages (item
274, row 4).

Mobile's templates block printed the brief's `verdict` word alone: "12 clean"
over twelve templates, while the checks table beneath had `tap-target` open
on all twelve traced pages. The verdict is now derived from the open
automatic rows on each template's pages - any is "defective", else a check
the analysis held there is "partial", else "clean" - and the model's word is
kept beside it.
"""

from __future__ import annotations

from pathlib import Path

from clauditseo.persistence import runs

B = "https://t.fixture"
SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"


def _row(check, *paths, source="deterministic"):
    return {"check_id": check, "source": source, "urls": [B + p for p in paths]}


def test_the_verdict_is_read_off_the_templates_pages():
    templates = [{"template": "/seo/<slug>/", "verdict": "clean"},
                 {"template": "/about/", "verdict": "clean"},
                 {"template": "/contact/", "verdict": "clean"},
                 {"template": "/", "verdict": "clean"}]
    rows = [_row("tap-target", "/seo/local/", "/"),
            # An analysis row is not the automatic checks' reading.
            _row("viewport-units", "/about/", source="model-judgement")]
    held = [{"check": "TEC/font-size-small", "page": "/contact/", "needs": "a trace"}]
    got = {t["template"]: t for t in runs.template_verdicts(templates, rows, held)}
    assert got["/seo/<slug>/"]["verdict"] == "defective"
    assert got["/seo/<slug>/"]["verdict_faults"] == ["tap-target"]
    assert got["/"]["verdict"] == "defective"
    assert got["/about/"]["verdict"] == "clean"
    assert got["/contact/"]["verdict"] == "partial"
    assert got["/contact/"]["verdict_holds"] == ["font-size-small"]
    assert all(t["verdict_model"] == "clean" and t["verdict_by"] == "automatic checks"
               for t in got.values())


def test_a_site_wide_hold_makes_every_template_partial():
    got = runs.template_verdicts([{"template": "/a/", "verdict": "clean"}], [],
                                 [{"check": "TEC/font-size-small", "page": "*", "needs": "x"}])
    assert got[0]["verdict"] == "partial"


def test_a_template_that_is_not_a_path_keeps_the_models_word_and_says_so():
    got = runs.template_verdicts([{"template": "service pages", "verdict": "clean"}],
                                 [_row("tap-target", "/seo/local/")], [])
    assert got[0]["verdict"] == "clean" and got[0]["verdict_by"] == "analysis"


def test_the_table_says_where_the_analysis_differs():
    src = SRC.read_text(encoding="utf-8")
    assert "analysis said {t.verdict_model.toLowerCase()}" in src
