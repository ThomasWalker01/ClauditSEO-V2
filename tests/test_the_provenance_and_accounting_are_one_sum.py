"""The provenance and the accounting are one sum (items 277 row 9, 273
row 8).

The provenance read "9 rows returned · 5 kept · 4 dropped" and the
accounting under the cards "4 merged · 1 on their own · 4 dropped; 3 checks
could not be assessed" - the holds in one and not the other, and "kept" in
one and not the other. Both now carry the holds, and the accounting opens on
the kept figure it breaks down.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx"


def test_one_sum():
    src = SRC.read_text(encoding="utf-8")
    assert "` · ${n} check${n === 1 ? \"\" : \"s\"} held`" in src
    assert "{kept != null && <>{kept} kept: </>}{merged} merged onto" in src
