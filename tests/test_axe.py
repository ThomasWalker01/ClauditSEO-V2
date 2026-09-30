"""The rendered accessibility pass.

Everything here runs without a browser. The mapping from axe's output to our
findings, the de-duplication against dimensions that already own a check, and
the behaviour when the renderer is absent are all decidable from a recorded
result object — and they are where the bugs would be. Actually driving
Chromium is the one part that is upstream's job to get right.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

import pytest

from clauditseo import axe
from clauditseo.crawler.types import CrawlResult, Page
from clauditseo.engine.types import Severity, Tier
from clauditseo.modules.a11y import AccessibilityModule, _spread
from clauditseo.modules.pagefacts import extract_facts

VENDOR = Path(__file__).resolve().parents[1] / "clauditseo" / "vendor"

# One page's worth of axe output, trimmed to the shape we consume.
RESULT = {
    "url": "https://x.test/",
    "testEngine": {"name": "axe-core", "version": "4.13.0"},
    "violations": [
        {"id": "color-contrast", "impact": "serious",
         "help": "Elements must meet minimum colour contrast ratio thresholds",
         "helpUrl": "https://dequeuniversity.com/rules/axe/4.13/color-contrast",
         "tags": ["cat.color", "wcag2aa", "wcag143"],
         "nodes": [{"target": [".price"], "html": "<span class=price>$9</span>",
                    "failureSummary": "Expected 4.5:1 but got 2.1:1"},
                   {"target": [".note"], "html": "<p class=note>terms</p>",
                    "failureSummary": "Expected 4.5:1 but got 3.0:1"}]},
        {"id": "aria-required-children", "impact": "critical",
         "help": "Certain ARIA roles must contain particular children",
         "helpUrl": "https://dequeuniversity.com/rules/axe/4.13/aria-required-children",
         "tags": ["cat.aria", "wcag2a", "wcag131"],
         "nodes": [{"target": ["#menu"], "html": '<ul role="menu">',
                    "failureSummary": "Element has children which are not allowed"}]},
        # Owned by ONP. Must not come through, or one missing alt is deducted
        # under two dimensions.
        {"id": "image-alt", "impact": "critical", "help": "Images must have alt",
         "helpUrl": "https://x", "tags": ["wcag2a"],
         "nodes": [{"target": ["img"], "html": "<img>", "failureSummary": "no alt"}]},
    ],
}


# ---- the vendored asset ----------------------------------------------------

def test_the_vendored_script_matches_what_the_readme_records():
    """A silent swap of a 580KB third-party blob should fail the build, not
    be discovered by an operator wondering why findings changed."""
    js = VENDOR / "axe.min.js"
    readme = (VENDOR / "README.md").read_text(encoding="utf-8")
    digest = hashlib.sha256(js.read_bytes()).hexdigest()
    assert digest in readme, (
        f"axe.min.js is {digest} but README.md records something else — "
        "update the table when upgrading")
    assert f"{js.stat().st_size:,}" in readme
    assert (VENDOR / "axe-core-LICENSE.txt").is_file(), "MPL-2.0 text must ship"


def test_git_is_told_not_to_normalise_the_vendored_blob():
    """The hash check above is only as good as the bytes Git checks out.

    `.gitattributes` carried the rule from the start — and named
    `auditdeck/vendor/`, a package renamed away on 14 August 2026. The rule
    parsed, matched nothing, and bound nothing, so a fresh clone on a
    normalising Git rewrote the blob's line endings and failed the check
    above for a reason no one would look for. Windows especially, which is
    where most of this runs.

    Asserted through `git check-attr` rather than by reading `.gitattributes`
    as text, because the defect was a rule that read perfectly and applied to
    no file. Only Git can say what it actually binds.
    """
    js = VENDOR / "axe.min.js"
    rel = js.relative_to(Path(__file__).resolve().parents[1]).as_posix()
    # Resolved with no `or "git"` fallback: that produced a bare name at
    # exactly the moment resolution failed, and on Windows CreateProcess
    # searches System32 before PATH, so the program that ran need not be the
    # one that was looked for. Unresolvable git reaches the same skip as an
    # unusable one — this test asks Git what it binds, so without Git it has
    # no question to put.
    git = shutil.which("git")
    if not git:
        pytest.skip("git unavailable: not resolvable on PATH")
    try:
        out = subprocess.run([git, "check-attr", "text", "--", rel],
                             capture_output=True, text=True, timeout=30,
                             cwd=Path(__file__).resolve().parents[1])
    except (OSError, subprocess.SubprocessError) as exc:
        pytest.skip(f"git unavailable: {exc}")
    if out.returncode != 0:
        pytest.skip(f"git check-attr failed: {out.stderr.strip()}")
    value = out.stdout.strip().rsplit(": ", 1)[-1]
    assert value == "unset", (
        f"git reports `text: {value}` for {rel} — the -text rule is not "
        "binding it, so a fresh clone may normalise a blob this suite "
        "checks byte for byte")


def test_availability_needs_both_halves(monkeypatch):
    monkeypatch.setattr(axe, "AXE_JS", VENDOR / "does-not-exist.js")
    assert axe.available() is False


# ---- mapping ---------------------------------------------------------------

def test_violations_become_findings_with_severity_and_evidence():
    found = axe.findings_from(RESULT, "https://x.test/", "/")
    by_id = {f.check_id: f for f in found}

    contrast = by_id["axe-color-contrast"]
    assert contrast.severity is Severity.HIGH          # axe "serious"
    assert contrast.evidence["nodes_total"] == 2
    assert contrast.evidence["wcag"] == ["wcag143", "wcag2aa"]
    assert "2.1:1" in contrast.evidence["nodes"][0]["why"]
    assert contrast.evidence["help_url"].startswith("https://")

    assert by_id["axe-aria-required-children"].severity is Severity.CRITICAL


def test_rules_another_dimension_owns_are_dropped():
    ids = {f.check_id for f in axe.findings_from(RESULT, "https://x.test/", "/")}
    assert "axe-image-alt" not in ids, "ONP already raises img-alt-missing"
    assert ids == {"axe-color-contrast", "axe-aria-required-children"}


def test_check_ids_are_namespaced_so_upstream_cannot_collide_with_ours():
    for f in axe.findings_from(RESULT, "https://x.test/", "/"):
        assert f.check_id.startswith("axe-")


def test_an_unknown_impact_does_not_crash_or_silently_vanish():
    odd = {"violations": [{"id": "novel-rule", "impact": None, "help": "h",
                           "tags": [], "nodes": []}]}
    found = axe.findings_from(odd, "https://x.test/", "/")
    assert len(found) == 1 and found[0].severity is Severity.MEDIUM


def test_the_coverage_note_states_the_limit_of_automation():
    note = axe.coverage_note(5, {"name": "axe-core", "version": "4.13.0"})
    assert note.severity is Severity.INFO
    assert "4.13.0" in note.summary
    assert "third" in note.recommendation      # roughly a third of WCAG
    assert "still need a person" in note.recommendation


# ---- sampling --------------------------------------------------------------

def _facts(n: int):
    pages = [Page(url=f"https://x.test/p{i}", requested_url=f"https://x.test/p{i}",
                  status=200, content_type="text/html",
                  content="<html lang=en><body><main>x</main></body></html>")
             for i in range(n)]
    return [extract_facts(p) for p in pages]


def test_sampling_keeps_the_homepage_and_spreads_the_rest():
    picked = _spread(_facts(50), 5)
    assert len(picked) == 5
    assert picked[0].path == "/p0", "the entry page is always read"
    # Not simply the first five, which would all share the homepage template.
    assert [f.path for f in picked] != ["/p0", "/p1", "/p2", "/p3", "/p4"]


def test_sampling_returns_everything_when_the_crawl_is_small():
    assert len(_spread(_facts(3), 5)) == 3


# ---- integration with the dimension ----------------------------------------

def _run(**context):
    page = Page(url="https://x.test/", requested_url="https://x.test/", status=200,
                content_type="text/html",
                content="<html lang=en><body><main>hi</main></body></html>")
    crawl = CrawlResult(start_url="https://x.test/", tier=Tier.T2, pages=[page])
    return AccessibilityModule().run([], Tier.T2, {"crawl": crawl, **context})


def test_without_a_renderer_the_dimension_says_contrast_was_not_assessed():
    found = {f.check_id for f in _run(skip_axe=True)}
    assert "contrast-not-assessed" in found


def test_the_pass_is_skipped_silently_rather_than_failing_the_run(monkeypatch):
    """A bare install audits everything else and is told once what it lacks —
    not once per page, and not by an exception."""
    monkeypatch.setattr(axe, "available", lambda: False)
    found = _run()
    assert not [f for f in found if f.check_id.startswith("axe-")]
    assert "contrast-not-assessed" in {f.check_id for f in found}


def test_a_page_that_will_not_render_is_reported_as_unassessed(monkeypatch):
    """Never silently clean: a page that failed to load has not passed."""
    monkeypatch.setattr(axe, "available", lambda: True)
    monkeypatch.setattr(axe, "run_page",
                        lambda url, **kw: (_ for _ in ()).throw(RuntimeError("timeout")))
    found = _run()
    failed = [f for f in found if f.check_id == "axe-render-failed"]
    assert len(failed) == 1
    assert "timeout" in failed[0].evidence["error"]
    # Nothing rendered, so the dimension must still admit the gap.
    assert "contrast-not-assessed" in {f.check_id for f in found}


def test_a_successful_pass_replaces_the_unassessed_note(monkeypatch):
    monkeypatch.setattr(axe, "available", lambda: True)
    monkeypatch.setattr(axe, "run_page", lambda url, **kw: RESULT)
    found = {f.check_id for f in _run()}
    assert "axe-color-contrast" in found
    assert "axe-coverage" in found
    assert "contrast-not-assessed" not in found, \
        "the renderer ran, so the disclaimer would now be false"
