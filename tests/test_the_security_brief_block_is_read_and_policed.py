"""Item 143 step BD: the Security brief's block is stored whole, and two of its
rules are enforced by the parser rather than trusted to the model.

- `compromise`, `ledger`, `transport`, `headers`, `cookies`, `scripts` and
  `do_not_spend_on` are kept as the "now"; each row keeps its `config` per
  layer, which `extra` (scalars only) would have dropped.
- A row for a held check (G reputation, H infrastructure) is dropped with its
  reason: it may appear only under `not_assessable`.
- A row carrying exploitation content is dropped: exposure is reported, not
  weaponised.
"""

from __future__ import annotations

import json

from clauditseo import briefs
from clauditseo.analysts import contract

CHECKS = list(next(b for b in briefs.catalogue() if b.id == "security").checks)
PAGES = ["https://x.test/"]


def _parse(block: dict):
    text = "```json\n" + json.dumps(block) + "\n```\n\n### Security & transport — assessment\nok\n"
    return contract.parse(text, CHECKS, PAGES)


def _row(check, **kw):
    return {"check": check, "domain": "B", "page": None, "status": "FAIL",
            "severity": "MEDIUM", "evidence": "no CSP", **kw}


BLOCK = {
    "part": "security", "schema": "security/1",
    "compromise": {"verdict": "none observed", "basis": "all first-party"},
    "ledger": [{"domain": "A", "status": "assessed"},
               {"domain": "H", "status": "not assessed", "missing": "active_probing_authorised = true"}],
    "transport": {"tls": ["1.2", "1.3"], "legacy": False, "redirect_hops": 2},
    "headers": [{"header": "content-security-policy", "present": True, "verdict": "weak"}],
    "cookies": [{"name": "sid", "secure": True, "httponly": False}],
    "scripts": [{"origin": "www.googletagmanager.com", "class": "known vendor", "sri": False}],
    "do_not_spend_on": [{"control": "COOP/COEP", "why": "brochure site"}],
    "rows": [_row("SEC/csp-policy", replacement="Content-Security-Policy-Report-Only: default-src 'self'",
                  config=[{"layer": "edge", "stack": "cloudflare", "block": "Transform Rule"},
                          {"layer": "origin", "stack": "nginx", "block": "add_header ..."}],
                  deploy_risk="none as Report-Only", verify="curl -sI", rollback="remove the header",
                  order=3, staged="Report-Only 14 days")],
    "not_assessable": [{"check": "SEC/open-ports", "reason": "pending authorisation"}],
}


def test_the_now_fields_and_the_per_layer_config_are_kept():
    got = _parse(BLOCK)
    assert got.compromise == {"verdict": "none observed", "basis": "all first-party"}
    assert [e["domain"] for e in got.ledger] == ["A", "H"]
    assert got.transport["redirect_hops"] == 2
    assert got.headers and got.cookies and got.scripts and got.do_not_spend_on
    row = got.rows[0]
    assert [c["layer"] for c in row.config] == ["edge", "origin"]
    assert row.extra["verify"] == "curl -sI" and row.extra["order"] == 3
    stored = got.as_dict()
    for key in ("compromise", "ledger", "transport", "headers", "cookies", "scripts", "do_not_spend_on"):
        assert stored[key], key
    assert stored["rows"][0]["config"][1]["stack"] == "nginx"


def test_a_row_for_a_held_check_is_dropped_with_its_reason():
    block = dict(BLOCK, rows=[_row("SEC/open-ports", domain="H", evidence="port 22 open")])
    got = _parse(block)
    assert not got.rows
    assert "held" in got.dropped[0]["reason"] and "not_assessable" in got.dropped[0]["reason"]


def test_a_row_carrying_an_exploit_is_dropped_and_a_normal_fix_is_not():
    bad = _parse(dict(BLOCK, rows=[_row("SEC/cms-login-exposed",
                                        replacement="try the rockyou wordlist against wp-login.php")]))
    assert not bad.rows and "exploitation content" in bad.dropped[0]["reason"]
    bad = _parse(dict(BLOCK, rows=[_row("SEC/dangling-cname",
                                        replacement="heroku create old-app to prove it can be taken")]))
    assert not bad.rows
    fine = _parse(dict(BLOCK, rows=[_row("SEC/dangling-cname",
                                         replacement="Remove the CNAME before anyone can register the dangling target; rotate the password.")]))
    assert fine.rows, fine.dropped


def test_the_security_now_reaches_the_part_payload():
    import inspect

    from clauditseo.persistence import runs
    src = inspect.getsource(runs.anatomy_view)
    assert '"brief_security": brief_security.get(c.key)' in src
    for key in ("compromise", "ledger", "transport", "headers", "cookies", "scripts", "do_not_spend_on"):
        assert f'"{key}"' in src, key


def test_a_row_about_a_well_known_path_is_kept_site_level():
    """twenty22's first live Security run put `/wp-json/wp/v2/users` in `page`
    and the page-set rule dropped a true HIGH."""
    got = _parse(dict(BLOCK, rows=[_row("SEC/cms-user-enumeration", page="/wp-json/wp/v2/users",
                                        severity="HIGH", evidence="lists 2 users")]))
    assert got.rows, got.dropped
    assert got.rows[0].evidence.startswith("/wp-json/wp/v2/users")
    # A path that is neither crawled nor swept is still dropped.
    assert not _parse(dict(BLOCK, rows=[_row("SEC/csp-weak", page="/nowhere/")])).rows


