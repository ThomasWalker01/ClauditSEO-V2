"""Page mode says what it judged on the page, and only that (screen audits
round 3, Speed AC-01).

On one page Speed read "8 checks clean on every page this audit traced (12
traced of 45 crawled): ... ttfb-slow" while site mode had `ttfb-slow` open on
two traced pages, and "7 checks pass on this page: ... cwv-not-assessed", a
check filed with no URL, which page mode drops and so always read clean.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from clauditseo.persistence import runs

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"


def test_page_mode_names_the_checks_filed_for_the_site():
    src = inspect.getsource(runs.anatomy_view)
    assert 'site_level.setdefault(an.categorise(r["check_id"], r["dimension"]),' in src
    assert '"site_level_checks": sorted(site_level.get(c.key, ())),' in src


def test_the_checks_table_is_told_it_is_on_one_page():
    part = (SRC / "part_page.tsx").read_text(encoding="utf-8")
    assert part.count("onePage={Boolean(page)}") == 3
    assert '{onePage ? " this page" : " every "}' in part
    assert "clean on this page's trace" in part
    assert "filed\n                for the site as a whole, not per page" in part.replace("\r\n", "\n")


def test_neither_pass_list_counts_a_site_level_check():
    part = (SRC / "part_page.tsx").read_text(encoding="utf-8")
    assert ".filter((c) => !(page && (part.site_level_checks ?? []).includes(c)));" in part
    anatomy = (SRC / "anatomy.tsx").read_text(encoding="utf-8")
    assert "!why.has(c.check) && !siteLevel.has(c.check)" in anatomy
