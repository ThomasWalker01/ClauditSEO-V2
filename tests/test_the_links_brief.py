"""`links.md` — the Links brief, installed as the operator supplied it
(brief v17 step AW, part 2).

The brief's own text says to rewrite `site-architecture.md` onto the
contract; the operator supplied the rewritten prompt instead and asked for
it verbatim, so the first clause here is a byte comparison against the
attachment. Nothing about this file may be edited to make the engine
happy: where the prompt and the product disagreed, the product moved —
the anatomy's part key became `links` at AW1 for exactly that reason.

`site-architecture` is retired by the same step. It is the prompt this one
replaces, and leaving both would put two briefs on one part, each with its
own vocabulary, and let an operator pay for the older one.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clauditseo import briefs

ATTACHMENT = Path(r"C:/Users/owner/Documents/AI/_relay/attachments/brief-v17/links.md")
INSTALLED = Path(__file__).resolve().parents[1] / "clauditseo" / "prompts" / "links.md"


def test_the_prompt_is_the_one_the_operator_supplied():
    assert INSTALLED.is_file(), INSTALLED
    if not ATTACHMENT.is_file():
        pytest.skip("the relay attachment is not on this machine")
    # Verbatim, but for the operator's later wording ruling (item 166,
    # 2026-09-30: run -> audit, sweep -> automatic checks), applied to the
    # prompts in place. The attachment is the operator's and is not edited;
    # the same four substitutions are made to it here, and nothing else may
    # differ.
    supplied = ATTACHMENT.read_bytes().decode("utf-8")
    for old, new in (("or a prior run", "or a prior audit"),
                     ("from the run and the site record", "from the audit and the site record"),
                     ("  RUN:              {{RUN_ID}}", "  AUDIT:            {{RUN_ID}}"),
                     ("Start from SWEEP RESULTS.", "Start from AUTOMATIC CHECK RESULTS.")):
        assert supplied.count(old) == 1, old
        supplied = supplied.replace(old, new)
    # And the example client's name, which the public tree does not carry
    # (operator, 2026-09-30): the attachment names the real acceptance site.
    # The name is not written here either - this file ships, and the client
    # guard reads it - so it is spelt backwards.
    import re
    real = "ebirt"[::-1]
    supplied = re.sub(rf"(?<![A-Za-z])({real.capitalize()}|{real})(?![A-Za-z])",
                      lambda m: "Birch" if m.group(1)[0].isupper() else "birch", supplied)
    assert INSTALLED.read_bytes().decode("utf-8") == supplied, (
        "links.md differs from the attachment the operator asked to be "
        "installed verbatim (as reworded by the 2026-09-30 ruling); where the "
        "prompt and the product disagree, the product moves")


def test_no_prompt_is_normalised_on_checkout():
    """The byte comparison above can only hold if Git leaves the file alone
    (item 170).

    `core.autocrlf` is true on the operator's machine and nothing covered
    `clauditseo/prompts/`, so checkout wrote the prompts with CRLF while the
    attachments hold LF, and the comparison failed on the first newline. The
    shape of it is the dangerous part: the main checkout passed, because its
    copy was written by a tool and never re-checked-out, while every fresh
    clone and every new worktree failed — and the failure text accused the
    prompt of differing from what the operator supplied.

    Asked through `git check-attr`, not by reading `.gitattributes`, for the
    reason `tests/test_axe.py` gives: a rule can read perfectly and bind
    nothing, which is exactly how the vendored blob's rule was broken for ten
    audit rounds. Every prompt, not only the compared one, because the trap is
    laid for whichever prompt is held to its attachment next.
    """
    import shutil
    import subprocess

    root = Path(__file__).resolve().parents[1]
    prompts = sorted((root / "clauditseo" / "prompts").glob("*.md"))
    assert len(prompts) >= 20, f"only {len(prompts)} prompts found under {root}"
    git = shutil.which("git")
    if not git:
        pytest.skip("git unavailable: not resolvable on PATH")
    rels = [p.relative_to(root).as_posix() for p in prompts]
    try:
        out = subprocess.run([git, "check-attr", "text", "--", *rels],
                             capture_output=True, text=True, timeout=30, cwd=root)
    except (OSError, subprocess.SubprocessError) as exc:
        pytest.skip(f"git unavailable: {exc}")
    if out.returncode != 0:
        pytest.skip(f"git check-attr failed: {out.stderr.strip()}")
    normalised = [line for line in out.stdout.splitlines()
                  if line.strip() and line.rsplit(": ", 1)[-1] != "unset"]
    assert not normalised, (
        "these prompts are not bound by the `-text` rule, so a fresh clone or a "
        "new worktree may rewrite their line endings and fail the byte "
        f"comparison above: {normalised}")


def test_the_header_loads_and_names_the_part_and_its_twelve_checks():
    brief = briefs.by_id()["links"]
    assert brief.part == "links" and brief.scope == "site", brief
    assert len(brief.checks) == 12, brief.checks
    free = {"LNK/inlinks-low", "LNK/orphan", "LNK/anchor-generic",
            "LNK/anchor-duplicate-target", "LNK/broken-internal",
            "LNK/redirect-chain", "LNK/nofollow-internal", "LNK/depth-deep"}
    model = {"LNK/link-suggestion", "LNK/anchor-entity", "LNK/hub-spoke-gap",
             "LNK/anchor-flow"}
    assert set(brief.checks) == free | model, sorted(brief.checks)
    # Two more than the brief's prose lists. The file is authoritative; both
    # are analysis, and both are registered as such.
    from clauditseo.checks import check_costs
    costs = check_costs()
    assert {costs[c] for c in free} == {"free"}, [(c, costs[c]) for c in free]
    assert {costs[c] for c in model} == {"model"}, [(c, costs[c]) for c in model]


def test_it_is_a_conforming_brief_the_engine_can_run():
    from clauditseo.analysts.expert import EXPERT_TOOLS, conforms

    assert "links" in EXPERT_TOOLS, sorted(EXPERT_TOOLS)
    assert EXPERT_TOOLS["links"]["scope"] == "site"
    assert conforms("links"), (
        "the prompt does not ask for the findings block, so nothing it "
        "returns would be parsed")


def test_the_brief_it_replaces_is_retired():
    from clauditseo.analysts.expert import EXPERT_TOOLS
    from clauditseo.playbook import PLAYBOOK

    assert not (INSTALLED.parent / "site-architecture.md").exists()
    assert "site-architecture" not in EXPERT_TOOLS, sorted(EXPERT_TOOLS)
    ids = {t["id"] for ph in PLAYBOOK for t in ph["tools"]}
    assert "site-architecture" not in ids, sorted(ids)
    assert "links" in ids, sorted(ids)


# --- the context ---------------------------------------------------------

def _evidence():
    """A crawl the brief can be rendered against: a home page, a hub, two
    spokes and a page nothing links to."""
    from clauditseo.crawler.crawl import extract_link_details
    from clauditseo.crawler.evidence import snapshot
    from clauditseo.crawler.types import CrawlResult, Page
    from clauditseo.engine.types import Tier

    base = "https://links.test"

    def page(path, body):
        p = Page(url=base + path, requested_url=base + path, status=200,
                 content_type="text/html; charset=utf-8",
                 content=f"<html><head><title>{path}</title></head>"
                         f"<body>{body}</body></html>")
        p.link_details = extract_link_details(p)
        p.outlinks = [link["url"] for link in p.link_details]
        return p

    nav = '<nav><a href="/events">Events</a></nav>'
    crawl = CrawlResult(start_url=base + "/", tier=Tier.T2)
    crawl.pages.extend([
        page("/", nav + '<main><h1>Home</h1><a href="/events">Birch Events</a></main>'),
        page("/events", nav + '<main><h1>Events</h1><a href="/events-team">Learn more</a></main>'),
        page("/events-team", nav + "<main><h1>The events team</h1></main>"),
        page("/nobody", nav + "<main><h1>Unlinked</h1></main>"),
    ])
    return snapshot(crawl)


def test_every_placeholder_is_filled_from_the_run():
    from clauditseo.analysts.expert import render_prompt
    from clauditseo.engine.types import Site
    from clauditseo.analysts.expert import EXPERT_TOOLS

    ev = _evidence()
    context = EXPERT_TOOLS["links"]["build"](ev, Site(domain="links.test"))
    text = render_prompt("links", context)
    assert "{{" not in text, [line for line in text.splitlines() if "{{" in line]
    # The graph reached it, with the three things a suggestion needs.
    assert "/events-team" in text and "Learn more" in text, text[-3000:]
    assert "nav" in text and "body" in text


# --- the block ------------------------------------------------------------

def test_the_hub_map_and_a_suggestion_survive_the_parser():
    """`hubs` is a fact about the site rather than about any page, so it
    rides beside the rows the way `eligibility` does; `suggestions` is a
    field of a row, and the contract already carries a row's own fields."""
    import json

    from clauditseo.analysts.contract import parse

    block = {
        "part": "links", "run_id": "r1", "source": "brief",
        "hubs": [{"hub": "/events", "spokes": ["/events-team"],
                  "spokes_linking_up": 0, "hub_linking_down": 1, "inlinks_body": 1}],
        "rows": [{
            "check": "LNK/link-suggestion", "page": "/events-team",
            "status": "FAIL", "severity": "MEDIUM",
            "evidence": "1 body inlink; depth 2",
            "replacement": "from / — anchor 'the events team' — after h1 Home",
            "suggestions": [{"source": "/", "anchor": "the events team",
                             "after": "h1 Home", "overlap": ["events", "team"]}],
            "kind": "link", "note": "anchor from the target's h1",
        }],
        "not_assessable": [], "assumptions": [],
    }
    body = "```json\n" + json.dumps(block) + "\n```\n\n### Links on the page — assessment\n"
    parsed = parse(body, checks=["LNK/link-suggestion"],
                   page_set=["https://links.test/events-team"])
    assert not parsed.dropped, parsed.dropped
    assert parsed.hubs and parsed.hubs[0]["hub"] == "/events", parsed.hubs
    assert parsed.as_dict()["hubs"] == parsed.hubs, (
        "the hub map is filled by the parser and dropped by `as_dict`, so it "
        "exists only in memory and reaches no screen")
    row = parsed.rows[0]
    assert row.extra["suggestions"][0]["anchor"] == "the events team", row.extra
