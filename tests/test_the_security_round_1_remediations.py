"""Round-1 remediations 3, 4, 9 and 10 on Security & transport (item 276,
row 9). The round-2 audit found each unchanged (IP-08, UI-01):

- #3: the grid said "do not spend on Permissions-Policy: no restricted
  feature is used here" with nothing measured behind it, while the analysis's
  Order 8 card added the header.
- #4: a layer card the ledger names dropped its found count, hiding three
  Highs on A and D.
- #9: the TLS floor and certificate expiry were read from a page's facts, so
  site scope never drew them.
- #10: `Server: cloudflare` read SET in the good tone, and counted as a
  header in place.

The verdict, headings, tiles and held wording (#8, #14, #15) are guarded in
`test_the_security_part_page_leads_with_the_verdict.py`.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "dashboard" / "src"


def test_the_do_not_spend_clause_waits_on_a_measurement():
    grid = (SRC / "headers_grid.tsx").read_text(encoding="utf-8")
    assert ('absent.includes(DO_NOT_SPEND) && grid.restricted_features_used === false'
            in grid)
    assert '"worth doing"' not in grid


def test_a_ledger_card_keeps_its_found_count():
    page = (SRC / "part_page.tsx").read_text(encoding="utf-8")
    assert ('note = [found ? `${found} finding${found === 1 ? "" : "s"} open` : null,\n'
            '              why ?? entry.summary ?? (found ? null : "assessed")]'
            '.filter(Boolean).join(" · ");') in page


def test_transport_is_drawn_from_the_part():
    page = (SRC / "part_page.tsx").read_text(encoding="utf-8")
    assert "<TransportFacts transport={part.transport ?? facts?.site?.transport ?? null} />" in page


def test_the_server_row_is_bare_and_not_in_place(tmp_path):
    from clauditseo import security_headers as sh
    from clauditseo.persistence import runs
    import inspect
    src = inspect.getsource(runs.security_headers_payload)
    assert '"inverted": key in sh.INVERTED' in src
    assert 'if not r["inverted"]' in src
    assert '"transport": evidence.get("transport")' in src
    # `cell_state` reads a bare vendor name as not disclosing a version: SET,
    # which the grid draws as BARE.
    assert sh.cell_state("server", {"server": "cloudflare"}, True) == sh.SET
    assert sh.cell_state("server", {"server": "Apache/2.4.1"}, True) == sh.WEAK
    grid = (SRC / "headers_grid.tsx").read_text(encoding="utf-8")
    assert '{bare ? "BARE" : WORD[state]}' in grid
    assert "grid.rows.filter((r) => !r.inverted).length" in grid


def test_security_does_not_draw_the_measurement_bands():
    page = (SRC / "part_page.tsx").read_text(encoding="utf-8")
    # Item 279 (row 9) took Accessibility out too.
    assert 'const BAND_PARTS = new Set(["title-desc", "speed"]);' in page


def test_the_certificate_date_reads_the_probes_form(tmp_path):
    """twenty22's site scope drew "valid to Dec 14 13:" - the OpenSSL text
    form cut at ten characters. Run as the screen runs it."""
    import shutil
    import subprocess
    dash = SRC.parent
    esbuild = dash / "node_modules" / ".bin" / ("esbuild.cmd" if shutil.which("cmd") else "esbuild")
    node = shutil.which("node")
    if not node or not esbuild.exists():
        import pytest
        pytest.skip("node or the dashboard's esbuild is not installed")
    (tmp_path / "probe.ts").write_text(
        'import { certDay } from "%s";\n'
        'console.log(JSON.stringify([certDay("Dec 14 13:05:09 2026 GMT"),'
        ' certDay("2026-11-02T00:00:00Z"), certDay("not a date")]));'
        % (SRC / "part_page").as_posix(), encoding="utf-8")
    subprocess.run([str(esbuild), str(tmp_path / "probe.ts"), "--bundle", "--platform=node",
                    "--format=cjs", "--loader:.css=empty", "--log-level=error",
                    f"--outfile={tmp_path / 'probe.cjs'}"], check=True, cwd=dash)
    # In UTC, so the expected days do not depend on this machine's zone.
    import os
    out = subprocess.run([node, str(tmp_path / "probe.cjs")], check=True,
                         capture_output=True, text=True, encoding="utf-8",
                         env={**os.environ, "TZ": "UTC"}).stdout
    import json
    assert json.loads(out) == ["2026-12-14", "2026-11-02", "not a date"]
