"""A hold reads as a sentence, and a pass is not a hold (item 276, row 7).

On twenty22's Security, `cert-key` was held with the reason "not raised by
the sweep for the observed leaf (...) - reported as passing from the TLS
probe data supplied", which is a pass. The ledger's example taught
"active_probing_authorised = true", which the screen printed as code. And a
reason that began "needs" read "needs needs" under the screen's own word.
"""

from __future__ import annotations

from clauditseo.analysts import contract


def _clean(*held):
    parsed = contract.Parsed(status=contract.READ, not_assessable=list(held))
    return contract.clean_holds(parsed)


def test_a_reason_that_reports_a_pass_is_a_pass():
    got = _clean({"check": "SEC/cert-key", "page": "",
                  "needs": "not raised by the sweep for the observed leaf (ec 256 bits) - "
                           "reported as passing from the TLS probe data supplied"})
    assert not got.not_assessable and got.dropped[0]["reason"] == "a pass, not a hold"


def test_a_setting_is_said_in_words_and_needs_is_said_once():
    got = _clean({"check": "SEC/open-ports", "page": "",
                  "needs": "needs active_probing_authorised = true on the site record"})
    assert got.not_assessable[0]["needs"] == "active probing authorised on the site record", got


def test_the_security_brief_teaches_the_sentence():
    from pathlib import Path
    md = (Path(contract.__file__).resolve().parents[1] / "prompts" / "security.md").read_text(encoding="utf-8")
    # The bare token in any form, not only "= true" (the channel's answer,
    # 20261005-2332): line 331's example taught it without one.
    assert "active_probing_authorised" not in md
