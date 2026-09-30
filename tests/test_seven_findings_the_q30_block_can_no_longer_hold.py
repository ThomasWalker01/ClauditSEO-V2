"""The six findings Q-30 can no longer block, and the one that joined them.

**Why this file exists at all.** `audit-fix/SKILL.md` step 4 allows six
dispositions for a finding at ten reports survived, one of which is *blocked
on an operator decision* — and it caps that one: *"A blocked finding may not
be re-blocked twice without the question being answered."* `QUESTIONS.md`
Q-30 was asked at report 107 (block one), re-blocked at round 108 (block two),
and left standing at rounds 110 and 111. Round 111 took the two oldest members
of the group as its lever (UX-87, UX-88) precisely because a third block was
not available to it, and recorded in `audits/DISPOSITIONS.md` that the
remaining six *"cannot be blocked again"*.

Round 112 is the next round to walk the cohort, so the six —
**WF-97, UX-91, CQ-215, CQ-216, UI-21, WF-99** — must each take one of the
five remaining dispositions. They take the same one, for the reason round 111
gave for its own eight: every one of them is decidable from source, none rests
on a spend, a routing judgement or a latitude, so blocking any would mean
inventing a question nobody has, and disputing one would mean claiming
evidence this round does not have.

**WF-103 joins them from the other side.** It crossed ten reports at *this*
round, alongside UX-96 and UX-97 — all three first raised at report 102. UX-96
and UX-97 are this round's lever; WF-103 sits inside the same twenty lines and
is the one of the three whose fix is a product-wording decision rather than an
attribute, so it is recorded here rather than swept in beside them.

**Round 118 is the deadline, and the spacing is deliberate.** Round 113 owes
four (`test_four_findings_at_ten_reports_are_recorded_not_invisible.py`) and
round 116 owes eight (`test_eight_...`). Putting these seven at 118 keeps three
rounds between each cohort rather than letting eleven fall due at once — the
same load-spreading round 111 recorded when it chose 116 over 113.

**Three of the seven came off that deadline on 2026-08-31, and none came off
this file.** The operator answered Q-30 — *route the product-wording and a11y
ones to `/backlog-plan`* — and the answer's own enumeration names WF-97, UX-91
and UI-21 (UX-87 and UX-88 were the other two and round 111 took them). Routing
moves **who owes the work**, so those three carry `ROUTED` instead of a
deadline: no round is obliged to reach them at 118, and `/backlog-plan`
schedules them. Everything else about them is unchanged — same clause body, same
`strict=True`, same XPASS-turns-the-suite-red the day the defect goes. That is
the distinction this file is built on: a deadline says *when*, strictness says
*it cannot be forgotten*, and only the first of those is a round's to own.
CQ-215, CQ-216, WF-99 and WF-103 kept round 118. Recorded in
`audits/DISPOSITIONS.md` under *Relay 112*.

**Round 118 came, and all four were taken as one sweep.** Their markers are
gone and their clauses are ordinary tests now — which is the mechanism
finishing, not an exception to it. What made them fall together is that the
deadline was a date rather than a ranking: severity had preferred a fresher
High for fourteen reports and would have again. The `DEADLINE` constant went
with the last marker that used it; three `ROUTED` clauses remain, and they are
`/backlog-plan`'s to schedule, not a round's to reach.

**Strict, and that is the whole mechanism.** The day one of these defects is
fixed the clause XPASSes and turns the suite red, forcing whoever fixed it to
retire the marker and close the finding. A non-strict xfail is a finding that
has been made invisible, which is what step 4 forbids and what "not this
round" for fourteen rounds already produced. All four of the round-118 set
XPASSed the moment their fixes landed and turned the suite red exactly as
written; retiring them was not a choice this round got to make.

**Every clause reads source and asserts the FIXED state.** So each one is a
specification of what closing the finding requires, not a restatement of the
defect — and it cannot be satisfied by deleting the thing it is about, because
each derives its population from the tree and asserts it non-empty first.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

VIEWS = Path("dashboard/src/views.tsx")
ADMIN = Path("dashboard/src/admin.tsx")
API_TS = Path("dashboard/src/api.ts")
APP_PY = Path("clauditseo/api/app.py")
SCHEDULE = Path("dashboard/src/schedule.tsx")
TOOLS = Path("dashboard/src/tools.tsx")
SELECTION = Path("dashboard/src/selection.tsx")
TESTS = Path("tests")

ROUTED = ("routed to `/backlog-plan` by QUESTIONS.md Q-30, answered "
          "2026-08-31 — no round deadline")

#: The guard CQ-215 is about, named rather than located by line.
PRICE_GUARD = TESTS / "test_a_brief_price_says_which_site_it_was_drawn_from.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _component_body(source: str, name: str) -> str:
    """One component's source, from its declaration to the first column-zero
    close brace — the reading every guard in this repo takes."""
    for opener in (f"export function {name}(", f"function {name}("):
        if opener in source:
            return source.split(opener, 1)[1].split("\n}", 1)[0]
    raise AssertionError(
        f"{name} is no longer defined where this guard reads it; the "
        "population is empty and the clause would pass by finding nothing")


def _uncommented(body: str) -> str:
    body = re.sub(r"/\*.*?\*/", " ", body, flags=re.S)
    return re.sub(r"//[^\n]*", " ", body)


# --------------------------------------------------------------------------
# WF-97 — carried from report 095, sixteen reports
# --------------------------------------------------------------------------

@pytest.mark.xfail(strict=True, reason=f"WF-97 — {ROUTED}")
def test_the_comparison_generate_control_cannot_quietly_make_a_second_copy():
    """WF-97 (Medium). `CompareView`'s generate control POSTs
    `{template, audience, run_ids}` to `/api/reports` and nothing in that body
    or on the button distinguishes a first press from a second. Two presses
    against the same run pair write two client documents that differ in
    nothing an operator can see, and the screen that made them says nothing
    about the first one still existing.

    The fixed state asserted here is the weaker of the two available remedies:
    the request must carry something that identifies *this* press, so the
    server can recognise a repeat. Refusing the second press on the client
    would also satisfy the finding, and would satisfy this clause too — the
    guard names the request because that is the half a reload cannot defeat.
    """
    body = _uncommented(_component_body(_read(VIEWS), "CompareView"))
    post = re.search(r'api\.post<[^>]*>\(\s*"/api/reports"\s*,\s*\{(.*?)\}',
                     body, flags=re.S)
    assert post, (
        "CompareView no longer POSTs to /api/reports; this clause's "
        "population is empty and WF-97's premise has gone")
    fields = post.group(1)
    assert re.search(r"idempoten|request_id|client_token|dedupe", fields,
                     flags=re.I), (
        "the comparison generate request carries nothing that identifies the "
        "press: it sends only "
        f"{' '.join(fields.split())!r}. A second press against the same run "
        "pair therefore writes a second indistinguishable client document, "
        "and the screen that made both reports neither.")


# --------------------------------------------------------------------------
# UX-91 — carried from report 096, fifteen reports
# --------------------------------------------------------------------------

@pytest.mark.xfail(strict=True, reason=f"UX-91 — {ROUTED}")
def test_a_logo_that_cannot_be_fetched_does_not_render_as_one_still_loading():
    """UX-91 (Low). `useObjectUrl` (`api.ts:148`) swallows the failure —
    `.catch(() => { if (live) setUrl(null); })` — so `null` means both *not
    yet* and *never*. `admin.tsx` then renders `{logo && <img …>}`, and a
    registered logo whose bytes cannot be fetched is painted identically to
    one still arriving, on the one panel an operator would go to to replace
    it.

    The hook has exactly one consumer, measured by grep across
    `dashboard/src` at round 112: `admin.tsx:794`. So the fix is bounded —
    which is why this is recorded with a deadline rather than blocked.

    The fixed state: the hook distinguishes the two, and the panel says so.
    """
    hook = _read(API_TS).split("export function useObjectUrl", 1)
    assert len(hook) == 2, (
        "useObjectUrl is no longer exported from api.ts; the population is "
        "empty and UX-91's premise has gone")
    body = hook[1].split("\n}", 1)[0]
    assert not re.search(r"\.catch\(\(\)\s*=>\s*\{[^}]*setUrl\(null\)[^}]*\}\)",
                         body), (
        "useObjectUrl still collapses a failed fetch into the same `null` it "
        "returns while loading, so no consumer can tell the two apart:\n"
        f"{' '.join(body.split())[:300]}")


# --------------------------------------------------------------------------
# CQ-215 — carried from report 097, fourteen reports
# --------------------------------------------------------------------------

def test_the_price_frame_guard_does_not_decide_by_counting_a_substring():
    """CQ-215 (Medium). The guard that decides whether a price frame is on
    screen counts occurrences of a string in a source file —
    `rendered = len(re.findall(rf"<{OWNER}\\b", source))` — and derives its
    own population the same way, by testing `"typical_cost" in p.read_text()`.
    Both are satisfiable by a comment and breakable by a rename, so the guard
    can pass on a screen that paints nothing and fail on one that paints
    correctly.

    The fixed state: the file decides membership and count from something the
    product actually rendered, not from its own source text.
    """
    source = _read(PRICE_GUARD)
    assert "typical_cost" in source, (
        f"{PRICE_GUARD} no longer mentions the field it is about; the "
        "population is empty and CQ-215's premise has gone")
    substring_decisions = re.findall(
        r'(?:re\.findall|re\.search|\bin\b)[^\n]*read_text\(|'
        r'len\(re\.findall\([^\n]*source\)', source)
    assert not substring_decisions, (
        "the price-frame guard still decides from substrings of its own "
        f"source text: {substring_decisions}. A comment naming the field "
        "satisfies it and a rename breaks it, so what it verifies is the "
        "spelling rather than the screen.")


# --------------------------------------------------------------------------
# CQ-216 — carried from report 097, fourteen reports
# --------------------------------------------------------------------------

def test_no_comment_tells_the_next_reader_a_key_has_no_reader_it_now_has():
    """CQ-216 (Low). Three comments were left false by the commits that wrote
    them. The oldest, in `app.py`, still reads *"Giving this key a reader is
    CQ-198 and is not done here"* — and `scoped_to_site` now has three
    readers, in `schedule.tsx`, `tools.tsx` and `expert.tsx`. This clause
    pins that one, because it is the one a future reader would act on: it
    tells them not to look for the consumers that exist.

    The population is the readers, derived from the tree rather than listed,
    so the clause cannot be satisfied by deleting them.
    """
    readers = sorted(
        p.name for p in Path("dashboard/src").glob("*.tsx")
        if "scoped_to_site" in _read(p) or "priceScope" in _read(p))
    assert readers, (
        "nothing on any screen reads the scoped population any more, so the "
        "comment would be true and CQ-216's premise has gone")
    # Comment markers and line wrapping removed before matching. The first
    # draft of this clause XPASSED against the unfixed tree because the
    # sentence wraps — `…a *reader* is` ends one line and `CQ-198 and is not
    # done here` begins the next behind a `#` — so a contiguous pattern found
    # nothing and the clause reported the defect fixed. That is round 111's
    # CQ-229 mistake in a different spelling, and it is caught here by
    # normalising the text rather than by a longer regex.
    flat = " ".join(re.sub(r"^\s*#", " ", _read(APP_PY), flags=re.M).split())
    stale = re.search(r"Giving this key a \*?reader\*? is CQ-198 and is not "
                      r"done here", flat)
    assert not stale, (
        f"`{APP_PY}` still tells the next reader that `scoped_to_site` has no "
        f"reader. It has {len(readers)}: {readers}.")


# --------------------------------------------------------------------------
# UI-21 — carried from report 097, fourteen reports
# --------------------------------------------------------------------------

@pytest.mark.xfail(strict=True, reason=f"UI-21 — {ROUTED}")
def test_the_price_ledger_does_not_name_its_author_with_a_route():
    """UI-21 (Low). `actor_of` (`app.py:47`) records `operator:<id>` or
    `api:<route>`, and `admin.tsx` paints `p.entered_by` raw into the Source
    cell. So the column that answers *"who put this number in my ledger"*
    reads `api:fetch-prices` to an operator quoting the price to a client.

    **Why this was not swept into round 112's lever, recorded here because it
    is the reason the finding is dated rather than done.** DISCIPLINE rule 3's
    grep found a consumer:
    `tests/test_the_price_ledger_names_its_author_on_the_panel.py::test_the_
    panel_names_the_author_where_there_is_one` asserts the *raw* stored value
    reaches a cell of the row. Any fix to the rendering turns that driven test
    red, and whether a test that asserted the old behaviour is updated or kept
    is DISCIPLINE rule 6's operator call. That is a shared call site, so the
    finding fails the sweep rule's independence test rather than the round's
    capacity.

    The fixed state: the raw vocabulary does not reach the cell.
    """
    body = _component_body(_read(ADMIN), "Money")
    assert "entered_by" in body, (
        "the Money panel no longer paints an author at all; the population is "
        "empty and UI-21's premise has gone")
    assert not re.search(r"\{\s*p\.entered_by\s*\?\?", body), (
        "the price panel still paints the stored actor token straight into "
        "the Source cell, so an operator reading who stored a price they are "
        "about to quote is shown a route name (`api:fetch-prices`) or an "
        "opaque id (`operator:<id>`).")


# --------------------------------------------------------------------------
# WF-99 — carried from report 097, fourteen reports
# --------------------------------------------------------------------------

def test_the_remembered_selection_path_is_exercised_before_the_page_loads():
    """WF-99 (Medium). `SelectionProvider` reads `clauditseo:site` once,
    inside the `/api/sites` effect (`selection.tsx:46`, `:105-110`). A browser
    drive that writes the key *after* `goto` therefore cannot reach the
    remembered-selection path at all — the read has already happened — and one
    drive of exactly that shape is on the record in `KNOWN_ISSUES.md` as
    KI-54, disproving report 096's WF-98.

    The two outcomes that evidence cannot separate are *"the remembered id was
    used and the app recovered from it"* and *"the remembered id was never
    read"*. Both paint the same screen.

    The fixed state: some test writes the key before the document loads —
    `add_init_script`, or a write followed by a reload — so the path the
    finding is about is actually taken.
    """
    key = re.search(r'const KEY = "([^"]+)"', _read(SELECTION))
    assert key, (
        "selection.tsx no longer names a storage key; the population is empty "
        "and WF-99's premise has gone")
    name = key.group(1)
    users = [p for p in TESTS.rglob("test_*.py")
             if p.name != Path(__file__).name and name in _read(p)]
    before_load = [
        p for p in users
        if re.search(r"add_init_script\(|\.reload\(", _read(p))]
    assert before_load, (
        f"no test writes {name!r} before the document loads, so nothing in "
        "the tree exercises the remembered-selection path. The drives that "
        f"do mention it ({[p.name for p in users]}) set it after `goto`, "
        "which is the shape KI-54 used to retire WF-98 and cannot tell a "
        "recovered selection from an unread one.")


# --------------------------------------------------------------------------
# WF-103 — carried from report 102, ten reports at this round
# --------------------------------------------------------------------------

def test_a_refused_start_url_does_not_tell_the_operator_to_set_an_env_var():
    """WF-103 (Medium). `_validate_start_url` refuses an off-site host with
    *"set CLAUDITSEO_ALLOW_ARBITRARY_START_URL=1 to audit staging targets"* —
    a shell variable and a service restart, offered to an operator working in
    a browser. The product's own established pattern is the opposite
    everywhere else: provider keys are a per-site control on a screen (UX-13),
    not an environment variable named in an error.

    This message is what the *"Check this URL"* control exists to surface, so
    round 112's lever made it reach a screen reader without changing what it
    says. That is the finding staying open by construction, and it is why
    this is dated rather than closed.

    The fixed state, either way the operator's decision goes: the sentence a
    refused check paints names no environment variable. Surfacing the setting
    as a control satisfies this; so does rewriting the message.
    """
    source = _read(APP_PY)
    assert "_validate_start_url" in source, (
        "the start-URL validator is gone; the population is empty and "
        "WF-103's premise has gone")
    refusal = re.search(
        r"return \(f?\"start_url host .*?\)\n", source, flags=re.S)
    assert refusal, (
        "the off-site refusal message could not be located; this clause reads "
        "the return rather than a line number and it has changed shape")
    assert "CLAUDITSEO_" not in refusal.group(0), (
        "the off-site refusal still tells the operator to set an environment "
        "variable and restart the service:\n"
        f"  {' '.join(refusal.group(0).split())}")
