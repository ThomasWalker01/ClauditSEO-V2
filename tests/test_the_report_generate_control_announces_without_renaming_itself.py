"""The fourth control to carry a name that changes under the operator.

**UX-66, carried from report 100 to report 123.** `ReportView`'s "Generate"
button — the standalone report-generation control at
`dashboard/src/views.tsx` — swaps its own caption to `Generating…` while the
request is in flight. A button's label is its accessible name, so a name that
changes mid-press is announced as a *different control appearing*: the
operator who pressed one button is told another now has focus.

**The fix shape is three times precedented in this tree and was written down
each time.** `dashboard/src/reports.tsx:270-289` moved the busy word off the
Deliverables regenerate control (UX-64) and recorded the reason — *"A control
whose name changes mid-action is announced as a different control, and the
label is the accessible name — so the state has to be said beside it rather
than in it."* Round 111 applied it to `CompareView`'s generate control
(UX-88); round 112 applied it to `LauncherView`'s "Check this URL" (UX-96),
whose comment calls itself *"that convention taken a third time rather than a
fourth wording"*. This is the fourth time, and report 123's own remediation
table records that six consecutive reports named it without a round taking it.

**Why the region is mounted unconditionally.** A live region inserted into the
DOM in the same render as its content gives assistive technology nothing to
observe a change against, so the announcement most screen readers make is
none. The region has to be there ahead of the text. `Loading`
(`dashboard/src/components.tsx:775`) is the house pattern for the words;
`views.tsx:1814` (UX-88) is the house pattern for the always-mounted wrapper.

**Read from source, not driven.** These are claims about which element carries
which attribute. A Chromium drive would answer whether a screen reader
*speaks* it, which no test in this repository can answer — the same reading
`test_the_url_check_control_announces_without_renaming_itself.py` took of the
same defect one control earlier, and the clauses below are written in its
shape so a fix cannot satisfy one guard and defeat the other.

**The class, and what was deferred.** DISCIPLINE rule 3 asks for every consumer
from a grep rather than from the list a report happened to name. Report 123's
UX-66 row names five anchors and says *twenty* controls; the enumeration below
finds **twenty-nine**, which is the count the register records. Round 123 fixed
one — the control the report sequenced — and named the remaining twenty-eight
in `DEFERRED` rather than leaving them invisible.

**Round 135 swept twenty-seven of those twenty-eight, and relay 126 took the
last one.** The one left over was `components.tsx`'s `ErrorNote` retry, held
on an operator decision rather than on effort: `tests/test_fetch_state.py`
drove that control and asserted the busy word is inside its own text, which is
the defect. DISCIPLINE rule 6 says a test asserting the old wrong behaviour is
the operator's call, so round 135 left both standing and `QUESTIONS.md` Q-43
asked. The operator answered *fix the control and re-point the test* on
2026-09-02; the control now keeps the caption `Try again`, carries
`aria-busy={retrying}`, and says the busy word in the `<p role="alert">` it
already sits inside — not in a `role="status"` region like the other
twenty-seven, because a live region nested in a live region announces nothing
and a `<div>` inside a `<p>` is invalid besides. `DEFERRED` is now empty, and
the comparison stays exact in both directions: a thirtieth control added later
fails this file and is named in the failure.

Emptying it cost this file its population, and that had to be
replaced rather than dropped. `test_the_enumeration_still_finds_a_population` proved the reader
by finding defects in the product — `len(found) > 10` — which is not a clause
that survives fixing them, and a class comparison against an empty tree passes
however broken the reader is. So the sample moved off the product:
`BEFORE_THE_SWEEP` holds four captions copied out of the tree as they stood,
`AFTER_THE_SWEEP` the same four in the shape the sweep left them, and the
reader is required to find all of the first and none of the second. Without
the second clause the first is satisfied by a reader that matches everything.
"""

from __future__ import annotations

import re
from pathlib import Path

DASHBOARD_SRC = Path("dashboard/src")
VIEWS = DASHBOARD_SRC / "views.tsx"

#: Named rather than located by line, so an edit above it cannot silently
#: empty this guard's population.
OWNER = "ReportView"

#: The control's caption, which is also its accessible name.
LABEL = "Generate"

ELLIPSIS = "…"

#: A caption that swaps to a busy word: a conditional whose taken branch is a
#: string or template literal ending in an ellipsis. That is the defect's
#: shape, and it is what the three prior fixes each removed.
SWAPPING = re.compile(r'\?\s*(?:"[^"]*' + ELLIPSIS + r'"|`[^`]*' + ELLIPSIS + r'`)')

