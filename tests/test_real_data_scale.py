"""The real-data-scale invariant, with its population derived from source.

`auditor.md` promoted the invariant on 15 August 2026 after four instances in
three mechanisms, and states two clauses:

    a collection rendered from crawl data must be bounded at its render site
    by a filter or pagination, and any element displaying a crawl-derived
    string must set `overflow-wrap`.

Only the second clause has ever had a guard, and its population was the tuple
`UNBROKEN_TOKEN_CLASSES = ("fact-mono",)` in `test_dashboard_a11y.py` —
hand-kept, one element long, and carried by eleven audit reports as CQ-27. A
hand-kept population cannot fail for a class nobody remembered to add, which
is the whole defect: the guard was written for the one class that had already
caused a fault.

The *bounded* clause had no guard anywhere. That is what left the heading
outline and the images table unbounded for eleven reports as UX-18, and it is
why the two findings are one subsystem rather than two: they are the guard
and the screen it protects, for the same invariant.

Both populations are derived here from the crawl payloads' own declarations
— `type Facts` for the page-facts panel, and the inline type argument at
every fetch of a route in `CRAWL_ROUTES` for the payloads that have no name
— so a collection added to the crawl joins this guard on the day it is
declared rather than on the day somebody remembers.

`type Facts` alone was the population for two rounds, and one payload is one
screen: the file sweep could glob every `dashboard/src/*.tsx` and still only
ever name `anatomy.tsx`, because a field list is a screen's field list. Two
page pickers rendered the crawl's whole page set into an unfiltered
`<option>` list the entire time, carried as UX-19 since report 019, and the
guard could not fail for either. Report 070 filed that as CQ-144;
`test_the_population_is_the_crawl_payloads_own_declaration` now asserts the
population reaches more than one screen, which is the shape of the assertion
a count of render sites could not make.

That is the same shape as `STATE_MEANING`'s guard from round 067
and `PAINTED_BY_NOTHING`'s in `test_dashboard_a11y.py`: derive the
population, record the exceptions with a reason, and let the next one fail
instead of shipping.

Source, here, means source and not the prose around it. Every derivation
below reads through `_source_text`, which strips comments first, because
until that existed a `//` line quoting a render site put the quotation into
the population — and `pages` carries no `UNBOUNDED_BY_MEASUREMENT` row, so
the phantom was a red gate rather than noise. The workaround in force before
this was a rule that one comment in this file may not quote code, which is
a rule no assertion enforced and every other comment here breaks.
`test_a_comment_cannot_change_what_this_guard_covers` is what replaces it,
and it derives its mutation from each file's own reported sites rather than
from a line somebody picked.

What this cannot do: it reads source, so it knows what the author declared
and not what a browser painted. `test_reflow.py` drives the rendered screens
at 320px and is what actually observes a column leaving the viewport; this is
what makes a *new* unbounded render fail on the gate before it gets that far.
Neither replaces the other.

The four `@live` clauses at the foot of this file are the third leg, and what
they are for is narrower than "the control works": each one holds a bounded
render site to the rule that **the number above the list is the list**, and
each is driven against a fixture page where the filter selects a *strict*
subset. That last word is the whole design. The images clause opened `/deep`
for two rounds — one image, and it is the one missing its alt attribute — so
`before`, `promised` and the filtered count were all 1 and every assertion
held by identity. Report 070 filed it as CQ-141: a clause that would stay
green if the control it drives were inert. Proven, not argued, on one build
with the `<select>`'s `onChange` replaced by a no-op — the `/deep` drive
passed and the `/gallery` drive failed with `4 -> 4`. The two picker clauses
were proven the same way, `15 -> 15` each.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"
ANATOMY = SRC / "anatomy.tsx"
CSS = SRC / "styles.css"

#: Render sites over a crawl-derived collection that are deliberately not
#: bounded by a control, with the ceiling that makes that honest. Every
#: number here was measured on 21 August 2026 across the **557 stored crawl
#: pages** in `data/clauditseo.db` — `max(len(page[field]))` over every
#: `audit_runs.crawl_evidence` row — not estimated from the code.
#:
#: A row is admissible only where the ceiling is small enough that a filter
#: would be furniture. The two the invariant was promoted for are absent on
#: purpose: `headings` measured max 60 / p95 47 / median 21, and `images`
#: measured max 60 / p95 60 / median 25, both sitting on the crawl's own
#: `HEADING_CAP` / `IMAGE_CAP` of 60 (`clauditseo/crawler/evidence.py:36-39`)
#: — a cap that says how much is kept, not how much is readable at once.
UNBOUNDED_BY_MEASUREMENT = {
    "schema_types": "max 12 across 557 stored pages; chips, one line",
    "hreflang": "max 5 across 557 stored pages; chips, one line",
    "viewport_tags": "max 1 across 557 stored pages; a page declares one",
    "nap_mentions": "max 6, and the render site already slices to 6",
    "link_sample": (
        "hard-capped at 25 by the payload — `links[:25]`, "
        "`clauditseo/persistence/runs.py:2713` — so the ceiling is in the "
        "server, not in a control the operator can miss. Absent from all 557 "
        "stored pages, because it is assembled per request rather than "
        "stored, so 25 is the only number available and it is exact"
    ),
}

#: Array fields of the crawl payload that `render_sites()` finds no render
#: site for, each with the reason that makes the absence honest. Measured on
#: 21 August 2026 by grepping `dashboard/src` for each name, not read off the
#: skip messages this replaces.
#:
#: This exists because the alternative was `pytest.skip`, and a skip is a pass
#: that reports itself as neither. Two costs, both paid. The detection reads
#: source for `.map(` over a `facts.` chain, so the day it breaks — a rename
#: of `type Facts`, a chain scoped to the wrong span — every field it can no
#: longer see goes quiet rather than red, which is the failure mode
#: `test_the_population_is_the_crawl_payloads_own_declaration` was written
#: to catch for exactly two founding fields and cannot catch for the rest. And
#: the file is in the `rendered-a11y` sweep, whose step greps `[0-9]+ skipped`
#: and exits 1 (`.github/workflows/ci.yml:365`), so the two skips reddened
#: that job on every push from the commit that added the file. A stated
#: exception costs one line and fails when it stops being true; a skip costs
#: nothing and never does.
RENDERED_NOWHERE = {
    "missing": (
        "computed by `page_facts` and declared in `type Facts`, and no file "
        "under `dashboard/src` reads `facts.missing` — the screen re-derives "
        "a weaker per-category answer with `if (!facts.images) … absent(…)` "
        "instead. Filed as CQ-142 in report 069; this row goes when that is "
        "settled either way, because rendering it or deleting it both end "
        "with the field no longer being an unexplained absence"
    ),
    "profile_links": (
        "computed by `page_facts` and declared in `type Facts`, and read by "
        "the Structured data brief rather than by any screen (brief v16 step "
        "AS). It is the page's links to profile hosts, handed to the brief "
        "as *candidates* beside the site record's own `sameas_sources` - "
        "whether the entity controls a profile is a fact about ownership no "
        "crawl can see, and rendering the candidates on a card would be the "
        "screen making that claim on the crawl's behalf. Checked at "
        "`SchemaNow` in `part_page.tsx`, which renders the blocks and the "
        "two verdicts and not this"
    ),
    "redirect_chain": (
        "rendered, but not through `.map(` and so not as a collection: "
        "`anatomy.tsx:1208-1209` joins it with an arrow into a single `Row` "
        "value. The bounded clause is about a list an operator scrolls; one "
        "joined string is bounded by the row it sits in"
    ),
}

#: Classes whose declared union must carry `overflow-wrap`, keyed by the
#: crawl-derived render site that applies them. Derived, never written here.
#: This is what replaces `UNBROKEN_TOKEN_CLASSES`.


#: Crawl payloads that are declared as a *named* type, and the source that
#: declares each. A payload is a response assembled from crawl data; its
#: collections are its array-typed top-level fields.
#:
#: **This was one entry, and one entry is why the guard covered one panel.**
#: `type Facts` is the page-facts panel's own declaration, so a population
#: derived from it alone can only ever name render sites in `anatomy.tsx` —
#: which is exactly what round 069's widened file sweep returned: 7 render
#: sites and 10 string sites, every one of them `anatomy.tsx`, over a glob of
#: every `dashboard/src/*.tsx`. The sweep was widened along the axis that was
#: cheap to widen, and the guard stayed blind to two live breaches this
#: register already carries as UX-19. Filed as CQ-144 in report 070.
NAMED_PAYLOADS = {"Facts": ANATOMY}

#: Crawl routes whose response is a payload too, matched against the fetch
#: site's own template literal — `${...}` is any interpolation.
#:
#: These need a second producer because they have no name to key on. The page
#: list is declared *inline* at the fetch, twice — `views.tsx:1001` and
#: `tools.tsx:301` — and reaches its render site through `useState` rather
#: than through a prop, so neither a named type nor a `facts.` prefix can
#: reach it. Keying on the route rather than on the shape is deliberate: the
#: shape is written twice and could drift, while the route is what makes the
#: data crawl-derived in the first place.
CRAWL_ROUTES = (r"/api/runs/\$\{[^}]+\}/pages",)


def _flatten(body: str) -> str:
    """A type body with nested object types removed.

    Nested braces are stripped rather than parsed: every collection this
    guard is about is declared at the top level of the payload, and a
    brace-counting reader that returned nested fields would have to invent a
    render-site rule for `facts.site.sitemaps` that no screen uses.
    """
    depth, out = 0, []
    for ch in body:
        if ch == "{":
            depth += 1
        if depth == 0:
            out.append(ch)
        if ch == "}":
            depth -= 1
    return "".join(out)


def _fields(body: str) -> list[tuple[str, str]]:
    """(name, declared type) for every top-level field of a payload body."""
    return re.findall(r"([a-z_0-9]+)\??\s*:\s*([^;]+);",
                      _flatten(body).strip().rstrip(";") + ";")


def _named_bodies() -> list[str]:
    bodies = []
    for name, path in NAMED_PAYLOADS.items():
        text = _source_text(path)
        # `export type` counts: exporting a declaration does not change
        # what it declares, and `Facts` is exported since brief v13 step AO
        # so the part page can render it.
        body = re.search(r"^(?:export )?type " + name + r" = \{(.*?)^\};", text, re.S | re.M)
        assert body, f"type {name} is not declared in {path.name}"
        bodies.append(body.group(1))
    return bodies


def _fetched_bodies(text: str) -> list[str]:
    """Type arguments of every `api.get<{…}>` / `useFetch<{…}>` on a crawl route.

    The route is looked for in the text that follows the type argument, which
    is where a fetch call puts it. An inline object type is the only shape
    read here: a payload named well enough to be a `type` belongs in
    `NAMED_PAYLOADS`, where its declaration is one place rather than one per
    fetch site.
    """
    out = []
    for m in re.finditer(r"(?:api\.get|useFetch)<\{(.*?)\}>\(", text, re.S):
        tail = text[m.end():m.end() + 240]
        if any(re.search(r, tail) for r in CRAWL_ROUTES):
            out.append(m.group(1))
    return out


def collections_() -> list[str]:
    """Every array-typed field of every crawl payload, deduplicated.

    Deduplicated because two screens declare the page list separately and a
    field checked twice would parametrize twice under one name.
    """
    seen, out = set(), []
    bodies = _named_bodies()
    for path in _sources():
        bodies += _fetched_bodies(_source_text(path))
    for body in bodies:
        for n, t in _fields(body):
            if "[]" in t and n not in seen:
                seen.add(n)
                out.append(n)
    return out


def _sources() -> list[Path]:
    return sorted(SRC.glob("*.tsx"))


def _strip_comments(text: str) -> str:
    """Blank every `//` and `/* */` comment, keeping lines and columns intact.

    Columns and line count are preserved — a comment becomes spaces rather
    than disappearing — because every site this file reports carries a line
    number, and a stripper that reflowed the file would make each of them
    point somewhere else. CQ-143 is the standing evidence for how a wrong
    line number ages here.

    **What it models, and why that is the model.** A `'` or `"` string
    cannot span a line in JavaScript and a template literal can, so the
    first two reset at every newline and the third does not. That is not a
    simplification: it is what makes a bare apostrophe in JSX prose —
    ``<p>the operator's work</p>``, and there are 199 of those across these
    files — heal at the end of its own line instead of swallowing the rest
    of the file.

    **Three limits, stated rather than fixed, per this file's own rule.**

    1. It is a scanner, not a parser, so it does not know a regex literal
       from a division. A `//` inside a regex literal would read as a
       comment. None exists today — every `/` in a regex under
       `dashboard/src` is escaped as `\\/` or separated, checked across all
       20 files — and if one appears, the two directions are both asserted:
       over-stripping fails
       `test_the_population_is_the_crawl_payloads_own_declaration`'s
       founding-field clauses, under-stripping fails
       `test_a_comment_cannot_change_what_this_guard_covers`.
    2. JSX *text* is not a string literal, so a bare `//` written as prose
       between tags would be stripped. One `https://` exists under
       `dashboard/src` and it is inside a quoted attribute, so it is
       already handled; this is the case that is not.
    3. An odd number of apostrophes in one line of JSX text hides anything
       after it on that line, including a real trailing comment. It
       under-strips, and it recovers at the newline.
    """
    out, i, n = [], 0, len(text)
    state = None          # None | "line" | "block" | "'" | '"' | "`"
    while i < n:
        ch, nxt = text[i], text[i + 1] if i + 1 < n else ""
        if state is None:
            if ch == "/" and nxt == "/":
                state, out, i = "line", out + ["  "], i + 2
                continue
            if ch == "/" and nxt == "*":
                state, out, i = "block", out + ["  "], i + 2
                continue
            if ch in "'\"`":
                state = ch
            out.append(ch)
        elif state == "line":
            if ch == "\n":
                state = None
                out.append(ch)
            else:
                out.append(" ")
        elif state == "block":
            if ch == "*" and nxt == "/":
                state, out, i = None, out + ["  "], i + 2
                continue
            out.append(ch if ch == "\n" else " ")
        else:                                   # inside a string
            if ch == "\\":
                out.append(ch)
                if nxt:
                    out.append(nxt)
                    i += 2
                    continue
            elif ch == state:
                state = None
            elif ch == "\n" and state in "'\"":
                # A quoted string cannot span a line; an unbalanced quote in
                # JSX prose is a quote in prose, so give up on it here.
                state = None
            out.append(ch)
        i += 1
    return "".join(out)


def _source_text(path: Path) -> str:
    """The one place this file turns a source path into text to match against.

    Every derivation here reads through it, so what counts as source is
    decided once instead of at four `read_text` calls — and comments stop
    being source in one place rather than four.
    """
    return _strip_comments(path.read_text(encoding="utf-8"))


#: `const X = <expr>`, resolved transitively, so `const rows = facts.headings`
#: followed by `const shown = rows.filter(...)` is a chain this can follow.
#: Without it a render site could be bounded one line above the `.map(` and
#: this guard would still call it unbounded.
#: A binding, with or without a type annotation. Without the annotation
#: `const inventory: ImageRecord[] = facts.image_inventory` bound nothing, so
#: the image grid's filename cell was in the population only because an
#: unrelated `.map(([src, alt]) =>` bound the word `src` and `i.src` held
#: it - found at item 241, when the cell became `fileOf(fileSrc(i))`.
_BIND = re.compile(r"const\s+(\w+)\s*(?::\s*[^=]+?)?=\s*(.+)$")


def _statements(text: str) -> list[str]:
    """Source lines, with a `const` binding joined into one statement.

    Line-based reading was the first version and it was wrong in the way
    that matters: a render site bounded by a `.filter(` on the line *below*
    its `const` read as unbounded, so the guard would have demanded a second
    bound for one that was already there. A binding is accumulated until its
    brackets balance and it ends in `;`.
    """
    lines, out, i = text.split("\n"), [], 0
    while i < len(lines):
        line = lines[i]
        if _BIND.search(line):
            stmt, depth = line, 0
            while True:
                depth += (stmt.count("(") + stmt.count("[")
                          - stmt.count(")") - stmt.count("]"))
                if (depth <= 0 and stmt.rstrip().endswith(";")) \
                        or i + 1 >= len(lines):
                    break
                i += 1
                stmt += " " + lines[i].strip()
                depth = 0
            out.append(stmt)
        else:
            out.append(line)
        i += 1
    return out


#: `const [x, setX] = useState` - the state variable a crawl collection is
#: hoisted into, and the setter that puts it there.
_STATE = re.compile(r"const\s*\[\s*(\w+)\s*,\s*(set\w+)\s*\]\s*=\s*useState")


def _named_roots(text: str) -> set[str]:
    """Local names holding a *named* crawl payload, from their type annotation.

    `facts: Facts` is how the anatomy panel receives its payload, and it was
    the one root this guard knew - spelled as the literal string `facts.`
    rather than derived, so a second screen naming its payload anything else
    was invisible.

    **Stated limit: this is file-scoped and `_fetch_roots` is not.** The
    caller unions one whole-file set of named roots into every block, so an
    ordinary local sharing a name with a payload root anywhere in the file
    is read as that payload everywhere in it. Only `anatomy.tsx` has a named
    root today (`facts`), so the blast radius is one identifier in one file
    - measured, not assumed: `_named_roots` returns a non-empty set for
    exactly one of the 21 sources. It is recorded here rather than fixed
    because the fix is to scope the annotation to the block that carries it,
    which is `_blocks`' concern and a separate change.
    """
    return {m for name in NAMED_PAYLOADS
            for m in re.findall(r"(\w+)\s*:\s*" + name + r"\b", text)}


def _fetch_roots(text: str) -> set[str]:
    """Callback parameters receiving a crawl-route response, in this scope.

    An inline payload has no type name, so the only thing that identifies its
    response object is the call that produced it: within a scope that fetches
    a crawl route, the parameter of a `.then(` is that response. Scoped to
    the block rather than the file so a `.then((d) =>` elsewhere in the same
    screen is not read as a payload.
    """
    if not any(re.search(r, text) for r in CRAWL_ROUTES):
        return set()
    return set(re.findall(r"\.then\(\s*\(?\s*(\w+)\s*\)?\s*=>", text))


def _reads(expr: str, roots: set[str], field: str) -> bool:
    """Does `expr` read `<a payload root>.<field>`?"""
    return any(re.search(r"\b" + re.escape(r) + r"\s*\.\s*" + field + r"\b", expr)
               for r in roots)


def _chains(text: str, fields: list[str],
            roots: set[str]) -> dict[str, tuple[str, bool]]:
    """Local name -> (crawl field it derives from, bounded anywhere in chain).

    Bounded means the chain passes through `.slice(` - a cap - or a
    `.filter(` whose predicate reads a `useState` value declared in the same
    file. The `useState` requirement is what stops `.filter(Boolean)` and
    `.filter((g) => g !== "workflow")` from counting: those narrow a list by
    a rule the operator cannot change, which is not a control, and the
    invariant asks for a control.

    Two ways a chain starts, because the product has two. A payload passed
    down as a prop is read straight off its root - `const rows =
    facts.headings`. A payload *fetched* by the screen that renders it is
    hoisted into `useState` first, so the chain starts at the setter call and
    the local name is the state variable: `setPages(d.pages ?? [])` makes
    `pages` the page list. Only the first shape existed here, and it is why
    every render site this guard could name lived in the one screen that
    receives its payload as a prop (CQ-144).
    """
    state = set(_STATE.findall(text))
    names = {n for n, _ in state}
    chain: dict[str, tuple[str, bool]] = {}
    # The setter hop runs *before* the bindings, and the order is the whole
    # point rather than a detail. The binding loop resolves an alias only
    # against what it already knows, so with the hop second, `const shown =
    # pages.filter(…)` is read while `pages` is still an ordinary local and
    # the alias is never linked. Measured while this was being written: the
    # bounded page pickers then reported *no* render site for `pages` at all,
    # which the parametrized clause reads as "rendered nowhere" — a fixed
    # render site disappearing into a pass is the failure mode this whole
    # file exists to remove. A setter is a declaration wherever it sits, so
    # it is read first; the setter call is not a `const`, so `_statements`
    # does not join it and it is read line by line.
    #
    # Stated limit, and the reason it is a limit rather than a bug fixed
    # here: the hop matches only a *direct* read of the payload field in the
    # setter's own argument. `setPages(d.pages ?? [])` links `pages`;
    # `const rows = d.pages ?? []; setPages(rows);` does not, and the state
    # variable drops out of the chain. Reproduced by rewriting `tools.tsx`'s
    # fetch that way in memory and re-deriving.
    #
    # `8fe5c74`'s commit body records this as silently removing a whole file
    # from the population - "tools.tsx dropped out and the payload-
    # declaration clause fell to two files". **That overstates it, and the
    # correction belongs here rather than in a commit body nobody rereads.**
    # In the reproduction `pages` did leave the chain and `tools.tsx` kept
    # its render site anyway, through the downstream alias `const shownPages
    # = pages.filter(...)`. So the defect is real and its consequence is
    # conditional on nothing downstream re-deriving the link.
    #
    # Not fixed in the same step as the comment stripper: resolving the
    # setter's argument through `_statements` is chain resolution, not text
    # reading, and bundling them would make a regression ambiguous between
    # the two.
    setters = {s: n for n, s in state}
    for line in text.split("\n"):
        for m in re.finditer(r"\b(set\w+)\(", line):
            name = setters.get(m.group(1))
            if not name or name in chain:
                continue
            arg = line[m.end():]
            for f in fields:
                if _reads(arg, roots, f):
                    chain[name] = (f, _bounds(arg, names))
                    break
    for line in _statements(text):
        m = _BIND.search(line)
        if not m:
            continue
        name, expr = m.group(1), m.group(2)
        for f in fields:
            if _reads(expr, roots, f):
                chain[name] = (f, _bounds(expr, names))
                break
        else:
            for known, (f, bounded) in list(chain.items()):
                if known != name and re.search(r"\b" + known + r"\b", expr):
                    chain[name] = (f, bounded or _bounds(expr, names))
                    break
    return chain


def _bounds(expr: str, state: set[str]) -> bool:
    if ".slice(" in expr:
        return True
    for call in re.findall(r"\.filter\((.*)", expr):
        if any(re.search(r"\b" + s + r"\b", call) for s in state):
            return True
    return False


#: A top-level declaration, which is where one component's scope begins.
_TOP = re.compile(r"^(?:export\s+)?(?:async\s+)?(?:function\s+\w+|const\s+\w+\s*=)")


def _blocks(text: str) -> list[tuple[int, list[str]]]:
    """(first line number, lines) per top-level declaration.

    Scoping is not tidiness. `anatomy.tsx` binds `const rows` twice — to
    `facts.headings` in `Outline` and to `facts.images` in `ImagesTable` —
    and a file-scoped chain let the second overwrite the first, which
    attributed the outline's render site to `images` and reported `headings`
    as rendered nowhere. A field this guard believes is rendered nowhere is
    a field it silently passes, which is the failure mode it exists to
    remove, so the scope has to be the component.
    """
    lines = text.split("\n")
    starts = [i for i, l in enumerate(lines) if _TOP.match(l)] or [0]
    if starts[0] != 0:
        starts.insert(0, 0)
    bounds = starts + [len(lines)]
    return [(bounds[n] + 1, lines[bounds[n]:bounds[n + 1]])
            for n in range(len(starts))]


def _render_sites_in(name: str, whole: str,
                     fields: list[str]) -> list[tuple[str, str, int, bool]]:
    """`render_sites()` for one file's text, so the derivation can be driven.

    Split out from `render_sites()` rather than inlined there because a
    derivation that can only be run against the files on disk cannot be
    asked what it does to text it has not been handed — and "what does this
    guard cover" is the question the guard exists to answer.
    `test_a_comment_cannot_change_what_this_guard_covers` is what needed it.
    """
    found = []
    whole = _strip_comments(whole)
    named = _named_roots(whole)
    for first, lines in _blocks(whole):
        text = "\n".join(lines)
        roots = named | _fetch_roots(text)
        chain = _chains(text, fields, roots)
        state = {n for n, _ in _STATE.findall(text)}
        for n, line in enumerate(lines, first):
            for f in fields:
                for r in roots:
                    m = re.search(re.escape(r) + r"\." + f + r"\b(.*?)\.map\(",
                                  line)
                    if m:
                        found.append((f, name, n, _bounds(m.group(0), state)))
            for local, (f, bounded) in chain.items():
                m = re.search(r"\b" + local + r"\b(.*?)\.map\(", line)
                if m and "const " not in line:
                    found.append((f, name, n,
                                  bounded or _bounds(m.group(0), state)))
    return found


def render_sites() -> list[tuple[str, str, int, bool]]:
    """(field, file, line, bounded) for every `.map(` over a crawl collection."""
    fields = collections_()
    return [s for path in _sources()
            for s in _render_sites_in(path.name, _source_text(path), fields)]


def test_the_population_is_the_crawl_payloads_own_declaration():
    """The guard reports what it covered, not a bare pass.

    A derived population can silently become empty — a rename of `type
    Facts`, a change to how fields are declared — and a guard over an empty
    population passes every time. This is the assertion that the derivation
    still finds something to check.
    """
    fields = collections_()
    assert len(fields) >= 10, (
        "the crawl payloads declare fewer array fields than the ten this "
        f"was derived against, so the derivation has probably broken: {fields}")
    # The population is *payloads*, plural, and this is the assertion that
    # says so. A population derived from one payload can only ever name
    # render sites in the one screen that reads it, and it passes while doing
    # so — round 069 widened the file sweep to every `dashboard/src/*.tsx`
    # and still returned seven render sites, all `anatomy.tsx`, over two
    # unbounded page pickers on two other screens. That was CQ-144, and a
    # count of sites could not have caught it: seven is a healthy number.
    # What has to be true is that more than one screen is reachable.
    screens = {p for _, p, _, _ in render_sites()}
    assert len(screens) >= 3, (
        "every render site this guard can see is in "
        f"{sorted(screens)}, so its population is one screen's payload "
        "however wide the file sweep is. Add the payload the other screens "
        "read to NAMED_PAYLOADS or CRAWL_ROUTES.")
    sites = render_sites()
    assert len(sites) >= 6, (
        "no render sites were found over the crawl's own collections, so "
        "this guard is passing over an empty population: "
        f"{fields} against {[p for _, p, _, _ in sites]}")
    # A field the detection cannot see is a field this guard *skips*, which
    # reads as a pass. It happened while this was being written — a chain
    # scoped to the file rather than the component lost `headings` entirely,
    # and the parametrized case went green as a skip. These two are the
    # instances the invariant was promoted for, so if the detection stops
    # finding them it has broken, whatever the rest of it still reports.
    rendered = {f for f, _, _, _ in sites}
    for founding in ("headings", "images"):
        assert founding in rendered, (
            f"facts.{founding} is rendered by the anatomy panel and this "
            "guard can no longer find its render site, so its case now "
            "passes as a skip rather than checking anything")
    # Clause two has the same failure mode and, until report 069, had no
    # equivalent assertion — which is exactly how it went wrong. Round 068
    # derived clause two's population from a window and moved `ImagesTable`
    # out of that window in the same commit, so the cell that founded this
    # invariant sat outside the guard written to cover it and nothing went
    # red. `audits/DISPOSITIONS.md` then struck the row as taken.
    #
    # Keyed on what the site renders rather than on its line number, on
    # purpose: `anatomy.tsx:980` is the anchor three registers have already
    # recorded wrongly, and an assertion keyed on a line is one more thing
    # that goes stale silently. A count would not do either — any ten sites
    # satisfy `len(...) >= 10`, and what has to be true is that *this* one is
    # among them.
    #
    # The cell moved at brief v15 step AR: the images table became a grid on
    # the part page, so the filename it renders is `.img-name` on
    # `fileOf(i.src)` in `part_page.tsx` and the old `.fact-mono` cell went
    # with the table it was a cell of. The site is repointed and the reason
    # is not — a filename is still the longest unbroken token the crawl
    # hands the screen, and still the one element that has actually failed.
    # Item 241: it names `fileSrc(i)` now - the file a lazy loader swaps in
    # where `src` is its placeholder - which is still a crawled filename.
    founding = [s for s in _crawl_derived_string_sites()
                if s[0] == "part_page.tsx" and "img-name" in s[2]
                and "fileSrc(i)" in s[3]]
    assert founding, (
        "the image grid's filename cell — `.img-name` on `{fileOf(fileSrc(i))}`, "
        "the site that founded this invariant when a 140-character filename "
        "widened the Image column until Alt text left the screen — is not "
        "in clause two's population, so the guard for that clause is passing "
        "over the one element that has actually failed: "
        + str([(f, ln, c) for f, ln, c, _ in _crawl_derived_string_sites()]))


def test_a_comment_cannot_change_what_this_guard_covers():
    """Prose about the code is not the code, and this guard could not tell.

    Both derivations above match against raw source lines, and neither knew
    what a comment was — so a `//` line quoting a render site put that
    quotation into the population, and a block comment quoting `facts.` put
    it into clause two's. A guard whose coverage can be changed by writing a
    sentence cannot say what it covers, which is the one thing this file
    exists to be able to say.

    **This was already being worked around by hand rather than fixed.** The
    commit that closed WF-88 and CQ-143 recorded three limits it hit here,
    one of them this: "it reads `//` lines as source, so the comment
    explaining the first dead end re-created the phantom by quoting code. The
    comment is prose-only for that reason." A comment forbidden from quoting
    code, in the file whose every other comment quotes code, is a workaround
    with no assertion behind it — and `anatomy.tsx:778` already carries
    ``*  `headings` is `facts.headings[:HEADING_CAP]``` in a block comment.

    Measured before the fix, by inserting one line into `tools.tsx`'s text
    and re-deriving: `render_sites()` went from 9 sites to 10, the extra one
    `('pages', 'tools.tsx', 346, False)`. `pages` holds no
    `UNBOUNDED_BY_MEASUREMENT` row, so that phantom is not noise — it is a
    red suite, on a gate that runs on every push, caused by a comment.

    The mutation is derived from each file's own render sites rather than
    written here, so this cannot rot into a check against one hand-picked
    line the way `UNBROKEN_TOKEN_CLASSES` did. Every site is quoted back at
    itself: whatever the guard reports for a file, commenting out a copy of
    the line it reported must report the same thing.
    """
    fields = collections_()
    checked = 0
    for path in _sources():
        text = path.read_text(encoding="utf-8")
        before = _render_sites_in(path.name, text, fields)
        strings = _string_sites_in(path.name, text, fields)
        if not before and not strings:
            continue
        checked += 1
        lines = text.split("\n")
        # Quote every reported line back as a comment, deepest first so the
        # earlier insertions do not move the later addresses.
        at = sorted({n for _, _, n, _ in before} | {n for _, n, _, _ in strings},
                    reverse=True)
        for n in at:
            lines.insert(n, "        // " + lines[n - 1].strip())
        mutated = "\n".join(lines)
        # Compared without line numbers: the insertions shift every address
        # below them, and it is the *population* that must not move.
        assert _sig(_render_sites_in(path.name, mutated, fields)) \
            == _sig(before), (
            f"commenting out a copy of each render site in {path.name} "
            "changed what clause one covers, so a comment quoting code is "
            "read as code: "
            f"{_sig(before)} -> {_sig(_render_sites_in(path.name, mutated, fields))}")
        assert _sig(_string_sites_in(path.name, mutated, fields)) \
            == _sig(strings), (
            f"commenting out a copy of each string site in {path.name} "
            "changed what clause two covers: "
            f"{_sig(strings)} -> {_sig(_string_sites_in(path.name, mutated, fields))}")
    assert checked >= 2, (
        "fewer than two source files reported any site at all, so this "
        f"clause is asserting invariance over almost nothing: {checked}")


def _sig(sites: list[tuple]) -> list[tuple]:
    """A population with its line numbers dropped, for comparing across edits."""
    return sorted(tuple(str(p) for i, p in enumerate(s) if not isinstance(p, int))
                  for s in sites)


@pytest.mark.parametrize("field", sorted(collections_()))
def test_a_crawl_derived_collection_is_bounded_where_it_is_rendered(field: str):
    """Clause one: bounded at the render site by a filter or pagination.

    A field rendered nowhere must hold a row in `RENDERED_NOWHERE` saying so
    — it does not pass for free, because "this guard found no render site"
    and "this field has no render site" are the same sentence from the
    detection and from the code, and only one of them is a fact. A field
    rendered somewhere must either bound it, or hold a row in
    `UNBOUNDED_BY_MEASUREMENT` stating the ceiling that makes leaving it
    unbounded honest.
    """
    sites = [s for s in render_sites() if s[0] == field]
    if not sites:
        assert field in RENDERED_NOWHERE, (
            f"facts.{field} has no render site this guard can see. Either it "
            "is rendered somewhere the detection cannot follow — in which "
            "case the detection is broken and this clause is now passing "
            "over a real render site — or it is genuinely rendered nowhere, "
            "in which case add a row to RENDERED_NOWHERE with the reason and "
            "where it was checked.")
        return
    unbounded = [f"{p}:{ln}" for _, p, ln, ok in sites if not ok]
    if not unbounded:
        return
    assert field in UNBOUNDED_BY_MEASUREMENT, (
        f"facts.{field} is rendered from crawl data at {', '.join(unbounded)} "
        "with no filter, no pagination and no cap, which the real-data-scale "
        "invariant forbids. Bound it at the render site, or — if its measured "
        "ceiling is small enough that a control would be furniture — add a row "
        "to UNBOUNDED_BY_MEASUREMENT with the number and where it was measured.")


#: A `.map(` and what it binds: either destructured — `.map(([src, alt], i)`
#: — or a plain parameter, `.map((l) =>`. The head is captured so the caller
#: can ask whether the thing being mapped is a crawl collection at all.
_MAPPED = re.compile(r"\b(\w+)\b[^;]*?\.map\(\s*\(?\s*(?:\[([^\]]*)\]|(\w+))")

#: An element with a class list rendering a single braced expression.
_RENDERED = re.compile(r'className="([a-z0-9 \-]+)"[^>]*>\s*\{(.+?)\}')


def _crawl_derived_string_sites() -> list[tuple[str, int, list[str], str]]:
    """(file, line, classes, expression) for elements rendering a crawl string.

    Derived the way `render_sites()` derives clause one's population, and by
    the same helpers: every top-level block of every `dashboard/src/*.tsx`,
    with `_chains()` resolving a local name back to the crawl field it came
    from. Crawl-derived means the rendered expression reads `facts.`
    directly, or reads a name the component bound out of a `.map(` over one
    of the payload's own collections — which is how the images table's `src`
    reaches a cell three lines from any mention of `facts`.

    **This was a window, and the window is why CQ-27 reached eleven rounds.**
    It ran from `function PageFactsBody` to `const Row = `: two hand-picked
    landmark lines. Round 068 derived this population *and* moved
    `ImagesTable` out of that window in the same commit, so the cell that
    founded the invariant — a 140-character filename that widened the Image
    column until Alt text left the screen — sat outside the guard written to
    cover it. Nothing went red, and `audits/DISPOSITIONS.md` struck the row
    as taken.

    **Widening the window would not have been enough, which is the dead end
    worth leaving here.** The old `bound` derivation required `facts.<field>`
    and `.map(` on one source line, and no line in `anatomy.tsx` carries
    both: `ImagesTable` maps over `shown`, aliased from `facts.images`
    through `rows`. So the remedy as written — move the window's end past
    `ImagesTable` — still returned a population without the images cell in
    it. Measured either way before this was rewritten: the old derivation
    found four sites, at `anatomy.tsx:1059`, `:1067`, `:1076` and `:1081`.
    The alias-following that actually closes the gap already existed one
    clause up in `_chains()`; it was simply never shared, and re-deriving it
    here rather than calling it is how the two clauses would drift apart
    again.

    Scoped to the whole file set rather than to one component, so a site
    added to another screen joins the guard on the day it is written rather
    than on the day somebody widens a window to reach it.

    **The sentence that used to end that paragraph was the next defect, and
    it is corrected rather than deleted.** It read "today every crawl-derived
    string site is in `anatomy.tsx`, so the sweep costs nothing" — offered as
    the justification for the sweep, and true only because the *fields* came
    from `type Facts`, which is anatomy's payload. A file sweep over a
    single-payload field list cannot return a site anywhere else, so the
    observation was a property of the derivation reported as a property of
    the product. Report 070 filed it as CQ-144.

    **Three limits, all met while this was being written, all stated rather
    than fixed** — a guard whose coverage is unstated is the thing CQ-27 was.

    1. `bound` is one flat set per component, so two `.map(` callbacks in one
       component that name their parameter the same thing merge. Observed:
       `PageFactsBody` binds `l` twice — `facts.link_sample.map((l, i)` at
       `anatomy.tsx:1177` and `a.landmarks.map((l)` at `:1162` — so the
       landmark chip is reported as crawl-derived on the link sample's
       binding. It over-includes rather than under-includes, which is the
       safe direction for a guard and the opposite of what went wrong here;
       and in this instance the element it over-included renders a crawl
       string anyway, since a landmark role is read off the page too.
       Scoping `bound` to each callback's own extent is the fix and is a
       parser, not a regex.
    2. `_RENDERED` requires a `className`, so an element styled by a
       descendant selector is invisible to this guard. Observed at
       `anatomy.tsx:1180`, `<code>{l.url}</code>` — a URL, the exact fault
       class this invariant exists for — which *is* wrapped, by
       `.anchor-list code { overflow-wrap: anywhere; }` in `styles.css`, and
       is correct by luck rather than by this guard. Reading descendant
       selectors means resolving CSS specificity against a DOM this test
       never builds; `test_reflow.py` drives the real one at 320px and is
       where that belongs.
    3. Only `_named_roots()` counts here, so clause two sees a payload passed
       down as a prop and not one a screen fetches for itself. Clause one
       reads both. The asymmetry is deliberate and costs nothing today: an
       inline payload's root is a `.then(` parameter, typically one character
       — `d` — and `\\bd\\.` inside a rendered expression matches far more
       than it should, while the two render sites the fetched payload
       actually has are `<option>` elements, which limit 2 already excludes
       for having no `className`. Both would have to be answered together,
       and answering either one alone would only add noise.
    """
    fields = collections_()
    return [s for path in _sources()
            for s in _string_sites_in(path.name, _source_text(path), fields)]


def _string_sites_in(name: str, whole: str,
                     fields: list[str]) -> list[tuple[str, int, list[str], str]]:
    """`_crawl_derived_string_sites()` for one file's text.

    Split out for the same reason as `_render_sites_in`: both clauses'
    populations have to be drivable against text for the comment clause to
    be able to assert anything about either of them.
    """
    sites: list[tuple[str, int, list[str], str]] = []
    whole = _strip_comments(whole)
    named = _named_roots(whole)
    for first, lines in _blocks(whole):
        text = "\n".join(lines)
        chain = _chains(text, fields, named | _fetch_roots(text))
        bound: set[str] = set()
        for line in lines:
            for m in _MAPPED.finditer(line):
                reads_crawl = m.group(1) in chain or any(
                    _reads(line, named, f) for f in fields)
                if not reads_crawl:
                    continue
                if m.group(2):
                    bound |= {n.strip() for n in m.group(2).split(",")
                              if n.strip()}
                elif m.group(3):
                    bound.add(m.group(3))
        for i, line in enumerate(lines, first):
            for m in _RENDERED.finditer(line):
                expr = m.group(2)
                crawly = any(re.search(r"\b" + re.escape(r) + r"\.", expr)
                             for r in named) or any(
                    re.search(r"\b" + n + r"\b", expr) for n in bound)
                if crawly:
                    sites.append((name, i, m.group(1).split(), expr))
    return sites


def test_an_element_rendering_a_crawl_string_can_break_it():
    """Clause two, with the population derived instead of hand-kept.

    This is what `UNBROKEN_TOKEN_CLASSES = ("fact-mono",)` was. `.fact-mono`
    is the class that has actually caused a fault — a 140-character filename
    in the images cell widened the Image column until Alt text left the
    screen — and it was in that tuple because it had already gone wrong. The
    point of deriving is that the next one is in the population before it
    goes wrong.

    The union of an element's classes is what has to declare the wrapping,
    not each class on its own: three of `.fact-mono`'s four uses pair it with
    `.fact-val`, which already carries `overflow-wrap: anywhere`, and a rule
    demanding it of every class would have demanded it of `.fact-key`.
    """
    css = CSS.read_text(encoding="utf-8")
    sites = _crawl_derived_string_sites()
    assert sites, ("no crawl-derived string render sites were found in any "
                   "dashboard source, so this guard is checking nothing")
    offenders = []
    for name, line, classes, expr in sites:
        declared = ""
        for cls in classes:
            for rule in re.finditer(rf"^\.{re.escape(cls)}\s*\{{([^}}]*)\}}",
                                    css, re.MULTILINE):
                declared += rule.group(1)
        if "overflow-wrap" not in declared:
            offenders.append(
                f"{name}:{line} — {'.'.join([''] + classes)} on "
                f"{expr.strip()[:48]}")
    assert not offenders, (
        "an element renders a crawl-derived string and none of its classes "
        "declares `overflow-wrap`, so one unbroken token — a URL, a filename, "
        "a cipher suite — cannot be broken and widens its column until the "
        "one beside it leaves the screen:\n  " + "\n  ".join(offenders))


# --- the same invariant, on the screen, in a browser -------------------------
#
# Everything above reads source, and source cannot tell a filter that filters
# from one that renders a control and narrows nothing. These two drive the
# built bundle against the fixture crawl and read the counts back out of the
# rendered page, which is what makes the bounding a measurement rather than a
# shape. Fixtures, the `live` gate and the page-opening helper are reused from
# the tests that already drive this panel rather than rebuilt beside them.

from tests.test_a11y_rendered import DIST, served  # noqa: E402,F401
from tests.test_heading_fault import (  # noqa: E402,F401
    browser_page, live, open_headings)
from tests.parts import open_part, open_page_filter


def _open_images(pg, base: str, site: str, path: str) -> None:
    """Images, for one page — the same two steps `open_headings` needs, and
    for the same reason: the facts half renders only once a page is chosen."""
    pg.goto(f"{base}/#/sites/{site}?tab=findings", wait_until="load")
    pg.wait_for_selector(".anat-layout", timeout=15_000)
    open_part(pg, 'Images')
    open_page_filter(pg)
    pg.fill(".page-find", path)
    # The part's own card since brief v15 step AR, where the facts panel and
    # its alt filter were.
    pg.wait_for_selector(".now-card", timeout=15_000)
    pg.wait_for_selector(".img-grid-body .img-card", timeout=15_000)
    pg.wait_for_timeout(300)


@live
def test_the_outline_card_states_nothing_dropped_when_the_crawl_kept_all(served,
                                                                        browser_page):
    """UX-60's negative half. `/deep` keeps all 15 of its 15 headings against
    HEADING_CAP=60, so the crawl dropped nothing and the not-kept notice must
    not appear. The tagged list, its `show all N` control and the level filter
    that once narrowed it retired with Q-51 (2026-09-07); the outline is now
    the v16d ladder, and the card must still state the crawl's own limit only
    when the crawl hit it. The positive half — the notice present and unmoved
    on a truncated page — is the test below, on `/many`.
    """
    base, ids = served
    open_headings(browser_page, base, ids["site"], "/deep")
    assert browser_page.query_selector(".ho-ladder"), "the ladder did not render"
    assert not browser_page.query_selector(".not-kept"), (
        "`/deep` carries 15 headings against HEADING_CAP=60, so the crawl "
        "dropped nothing and there is nothing for a not-kept notice to say: "
        + browser_page.inner_text(".not-kept"))


@live
def test_the_crawls_own_limit_is_stated_whatever_the_filter_shows(served,
                                                                 browser_page):
    """UX-60. The sentence is about the crawl, so a filter cannot silence it.

    `/many` is the only fixture page the crawl truncates — 71 headings and 65
    images against caps of 60 — and it exists for this clause. Measured over
    every `*_HTML` constant before it was added: 15 headings and 4 images
    were the maxima, so `heading_total > len(headings)` was false on every
    crawled page and the branch that says what the crawl dropped had never
    rendered under any test in this repository. A guard whose fixture cannot
    express the failure can only ever pass, which is DISCIPLINE rule 5.

    Both surfaces are driven, not one. A clause covering "the not-kept
    notice" would go green on whichever it reached and retire the question
    for the other — CQ-144's shape, one layer out. The counts differ on
    purpose, 11 against 5, so a component reading the wrong total is caught
    rather than accommodated.

    The two tails were the same four lines of JSX written twice in
    `anatomy.tsx`; at brief v14 step AP and brief v15 step AR each part took
    its own card, so they are now the outline card's `NotKept` and the image
    grid's own sentence. Two writings still, on two screens, which is why
    this clause still drives both.
    """
    base, ids = served
    open_headings(browser_page, base, ids["site"], "/many")

    # The unfiltered state first: what the crawl kept, and the tally above
    # the list, which counts the whole page. Their disagreement is the
    # finding — `heading_counts` comes from `heading_levels`, stored
    # uncapped at `evidence.py:214`, while `headings` is capped at 60.
    # The card's own bound and the crawl's are two different numbers, and
    # the second is the one this clause is about. Since brief v14 step AP
    # the outline card carries both: `show all N` is what it is holding
    # back, and the notice is what the crawl never had.
    notice = browser_page.inner_text(".not-kept").strip()
    kept = int(re.search(r"kept (\d+) of", notice).group(1))
    total = int(re.search(r"of the (\d+) headings", notice).group(1))
    assert total > kept, (
        f"the fixture stopped being able to express the defect: the crawl "
        f"kept {kept} of {total}, so nothing was dropped to state")

    # The reveal-and-re-read half of UX-60 is on the image surface below now.
    # Q-51 retired the headings list and its `show all` control, so on the
    # headings card there is no longer a control that grows the outline; the
    # ladder shows what the crawl kept. Here the headings notice is asserted
    # present and stating the crawl's total; that the notice does not move when
    # a list is revealed is proven on `/many`'s image grid, which still has the
    # control. The point the two-surface drive protects — a notice rendered
    # from the wrong total — survives: the counts differ, 11 against 5.

    # The second surface, same rule, different numbers.
    _open_images(browser_page, base, ids["site"], "/many")
    img_notice = browser_page.inner_text(".not-kept").strip()
    img_kept = int(re.search(r"kept (\d+) of", img_notice).group(1))
    img_total = int(re.search(r"of the (\d+) images", img_notice).group(1))
    assert img_total > img_kept, (
        f"the fixture stopped being able to express the defect: the crawl "
        f"kept {img_kept} of {img_total} images, so nothing was dropped to state")
    assert img_notice != notice, (
        "the heading and image notices carry different counts on this page — "
        "11 dropped against 5 — so reading the same sentence at both means "
        f"one of them is rendered from the other's total: {img_notice!r}")

    # The name filter went with the facts panel at brief v15 step AR. The
    # control that still changes how much of the list stands is the reveal,
    # and it is held to the rule the filter was: what the crawl kept is a
    # fact about the crawl, so the sentence must not move when the grid
    # grows. The reveal is what makes that testable here — 24 cards stand
    # against 60 kept, so a notice rendered from the grid rather than from
    # the crawl would say 24 and then say 60.
    cards = browser_page.eval_on_selector_all(".img-grid-body .img-card", "els => els.length")
    assert 0 < cards <= img_kept, f"the grid shows {cards} of the {img_kept} kept"
    more = browser_page.query_selector(".now-card .out-more button")
    assert more is not None, (
        f"the fixture page keeps {img_kept} images and the grid shows all "
        f"{cards} of them, so this clause has nothing to press and cannot "
        "tell a notice that moves from one that does not")
    more.click()
    browser_page.wait_for_timeout(200)
    opened = browser_page.eval_on_selector_all(".img-grid-body .img-card", "els => els.length")
    assert opened > cards, (
        f"the reveal rendered but revealed nothing: {cards} -> {opened}")
    assert browser_page.inner_text(".not-kept").strip() == img_notice, (
        "the crawl's limit is not a fact about how much of the grid stands, "
        "on this surface either: " + browser_page.inner_text(".not-kept").strip())


@live
def test_every_image_states_its_own_alt(served, browser_page):
    """The question the panel was opened with — which images have no alt
    text — answered on the face of every card, instead of behind a control.

    Renamed at brief v15 step AR, which replaced the facts panel and its alt
    filter with a grid that states each image's alt beside the image. The
    filter's whole purpose was to reach a subset the reader could not see;
    a grid that spells out `alt missing`, `alt empty` or the alt itself on
    every card has no subset to reach. What survives the move is the fixture
    discipline the filter clause was built for, below.

    Driven against `/gallery`, and the choice of page *is* the assertion.
    That page carries four images — two with no alt attribute, one
    described, one `alt=""` — so all three readings are on screen at once
    and a card that printed the same word for every image would fail here.
    The clause opened `/deep` for two rounds, which carries one image, and
    that one image is the one missing its alt attribute: every count agreed
    with itself by identity and the clause passed against a control that did
    nothing. Report 070 filed that as CQ-141, and a fixture that stops being
    able to express the defect is the failure mode `.claude/DISCIPLINE.md`
    rule 5 names. `assert cards > 1` and the `alt missing` assertion below
    are what keep this page held to it.
    """
    base, ids = served
    _open_images(browser_page, base, ids["site"], "/gallery")

    cards = browser_page.eval_on_selector_all(".img-grid-body .img-card", "els => els.length")
    assert cards > 1, f"the fixture page renders too few images to read: {cards}"

    # The alt filter went with the panel at brief v15 step AR. What must
    # still hold is that every card states its own alt - verbatim, empty or
    # missing, never blank - so a reader can tell the three apart without a
    # control, and that the grid is bounded where it is rendered, which is
    # the half of this clause the invariant beside it also asks for.
    alts = browser_page.eval_on_selector_all(
        ".img-grid .img-alt", "els => els.map((e) => e.innerText.trim())")
    assert len(alts) == cards, (len(alts), cards)
    assert all(a for a in alts), alts
    assert any(a == "alt missing" for a in alts), alts
    more = browser_page.query_selector(".now-card .out-more button")
    assert (cards <= 24) == (more is None), (
        f"the grid holds {cards} cards and "
        f"{'offers' if more else 'offers no'} control to see the rest")



#: The picker's own option list, asked whether it has narrowed off `was`.
#: `document.querySelectorAll` rather than a Playwright locator because the
#: caller's `opts` is already a raw CSS selector and the count is the whole
#: question.
OPTIONS_NARROWED = """([sel, was]) => {
  const n = document.querySelectorAll(sel).length;
  return n > 0 && n < was;
}"""

#: The same list, asked whether it is down to exactly `want` options - the
#: empty-result half, where `want` is 1 for a picker with a pinned selection
#: and 0 for one without.
OPTIONS_LEFT = """([sel, want]) =>
  document.querySelectorAll(sel).length === want"""


def _settled(pg, js: str, arg) -> None:
    """Wait for the option list to reach `js`, and swallow the timeout.

    KI-22, and Q-31's authorisation to rearrange it. Both call sites below
    were `pg.wait_for_timeout(200)`: under `-n auto` beside seven other
    Chromium workers, 200ms is not enough for React to re-render and the
    clause reads the list it had before the fill. Measured at round 109's
    preflight - `test_the_brief_target_picker_is_narrowed_by_its_url_filter`
    red in the pinned suite, green alone immediately after with a 0.88s call.
    That is the third node KI-22 has collected and the second file, and the
    fix the row has prescribed since 2026-08-19 is this one: wait on the
    state, not on a duration.

    **The timeout is swallowed deliberately, and that is what keeps this a
    strengthening rather than the weakening CQ-212 warns about.** The
    condition waited on *is* the assertion's own, so a bare `wait_for_function`
    would turn a picker that stopped filtering into a timeout with no message.
    Falling through instead means the caller's assertion runs either way: a
    slow picker is now waited for and passes, a broken one still fails on the
    sentence that names what it did. The only cost of the swallow is that a
    genuine break takes the timeout rather than 200ms to report - paid once,
    on a red run, and worth the false red it removes from every green one.

    There is no distinct 'the filter was applied' signal to wait on instead:
    `.page-count` renders `N URLs fetched` or `N of M URLs fetched` keyed
    on whether the list
    narrowed (`views.tsx:1195-1199`, `tools.tsx:1061-1065`), so it carries the
    same information as the option count and not a second fact.
    """
    from playwright.sync_api import TimeoutError as PWTimeout
    try:
        pg.wait_for_function(js, arg=arg, timeout=10_000)
    except PWTimeout:
        pass


def _picker_narrows(pg, opts: str, needle: str, misses: str) -> None:
    """Hold one bounded page picker to the rule the outline is held to.

    One helper and two call sites, because `views.tsx` and `tools.tsx` render
    the same control twice and a clause written twice is how two screens end
    up reporting different totals for the same list — the defect B-12 closed
    in the product, re-entered from the test side.

    `needle` must match a strict subset of the crawled pages and `misses`
    none of them; both are asserted rather than assumed, for the reason the
    images clause above records: a filter that selects everything satisfies
    every count by identity, which is exactly what CQ-141 was.

    `opts` selects the option elements of this screen's own picker: both
    screens render exactly one `input[aria-label='page URL filter']`, so the
    filter needs no scoping, but a bare `select option` would collect the
    audience and template pickers beside it.

    **The pinned option, and it is correct.** `tools.tsx:217-218` keeps
    `p.url === pageUrl` in the list whatever the filter says, because that
    picker is a controlled `<select>` with a real selection: an option list
    that dropped its own current value would reset the operator's choice to
    whatever the filter happened to leave first. `views.tsx` has no pin
    because its picker is a navigation door with `defaultValue=""` and no
    selection to lose. Two screens, two right answers.

    This clause first asserted that every surviving option matches the
    needle, and the drive said otherwise — `['…/', '…/gallery']` for
    `gallery`, home being the default selection. The dead end is recorded
    here rather than fixed away: the assertion below allows exactly the
    selected value through and nothing else, so a picker that stopped
    filtering still fails while one that protects its selection passes.
    """
    sel = "input[aria-label='page URL filter']"
    sel_el = opts.split(" option")[0]

    # The page list arrives after the screen; under a parallel run it can
    # arrive after this reader, which read 0 twice on 2026-09-03.
    pg.wait_for_function("(o) => document.querySelectorAll(o).length > 1",
                         arg=opts, timeout=15_000)
    # The pinned selection is read AFTER that wait, and was read before it
    # until 2026-09-20. `tools.tsx` sets the options and the selected value in
    # one response handler, so before the options exist the value is still ""
    # - and an empty `pinned` turns the home option, which the pin is there to
    # protect, into "an option survived the filter without matching". That is
    # what the full suite reported while the file passed alone: the failure was
    # the reader arriving early, not the picker keeping the wrong row.
    pinned = pg.eval_on_selector(sel_el, "el => el.value") or ""
    before = pg.eval_on_selector_all(opts, "els => els.length")
    assert before > 1, f"the picker offers too few pages to narrow: {before}"
    # `startswith` rather than `==`, and only for the two counts the
    # Pages pane may extend: that pane appends a distinct-page clause when the
    # run fetched one page under two spellings (`16 URLs fetched · 15 distinct
    # pages (2 spellings of /apply)`), which is a second fact and not this
    # clause's. The prefix still separates the states it has to: a filtered
    # render reads `N of M URLs fetched` and does not begin `M URLs fetched`.
    assert pg.inner_text(".page-count").strip().startswith(f"{before} URLs fetched"), (
        "unfiltered, the count beside the picker must name the whole list: "
        f"{pg.inner_text('.page-count').strip()!r} against {before} options")

    pg.fill(sel, needle)
    _settled(pg, OPTIONS_NARROWED, [opts, before])
    after = pg.eval_on_selector_all(opts, "els => els.map(e => e.value)")
    assert 0 < len(after) < before, (
        f"the URL filter rendered but narrowed nothing: {before} -> "
        f"{len(after)} for {needle!r}")
    assert all(needle in u.lower() or u == pinned for u in after), (
        f"an option survived the {needle!r} filter without matching, and it "
        f"is not the pinned selection {pinned!r}: {after!r}")
    assert pg.inner_text(".page-count").strip().startswith(
            f"{len(after)} of {before} URLs fetched"), (
        f"the count says {pg.inner_text('.page-count').strip()!r} and the "
        f"picker holds {len(after)} of {before}")

    # The empty result, which is the state an unbounded list never had to have
    # a word for. A `<select>` with no options reads as "this site has no
    # pages" rather than "none match", so the placeholder has to say which.
    pg.fill(sel, misses)
    _settled(pg, OPTIONS_LEFT, [opts, 1 if pinned else 0])
    left = pg.eval_on_selector_all(opts, "els => els.map(e => e.value)")
    assert left == ([pinned] if pinned else []), (
        f"{misses!r} was supposed to leave nothing but the pinned selection "
        f"{pinned!r} and left {left!r}")
    assert pg.inner_text(".page-count").strip().startswith(f"{len(left)} of "), (
        f"an empty result must still say what it is empty of: "
        f"{pg.inner_text('.page-count').strip()!r}")


@live
def test_the_page_dossier_picker_is_narrowed_by_its_url_filter(served, browser_page):
    """`PageFinder` on the client screen — `views.tsx:1025-1032`, UX-19's
    first render site, bounded in round 070 and driven by nothing until here.

    `.page-count` sat in `PAINTED_BY_NOTHING` with the reason "the two page
    pickers this round bounded are driven by no browser test, which is
    CQ-141 one screen further out". This clause is what that row was
    waiting for; the class moves to `SELECTED_NOT_PAINTED` naming this test.
    """
    base, ids = served
    # Behind the Pages tab, reached by the product's own deep link rather
    # than by clicking: `?tab=pages` is read on mount and on hashchange
    # (`views.tsx:604-611`). Worth saying plainly, because it means the
    # `client` route in `test_a11y_rendered.ROUTES` has never painted this
    # control either — a route is not a screen, which is DISCIPLINE rule 4.
    browser_page.goto(f"{base}/#/sites/{ids['site']}?tab=pages", wait_until="load")
    browser_page.wait_for_selector("input[aria-label='page URL filter']",
                                   timeout=15_000)
    _picker_narrows(browser_page,
                    "select[aria-label='Open the dossier for a page'] "
                    "option:not([disabled])",
                    "gallery", "zzzz-no-such-page")


# RETIRED with item 188 (test_the_brief_target_picker_is_narrowed_by_its_url_filter):
#   this clause existed BECAUSE there were two pickers of the same shape in
#   two files - its own docstring says so: "one clause covering 'the page
#   picker' would go green on whichever one it happened to reach and retire
#   the question for the other". Item 188 removed one of the two. The
#   survivor is `views.tsx`'s `PageFinder`, and
#   `test_the_page_dossier_picker_is_narrowed_by_its_url_filter` drives it
#   through the same `_picker_narrows` helper, which stays.
