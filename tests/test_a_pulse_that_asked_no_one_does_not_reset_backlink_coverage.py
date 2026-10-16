"""A Quick pulse that asked no provider does not reset the Backlinks part's
stated coverage.

Screen audits round 3, Backlinks IP-02 (High): the header said "0 of 2
backlinks signals measured" over a first row reading "22 referring domains
(moz)". The coverage read the newest open `backlinks-not-assessed` row, which
was a free Quick pulse: T1 makes no external call, so every signal was dark.
"""
from __future__ import annotations

import inspect
import json
import sqlite3

from clauditseo.modules import ofp
from clauditseo.persistence import runs


class _Conn:
    """The payload's query, answered from a list, newest first."""

    def __init__(self, rows):
        self.rows = rows

    def execute(self, sql, params=()):
        assert "backlinks-not-assessed" in sql and "ORDER BY f.created_at DESC" in sql
        return [{"evidence": json.dumps(e), "summary": s} for e, s in self.rows]


def test_an_unasked_row_is_passed_over_for_the_reading_that_asked():
    rows = [({"unmeasured": ["referring domains", "anchor text distribution"],
              "unasked": True}, "Not assessed: referring domains, anchor text distribution."),
            ({"unmeasured": ["anchor text distribution"], "providers_answering": ["moz"]},
             "Not assessed: anchor text distribution.")]
    got = runs.signal_coverage_payload(_Conn(rows), "site")
    assert got["measured"] == ["referring domains"] and got["providers"] == ["moz"], got


def test_a_row_from_before_the_flag_is_known_by_its_sentence():
    rows = [({"unmeasured": ["referring domains", "anchor text distribution"]},
             "Not assessed: referring domains. Not requested at this depth; a Standard "
             "re-check asks the provider.")]
    got = runs.signal_coverage_payload(_Conn(rows), "site")
    assert got["unmeasured"] == [], got


def test_the_module_marks_the_row_it_files_unasked():
    assert '"unasked": unasked},' in inspect.getsource(ofp)