_LITERAL = re.compile(r'"([^"]*' + ELLIPSIS + r')"|`([^`]*' + ELLIPSIS + r')`')


# --------------------------------------------------------------------------
# Reading. Shared with the UX-96 guard in shape on purpose.



def _as_buttons(source: str) -> str:
    """Item 183: every button is one of the five variants now, and the two that
    render a `<button>` are written `PrimaryButton` and `SecondaryButton`. Read
    as the element they render, so this guard keeps reading captions."""
    source = re.sub(r"<(?:PrimaryButton|SecondaryButton)\b", "<button", source)
    return re.sub(r"</(?:PrimaryButton|SecondaryButton)>", "</button>", source)


def _body(owner: str, path: Path = VIEWS) -> str:
    """One component's source, from its declaration to the first column-zero
    close brace — the identical reading the UX-88 and UX-96 guards take.

    `path` defaults to `views.tsx` because every control this class was taken
    for until relay 126 lived there. `ErrorNote`, the last of the twenty-nine,
    is in `components.tsx`, and a second copy of this function to read it is
    the two-copies-of-one-rule defect `DISCIPLINE.md`'s own preamble is about.
    """
    source = _as_buttons(path.read_text(encoding="utf-8"))
    for opener in (f"export function {owner}", f"function {owner}"):
        if opener in source:
            return source.split(opener, 1)[1].split("\n}", 1)[0]
    raise AssertionError(
        f"{owner} is not defined in {path}; this guard's population is empty "
        "and every clause below would pass by finding nothing")


def _uncommented(body: str) -> str:
    """Source with comments removed. The fix explains itself in comments that
    quote the defect, and a guard that read them would find its own
    explanation and report it as the fault."""
    body = re.sub(r"/\*.*?\*/", " ", body, flags=re.S)
    return re.sub(r"//[^\n]*", " ", body)


#: Deliberately not `'`. Apostrophes are ordinary prose in this tree — thirty
#: five of them sit inside `//` comments and many more in JSX text — and the
#: only two single-quoted runs in `dashboard/src` are `state='fixed'` inside
#: SQL template literals, which backtick state already covers. Treating `'` as
#: a delimiter is what swallowed `views.tsx:1127`'s `WF-95's` and everything
#: after it.
_QUOTES = "\"`"


def _blank_comments(source: str) -> str:
    """`source` with every comment body replaced by spaces of equal length.

    Offsets and line numbers are preserved, so everything downstream can be
    read positionally. Done first because a comment is where the characters
    this reader keys on — `>`, `{`, `'` — appear without meaning any of it.
    """
    out = list(source)
    i, quote = 0, None
    backslash = chr(92)
    while i < len(source):
        ch = source[i]
        if quote:
            if ch == backslash:
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in _QUOTES:
            quote = ch
        elif source.startswith("//", i):
            end = source.find("\n", i)
            end = len(source) if end < 0 else end
            out[i:end] = " " * (end - i)
            i = end
            continue
        elif source.startswith("/*", i):
            end = source.find("*/", i + 2)
            end = len(source) if end < 0 else end + 2
            for j in range(i, end):
                if source[j] != "\n":
                    out[j] = " "
            i = end
            continue
        i += 1
    return "".join(out)


def _caption(source: str, start: int) -> str:
    """The text between a `<button ...>` opening tag and its `</button>`.

    `source` must already have been through `_blank_comments`. The opening tag
    is found by tracking brace depth and string state rather than by the first
    `>`: nearly every button here carries an arrow function in `onClick`, and
    `=>` would end the tag two attributes early.
    """
    i, depth, quote = start, 0, None
    backslash = chr(92)
    while i < len(source):
        ch = source[i]
        if quote:
            if ch == backslash:
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in _QUOTES:
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif ch == ">" and depth == 0 and source[i - 1] != "=":
            return source[i + 1:source.find("</button>", i)]
        i += 1
    raise AssertionError(
        f"a <button at offset {start} has no closing tag this reader can find; "
        "the enumeration below would silently under-count")


def _swapping_in(source: str) -> list[tuple[str, ...]]:
    """The busy words of every swapping caption in one file's source.

    Split out from `_swapping_captions` so the reader can be pointed at
    source that is not on disk. With the class empty the product no longer
    contains an example of the defect, so nothing in this tree can show that
    this function still recognises one — see
    `test_the_reader_still_recognises_the_defect_it_was_written_for`.
    """
    source = _blank_comments(source)
    found: list[tuple[str, ...]] = []
    for match in re.finditer(r"<button\b", source):
        caption = _caption(source, match.start())
        if SWAPPING.search(caption):
            found.append(tuple(a or b for a, b in _LITERAL.findall(caption)))
    return found


