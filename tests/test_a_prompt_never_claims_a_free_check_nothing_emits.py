"""A prompt may read a free check; it may not invent one (brief v17 step
AV2).

`cost: free` is the engine promising to answer a check for nothing. A
prompt that lists a free check no sweep emits puts a row on a part page
that no run can produce: it appears in the checks table, is never raised,
and reads as permanently clean - which is the most expensive kind of wrong
answer, because nobody goes looking for it.
"""

from __future__ import annotations

import pytest

from clauditseo import briefs
from clauditseo.checks import FREE, check_cost, check_costs, sweep_checks


def test_every_check_has_a_cost_and_none_is_blank():
    """AV1's own acceptance. A check with no cost is a check the operator
    cannot be told the price of, and the split is the whole point of the
    step."""
    costs = check_costs()
    assert len(costs) >= 120, len(costs)
    assert all(v in ("free", "model") for v in costs.values()), {
        k: v for k, v in costs.items() if v not in ("free", "model")}


def test_a_check_the_sweep_emits_is_free_even_where_a_brief_reads_it_too():
    """AV1's rule about two sources. The brief corroborates a sweep row; it
    does not create one, so the check stays free and the operator is not
    told they must pay for something they already have."""
    assert check_cost("ONP/title-length") == FREE
    assert check_cost("ONP/img-alt-missing") == FREE
    # And a check no sweep can answer costs a model call.
    assert check_cost("ONP/title-entity-alignment") == "model"
    assert check_cost("ONP/schema-entity-thin") == "model"


@pytest.mark.parametrize("brief", [b for b in briefs.catalogue() if b.checks],
                         ids=lambda b: b.id)
def test_no_prompt_lists_a_free_check_no_sweep_emits(brief):
    emitted = sweep_checks()
    # A SEC check whose collector is not built yet is registered free and
    # listed by `security.md`, and does not read clean: the part page and the
    # brief's context both name it not assessed with the collector it waits on
    # (`sec.NOT_YET_COLLECTED`, item 143 step BD). The register is what this
    # guard's clean-for-ever failure needs to be absent, so it is accepted
    # here by name and nowhere else.
    from clauditseo.modules.sec import NOT_YET_COLLECTED
    claimed = [c for c in brief.checks
               if check_cost(c) == FREE and c.split("/")[-1] not in emitted
               and not (c.startswith("SEC/") and c.split("/")[-1] in NOT_YET_COLLECTED)]
    assert not claimed, (
        f"{brief.path.name} lists {', '.join(claimed)} as checks it may emit. "
        "Each is registered free - the engine promising to answer it for "
        "nothing - and no sweep tool in the playbook declares it, so the row "
        "would sit in the checks table reading clean for ever. Either the "
        "sweep should emit it, or it belongs in the brief-only register.")


def test_the_part_page_reads_two_sections_free_first():
    """AV3. The order is the argument: what the audit found for nothing,
    then what a model was asked to read on top of it. An operator deciding
    whether to spend is owed the first half before the second.

    Asserted on the source rather than driven, because what matters is that
    there is one place the split is decided and it reads the payload's
    `check_cost` - a screen that inferred the cost from `source` would say
    "free" of a model check a sweep happened to corroborate.
    """
    from pathlib import Path

    ui = Path(__file__).resolve().parents[1] / "dashboard" / "src"
    # `cost.ts` since brief v17 step AV4: four things ask what a check
    # costs, and the answer's obvious home beside the `Category` type is
    # the one module that already imports the part page.
    cost = (ui / "cost.ts").read_text(encoding="utf-8")
    assert "export const costOf" in cost
    # Read from the payload, by the stored id first; item 219 added the
    # `EXP:` row's `CNT/` price between that and the `ONP/` fallback.
    assert "return c[check] ??" in cost and "c[`ONP/${bare}`]" in cost
    src = (ui / "part_page.tsx").read_text(encoding="utf-8")
    # The literal the sections are drawn from, not the surrounding prose:
    # the comment above it names Analysis first while explaining why it
    # comes second, and reading the raw text called that an inversion.
    assert '[["free", "Free checks"],' in src and '["model", "Analysis"]];' in src, (
        "the two sections are not drawn from one ordered list, so their "
        "order is wherever they happen to be written")
    # And both readers of that list draw on it rather than on their own
    # copy - the checks table and, since step AV3's other half, the fix
    # cards, which is where an operator actually acts.
    assert src.count("SECTIONS.map(") == 2, (
        "the checks table and the fix cards do not both read one ordered "
        "list of sections")
    table = src[src.index('<section className="part-checks">'):]
    # The provenance rides on the Analysis heading: a heading that says
    # "Analysis" without saying who ran it and for how much asks an
    # operator to take the price on trust.
    assert "checks-prov" in table and "part.brief_run" in table


def test_the_cost_is_the_servers_answer_and_not_the_screens_guess():
    """`costOf` falls back to free, not to model.

    A check the app has never heard of is not a reason to tell an operator
    they will be charged: the screen guessing "model" would put a price on
    work that is free, which is the error that costs someone money rather
    than the one that costs them a click.
    """
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "dashboard" / "src"
           / "cost.ts").read_text(encoding="utf-8")
    fn = src[src.index("export function checkCost"):]
    ret = fn[fn.index("  return "):]
    assert ret[:ret.index(";")].rstrip().endswith('?? "free"'), ret[:200]
