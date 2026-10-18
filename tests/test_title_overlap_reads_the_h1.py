"""Title overlap reads the H1, not the first heading (item 269, row 6).

`_same_page_title` compared `headings[0]`, the first heading of any level.
On twenty22 every page's first heading is a template H3, "About the Design
Process", so the check reported one group of 45 pages sharing a title. It
compares the H1. (The row's second half, containment, waits on the channel:
20261006-1350-269-title-overlap-containment.)
"""

from __future__ import annotations

from types import SimpleNamespace

from clauditseo.modules import cnt


def _p(title, headings):
    return SimpleNamespace(title=title, headings=headings)


def test_a_shared_template_heading_is_not_a_shared_h1():
    a = _p("Website design for builders", [(3, "About the Design Process"), (1, "Builders")])
    b = _p("Search engine optimisation", [(3, "About the Design Process"), (1, "Optimisation")])
    assert not cnt._same_page_title(a, b, set())


def test_a_shared_h1_still_is():
    a = _p("Plumbing", [(2, "Intro"), (1, "Emergency plumbing services")])
    b = _p("Drains", [(2, "Other"), (1, "Emergency plumbing services")])
    assert cnt._same_page_title(a, b, set())