def _swapping_captions() -> list[tuple[str, tuple[str, ...]]]:
    """Every button in `dashboard/src` whose caption swaps to a busy word,
    keyed by file and by the busy words themselves — not by line, which every
    edit above a control moves."""
    return sorted(
        (path.as_posix(), words)
        for path in sorted(DASHBOARD_SRC.glob("*.tsx"))
        for words in _swapping_in(_as_buttons(path.read_text(encoding="utf-8"))))


# --------------------------------------------------------------------------
# Population. Without these, deleting the control turns this file green.


def test_the_component_and_its_control_are_both_still_here():
    body = _uncommented(_body(OWNER))
    assert "<button" in body, f"{OWNER} renders no button at all"
    captions = [
        _caption(body, m.start()) for m in re.finditer(r"<button\b", body)]
    assert any(re.search(rf"\b{LABEL}\b", c) for c in captions), (
        f"{OWNER} no longer carries a control captioned {LABEL!r}; the clauses "
        f"below would pass by finding nothing to check. Captions read: "
        f"{[' '.join(c.split()) for c in captions]}")


#: One control of each shape the class actually took, in the JSX this tree
#: writes. Verbatim from `admin.tsx`, `analyses.tsx`, `expert.tsx` and
#: `tools.tsx` as they stood before the sweep, so this is the defect as it
#: really appeared and not a caricature of it.
BEFORE_THE_SWEEP = """
  <button className="pill-btn" disabled={busy} onClick={refresh}>
    {busy ? "fetching…" : "refresh reference rates"}
  </button>
  <button className={`pill-btn`} disabled={busy} onClick={() => onAct(a)}>
    {spends && !open && <SpendMark />}
    {busy ? "…" : open ? "close" : a.verb}
  </button>
  <button className="pill-btn" disabled={busy === row.name}
          onClick={() => save(row)}>
    {busy === row.name ? "saving…" : "save"}
  </button>
  <button className="pill-btn pill-run" disabled={busy !== null}>
    <SpendMark />{busy === t.id ? (stored[t.id] ? "opening…"
                                 : "analysing…") : t.name}
  </button>
"""

#: The same four after it, in the shape the sweep left them: caption fixed,
#: state on `aria-busy`, words in a region beside the control.
AFTER_THE_SWEEP = """
  <button className="pill-btn" disabled={!!busy} aria-busy={busy === "rates"}
          onClick={refresh}>
    refresh reference rates
  </button>
  <span className="muted" role="status" aria-live="polite">
    {busy === "rates" && "Fetching reference rates…"}
  </span>
  <button className={`pill-btn`} disabled={busy} aria-busy={busy}
          onClick={() => onAct(a)}>
    {spends && !open && <SpendMark />}
    {open ? "close" : a.verb}
  </button>
  <span className="muted" role="status" aria-live="polite">
    {busy && `${a.verb}…`}
  </span>
  <button className="pill-btn" disabled={busy === row.name}
          aria-busy={busy === row.name} onClick={() => save(row)}>
    save
  </button>
  <button className="pill-btn pill-run" disabled={busy !== null}
          aria-busy={busy === t.id}>
    <SpendMark />{stored[t.id] ? `show ${t.name}` : t.name}
  </button>
"""


def test_the_reader_still_recognises_the_defect_it_was_written_for():
    """The population proof, moved off the product because the product no
    longer supplies one.

    Until round 135 this clause read `len(_swapping_captions()) > 10`: the
    reader was proven by the twenty-eight controls that still carried the
    defect. Emptying `DEFERRED` empties that population, and a comparison
    against nothing passes however broken the reader is — which is the exact
    failure `test_the_class_is_exactly_what_this_round_recorded` says it is
    guarding against. So the sample is stated here instead, and it is the
    real one: four captions copied out of the tree as they stood.
    """
    found = _swapping_in(BEFORE_THE_SWEEP)
    assert len(found) == 4, (
        f"the reader found {len(found)} of the four swapping captions in the "
        "sample. It has stopped matching the shape it was written for, and "
        "the class comparison below would then pass by finding nothing. "
        f"Read: {found}")
    assert ("…",) in found, (
        "the reader missed the bare-ellipsis caption. That one is the worst "
        "of the class — the control's accessible name becomes '…' — and "
        "it is the one a narrower pattern drops first")


