"""No row names an llms.txt that does not exist (item 267, row 13).

On twenty22 the `llms-txt-conflict` card said four URLs "are excluded from
the authored llms.txt", the Declined list pointed at "the llms.txt section",
and a hold read "needs file was absent and false was false at sweep time" -
while the site served no /llms.txt and the run built none. Such a row is now
dropped with the reason; the coverage and thin holds are said from the slot's
name; a Declined item no longer points at a section the page does not draw.
"""

from __future__ import annotations

from types import SimpleNamespace

from clauditseo.analysts import ai_surface as ais


def test_a_conflict_in_no_file_is_dropped():
    row = {"check": "AIS/llms-txt-conflict", "page": "/",
           "evidence": "4 URLs are excluded from the authored llms.txt"}
    kept, why, _ = ais.police_row("AIS/llms-txt-conflict", row, llms_txt_build=False,
                                  raised={"llms-txt-missing": set()})
    assert kept is None and "does not exist" in why
    # Where the site publishes its own file, the conflict may be about it.
    kept, why, _ = ais.police_row("AIS/llms-txt-conflict", row, llms_txt_build=False,
                                  raised={})
    assert why is None or "does not exist" not in why


def test_the_holds_and_the_declined_pointer_say_the_slot():
    parsed = SimpleNamespace(
        not_assessable=[{"check": "AIS/llms-txt-thin", "needs": "file was absent and false was false"}],
        ai_surface={"llms_txt_file": None, "declined": [
            {"item": "Authoring llms-full.txt", "handled_at": "llms.txt section, readable block"}]})
    ais.police_absent_llms(parsed, build=False)
    assert parsed.not_assessable[0]["needs"].startswith("the build input is off")
    assert parsed.ai_surface["declined"][0]["handled_at"].startswith("no llms.txt was built")
