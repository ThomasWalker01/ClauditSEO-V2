"""The International gate says its evidence as fields (item 274, row 12).

The card dumped the gate's prose in a <pre>, backticks and "[TO CONFIRM: ...]"
as source, and every line that quoted the gate cut its first sentence out of
that prose. The gate now carries one sentence (`why`) and the evidence as
fields, drawn as Observed; the prose stays, rendered, behind a disclosure.
"""

from __future__ import annotations

from pathlib import Path

from clauditseo.analysts.expert import ABSENT, _hreflang_applies, locale_facts

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"


def _rec(url, lang="en-au"):
    return {"url": url, "lang": lang, "hreflang": [], "content_type": "text/html", "status": 200}


def test_the_fields():
    facts = locale_facts([_rec("https://t.co/"), _rec("https://t.co/about/", lang="")])
    assert facts == {"pages_inspected": 2, "lang_values": ["en-au"], "lang_undeclared": 1,
                     "locale_folders": [], "alternates_on": 0}


def test_the_card_draws_them():
    page = (SRC / "part_page.tsx").read_text(encoding="utf-8")
    intl = page.split("function IntlNow", 1)[1].split("\n}\n", 1)[0]
    assert "<pre className=\"intl-gate-reason\"" not in intl
    assert "gate.evidence.lang_values" in intl and "<Markdown source={gate.reason} />" in intl
    assert "why: gate.why || gate.reason" in (SRC / "measure.tsx").read_text(encoding="utf-8")
