"""The verdict leads the disclosure, with the Patterns under it (item 268,
row 9).

Headings writes its assessment as a paragraph of counts ending in a
one-sentence verdict, and its Patterns as a section of their own beside it,
so the disclosure showed the counts and stopped: the one sentence that says
the one change was its last clause, and the Patterns were not on screen.
"""

from __future__ import annotations

from clauditseo.persistence.runs import brief_assessment

REPORT = """### Headings — assessment
12 FAIL · 6 WARN · 2 not assessable · 45 pages. A form-builder pattern breaks levels on every quote page.

### Corrected outlines — patterns only
Eight pages change.

### Patterns
`/quote/*`: h2 then h4 from the form plugin; one template change.

### Not assessable
None.
"""


def test_verdict_then_patterns_then_counts():
    got = brief_assessment(REPORT)
    assert got.startswith("**A form-builder pattern breaks levels on every quote page.**"), got
    assert got.index("### Patterns") < got.index("12 FAIL"), got
    # Item 270 (row 13): the corrected-outline patterns follow the Patterns.
    assert got.index("### Patterns") < got.index("Eight pages change") < got.index("12 FAIL"), got
