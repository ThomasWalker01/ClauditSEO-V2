"""Speed's depth pills, and the sample the trace now takes (item 141, brief
v19 step BC; unheld by the operator 2026-09-11 with two conditions).

The brief puts three pills on the Speed part's actions row:

    Re-check PRF · free        the sweep's trace and the thirteen free checks
    Run brief · Standard       `speed.md` on the templates
    Run brief · Deep           the same plus a per-page third-party waterfall,
                               when the trace has one

and says "everywhere else the pills stay gone".

**Condition one: a slot only Speed fills, not a change to the actions row's
default.** `.cat-run` is shared by every across-the-site part, and BC's six
visuals and BJ's header were written against it. So the pills are a component
one part mounts, and the enforcement is that nobody else mounts it — which is
what `test_no_other_part_mounts_the_pills` reads, off the source, because a
rendered clause can only check the parts a fixture happens to have open.

**Condition two: the trace samples, and the sample is stated.** The brief's
"a performance trace per page" predates the CPU 4x / Slow-4G CDP session this
pass applies; a T3 at five hundred throttled traces is a different audit. So
T2 and T3 take one page per template and T1 takes all three pages of the
pulse, and the part states which beside the device profile — for the same
reason that one is stated: a figure read under conditions the reader cannot
see is a figure they cannot check.
"""

from __future__ import annotations

from pathlib import Path

from clauditseo import perf
from clauditseo.engine.types import Tier

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "dashboard" / "src"
ANATOMY = (SRC / "anatomy.tsx").read_text(encoding="utf-8")
SPEED = (SRC / "speed_now.tsx").read_text(encoding="utf-8")
APP = (ROOT / "clauditseo" / "api" / "app.py").read_text(encoding="utf-8")
EXPERT = (ROOT / "clauditseo" / "analysts" / "expert.py").read_text(encoding="utf-8")
RUNS = (ROOT / "clauditseo" / "persistence" / "runs.py").read_text(encoding="utf-8")


class _Page:
    def __init__(self, url, status=200, content_type="text/html"):
        self.url, self.status, self.content_type = url, status, content_type


BASE = "https://x.test"


def _acts(code_only: bool = False) -> str:
    """The `SpeedActions` component's own source.

    `code_only` strips `//` comment lines, for the clauses that assert
    something is ABSENT: this file's notes quote the thing they say is gone,
    and a search over the prose would fail on its own explanation.
    """
    acts = SPEED[SPEED.index("export function SpeedActions"):]
    if not code_only:
        return acts
    return "\n".join(l for l in acts.splitlines()
                      if not l.lstrip().startswith("//"))


def _wide():
    """A crawl with four templates and forty-eight readable pages — the shape
    the sample exists for. Plus a stylesheet and a 404, because neither is a
    page a trace can be taken of."""
    return ([_Page(BASE + "/")]
            + [_Page(BASE + "/blog/p" + str(i)) for i in range(40)]
            + [_Page(BASE + "/services/s" + str(i)) for i in range(6)]
            + [_Page(BASE + "/about"),
               _Page(BASE + "/x.css", content_type="text/css"),
               _Page(BASE + "/gone", status=404)])


# --- condition two: the sample ---------------------------------------------

def test_a_pulse_traces_every_page_and_a_wider_run_traces_one_per_template():
    """T1's budget is three pages (`TIER_BUDGETS`), so "all three pages on T1"
    IS the whole crawl — there is nothing to sample, and a representative of
    three would be a worse answer for no saving. T2 and T3 take the template,
    which is the unit every Speed analysis row is written against."""
    pulse = [_Page(BASE + "/"), _Page(BASE + "/about"), _Page(BASE + "/contact")]
    urls, rule = perf.sample(pulse, Tier.T1)
    assert len(urls) == 3 and set(urls) == {p.url for p in pulse}, urls
    assert "every page of the pulse" in rule, rule

    for tier in (Tier.T2, Tier.T3):
        urls, rule = perf.sample(_wide(), tier)
        # Four templates: `/`, `/blog/<slug>`, `/services/<slug>`, `/about`.
        assert len(urls) == 4, (tier, urls)
        assert "one page per template" in rule, rule
        assert "4 of 48 readable" in rule, rule
        # One per template, and not four of the biggest one. Compared on the
        # pattern rather than on a path prefix: `/` and `/about` share a
        # prefix and are two templates, which is what a prefix proxy got
        # wrong when this clause was first written.
        from urllib.parse import urlsplit

        from clauditseo import urlshape
        picked = [urlshape.derive_pattern(urlsplit(u).path or "/") for u in urls]
        assert len(set(picked)) == len(urls) == 4, picked
        assert set(picked) == {"/", "/blog/<slug>", "/services/<slug>", "/<slug>"}, picked