def test_the_shape_the_sweep_left_is_not_read_as_the_defect():
    """The other direction, without which the clause above is satisfied by a
    reader that matches everything."""
    found = _swapping_in(AFTER_THE_SWEEP)
    assert found == [], (
        "the reader calls the fixed shape a defect, so it would refuse every "
        f"future fix of this class. Read: {found}")


def test_nothing_is_deferred_now_that_the_operator_has_answered():
    """The class is closed at twenty-nine of twenty-nine, and that is said
    here rather than left to be inferred from a short list.

    Until relay 126 this clause asserted the opposite — that `DEFERRED` held
    exactly the one control Q-43 was asked about — and its docstring said in
    terms that an answer in favour of the finding is what would turn it red.
    The operator answered *fix the control and re-point the test* on
    2026-09-02, so it is red-then-flipped rather than quietly deleted: the
    guard did the job it was written for.

    A row re-entering `DEFERRED` after this means a later round chose to
    defer a fresh instance, which is a decision that should have to be
    written down against a failing clause rather than added to a list.
    """
    assert DEFERRED == [], (
        "a control is deferred again with no operator decision behind it; "
        f"QUESTIONS.md Q-43 closed this register. It holds: {DEFERRED}")


# --------------------------------------------------------------------------
# UX-66 — the control the report sequenced.


def test_the_generate_control_keeps_one_accessible_name():
    body = _uncommented(_body(OWNER))
    swaps = SWAPPING.findall(body)
    assert not swaps, (
        f"{OWNER} still swaps a control caption to a busy word ({swaps}); the "
        "label is the accessible name, so the operator who pressed one button "
        "is told a different control appeared. reports.tsx:270-289 (UX-64), "
        "views.tsx:1799 (UX-88) and views.tsx:2162 (UX-96) are the shape")


def test_the_generate_control_carries_the_state_it_stopped_saying():
    body = _uncommented(_body(OWNER))
    generate = body[body.find("<button"):body.find("</button>") + 9]
    assert "aria-busy" in generate, (
        "the Generate button dropped the busy word from its label and put "
        "nothing in its place; `aria-busy` is what carries the state on all "
        "three prior fixes")


def test_the_in_flight_words_reach_a_region_that_was_already_mounted():
    # Uncommented, and that is not incidental: the fix explains itself in a
    # comment that quotes `role="status"` and `aria-live`, and a reader that
    # kept comments matches the explanation instead of the element.
    body = _uncommented(_body(OWNER))
    live = re.search(
        r'role="status"[^>]*aria-live="polite"'
        r'|aria-live="polite"[^>]*role="status"', body)
    assert live, (
        f'{OWNER} has no `role="status" aria-live="polite"` region, so the '
        "words that came off the button label are said nowhere")

    element = body.rfind("<", 0, live.start())
    close = body.find(">", live.end())
    opening = " ".join(body[element:close + 1].split())

    #: What immediately precedes the element in JSX. `&&`, `?`, `:` or a bare
    #: `(` all mean the region is rendered only once something is true.
    before = body[:element].rstrip()
    assert not before.endswith(("&&", "?", ":", "(")), (
        f"the live region is mounted behind a condition ({before[-24:]!r}). A "
        "region inserted in the same render as its content is not announced — "
        "views.tsx:1814 (UX-88) states the rule: the region has to be here "
        "before the text is")
    assert ELLIPSIS in body[close:body.find("</", close)], (
        "the mounted region says nothing while the request is in flight; the "
        f"word that left the button caption did not arrive. Opening tag read: "
        f"{opening}")


# --------------------------------------------------------------------------
# UX-66 — the twenty-ninth control, the one the operator had to decide.


#: The last control of the class, in `components.tsx` rather than `views.tsx`
#: and read by name for the same reason `OWNER` is: an edit above it must not
#: be able to empty this guard's population silently.
RETRY_OWNER = "ErrorNote"
COMPONENTS = DASHBOARD_SRC / "components.tsx"

#: The caption it keeps. Also its accessible name, which is the whole point.
RETRY_LABEL = "Try again"


def test_the_retry_control_and_its_caption_are_both_still_here():
    """The population clause, without which every clause below passes by
    finding nothing — the same shape
    `test_the_component_and_its_control_are_both_still_here` takes for
    `ReportView`."""
    body = _uncommented(_body(RETRY_OWNER, COMPONENTS))
    assert "<button" in body, f"{RETRY_OWNER} renders no button at all"
    captions = [
        _caption(body, m.start()) for m in re.finditer(r"<button\b", body)]
    assert any(RETRY_LABEL in c for c in captions), (
        f"{RETRY_OWNER} no longer carries a control captioned "
        f"{RETRY_LABEL!r}. Captions read: "
        f"{[' '.join(c.split()) for c in captions]}")


