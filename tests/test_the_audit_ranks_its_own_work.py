"""The audit ranks its own work, and nothing offers to sell a ranking.

Item 196. The operator's reading: "the wording being presented gives the user
another choice to do an audit under a different button. They will more than
likely spend on trying to get a consistent result across the sections with an
end result of costing more due to confusion on what to run."

Two defects underneath it, and this file guards the fix to both.

**The hold pointed at something that could not lift it.** "Critical or High
unassessed" is `state == 'open'`, and only `set_state` changes that. Triage
wrote one row, into `expert_reports`, and no `finding_states` row ever - so a
reader who followed the primary action spent, received a ranking, and watched
the held count stay exactly where it was. Three surfaces did this: the client
landing's held lane, the Reports step, and `report_hold.tsx` - which item 196's
own list did not name, and which grep found.

**A sort was a numbered step with a price.** It sat between Audit and Analyses
behind a paid confirm, and read "Ranked an older audit" the moment a new audit
landed - so every re-audit invited a re-triage to make the sections agree
again. That is the spend the operator predicted.

The ranking itself was never the problem and is kept: `checks.is_blocker`
first, then severity, then how many findings a check carries. Decision (b),
the operator's: deterministic, computed with the audit, never stale, no model.

**What this file does NOT assert.** That the ordering is "right" - a ranking is
a judgement and the rules are stated where they are implemented. It asserts
that the ranking exists without being bought, that nothing sells one, and that
the hold points at the record where assessment happens.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from clauditseo import axe
from clauditseo.analyses import audit_ranking
from clauditseo.checks import blocker_checks
from tests.test_a11y_rendered import DIST, served  # noqa: F401  (reused fixture)
from tests.test_heading_fault import browser_page  # noqa: F401  (reused fixture)

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "dashboard" / "src"


def live(fn):
    fn = pytest.mark.skipif(
        not (DIST / "index.html").is_file(),
        reason="dashboard not built (npm run build in dashboard/)")(fn)
    return pytest.mark.skipif(
        not axe.available(),
        reason="needs clauditseo[render] and `playwright install chromium`")(fn)


# --- the rules, without a browser -------------------------------------------

def test_a_blocker_outranks_a_worse_severity():
    """The registry's rule, and the one that cannot be expressed as severity.

    A blocker stops the page being reached at all, so no score beats it. The
    prompt-era ranking deferred to the same register - "Blockers are ranked
    first whatever they score, and the rule is the registry's rather than the
    model's" - which is why this is not a new judgement.
    """
    blocker = sorted(blocker_checks())[0]
    ranked = audit_ranking(
        [{"check_id": "ONP/title-missing", "severity": "critical", "summary": "x"},
         {"check_id": blocker, "severity": "low", "summary": "y"}],
        None, "run")["ranked"]
    assert [r["check"] for r in ranked] == [blocker, "ONP/title-missing"], ranked


def test_between_two_of_a_severity_the_wider_one_ranks_first():
    """Between two mediums, the one failing on forty pages is the one to open.
    The count is the third rule and the only one that reads the size of the
    problem rather than its kind."""
    ranked = audit_ranking(
        [{"check_id": "ONP/a-narrow", "severity": "medium", "summary": "x"},
         {"check_id": "ONP/b-wide", "severity": "medium", "summary": "y"},
         {"check_id": "ONP/b-wide", "severity": "medium", "summary": "y"}],
        None, "run")["ranked"]
    assert [r["check"] for r in ranked] == ["ONP/b-wide", "ONP/a-narrow"], ranked


def test_the_worst_severity_a_check_carries_is_the_one_it_ranks_at():
    """A check that fails critically on one page and quietly on thirty is a
    critical check. Taking the first row's severity instead would make the
    rank depend on which page was crawled first."""
    ranked = audit_ranking(
        [{"check_id": "ONP/x", "severity": "low", "summary": "quiet"},
         {"check_id": "ONP/x", "severity": "critical", "summary": "loud"}],
        None, "run")["ranked"]
    assert len(ranked) == 1 and ranked[0]["severity"] == "critical", ranked


def test_the_ranking_is_never_stale_and_names_no_purchase():
    """The staleness warning existed because a stored ranking could outlive
    its audit. Nothing can now, so the flag is False by construction - and the
    `ranking` key stays empty rather than inventing the cluster ranking the
    model used to return."""
    out = audit_ranking([{"check_id": "ONP/x", "severity": "low"}], "t", "run")
    assert out["stale"] is False
    assert out["ranking"] == []
    assert out["from_run"] == "run"


def test_every_ranked_row_names_the_part_it_belongs_to():
    """WF-07, and why it cannot recur in the same form.

    The rail once read "–" on every part under "Ranked 5 checks against this
    audit": triage named checks of its own invention -
    `sitemap-coverage-regressed`, `img-alt-missing-fix-incomplete` and three
    more - and the server's part-of-check registry knows only the record's
    ids, so its answer was null for all five. `test_triage_rank_reaches_the
    _parts.py` guarded the join that repaired it.

    The ids now come from the record rather than from a model, so a rank can
    only name a check the registry already knows. That makes the old defect
    structurally impossible rather than guarded - but only while the category
    is actually carried on the row, which is what this asserts. Drop it and
    every part reads "–" again, by a different route.
    """
    from clauditseo.anatomy import CHECK_CATEGORY

    known = next((c for c in CHECK_CATEGORY if CHECK_CATEGORY[c]), None)
    assert known, "the check-to-part registry is empty"
    [row] = audit_ranking([{"check_id": known, "severity": "high"}],
                          None, "run")["ranked"]
    assert row["category"] == CHECK_CATEGORY[known], (
        "a ranked row does not name the part its check belongs to, so the "
        f"rail has nothing to place it against: {row}")


def test_the_ranking_is_not_a_purchasable_analysis():
    """The inverse of the UI removal, and the half a screen test cannot see:
    if the tool stays registered, anyone who posts can still buy the sort."""
    from clauditseo.analysts.expert import EXPERT_TOOLS
    from clauditseo.playbook import PLAYBOOK

    assert "triage" not in EXPERT_TOOLS, (
        "the triage brief is still registered, so the model call the UI no "
        "longer offers can still be bought over the wire")
    ids = [t["id"] for ph in PLAYBOOK for t in ph["tools"]]
    assert "triage" not in ids, f"the catalogue still lists triage: {ids}"
    assert not (ROOT / "clauditseo" / "prompts" / "triage.md").exists()


# --- the surface ------------------------------------------------------------

def test_no_source_offers_a_route_to_a_triage_screen():
    """Six entry points, one destination, four verbs (items 182 and 184) - and
    the destination is gone. Read from source rather than a rendered page
    because a link on a screen this suite does not drive is still a link."""
    offenders = []
    for path in sorted(SRC.glob("*.tsx")) + sorted(SRC.glob("*.ts")):
        text = path.read_text(encoding="utf-8")
        code = "\n".join(ln for ln in text.splitlines()
                         if not ln.lstrip().startswith(("//", "*", "/*")))
        if "tab=triage" in code or "TRIAGE_VERB" in code:
            offenders.append(path.name)
    assert not offenders, (
        "these still route to a triage screen, which no longer exists: "
        + ", ".join(offenders))


def test_the_registry_has_no_word_for_a_retired_screen():
    """Item 166: one definition per word, and a definition for a screen that
    no longer exists is the stale entry the register exists to prevent."""
    entries = json.loads(
        (ROOT / "clauditseo" / "glossary.json").read_text(encoding="utf-8"))
    rows = entries["entries"] if isinstance(entries, dict) else entries
    ids = [e.get("id") for e in rows]
    assert "open-triage" not in ids, (
        "the glossary still defines `open-triage`, whose screen is retired")


def test_all_three_held_surfaces_point_at_the_record():
    """The defect, read from the three places that carried it.

    The hold is "unassessed", which only `set_state` changes. Triage wrote one
    `expert_reports` row and no `finding_states` row ever, so each of these
    offered a way out that could not work: the reader spent, received a
    ranking, and the held count stayed exactly where it was.

    Three surfaces, and the third is why this reads source rather than one
    screen: `report_hold.tsx` is not in item 196's list of call sites. It was
    found by grep, and a clause that drove the landing alone would have passed
    while it still pointed at triage.

    **Why this is not the driven test item 196 asked for.** That test wants a
    site holding an unassessed Critical or High so the held lane is drawn;
    `test_a11y_rendered.py`'s shared fixture holds none, and planting one
    mutates a module-scoped fixture every other rendered test also uses. The
    driven version belongs with a fixture of its own - the shape
    `test_a_held_client_report_never_pays_for_its_plan.py` already has - and
    is recorded as unfinished rather than written as a clause that skips.
    A skip here would also red `rendered-a11y`, which fails on any skip.
    """
    # Item 202: the three now share one address, `heldRecordHref`, which is
    # the record on what is open - the site's, since item 239 step 7 made the
    # hold the running record's - so the marker is the helper and its address.
    hold = (SRC / "report_hold.tsx").read_text(encoding="utf-8")
    assert "tab=all&state=open" in hold[hold.index("export function heldRecordHref"):], (
        "the held address no longer opens the record on what is open")
    for name, marker in (("client_lanes.tsx", "heldRecordHref(siteId)"),
                         ("anatomy.tsx", "heldRecordHref(siteId)"),
                         ("report_hold.tsx", "heldRecordHref(siteId)")):
        text = (SRC / name).read_text(encoding="utf-8")
        assert marker in text, (
            f"{name} no longer points a held report at the record; it is one "
            "of the three surfaces that offered triage instead, and triage "
            "could not lift the hold")


@live
def test_the_landing_offers_no_route_to_a_ranking(served, browser_page):
    """The absence, on the screen rather than in the source: six entry points
    reached triage (items 182 and 184), and a source grep proves the strings
    are gone while a rendered page proves nothing builds one at runtime."""
    base, ids = served
    browser_page.goto(f"{base}/#/sites/{ids['site']}", wait_until="load")
    browser_page.wait_for_selector(".cl-landing", timeout=15_000)

    # The absence, across the whole screen: six entry points reached triage
    # (items 182 and 184), so a clause that checked one control would pass
    # while five others still sold it.
    hrefs = browser_page.eval_on_selector_all(
        "a[href]", "els => els.map(e => e.getAttribute('href') || '')")
    assert not any("tab=triage" in h for h in hrefs), (
        "the landing still offers a route to triage: "
        + repr([h for h in hrefs if "tab=triage" in h]))

    # The sequence strip draws at all, which is the half a source grep cannot
    # see. Removing the Triage step shortened the array `destinationsOf`
    # indexed by position, so `seq.steps[5]` was undefined and reading `.href`
    # off it threw before the screen drew anything - 169 errors and 192
    # failures, on a landing that rendered as a blank page.
    names = browser_page.eval_on_selector_all(
        ".seq-name", "els => els.map(e => (e.textContent || '').trim())")
    assert names, (
        "the sequence strip drew nothing, so the screen is failing to render "
        "rather than merely missing a step")
    assert not any("triage" in n.lower() for n in names), names
