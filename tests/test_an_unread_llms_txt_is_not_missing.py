"""An llms.txt the crawl did not request is not missing (screen audits round
4, AI surface AC-02).

"/llms.txt: not requested on this audit" stood over `llms-txt-missing`
"open · No llms.txt file found." on the same audit: the stored evidence was
`{"status": null}`, and the check raised on any status but 200. It now
raises only on a status it read, and a run that read none does not measure
the llms.txt checks, so its silence cannot clear them either.
"""
from __future__ import annotations

import inspect

from clauditseo.modules import ais
from clauditseo.persistence.runs import Reading, instruments_of, measured


def _reading(instruments):
    return Reading("r", frozenset({"AIS"}), frozenset({"/"}), frozenset(), frozenset(),
                   True, frozenset(), frozenset(instruments), frozenset())


def test_the_check_raises_only_on_a_status_it_read():
    src = inspect.getsource(ais)
    assert "crawl.llms_txt_status is not None and crawl.llms_txt_status != 200" in src


def test_a_run_that_did_not_request_it_does_not_measure_it():
    have, _ = instruments_of(None, None, None, None, None)
    assert "llms_txt" not in have
    state, why = measured(_reading(have), "AIS", "llms-txt-missing", [])
    assert state == "unmeasured" and "llms txt" in why
    for status in (404, 200, "unknown"):
        assert "llms_txt" in instruments_of(None, None, None, None, status)[0], status
    assert measured(_reading({"llms_txt"}), "AIS", "llms-txt-missing", [])[0] == "clean"