def test_the_retry_control_carries_the_state_it_stopped_saying():
    """`aria-busy` is what the busy word was traded for.

    The class enumeration below would be satisfied by a fix that simply
    deleted `Trying…` and put nothing in its place — the caption would stop
    swapping and the state would be said nowhere, which is a worse screen
    than the defect. That is what this clause and the next one hold.
    """
    body = _uncommented(_body(RETRY_OWNER, COMPONENTS))
    start = body.find("<button")
    button = body[start:body.find("</button>", start) + 9]
    assert "aria-busy" in button, (
        f"the {RETRY_LABEL!r} button dropped the busy word from its label and "
        "put nothing in its place; `aria-busy` is what carries the state on "
        f"every prior fix of this class. Read: {' '.join(button.split())}")


def test_the_retry_words_go_in_the_alert_and_not_in_a_nested_live_region():
    """Where the other twenty-eight put a `role="status"` region, this one
    puts the words in the `<p role="alert">` the button already sits inside.

    Both directions, because either alone is satisfiable by the wrong fix. A
    nested region is the mistake the operator's answer names in terms — a
    live region inside a live region announces nothing, and a `<div>` inside
    a `<p>` is invalid besides — so it is asserted absent; and the alert must
    actually gain the word, or the state is again said nowhere.
    """
    body = _uncommented(_body(RETRY_OWNER, COMPONENTS))
    assert 'role="status"' not in body, (
        f"{RETRY_OWNER} nests a `role=\"status\"` region inside its "
        '`role="alert"` paragraph. A live region inside a live region is not '
        "announced, and the element would be a <div> inside a <p>. "
        "QUESTIONS.md Q-43 names this as what the fix must not do")
    assert 'role="alert"' in body, (
        f"{RETRY_OWNER}'s paragraph is no longer an alert, so the words that "
        "came off the button label are not re-announced when they change")

    start = body.find("<button")
    after = body[body.find("</button>", start):]
    assert ELLIPSIS in after, (
        "nothing beside the control says it is trying; the word that left the "
        f"button caption did not arrive. Read after the button: "
        f"{' '.join(after.split())[:120]}")


# --------------------------------------------------------------------------
# DISCIPLINE rule 3 — the deferrals, named rather than left short.


#: Every button in `dashboard/src` still carrying the UX-66 defect, keyed by
#: `(file, the busy words in its caption)`. Deferred, not absent: this round
#: takes one lever, and report 123's remediation item 4 scoped it to the one
#: control it named. Struck a row at a time as each is fixed — the comparison
#: below is exact in both directions, so a fix that leaves this list stale
#: fails here rather than passing quietly.
DEFERRED: list[tuple[str, tuple[str, ...]]] = [
    # Empty since relay 126, and empty is a claim rather than an absence: the
    # comparison below is exact in both directions, so a thirtieth control
    # written tomorrow fails here and is named in the failure.
    #
    # Round 135 swept twenty-seven of the twenty-eight it inherited. The
    # twenty-eighth — `components.tsx`'s `ErrorNote` retry — was held on an
    # operator decision rather than on effort, because
    # `tests/test_fetch_state.py`'s
    # `test_the_error_offers_a_retry_and_says_when_it_is_trying` drove that
    # control and asserted `"trying" in retry.inner_text()`, the busy word
    # inside the button's own text, which is the defect UX-66 names. The two
    # could not both hold, and DISCIPLINE rule 6 says a test failing because
    # it asserted the old wrong behaviour is the operator's call and not a
    # round's cleanup. `QUESTIONS.md` Q-43, answered *fix the control and
    # re-point the test* by the operator on 2026-09-02; relay 126 did both.
]


def test_the_class_is_exactly_what_this_round_recorded():
    found = _swapping_captions()
    expected = sorted(DEFERRED)
    new = [f for f in found if found.count(f) > expected.count(f)]
    gone = [e for e in expected if expected.count(e) > found.count(e)]
    assert found == expected, (
        "the set of controls whose caption swaps to a busy word is not the "
        f"set this round recorded ({len(found)} found, {len(expected)} "
        f"recorded).\n  no longer deferred, strike its row: {sorted(set(gone))}"
        f"\n  not recorded, a new instance of UX-66: {sorted(set(new))}")


def test_the_control_this_round_fixed_is_not_in_the_deferred_register():
    assert ("dashboard/src/views.tsx", ("Generating" + ELLIPSIS,)) not in DEFERRED, (
        "the control UX-66 was taken for is still listed as deferred; the "
        "register would then pass while the lever had not landed")