def test_the_sample_skips_what_a_trace_cannot_be_taken_of():
    """A stylesheet is not a page and a 404 is not a load. Both are in the
    crawl and neither is in the sample, so the denominator the part states
    (`N of M readable`) counts pages a trace could have been taken of."""
    urls, rule = perf.sample(_wide(), Tier.T2)
    assert not [u for u in urls if u.endswith(".css") or u.endswith("/gone")], urls
    assert "48 readable" in rule, rule
    assert perf.sample([], Tier.T2) == ([], "nothing readable to trace")


def test_the_largest_template_leads_so_the_cap_drops_the_rarest():
    """Where the cap bites it must drop the rarest shape rather than whichever
    the crawl reached last. `/blog/` holds forty of the forty-eight pages, so
    it is first."""
    urls, _rule = perf.sample(_wide(), Tier.T2)
    assert "/blog/" in urls[0], urls

    many = [_Page(BASE + "/t" + str(i) + "/p" + str(j))
            for i in range(perf.SAMPLE_CAP + 5) for j in range(2)]
    urls, rule = perf.sample(many, Tier.T2)
    assert len(urls) == perf.SAMPLE_CAP, len(urls)
    assert ("capped at " + str(perf.SAMPLE_CAP)) in rule, rule
    assert "largest templates first" in rule, rule


def test_the_trace_is_on_by_default_and_the_suite_turns_it_off():
    """The gate inverted at this stage, and the ordering is the operator's:
    the thirteen trace checks fire only on traced pages, so the four
    overlapping header/HTML checks cannot be retired while every ordinary
    audit has no traces at all.

    The suite's opt-out is a COST decision and is asserted here so it cannot
    quietly become a correctness one — a throttled pass per fixture audit
    would add minutes, and the Speed clauses drive stored traces instead.
    """
    import os

    # Default ON: absent means traced. The gate lives in `perf.trace_for_run`
    # since 2026-09-14, where both launch paths take the pass.
    perf_src = (Path(__file__).resolve().parents[1] / "clauditseo" / "perf.py").read_text(encoding="utf-8")
    assert 'os.environ.get("CLAUDITSEO_TRACE_PERF", "1")' in perf_src, (
        "the trace pass is not on by default")
    conftest = (Path(__file__).resolve().parent / "conftest.py").read_text(encoding="utf-8")
    assert 'os.environ["CLAUDITSEO_TRACE_PERF"] = "0"' in conftest
    # And it is actually off while this runs, which is what keeps every other
    # clause in the suite free of a browser pass.
    assert os.environ.get("CLAUDITSEO_TRACE_PERF") == "0"


def test_the_part_states_the_sample_beside_the_device_profile():
    """Condition two's other half. The payload carries the pass's OWN
    statement rather than a constant repeated on the client, which could say
    one thing while the pass did another."""
    assert '"sample": (evidence.get("perf_sample")' in RUNS
    assert "traced: {now.sample}" in SPEED, "the part does not state the sample"
    assert "sample: string;" in SPEED, "the sample is not on the type"
    # And a run stored before the pass recorded it gets an observation rather
    # than silence or a guess at the rule.
    assert "def _derived_sample" in RUNS
    assert "not recorded on this run" in RUNS


# --- condition one: a slot only Speed fills --------------------------------

def test_no_other_part_mounts_the_pills():
    """"Everywhere else the pills stay gone", enforced by the mount rather
    than by a conditional inside a shared row.

    Read off the source because a rendered clause can only check the parts a
    fixture happens to open — and the claim is about every part, including the
    ones 147 and 148 have not written yet.
    """
    assert "SpeedActions" in ANATOMY, "the pills are not mounted at all"
    assert ANATOMY.count("<SpeedActions") == 1, ANATOMY.count("<SpeedActions")
    assert 'current.key === "speed" && (' in ANATOMY, (
        "the pills are mounted without being Speed's")
    # And on the three-block layout Speed moved to (brief v25 step BP), once,
    # behind the same condition.
    part = (SRC / "part_page.tsx").read_text(encoding="utf-8")
    assert part.count("<SpeedActions") == 1, part.count("<SpeedActions")
    assert 'part.key === "speed" && onSpeedBrief ?' in part
    # Nobody else imports the component.
    others = [p.name for p in SRC.glob("*.tsx")
              if p.name not in ("anatomy.tsx", "speed_now.tsx", "part_page.tsx")
              and "SpeedActions" in p.read_text(encoding="utf-8")]
    assert not others, others
    # And the shared row carries no depth vocabulary of its own: the pills are
    # the slot's, not the row's.
    row = ANATOMY[ANATOMY.index('<div className="cat-run">'):]
    row = row[:row.index("</div>")]
    assert "Standard" not in row and "Deep" not in row, (
        "the shared row has grown depth words of its own")


