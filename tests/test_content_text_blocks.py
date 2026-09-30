"""The Content overlay's text blocks: captured, hashed, classified (item 136o
Part A).

The browser capture (`axe.py`) cannot run in a unit test, so this seeds the
stored `text_blocks` the way the rendered pass writes them and tests the
read-time classification - which is where the boilerplate / shared / thin /
unique decision actually lives.
"""

from __future__ import annotations

import json

import pytest

from clauditseo.db.connection import connect
from clauditseo.db.migrate import migrate
from clauditseo.modules import a11y
from clauditseo.modules.cnt import content_hash
from clauditseo.persistence import repo, runs


@pytest.fixture()
def seeded(tmp_path):
    conn = connect(tmp_path / "c.db"); migrate(conn)
    op = repo.ensure_default_operator(conn)
    site = repo.create_site(conn, repo.create_client(conn, op, "C"), "x.test")
    run_id = runs.create_run(conn, site, ["A11Y"], "T2")

    def blk(tag, text, landmark="main"):
        return {"tag": tag, "landmark": landmark,
                "words": len(text.split()), "name": " ".join(text.split()[:6]),
                "hash": content_hash(text), "rect": {"x": 0, "y": 0, "w": 10, "h": 10}}

    NAV = "Home About Services Contact Blog"          # on every page -> boilerplate
    HERO = "Bridging finance for Australian small business without the wait"
    SECTION = ("A lender founded in 2009 and run by a team of former brokers "
               "who know the trade, working across every state, funding "
               "amounts from ten thousand to five million, on terms a small "
               "business can actually meet, and settling most applications "
               "inside a single working day rather than the weeks a bank "
               "takes over the same paperwork every single time.")
    # Five pages, so HERO on two is 40 percent - shared, not boilerplate -
    # and NAV on all five is boilerplate. The item's own Acme example is
    # 227 pages; the 90 percent line only means something above a handful.
    tb = {
        "https://x.test/": [blk("p", NAV, landmark="nav"), blk("p", HERO)],
        "https://x.test/about": [
            blk("p", NAV, landmark="nav"),
            blk("p", HERO),                            # shared with home
            blk("h2", "Who we are"),
            blk("p", SECTION),                         # 60+ words -> not thin
            blk("h3", "Careers"),                      # thin: nothing under it
        ],
        "https://x.test/c": [blk("p", NAV, landmark="nav")],
        "https://x.test/d": [blk("p", NAV, landmark="nav")],
        "https://x.test/e": [blk("p", NAV, landmark="nav")],
    }
    conn.execute("UPDATE audit_runs SET crawl_evidence=? WHERE id=?",
                 (json.dumps({"pages": [{"url": u, "status": 200} for u in tb]}), run_id))
    conn.execute(
        "INSERT INTO findings (id, run_id, dimension, check_id, severity, source,"
        " summary, affected_urls, fingerprint, created_at, evidence)"
        " VALUES (?, ?, 'A11Y', 'axe-sampled', 'info', 'deterministic', 's', '[]',"
        " 'axe-sampled', ?, ?)",
        (repo.create_id(), run_id, repo.now_iso(),
         json.dumps({"rendered": 2, "crawled": 2, "text_blocks": tb})))
    conn.commit()
    yield conn, run_id
    conn.close()


def test_every_text_block_has_a_rect_words_and_hash(seeded):
    conn, run_id = seeded
    pl = runs.content_blocks_payload(conn, run_id, "https://x.test/about")
    assert pl["rendered"] is True
    for b in pl["blocks"]:
        assert set(("rect", "words", "hash", "tag", "klass")) <= set(b), b
        assert b["rect"].keys() >= {"x", "y", "w", "h"}


def test_the_hash_is_the_same_one_duplicate_content_uses(seeded):
    conn, run_id = seeded
    pl = runs.content_blocks_payload(conn, run_id, "https://x.test/about")
    hero = next(b for b in pl["blocks"] if "Bridging finance" in b["name"])
    assert hero["hash"] == content_hash(
        "Bridging finance for Australian small business without the wait")


