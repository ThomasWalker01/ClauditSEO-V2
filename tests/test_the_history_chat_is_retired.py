"""The history chat is retired (channel ruling 20261011-0747, after screen
audits round 3).

It was deterministic: a question without one of seven trigger words got "Latest
run ... with composite score N." with the latest run cited, drawn as a grounded
answer; its trend branch compared the first and last points without reading
`comparable`; a failed request was silent; and nothing linked to it.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "dashboard" / "src"


def test_its_address_lands_on_the_site():
    app = (UI / "App.tsx").read_text(encoding="utf-8")
    assert ('if (parts[0] === "sites" && parts[1] && parts[2] === "chat")\n'
            "    return <Redirect to={`#/sites/${parts[1]}`} />;") in app.replace("\r\n", "\n")
    for path in UI.glob("*.tsx"):
        assert "ChatView" not in path.read_text(encoding="utf-8"), path.name


def test_its_route_and_module_are_gone():
    assert not (ROOT / "clauditseo" / "api" / "chat.py").exists()
    app = (ROOT / "clauditseo" / "api" / "app.py").read_text(encoding="utf-8")
    assert '"/api/chat"' not in app and "chat_module" not in app


def test_nothing_claims_it():
    app = (ROOT / "clauditseo" / "api" / "app.py").read_text(encoding="utf-8")
    assert '"enables the analyst layer and expert analyses"' in app
    assert "history chat" not in (ROOT / "README.md").read_text(encoding="utf-8")
    assert "history chat" not in (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