def test_naming_an_attack_as_impact_is_not_carrying_one():
    """twenty22's user-enumeration row says usernames "narrow credential-
    stuffing"; that describes the risk and must survive."""
    got = _parse(dict(BLOCK, rows=[_row("SEC/cms-user-enumeration",
                                        note="usernames narrow credential stuffing against wp-login.php")]))
    assert got.rows, got.dropped


def test_a_rollout_reaches_the_record_and_the_card(tmp_path):
    from clauditseo.db.connection import connect
    from clauditseo.db.migrate import migrate
    from clauditseo.persistence import repo, runs
    conn = connect(tmp_path / "r.db")
    migrate(conn)
    op = repo.ensure_default_operator(conn)
    site = repo.create_site(conn, repo.create_client(conn, op, "R Co"), "x.test")
    run = runs.create_run(conn, site, ["SEC"], "T2")
    row = _parse(BLOCK).as_dict()["rows"][0]
    conn.execute("UPDATE audit_runs SET status='complete' WHERE id=?", (run,))
    conn.commit()
    runs.record_contract_findings(conn, run, "security", "m", [row])
    runs.store_expert_report(conn, run, "security", {"model": "m", "report": "", "contract": {"rows": [row]}})
    runs.recompute_contract_states(conn, site, "security")
    got = [s for s in runs.site_states(conn, site) if s["check_id"] == "csp-policy"]
    assert got and got[0]["rollout"]["verify"] == "curl -sI"
    assert [c["stack"] for c in got[0]["rollout"]["config"]] == ["cloudflare", "nginx"]
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "dashboard" / "src" / "part_page.tsx").read_text(encoding="utf-8")
    body = src[src.index("function SecurityFixBody"):src.index("function HeadingsSiteNow")]
    for label in ("Deploy risk", "Verify", "Roll back", "r?.config"):
        assert label in body, label


def test_a_proposed_csp_names_only_origins_the_crawl_saw_load():
    """Item 143 step BD: script, frame and default sources are held to the hosts
    the served markup loaded from, plus the site's own. font-src and connect-src
    load from CSS and script, which are not read, so they are not policed."""
    rules = contract.Rules(resource_origins={"www.googletagmanager.com", "player.vimeo.com"},
                           site_host="www.x.test")
    csp = ("Content-Security-Policy-Report-Only: default-src 'self'; "
           "script-src 'self' https://www.googletagmanager.com https://cdn.x.test 'nonce-<n>'; "
           "frame-src https://player.vimeo.com; font-src https://fonts.gstatic.com; "
           "connect-src https://api.segment.io; img-src 'self' data: https:")
    text = lambda block: "```json\n" + json.dumps(block) + "\n```\n\nok\n"  # noqa: E731
    kept = contract.parse(text(dict(BLOCK, rows=[_row("SEC/csp-policy", replacement=csp)])),
                          CHECKS, PAGES, rules=rules)
    assert len(kept.rows) == 1 and not kept.dropped
    guessed = csp.replace("frame-src https://player.vimeo.com",
                          "frame-src https://player.vimeo.com https://widget.trustpilot.com")
    bad = contract.parse(text(dict(BLOCK, rows=[_row("SEC/csp-policy", replacement=guessed)])),
                         CHECKS, PAGES, rules=rules)
    assert not bad.rows and "widget.trustpilot.com" in bad.dropped[0]["reason"]
    assert contract.csp_unobserved("script-src *.vimeo.com", {"player.vimeo.com"}, "") == []
    # Evidence from before the inventory: the rule cannot be judged and is not applied.
    old = contract.parse(text(dict(BLOCK, rows=[_row("SEC/csp-policy", replacement=guessed)])),
                         CHECKS, PAGES, rules=contract.Rules())
    assert len(old.rows) == 1


def test_the_evidence_carries_the_origins_and_the_brief_is_told_them():
    from clauditseo.crawler.evidence import resource_origins
    from clauditseo.crawler.types import Page
    html = ('<script src="https://www.googletagmanager.com/gtm.js"></script>'
            '<link rel="stylesheet" href="https://fonts.googleapis.com/css">'
            '<iframe src="https://player.vimeo.com/v/1"></iframe><img src="/a.png">'
            '<script src="data:text/javascript,1"></script>')
    page = Page(url="https://x.test/", requested_url="https://x.test/", status=200,
                content_type="text/html", headers={}, content=html)
    got = resource_origins([page, page])
    assert got == {"script": {"www.googletagmanager.com": 2}, "frame": {"player.vimeo.com": 2},
                   "style": {"fonts.googleapis.com": 2}, "img": {"x.test": 2}}
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "clauditseo" / "analysts" / "expert.py").read_text(encoding="utf-8")
    assert "OBSERVED RESOURCE ORIGINS" in src and "rules=contract_rules(site, evidence=evidence," in src
