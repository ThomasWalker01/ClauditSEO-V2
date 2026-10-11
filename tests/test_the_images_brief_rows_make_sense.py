"""Three sense rules on the Images brief (item 272, row 3).

- An `img-alt-missing` row whose own text quotes the alt: "alt present as
  'Twenty22 Website and SEO' on a 1x1 tracking/placeholder pixel" was a
  candidate telling the client an image lacked alt text.
- A hold whose reason says the check does not apply ("n/a ... SVG/vector
  assets do not require srcset by nature; check does not apply to vector
  format") was drawn as a hold on every page.
- A `srcset` whose descriptors fall as the files grow ("-480.avif 430w,
  -768.avif 344w, ...") was kept with a copy button; a browser would serve
  the smallest file at every width.
"""

from __future__ import annotations

import json

from clauditseo.analysts import contract

BASE = "https://t.fixture"
PAGES = [BASE + "/", BASE + "/about/"]
CHECKS = ["ONP/img-alt-missing", "ONP/img-no-srcset", "ONP/img-filename-generic"]


def _row(check, **kw):
    return {"check": check, "page": BASE + "/", "status": "FAIL", "severity": "MEDIUM",
            "evidence": "x", "replacement": "", "note": "", **kw}


def _parse(rows=(), held=()):
    block = json.dumps({"part": "images", "rows": list(rows), "not_assessable": list(held)})
    return contract.parse("```json\n" + block + "\n```\n", CHECKS, PAGES, rules=contract.Rules())


def test_an_alt_row_that_quotes_the_alt_is_dropped():
    got = _parse([_row("ONP/img-alt-missing", evidence="alt present as 'Twenty22 Website and SEO'"
                       " on a 1x1 tracking/placeholder pixel")])
    assert not got.rows
    assert got.dropped[0]["reason"] == "the row's own evidence says the alt text is present"
    got = _parse([_row("ONP/img-alt-missing", note='the hero has alt="Team photo"')])
    assert not got.rows, got.rows
    # An empty alt is the fault, and stays.
    assert _parse([_row("ONP/img-alt-missing", evidence='alt="" on the hero')]).rows


def test_a_hold_that_says_it_does_not_apply_is_a_pass():
    got = _parse(held=[{"check": "ONP/img-no-srcset", "page": "/",
                        "needs": "n/a - SVG/vector assets do not require srcset by nature; "
                                 "check does not apply to vector format"}])
    assert not got.not_assessable, got.not_assessable
    assert got.dropped[0]["reason"] == "a pass, not a hold"


def test_a_srcset_whose_descriptors_fall_is_dropped():
    bad = ('<img srcset="/a-480.avif 430w, /a-768.avif 344w, /a-1024.avif 303w, '
           '/a-1440.avif 347w" sizes="100vw">')
    got = _parse([_row("ONP/img-no-srcset", replacement=bad)])
    assert not got.rows
    assert got.dropped[0]["reason"] == "srcset descriptors fall as the files grow (-480 at 430w, -768 at 344w)"
    good = '<img srcset="/a-480.avif 480w, /a-768.avif 768w, /a-1024.avif 1024w" sizes="100vw">'
    assert _parse([_row("ONP/img-no-srcset", replacement=good)]).rows
