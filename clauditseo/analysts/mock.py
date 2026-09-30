"""Deterministic mock analyst provider.

First-class, not a test hack: it lets every analyst-layer gate (injection,
cache, ingest validation, budgets) run keyless and token-free, and gives a
predictable output shape to develop the dashboard against. Its output is a
pure function of the bundle, so it is immune to injection by construction —
which is exactly the property the real provider is prompted and validated
towards.
"""

from __future__ import annotations

import json

from .base import AnalystFindingDraft, AnalystResponse


class MockAnalyst:
    name = "mock"
    model_id = "mock-deterministic-1"

    def run_agent(self, system: str, bundle: dict, toolkit,
                  max_tokens: int, max_output: int = 0) -> AnalystResponse:
        """Deterministic page advisory, derived from the bundle and carrying
        no figures at all, so it passes the same validation a live model's
        output must."""
        page = bundle.get("page", {})
        topic = (page.get("title_tag") or page.get("path") or "this page").strip()
        advice = {
            "assumptions": ["Deterministic mock advisor: no live model was called."],
            "triage": {"commercial": False, "multi_page": True, "ymyl": False,
                       "search_facing": True,
                       "note": "mock triage — site has sibling pages and is public"},
            "page_read": {"page_type": "unclassified (mock)",
                          "primary_topic": topic,
                          "audience": "unclassified (mock)",
                          "intent": "informational (assumed)",
                          "alignment": "mock provider does not assess alignment"},
            "site_role": None,
            "keyword_intent": None,
            "recommended_h1": {"text": f"About {topic}",
                               "why": "Mock recommendation derived from the page's "
                                      "existing title; not a real judgement."},
            "answer_line": "Mock answer line: replace by configuring a live model.",
            "title_tag": {"text": topic, "why": "unchanged by the mock advisor"},
            "meta_description": {"text": "Mock meta description.",
                                 "why": "unchanged by the mock advisor"},
            "alternatives": [{"h1": f"{topic} explained", "angle": "informational",
                              "tradeoff": "mock alternative"}],
            "schema_notes": None,
            "compliance_notes": None,
            "conflicts": ["Mock output — configure ANTHROPIC_API_KEY for real advice."],
        }
        return AnalystResponse(findings=[], tokens_in=0, tokens_out=0,
                               text=json.dumps(advice))

    def analyse(self, bundle: dict, task: str, max_tokens: int,
                toolkit=None) -> AnalystResponse:
        findings = bundle.get("findings", [])
        extracts = bundle.get("extracts", [])
        cites = []
        if findings:
            cites.append(findings[0]["id"])
        if extracts:
            cites.append(extracts[0]["id"])
        if not cites:
            return AnalystResponse(findings=[], tokens_in=0, tokens_out=0)
        draft = AnalystFindingDraft(
            summary=f"[{task}] Deterministic judgement note derived from the cited "
                    "evidence items. No figures beyond the bundle are introduced.",
            cites=cites,
            severity="info",
            confidence="medium",
            recommendation="Review the cited evidence in order of severity.",
            subject=task.lower(),
        )
        # Simulated spend proportional to bundle size so budget maths is exercised.
        tokens_in = max(1, len(str(bundle)) // 8)
        return AnalystResponse(findings=[draft], tokens_in=tokens_in, tokens_out=120)