def test_boilerplate_is_landmark_or_on_ninety_percent_of_pages(seeded):
    conn, run_id = seeded
    pl = runs.content_blocks_payload(conn, run_id, "https://x.test/about")
    nav = next(b for b in pl["blocks"] if b["landmark"] == "nav")
    assert nav["klass"] == "boilerplate", nav


def test_shared_names_the_other_pages(seeded):
    conn, run_id = seeded
    pl = runs.content_blocks_payload(conn, run_id, "https://x.test/about")
    hero = next(b for b in pl["blocks"] if "Bridging finance" in b["name"])
    assert hero["klass"] == "shared", hero
    assert hero["other_pages"] == ["https://x.test/"], hero


def test_unique_is_everything_else(seeded):
    conn, run_id = seeded
    pl = runs.content_blocks_payload(conn, run_id, "https://x.test/about")
    body = next(b for b in pl["blocks"] if "founded in 2009" in b["name"])
    assert body["klass"] == "unique", body


def test_thin_is_a_heading_with_under_fifty_words_under_it(seeded):
    """Structural, from the captured blocks - NOT the `question-unanswered`
    model check the item names, which is about whether a question is answered
    and is a different set. The `Careers` h3 has nothing under it."""
    conn, run_id = seeded
    pl = runs.content_blocks_payload(conn, run_id, "https://x.test/about")
    careers = next(b for b in pl["blocks"] if b["name"] == "Careers")
    assert careers.get("thin") is True, careers
    # A heading with a real section under it is not thin.
    who = next(b for b in pl["blocks"] if b["name"] == "Who we are")
    assert who.get("thin") is False, who


def test_totals_sum_and_the_percentage_is_unique_over_all(seeded):
    conn, run_id = seeded
    pl = runs.content_blocks_payload(conn, run_id, "https://x.test/about")
    t = pl["totals"]
    # boilerplate is excluded from `words`; thin markers are excluded too.
    assert t["words"] == t["unique"] + t["shared"], t
    assert t["unique_pct"] == round(100 * t["unique"] / (t["unique"] + t["shared"]))


def test_an_unrendered_page_says_so(seeded):
    conn, run_id = seeded
    pl = runs.content_blocks_payload(conn, run_id, "https://x.test/never-rendered")
    assert pl["rendered"] is False, pl


def test_the_block_hash_matches_the_module_helper():
    """One normalisation. `a11y._block_hash` and `cnt.content_hash` are the
    same function, so a block stored by the pass and a page hashed by the
    check agree."""
    assert a11y._block_hash("Hello  World") == content_hash("Hello World")


def test_every_question_unanswered_heading_is_marked_thin():
    """Containment, not equality (operator ruling through the channel,
    2026-09-08). `CNT/question-unanswered` fires on a heading that is a
    question with NO text beneath - zero words - and zero is under fifty, so
    every such heading is thin by 136o's definition. Not the reverse: a plain
    heading with thirty words under it is thin and is not a question.

    The item said "same detector as question-unanswered". It is not the same
    detector - that one is `CNT/question-unanswered` (deterministic,
    cnt.py), narrower on two axes (the heading must be a question AND empty).
    Thin is the wider, structural fact; this asserts the true relationship
    between them.
    """
    from clauditseo.modules.cnt import is_question

    # The detector's own condition, in one line: a question heading whose
    # `next_text` is empty. `_mark_thin` sees the same heading with no
    # non-boilerplate words after it, so it must mark it thin.
    heading = {"tag": "h2", "words": 3, "klass": "unique",
               "name": "Do we lend to sole traders?"}
    following_none: list = [heading]      # nothing after it
    from clauditseo.persistence.runs import _mark_thin
    _mark_thin(following_none)
    assert is_question("Do we lend to sole traders?")
    assert heading["thin"] is True, ("a question heading the detector fires "
                                     "on is not thin, so containment is broken")

    # And a heading with a real section under it - which the detector would
    # NOT fire on - is not thin, so the two sets are genuinely different.
    h2 = {"tag": "h2", "words": 3, "klass": "unique", "name": "About us"}
    body = {"tag": "p", "words": 60, "klass": "unique", "name": "..."}
    both = [h2, body]
    _mark_thin(both)
    assert h2["thin"] is False
