"""Round 4 Mediums on Crawl, Security and Images (screen audits round 4).

- Crawl IP-10: nine `head-divergent` cards ended "Where: element"; the
  row names its elements under `element`, and the card now reads it.
- Crawl AC-06: a row the model returned PASS is said as a pass.
- Crawl AC-02: an analysis row filed on `/` for the site is seen by a sweep
  that raised its check on any page.
- Crawl UX-04, UI-01, UI-03: the folded agents have the matrix's header;
  the parity pages that differ come first.
- Security AC-06: an enforced DMARC policy missing only `rua` is Medium.
- Security AC-05, Images IP-01: a hold the reader set aside is not a row.
- Images AC-08: a WordPress size suffix does not hide an alt that is the
  file's name; AC-07: an alt chip is drawn on the placement it quotes.
"""
from __future__ import annotations

import inspect
from pathlib import Path

from clauditseo.modules import onp, sec
from clauditseo.persistence import runs

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"


def test_a_head_divergent_row_names_its_element():
    assert runs._element_said({"element": "og:title"}) == "og:title"
    assert runs._element_said({"tag": "a", "cls": "btn x"}) == "a.btn"


def test_a_pass_row_is_dropped_as_a_pass():
    src = inspect.getsource(runs)
    assert '"reason": "a pass, not a hold" if passed' in src


def test_a_site_row_on_home_is_seen_by_a_sweep_raising_it_anywhere():
    src = inspect.getsource(runs._unseen_by_sweeps)
    assert 'pages == {"/"} and any(c == check_id for c, _p in raised(sweep))' in src


def test_the_folded_agents_read_under_the_matrix_header():
    c = (SRC / "crawl_now.tsx").read_text(encoding="utf-8")
    assert c.count("<MatrixHead row={now.ua_matrix[0]} />") == 2
    assert "[...parity.pages].sort(" in c


def test_an_enforced_dmarc_policy_missing_reports_is_medium():
    src = inspect.getsource(sec)
    assert 'enforced = tags.get("p", "").lower() in ("quarantine", "reject")' in src
    assert 'severity=row.get("severity") or DEFAULT_SEVERITY[row["check"]]' in src


def test_a_set_aside_hold_is_not_a_returned_row():
    src = inspect.getsource(runs)
    assert '"tool": er["tool_id"], "hold": True})' in src
    p = (SRC / "part_page.tsx").read_text(encoding="utf-8")
    assert "(d) => !d.hold && heldChecks.has(" in p


def test_a_wordpress_size_suffix_does_not_hide_the_files_name():
    src = "https://gate-six.test/wp-content/uploads/2024/05/blue-gate-garden-300x300.webp"
    assert onp._alt_says_nothing("Blue gate garden", src) == "the file's name"
    edited = "https://gate-six.test/uploads/front-door-e1733966478717.jpg"
    assert onp._alt_says_nothing("front door", edited) == "the file's name"
    assert onp._alt_says_nothing("A blue garden gate at dusk", src) is None


def test_an_alt_chip_is_drawn_on_the_placement_it_quotes():
    p = (SRC / "part_page.tsx").read_text(encoding="utf-8")
    assert "problems(i.src, i.alt)" in p
    assert 'f.checkId.startsWith("img-alt")' in p
