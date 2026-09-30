"""One catalogue of briefs, read from the prompt files themselves.

Brief v10 step AD (`_plans/site-screen-brief-v10-2026-09-04.md`). Every
`clauditseo/prompts/*.md` opens with a YAML front-matter header carrying
`id`, `name`, `part`, `scope`, `tier` and `checks`. This module is the one
reader of that header: the analyst registry takes a brief's scope and tier
from it, the anatomy takes the part a brief writes to from it, and the
lanes payload carries `part` to the dashboard - so the catalogue drawer,
Admin's brief defaults, the run-all confirm panel and the part page's own
list all show the same briefs in the same order without a second mapping
anywhere. The order everywhere is the sidebar's: group, then part, then
name.

A prompt whose header is missing, or lacks a field, is a load error that
names the file and the field, never a brief filed quietly under "other".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"

#: Where a brief that writes to no part goes: triage ranks the rest and
#: stands on step 3 and in Admin's defaults, not in the catalogue.
NO_PART = "none"

#: The client report itself (brief v18 step AY). `plan.md` writes the front
#: of the deliverable - executive summary, roadmap, measures - and that is a
#: document, not a part page: there is no checks table for it, no fix cards
#: and no sidebar entry, because it emits no rows about the site. It is a
#: part value rather than `none` so the report assembly can ask for "the
#: brief that writes the report" by name instead of by id.
REPORT_PART = "report"

#: Part values that name no sidebar section. Every reader that buckets
#: briefs by part skips these - the anatomy's tool map, the part-page
#: registers, the catalogue drawer - and a single tuple is what stops the
#: next such value being added to two of the three.
PARTLESS = (NO_PART, REPORT_PART)

SCOPES = ("site", "page")
#: What a brief produces. `analysis` is every brief through v16: rows
#: judged against the header's checks. `generator` is brief v17 step AX's
#: addition - a document rather than findings, whose first block is a
#: record of what it wrote and whose `checks` list is empty by
#: construction. Absent means `analysis`, so no existing header changes.
KINDS = ("analysis", "generator")
TIERS = ("fast", "standard", "deep")
REQUIRED = ("id", "name", "part", "scope", "tier", "checks")

_FRONT = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n", re.S)


class BriefHeaderError(ValueError):
    """A prompt file whose header cannot be read as a brief: the file and
    the field are in the message, so the catalogue fails loudly at load
    rather than filing the brief somewhere by guess."""


@dataclass(frozen=True)
class Brief:
    id: str
    name: str
    part: str
    scope: str
    tier: str
    checks: tuple[str, ...]
    path: Path
    #: `analysis` (rows) or `generator` (a document). See `KINDS`.
    kind: str = "analysis"
    #: The checks a brief reads through and never emits (brief v22, item 145):
    #: rendered under their owning ids. Empty for every brief without the key.
    reads: tuple[str, ...] = ()
    #: Position in the sidebar's order (group, part, name); briefs with no
    #: part sort last.
    order: int = field(default=0, compare=False)


def split_front_matter(text: str) -> tuple[dict | None, str]:
    """The header as a dict (None where there is none) and the body after
    it - the prompt the model reads, which does not include the header."""
    m = _FRONT.match(text)
    if not m:
        return None, text
    try:
        data = yaml.safe_load(m.group(1))
    except yaml.YAMLError as e:
        raise BriefHeaderError(f"front matter is not YAML: {e}") from e
    if not isinstance(data, dict):
        raise BriefHeaderError("front matter is not a mapping")
    return data, text[m.end():]


def strip_front_matter(text: str) -> str:
    return split_front_matter(text)[1]


def header_of(path: Path, categories: tuple | None = None) -> dict:
    """Read and validate one prompt's header. `categories` is the sidebar's
    category tuple; when None it is read from the anatomy."""
    try:
        data, _ = split_front_matter(path.read_text(encoding="utf-8"))
    except BriefHeaderError as e:
        raise BriefHeaderError(f"{path.name}: {e}") from None
    if data is None:
        raise BriefHeaderError(
            f"{path.name}: no front matter - every prompt opens with a YAML "
            f"header carrying {', '.join(REQUIRED)}")
    for key in REQUIRED:
        if key not in data:
            raise BriefHeaderError(f"{path.name}: header lacks `{key}`")
    if data["id"] != path.stem:
        raise BriefHeaderError(
            f"{path.name}: header id {data['id']!r} is not the file's name {path.stem!r}")
    if data["scope"] not in SCOPES:
        raise BriefHeaderError(
            f"{path.name}: scope {data['scope']!r} is not one of {'|'.join(SCOPES)}")
    if data["tier"] not in TIERS:
        raise BriefHeaderError(
            f"{path.name}: tier {data['tier']!r} is not one of {'|'.join(TIERS)}")
    keys = {c.key for c in (categories if categories is not None else _categories())}
    if data["part"] not in PARTLESS and data["part"] not in keys:
        raise BriefHeaderError(
            f"{path.name}: part {data['part']!r} is not a sidebar part "
            f"({', '.join(sorted(keys))}) or one of "
            f"{', '.join(repr(p) for p in PARTLESS)}")
    checks = data["checks"] or []
    if not isinstance(checks, list) or not all(isinstance(c, str) for c in checks):
        raise BriefHeaderError(f"{path.name}: `checks` is not a list of check ids")
    return {**data, "checks": list(checks)}


def _categories():
    from clauditseo.anatomy import CATEGORIES
    return CATEGORIES


def load(prompt_dir: Path = PROMPT_DIR, categories: tuple | None = None) -> list[Brief]:
    """Every brief under `prompt_dir`, validated, in the sidebar's order."""
    cats = categories if categories is not None else _categories()
    index = {c.key: i for i, c in enumerate(cats)}
    briefs = []
    for path in sorted(prompt_dir.glob("*.md")):
        # `_CONTRACT.md` is the layout every conforming brief follows, not a
        # brief (brief v11 step AH): a file whose name opens with `_` is
        # skipped here and by every reader of the prompt directory.
        if path.name.startswith("_"):
            continue
        h = header_of(path, cats)
        briefs.append(Brief(id=h["id"], name=str(h["name"]), part=h["part"],
                            scope=h["scope"], tier=h["tier"],
                            checks=tuple(h["checks"]), path=path,
                            kind=str(h.get("kind") or "analysis"),
                            reads=tuple(str(r) for r in (h.get("reads") or []))))
    briefs.sort(key=lambda b: (index.get(b.part, len(index)), b.name.lower()))
    return [Brief(**{**b.__dict__, "order": i}) for i, b in enumerate(briefs)]


@lru_cache(maxsize=1)
def catalogue() -> tuple[Brief, ...]:
    """The installed prompts, read once per process. Tests that write
    prompt files call `reload()`."""
    return tuple(load())


def reload() -> None:
    catalogue.cache_clear()


def by_id() -> dict[str, Brief]:
    return {b.id: b for b in catalogue()}


def brief_parts() -> dict[str, str]:
    """Brief id -> the part it writes to (`none` for triage)."""
    return {b.id: b.part for b in catalogue()}


def parts(categories: tuple | None = None) -> list[dict]:
    """The sidebar's parts in order, each with the briefs filed under it -
    including the parts no brief writes to, which the drawer shows as a
    header reading "no brief yet" rather than hiding."""
    cats = categories if categories is not None else _categories()
    filed = {}
    for b in catalogue():
        filed.setdefault(b.part, []).append(b.id)
    return [{"key": c.key, "label": c.label, "group": c.group,
             "briefs": filed.get(c.key, [])}
            for c in cats if c.group != "workflow"]
