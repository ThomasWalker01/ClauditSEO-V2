"""One meaning, one definition, one place (item 166).

`glossary.json` is the registry: every tone and term the product draws, its
word as drawn, the engine name it maps to, and one paragraph of what it means.
The dashboard imports the same file, so a disclosure, the glossary route and a
client report's appendix are three renderings of one text and cannot drift.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

PATH = Path(__file__).with_name("glossary.json")

#: The first sentence ends at a full stop, question or exclamation mark that is
#: followed by a space and a capital, or by the end. `robots.txt` and
#: `schema.org` carry a stop with no space after it and so do not end one.
#: `glossary.ts` holds the same expression; a test holds them together.
FIRST_SENTENCE = r"^(.+?[.!?])(?=\s+[A-Z]|\s*$)"
_FIRST = re.compile(FIRST_SENTENCE, re.S)


@lru_cache(maxsize=1)
def entries() -> tuple[dict, ...]:
    return tuple(json.loads(PATH.read_text(encoding="utf-8"))["entries"])


def short(entry: dict) -> str:
    """The disclosure sentence: the first sentence of `full`, never a second
    string that could say something else."""
    text = entry["full"].strip()
    m = _FIRST.match(text)
    return m.group(1) if m else text


def terms_in(text: str) -> list[dict]:
    """The registry entries a document uses. Only entries carrying `matches`
    can be found: common words such as "open" or "site" would otherwise put a
    definition of every everyday word into every appendix."""
    found = []
    for e in entries():
        for m in e.get("matches", ()):
            if re.search(r"(?<![\w-])" + re.escape(m) + r"(?![\w-])", text):
                found.append(e)
                break
    return found


def appendix(markdown: str) -> str:
    """The client report's glossary, filtered to the terms the report uses.
    Empty when it uses none, so a document never carries an empty heading."""
    used = terms_in(markdown)
    if not used:
        return ""
    lines = ["", "## Glossary", "",
             "The technical terms this report uses, named as Google's own tools name them.", ""]
    for e in sorted(used, key=lambda e: e["word"].lower()):
        lines += [f"**{e['word']}**: {e['full']}", ""]
    return "\n".join(lines)