def test_the_free_pill_and_the_two_that_spend_are_told_apart():
    """F-10: the control that spends is marked and the one that does not is
    not. Three pills in one row is precisely where that could be lost, so the
    free one carries `action-free` and its own hook, and both paid ones are
    drawn from ONE branch so the two cannot drift apart."""
    acts = _acts()
    # Item 183: the free re-check is a SecondaryButton.
    assert "<SecondaryButton" in acts and 'className="sp-act-prf"' in acts
    # Item 183: one SpendButton, mapped over the two depths.
    assert acts.count("<SpendButton") == 1, (
        "the paid pills are not drawn from one branch, so the two could drift")
    assert "Re-check PRF · free" in acts
    assert '["standard", "deep"] as const' in acts
    # The phrase is split across concatenated lines in the title, so the
    # fragment is what is asserted rather than the sentence.
    assert "third-party " in acts and "waterfall where the trace has one" in acts


def test_deeps_price_is_a_floor_and_not_an_invented_multiple():
    """A first pass priced Deep at `cost * 1.6`. That is a made-up number: the
    two depths are ONE tool with one measurement, the waterfall's share of the
    tokens has never been measured, and `~USD 0.13` on a 1.6x guess reads as a
    promise — which is the same objection `SECS_PER_PAGE` records about false
    precision in an estimate.

    So Deep shows the standard estimate with a `+`: at least that, because
    Deep sends everything Standard sends and more. And `unpriced` where
    nothing has measured the tool at all, which is where it stands until the
    brief has run once.
    """
    # Comments stripped first: the note explaining why the multiple is gone
    # QUOTES it, and an assertion over the prose would fail on its own
    # explanation. The claim is about the code.
    acts = _acts(code_only=True)
    assert "* 1.6" not in acts, (
        "Deep's price is a multiple of Standard's, which nobody measured")
    assert 'depth === "deep" && cost != null ? "+" : ""' in acts
    assert "unpriced" in acts
    # And WHICH WAY the figure is wrong is in RENDERED TEXT, not in the pill's
    # title. It was in the title first, and
    # `test_that_a_money_total_understates_never_lives_only_in_a_title` caught
    # it - UX-80: the direction a money total is wrong in is the one thing an
    # operator cannot derive, and a tooltip is not a place they read.
    assert "sp-act-floor" in acts
    assert "Deep is at least the Standard figure" in acts
    titles = [expr for _line, expr in
              __import__("tests.test_dashboard_a11y", fromlist=["title_attrs"])
              .title_attrs(SPEED)]
    assert not [t for t in titles if "floor" in t], titles


def test_deep_is_a_bigger_context_and_not_a_bigger_model():
    """The brief's words: Deep is "the same plus a per-page third-party
    waterfall". More evidence, not more judgement — conflating the two would
    move the pill's price for a reason its label does not state."""
    speed = EXPERT[EXPERT.index("def _speed_context"):]
    speed = speed[:speed.index("\ndef ")]
    assert 'depth: str = "standard"' in speed
    assert 'if depth == "deep":' in speed
    assert "third_party_ledger" in speed
    # No model or tier choice inside the context builder.
    assert "model_for_tool" not in speed and "model_for_tier" not in speed, (
        "the depth is choosing a model as well as a context")
    # And a deep run that found nothing to add says so, rather than reading as
    # a standard run the operator was charged twice for.
    assert "no traced page on this run loaded a" in speed


def test_the_waterfall_reaches_the_model_through_a_slot_the_prompt_declares():
    """`speed.md` is the operator's and is installed VERBATIM, so it declares
    the slots it declares. The waterfall is appended to `PAGE_SET` — the
    per-page evidence block — rather than given a `{THIRD_PARTY_WATERFALL}` of
    its own, which would have meant editing a file the standing rule says not
    to touch.

    Asserted both ways: the prompt has no such placeholder, and the context
    builder invents no key the prompt cannot use.
    """
    prompt = (ROOT / "clauditseo" / "prompts" / "speed.md").read_text(encoding="utf-8")
    assert "{THIRD_PARTY_WATERFALL}" not in prompt
    assert "{DEPTH}" not in prompt
    speed = EXPERT[EXPERT.index("def _speed_context"):]
    speed = speed[:speed.index("\ndef ")]
    assert '"THIRD_PARTY_WATERFALL"' not in speed, (
        "the context invents a placeholder the prompt cannot fill")
    assert '"DEPTH"' not in speed
    assert "page_set +=" in speed and "deep depth" in speed


def test_the_route_refuses_a_depth_it_does_not_know():
    """An unknown depth is a 400 and not a silent `standard`: a pill that
    spent at a depth the server quietly replaced would bill for one thing and
    report another."""
    assert 'if asked not in ("standard", "deep"):' in APP
    assert "unknown depth" in APP
    assert "depth: str | None = None" in APP, "AdviseIn carries no depth"
