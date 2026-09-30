"""The AI surface brief's inputs and its block rules (item 145, brief v22 step BH).

`ai-surface.md` is installed verbatim (with the `reads:` correction from channel
20260915-0520). This module is the two things code has to do for it:

* **the context**: every placeholder filled from what the run stored and the
  site record, or ABSENT with what would fill it. The prompt's rule is that an
  empty record field makes the checks that need it `not_assessable` naming the
  field, and a value is stated as recorded or absent, never guessed. The three
  fields this product lacked (`legal_name`, `registered_ids`,
  `external_profiles`) are columns since migration 0063 (item 145 step BH).
* **the block rules the parser enforces rather than trusts**: every enrichment
  candidate names a permitted source; a lifted passage is at most sixty words;
  `absent_reads[].needs` is one of three values; a read-through entry is for a
  check the header reads, never one it owns; and every `[client to supply]`
  marker is counted so the part page can say what the client owes.
"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlsplit

ABSENT = "[NOT SUPPLIED]"

#: What `{{SECTION_CAP}}` and `{{LLMS_TXT_BUILD}}` default to, per the prompt.
SECTION_CAP = 15
LLMS_TXT_BUILD = "false"

#: The stored llms.txt body is capped: it is read by the brief and the stale
#: check, and a file past this is not one a convention reader would parse.
LLMS_TXT_CAP = 50_000

#: A lifted passage's word limit (prompt: "≤ 60 words").
PASSAGE_WORDS = 60

CLIENT_TO_SUPPLY = "[client to supply]"

#: The three sources an enrichment candidate may name (brief v22 BH). The
#: prompt forbids industry knowledge; the parser enforces it.
CANDIDATE_SOURCE = re.compile(
    r"^(?:site record: [a-z_][a-z0-9_]*(?:\s*,\s*[a-z_][a-z0-9_]*)*"
    r"|Coverage map: \S.*"
    r"|schema\.org: [A-Z][A-Za-z]*\.[a-z][A-Za-z]*)$")

#: `absent_reads[].needs`, exactly (brief v22, fourth addition).
NEEDS_UNRUN = "part has not run"
NEEDS_FREE_ONLY = "part ran free-only, this check is analysis"
NEEDS_BLOCKED = re.compile(r"^blocked: \S.*$")

#: Where each read-through renders, from its owning check (third addition).
READ_SCOPE = {"LNK/hub-unlinked": "entity", "INT/lang-en-absent": "site",
              "TEC/ai-crawler-blocked": "site"}

#: The page cap on `{{PAGE_SET}}`. Every page is in the inventory regardless;
#: the per-page detail past this is said to be cut, not silently absent.
PAGE_SET_CAP = 40


def needs_is_valid(value: str) -> bool:
    v = (value or "").strip()
    return v in (NEEDS_UNRUN, NEEDS_FREE_ONLY) or bool(NEEDS_BLOCKED.match(v))


def count_client_to_supply(value: Any) -> int:
    """Every `[client to supply]` marker anywhere inside a value."""
    if isinstance(value, str):
        return value.lower().count(CLIENT_TO_SUPPLY)
    if isinstance(value, dict):
        return sum(count_client_to_supply(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return sum(count_client_to_supply(v) for v in value)
    return 0


# --- the block ------------------------------------------------------------

NOW_OBJECTS = ("directives", "edge", "ua_matrix", "render", "anchor", "llms_txt")


def read_block(parsed, data: dict, reads: list[str], checks: list[str]) -> None:
    """The AI surface block's fields beside the rows: the "now", the
    read-through entries, the absences, the conflicts and the declines.
    Each kept only in the shape the screen draws."""
    now: dict[str, Any] = {k: data[k] for k in NOW_OBJECTS if isinstance(data.get(k), dict)}
    if isinstance(data.get("entities"), list):
        now["entities"] = [e for e in data["entities"] if isinstance(e, dict)]
    reads_set, checks_set = set(reads), set(checks)
    read_through, absent = [], []
    for entry in data.get("read_through") or []:
        if not isinstance(entry, dict):
            continue
        check = str(entry.get("check") or "").strip()
        if check in checks_set:
            parsed.dropped.append({"row": entry, "reason": f"read_through entry for {check}, "
                                   "which this analysis owns (it is in checks:, not reads:)"})
            continue
        if check not in reads_set:
            parsed.dropped.append({"row": entry, "reason": f"read_through entry for {check}, "
                                   "which the header does not read"})
            continue
        read_through.append({"check": check, "page": entry.get("page") or None,
                             "payload": entry.get("payload"),
                             "source_run": entry.get("source_run"),
                             "scope": READ_SCOPE.get(check, "page")})
    for entry in data.get("absent_reads") or []:
        if not isinstance(entry, dict):
            continue
        item = {"check": str(entry.get("check") or "").strip(),
                "part": str(entry.get("part") or "").strip(),
                "needs": str(entry.get("needs") or "").strip()}
        if item["check"] not in reads_set:
            parsed.dropped.append({"row": entry, "reason": f"absent_reads entry for "
                                   f"{item['check']}, which the header does not read"})
            continue
        # Held, not dropped: the count of reads still reconciles.
        if not needs_is_valid(item["needs"]):
            item["held"] = "unrecognised needs value"
        absent.append(item)
    parsed.ai_surface = {
        "now": now,
        "read_through": read_through,
        "absent_reads": absent,
        "conflicts": [c for c in (data.get("conflicts") or []) if isinstance(c, dict)],
        "declined": [d for d in (data.get("declined") or []) if isinstance(d, dict)],
        "client_to_supply": 0,
    }


#: Free checks whose identity is an agent, not a page: the automatic checks
#: raise one row per agent from the UA matrix. A brief row for one is keyed by
#: page and would lump agents the operator has told apart (twenty22's first
#: paid run put fifteen agents, six of them declared, on one HIGH row).
PER_AGENT_FREE = ("edge-blocks-ai-ua", "ua-sensitive")

#: Where an enrichment row names no candidate because the record is thin, it is
#: the prompt's own stop ("note names the field that would unlock more"), which
#: is a hold, not a failure: moved to not_assessable rather than dropped.
HOLD = "hold"


def police_row(check: str, raw: dict, *, llms_txt_build: bool = False
               ) -> tuple[dict | None, str | None, list[str]]:
    """One AI surface row, judged. Returns (the row as it may be stored or
    None, the reason it was dropped, notes on what was changed). A reason of
    `HOLD` means the row belongs in not_assessable, not in the drops."""
    notes: list[str] = []
    row = dict(raw)
    bare = check.partition("/")[2]
    if bare in PER_AGENT_FREE:
        return None, (f"{check} is raised per crawler by the automatic checks from the "
                      "crawler access test; an analysis row keyed by page would merge crawlers the site "
                      "record tells apart"), notes
    from clauditseo.checks import check_cost
    if check_cost(check) == "free":
        return None, "free check; the automatic checks measure it, the analysis may only read it", notes
    if bare == "llms-txt-authored" and not llms_txt_build:
        return None, ("llms-txt-authored may only be emitted when LLMS_TXT_BUILD is true, "
                      "and this run's is false"), notes
    if bare == "entity-enrichment":
        kept, dropped, held = [], [], []
        for c in row.get("candidates") or []:
            source = str((c or {}).get("source") or "").strip() if isinstance(c, dict) else ""
            # A held candidate names a permitted field the record leaves empty
            # and carries no sentence (twenty22's second paid run: "site
            # record: locations · [NOT SUPPLIED]"). That is the prompt's stop,
            # not a forbidden source.
            base = re.split(r"\s*[·|—-]\s*\[NOT SUPPLIED\]", source)[0].strip()
            if isinstance(c, dict) and CANDIDATE_SOURCE.match(base):
                (kept if str(c.get("sentence") or "").strip() else held).append(c)
            else:
                dropped.append(source or "(none)")
        if dropped:
            notes.append(f"{len(dropped)} candidate(s) dropped: source not a site record "
                         f"field, a Coverage map relation or a schema.org property "
                         f"({'; '.join(dropped[:3])})")
        if not kept:
            if dropped and not held:
                return None, "every enrichment candidate named a source the prompt forbids", notes
            return None, HOLD, notes
        if held:
            notes.append(f"{len(held)} candidate(s) held: the record field they need is empty")
        row["candidates"] = kept
    if bare == "answer-liftable":
        words = str(row.get("passage") or "").split()
        if len(words) > PASSAGE_WORDS:
            row["passage"] = " ".join(words[:PASSAGE_WORDS])
            notes.append(f"passage truncated from {len(words)} to {PASSAGE_WORDS} words")
    return row, None, notes


# --- the context ----------------------------------------------------------

def _record(site: Any, name: str):
    value = getattr(site, name, None)
    if value in (None, "", [], {}):
        return None
    return value


def _line(value) -> str:
    if value is None:
        return ABSENT
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def site_entities(site: Any) -> str:
    fields = ["brand", "legal_name", "sub_services", "location_pages", "locations",
              "service_area_entity", "authors", "gbp_primary_category",
              "entity_variants", "sameas_sources", "registered_ids", "canonical_id",
              "id_page_uri", "ai_crawler_policy", "ai_edge_blocked_agents"]
    # `legal_name` and `registered_ids` were stated as fields this product did
    # not have until migration 0063 (item 145 step BH). They are columns now,
    # so an empty one is an empty record field like any other and the checks
    # that need it are `not_assessable` naming it.
    return "\n".join(f"- {f}: {_line(_record(site, f))}" for f in fields)


def external_profiles(site: Any) -> str:
    """The record's branded profiles, each with the operator's claimed state
    (item 145 step BH, migration 0063).

    Empty is stated the way the prompt asks for: `entity-footprint-unlinked`
    then reads `sameas_sources` alone and says so. A profile is never invented
    here, and `claimed` is never inferred — an unclaimed profile is a
    different fix from an unlinked one, and only the operator knows which it
    is.
    """
    rows = []
    for entry in (_record(site, "external_profiles") or []):
        if isinstance(entry, dict):
            url = str(entry.get("url") or "").strip()
            claimed = entry.get("claimed")
        else:
            url, claimed = str(entry).strip(), None
        if not url:
            continue
        rows.append(f"- {url} · " + ("claimed" if claimed
                                     else "not claimed" if claimed is False
                                     else "claimed state not stated"))
    if not rows:
        return (ABSENT + " — the site record lists no external profiles; "
                "`entity-footprint-unlinked` reads `sameas_sources` alone")
    return "\n".join(rows)


def ai_ua_list() -> str:
    from clauditseo.crawler.ua_matrix import UA_MATRIX_AGENTS
    rows = [f"- {t} · {c} · " + (ua if ua else "robots token: read in robots.txt, never sent")
            for t, ua, c in UA_MATRIX_AGENTS]
    return ("The product's crawler list, with this product's four AI classes "
            "(dataset, training, index, answer-time) plus `search` for Googlebot and "
            "Bingbot, which are not AI crawlers. `index` and `answer-time` together are "
            "what the prompt's taxonomy calls retrieval: `index` builds an engine's own "
            "search index ahead of time, `answer-time` fetches when a user asks.\n"
            + "\n".join(rows))


def robots_directives(ev: dict) -> str:
    from clauditseo.crawler.robots import RobotsPolicy, robots_url_for
    from clauditseo.crawler.ua_matrix import UA_MATRIX_AGENTS
    start = ev.get("start_url") or ""
    body = ev.get("robots_txt")
    status = ev.get("robots_status")
    if not body:
        return f"robots.txt not read on this run (status {status})."
    policy = RobotsPolicy(robots_url_for(start), status, body)
    rows = []
    for token, _ua, klass in UA_MATRIX_AGENTS:
        stated = "stated" if policy.names(token) else "unstated (falls to *)"
        verdict = "allow" if policy.allows(start, token) else "block"
        rows.append(f"- {token} ({klass}): {verdict} · {stated}")
    return "robots.txt as served:\n```\n" + body[:4000] + "\n```\nPer crawler at the start URL:\n" + "\n".join(rows)


def meta_directives(ev: dict) -> str:
    rows = []
    for p in ev.get("pages") or []:
        said = " ".join(filter(None, [p.get("meta_robots"), p.get("x_robots_tag")]))
        if said:
            rows.append(f"- {p.get('url')}: {said}")
    return ("\n".join(rows[:200]) if rows
            else "no page carried a meta robots tag or X-Robots-Tag header")


def ua_matrix_text(ev: dict, site: Any) -> str:
    from clauditseo.crawler.ua_matrix import agent_class
    matrix = ev.get("ua_matrix") or []
    if not matrix:
        return (ABSENT + " — this run did not fetch pages as the named crawlers, so "
                "`AIS/edge-blocks-ai-ua` and `AIS/ua-sensitive` are not assessable.")
    declared = {t.strip() for t in (getattr(site, "ai_edge_blocked_agents", None) or "").split(",")
                if t.strip()}
    rows = []
    for m in matrix:
        agent = m.get("agent") or ""
        klass = m.get("agent_class") or agent_class(agent) or "-"
        if m.get("sent") is False:
            rows.append([agent, klass, m.get("robots"), "(robots token, not sent)", "-", "-", "-", "-"])
            continue
        headers = [m.get("headers") or {}, *(m.get("probe_headers") or [])]
        if not m.get("docs"):
            # A matrix from before per-response documents: statuses only.
            for i, status in enumerate([m.get("home_status"), *(m.get("probe_status") or [])]):
                sig = headers[i] if i < len(headers) else {}
                rows.append([agent, klass, m.get("robots"), "home" if i == 0 else f"probe {i}",
                             status, "; ".join(f"{k}={v}" for k, v in sig.items() if k in (
                                 "server", "cf-mitigated", "content-type", "retry-after")) or "-",
                             "-", "-"])
            continue
        for i, (url, doc) in enumerate((m.get("docs") or {}).items()):
            sig = headers[i] if i < len(headers) else {}
            rows.append([agent, klass, m.get("robots"), urlsplit(url).path or "/",
                         doc.get("status"),
                         "; ".join(f"{k}={v}" for k, v in sig.items() if k in (
                             "server", "cf-mitigated", "content-type", "retry-after")) or "-",
                         doc.get("main_hash") or "-",
                         f"{doc.get('words', '-')} words · {doc.get('title') or '-'}"])
    from clauditseo.analysts.expert import _table
    return ("Measured from one place, the audit's own address: each cell is how "
            "the firewall answered this crawler name, not what the vendor's crawler from its own "
            "IPs gets. Crawlers the operator declares blocked at the firewall on purpose: "
            + (", ".join(sorted(declared)) or "none") + ".\n\n"
            + _table(["Agent", "Class", "Robots", "Page", "Status", "Retained headers",
                      "Text hash", "Text length · title"], rows, limit=240))


def url_inventory(ev: dict, site: Any) -> str:
    from clauditseo.analysts.expert import _page_type_of, _table
    rows = []
    for p in ev.get("pages") or []:
        robots = " ".join(filter(None, [p.get("meta_robots"), p.get("x_robots_tag")])).lower()
        canon = p.get("canonical") or ""
        self_canonical = (not canon) or canon.rstrip("/") == (p.get("url") or "").rstrip("/")
        rows.append([p.get("url"), p.get("status"),
                     "self" if self_canonical else canon,
                     "noindex" if "noindex" in robots else "indexable",
                     _page_type_of(site, p.get("url") or "") or "-",
                     p.get("title") or "-", p.get("h1") or "-"])
    note = (f" The crawl was truncated by {ev['truncated_by']}: pages past the cap are "
            "absent and must not be inferred." if ev.get("truncated_by") else "")
    return (f"{len(rows)} crawled URL(s).{note}\n\n"
            + _table(["URL", "Status", "Canonical", "Indexability", "Page type", "Title", "H1"],
                     rows, limit=400))


def llms_txt_text(ev: dict) -> str:
    status = ev.get("llms_txt_status")
    body = ev.get("llms_txt")
    if status == 200 and body:
        return "Served at /llms.txt (HTTP 200):\n```markdown\n" + body[:LLMS_TXT_CAP] + "\n```"
    if status == 200:
        return ("Served at /llms.txt (HTTP 200), but this run predates storing its "
                "body, so its contents are " + ABSENT)
    if status is None:
        return ABSENT + " — /llms.txt was not requested on this run"
    return f"absent — /llms.txt returned HTTP {status}"


def schema_model_text(ev: dict, site: Any) -> str:
    from clauditseo import schema_graph
    lines = []
    for p in ev.get("pages") or []:
        raw = p.get("jsonld_raw") or []
        blocks = []
        for entry in raw:
            try:
                blocks.append({"source": entry.get("source") or "inline",
                               "json": json.loads(entry.get("text") or "")})
            except (TypeError, ValueError, AttributeError):
                continue
        if not blocks:
            continue
        host = urlsplit(p.get("url") or "").netloc.lower().removeprefix("www.")
        try:
            model = schema_graph.build_model(blocks, None, {"host": host, "page": p.get("url"),
                                                            "page_type": "page"}, [])
        except Exception:
            continue
        nodes = [f"{'/'.join(n.types) or '?'}"
                 + (f" @id={n.id}" if n.id else " (no @id)")
                 + (" [entity]" if n.role == "entity" else "")
                 for n in model.nodes if n.kind == "node"]
        dangling = [g.key for g in model.ghosts]
        lines.append(f"- {p.get('url')}: " + "; ".join(nodes)
                     + (f" · dangling refs: {', '.join(dangling[:10])}" if dangling else "")
                     + (f" · verdict: {json.dumps(model.verdict, ensure_ascii=False)}"
                        if model.verdict else ""))
    return ("\n".join(lines[:120]) if lines
            else "no page in this run stored a parsable JSON-LD block")


def _read_rows(conn, site_id: str, reads: list[str]) -> list[dict]:
    """The open rows the owning parts emitted for the declared reads, newest
    finding per fingerprint, with the payload verbatim."""
    if conn is None or not site_id:
        return []
    from clauditseo.persistence import runs as _runs
    out = []
    wanted = {tuple(r.split("/", 1)) for r in reads}
    for row in _runs.site_states(conn, site_id):
        if row["state"] not in ("open", "regressed"):
            continue
        if (row["dimension"], row["check_id"]) not in wanted:
            continue
        f = conn.execute("SELECT evidence, run_id FROM findings WHERE fingerprint=? "
                         "ORDER BY created_at DESC, rowid DESC LIMIT 1",
                         (row["fingerprint"],)).fetchone()
        try:
            payload = json.loads(f["evidence"] or "{}") if f else {}
        except (TypeError, ValueError):
            payload = {}
        urls = row.get("affected_urls") or []
        out.append({"check": f"{row['dimension']}/{row['check_id']}",
                    "page": urls[0] if urls else None,
                    "payload": payload, "source_run": f["run_id"] if f else None})
    return out


def absent_needs(conn, site_id: str, run_id: str | None, check: str) -> str:
    """Which of the three absences a read with no rows is, from the record:
    the owning dimension did not run in the audit, or it did and the check
    is analysis no brief has answered, or something else, named."""
    from clauditseo.checks import brief_only_checks
    dim = check.split("/", 1)[0]
    dims: set[str] = set()
    if conn is not None and run_id:
        r = conn.execute("SELECT dimensions FROM audit_runs WHERE id=?", (run_id,)).fetchone()
        try:
            dims = set(json.loads(r["dimensions"] or "[]")) if r else set()
        except (TypeError, ValueError):
            dims = set()
    if check in brief_only_checks():
        from clauditseo import briefs as _briefs
        owners = {b.id for b in _briefs.catalogue() if check in b.checks}
        ran = set()
        if conn is not None and site_id and owners:
            ran = {r["tool_id"] for r in conn.execute(
                "SELECT DISTINCT er.tool_id FROM expert_reports er JOIN audit_runs r"
                " ON r.id = er.run_id WHERE r.site_id = ?", (site_id,))} & owners
        if not ran:
            return NEEDS_FREE_ONLY
        return ("blocked: the analysis that owns it has run on this site and raised "
                "no open row, so there is nothing to read through")
    if dim not in dims:
        return NEEDS_UNRUN
    return ("blocked: the owning check ran on this audit and raised no open row, so "
            "there is nothing to read through")


def read_state(conn, site_id: str, run_id: str | None, reads: list[str]) -> tuple[list[dict], str]:
    rows = _read_rows(conn, site_id, reads)
    have = {r["check"] for r in rows}
    lines = []
    for check in reads:
        if check in have:
            lines.append(f"- {check}: {sum(1 for r in rows if r['check'] == check)} row(s)")
        else:
            lines.append(f"- {check}: no row · needs: {absent_needs(conn, site_id, run_id, check)}")
    return rows, "\n".join(lines)


def page_set(ev: dict, site: Any, read_rows: list[dict], sweep_by_page: dict[str, list[str]]) -> str:
    from clauditseo.analysts.expert import _page_type_of
    text_blocks = ev.get("_text_blocks") or {}
    pages = [p for p in ev.get("pages") or []
             if p.get("status") == 200 and "html" in (p.get("content_type") or "")]
    by_page: dict[str, list[dict]] = {}
    for r in read_rows:
        if r["page"]:
            by_page.setdefault(r["page"].rstrip("/"), []).append(r)
    out = []
    for p in pages[:PAGE_SET_CAP]:
        url = p.get("url") or ""
        # The first words under the H1, from the outline, and not the page's
        # first sixty words: on twenty22 those are the navigation, and the
        # first paid run judged three pages to "open with navigation" off it.
        under_h1 = None
        seen_h1 = False
        for lv, heading, in_main, nxt in (p.get("outline") or []):
            seen_h1 = seen_h1 or lv == 1
            # Navigation headings sit outside the main region; a hero H1 is
            # often followed straight by an H2, so the first text is under that.
            if seen_h1 and in_main and nxt:
                under_h1 = nxt if lv == 1 else f"(after H{lv} '{heading}') {nxt}"
                break
        from clauditseo.modules.pagefacts import rendered_words
        rendered = rendered_words(text_blocks.get(url, []))
        outline = [f"    H{lv}: {text}" + (f" — then: {nxt[:120]}" if nxt else "")
                   for lv, text, _in_main, nxt in (p.get("outline") or [])[:12]]
        schema = ", ".join(f"{s.get('type') or s.get('@type') or '?'}"
                           + (f" {s.get('id')}" if s.get("id") else "")
                           for s in (p.get("schema_inventory") or [])[:12]
                           if isinstance(s, dict)) or "none"
        reads_here = [f"    {r['check']}: {json.dumps(r['payload'], ensure_ascii=False)[:300]}"
                      for r in by_page.get(url.rstrip("/"), [])]
        out.append("\n".join([
            f"## {url}",
            f"  page_type: {_page_type_of(site, url) or '-'} · title: {p.get('title') or '-'}",
            f"  meta description: {p.get('meta_description') or '-'}",
            f"  H1: {p.get('h1') or '-'}",
            "  headings with the first words under each:", *(outline or ["    (none)"]),
            (f"  first words under the H1 (initial HTML, main region): {under_h1}"
             if under_h1 else
             "  first words under the H1: none recorded (no H1, or nothing after it in "
             "the main region); the page's first words, navigation included, are: "
             f"{p.get('opening') or '-'}"),
            f"  body words: initial HTML {p.get('word_count', '-')} · rendered "
            + (str(rendered) if rendered else "not rendered on this run"),
            f"  internal links out (initial HTML): {len(p.get('links') or [])}",
            f"  outbound profile links: {', '.join(p.get('profile_links') or []) or 'none'}",
            f"  schema nodes: {schema}",
            "  free rows on this page: " + ("; ".join(sorted(set(sweep_by_page.get(url, [])))) or "none"),
            "  read-through rows on this page:", *(reads_here or ["    none"]),
        ]))
    cut = (f"\n\n({len(pages)} readable pages; the first {PAGE_SET_CAP} are detailed "
           "here. Every page is in the inventory.)" if len(pages) > PAGE_SET_CAP else "")
    return ("The evidence keeps no page bodies: body text is the opening and the words "
            "after each heading, and the rendered side is a word count from the rendered "
            "pass where it ran.\n\n" + "\n\n".join(out) + cut)


def sweep_rows(conn, run_id: str | None, start: str) -> tuple[str, dict[str, list[str]]]:
    if conn is None or not run_id:
        return "not available for this run", {}
    found = conn.execute(
        "SELECT dimension, check_id, severity, summary, affected_urls FROM findings"
        " WHERE run_id=? AND source='deterministic' AND (dimension='AIS'"
        " OR (dimension='TEC' AND check_id='ai-crawler-blocked')) ORDER BY check_id",
        (run_id,)).fetchall()
    lines, per_page = [], {}
    for f in found:
        urls = json.loads(f["affected_urls"] or "[]")
        lines.append(f"- {f['dimension']}/{f['check_id']} · {f['severity']} · {f['summary']}")
        for u in urls[:50]:
            per_page.setdefault(u, []).append(f"{f['dimension']}/{f['check_id']}")
    return ("\n".join(lines) or "the automatic checks raised none of this analysis's rows"), per_page


def build(ev: dict, site: Any, conn=None, run_id: str | None = None, **_) -> dict[str, str]:
    from clauditseo import briefs as _briefs
    from clauditseo.analysts.expert import _latest_block, _run_started, _site_of_run
    brief = _briefs.by_id().get("ai-surface")
    reads = list(getattr(brief, "reads", ()) or ())
    start = ev.get("start_url") or ""
    site_id = _site_of_run(conn, run_id)
    read_rows, reads_text = read_state(conn, site_id, run_id, reads)
    if conn is not None and run_id:
        # The rendered blocks live on the run's A11Y row, not the evidence.
        from clauditseo.persistence.runs import _text_blocks_for_run
        ev = {**ev, "_text_blocks": _text_blocks_for_run(conn, run_id) or {}}
    sweep, per_page = sweep_rows(conn, run_id, start)
    coverage = _latest_block(conn, site_id, "content-coverage", "map")
    title_strategy = getattr(site, "title_strategy", None)
    host = urlsplit(start).netloc
    return {
        "RUN_ID": run_id or ABSENT,
        "RUN_STARTED": _run_started(conn, run_id) or ABSENT,
        "RUN_SCOPE": (f"same host ({host}); {len(ev.get('pages') or [])} pages fetched; "
                      f"tier {ev.get('tier')}.\n\nAUTOMATIC CHECK RESULTS (the automatic checks' own "
                      f"rows for this analysis's free checks and its reachability read):\n{sweep}"
                      f"\n\nREAD-THROUGH STATE (for `read_through[]` and `absent_reads[]`; "
                      f"copy each `needs` verbatim):\n{reads_text}"),
        "PAGE_SET": page_set(ev, site, read_rows, per_page),
        "URL_INVENTORY": url_inventory(ev, site),
        "SITE_ENTITIES": site_entities(site),
        "EXTERNAL_PROFILES": external_profiles(site),
        "COVERAGE_MAP": coverage or "empty — Coverage has not run on this site",
        "ROBOTS_DIRECTIVES": robots_directives(ev),
        "META_DIRECTIVES": meta_directives(ev),
        "AI_UA_LIST": ai_ua_list(),
        "UA_MATRIX": ua_matrix_text(ev, site),
        "LLMS_TXT": llms_txt_text(ev),
        "LLMS_TXT_BUILD": LLMS_TXT_BUILD,
        "LLMS_TXT_EXCLUDE": "none beyond the defaults",
        "SECTION_CAP": str(SECTION_CAP),
        "SCHEMA_MODEL": schema_model_text(ev, site),
        "TITLE_TEMPLATE": (f"title strategy on the site record: {title_strategy}"
                           if title_strategy else ABSENT),
        "LOCALE": getattr(site, "locale", None) or "en-AU",
    }


# --- the part page's reachability "now" (free) -----------------------------

#: What a state means, as the site tab's last column says it (mockup v2).
STATE_WORDS = {
    "stated": "Blocked in robots.txt. Someone decided this.",
    "edge policy": "Blocked at the firewall, and the site record says on purpose; robots.txt does not say so.",
    "unstated block": "Turned away at the firewall with nothing said and nothing declared. Nobody decided this.",
    "reachable": "Let in and shown the page.",
    "unstated": "Nothing said in robots.txt, and nothing to visit: a setting, not a visitor.",
    "not assessed": "This audit did not visit as this crawler, so nothing is claimed either way.",
}


def reachability_payload(conn, run_id: str | None, site: Any) -> dict | None:
    """One row per AI agent for the AI surface part: Told (robots.txt), Got
    (the edge's answer to this UA string), Shown (whether the page it was
    given differed), and where that leaves it. Read back off the run's own
    evidence and its free rows, so the part draws it with no brief run.
    Asked and Refused are the field pair: present only where a field source
    is named on the site record, and unfilled until a pull exists."""
    if conn is None or not run_id:
        return None
    from clauditseo.crawler.robots import RobotsPolicy, robots_url_for
    from clauditseo.crawler.ua_matrix import BLOCK_CONSEQUENCE, UA_MATRIX_AGENTS
    from clauditseo.persistence.runs import evidence_text, parsed_evidence
    raw = evidence_text(conn, run_id)
    if not raw:
        return None
    try:
        ev = parsed_evidence(raw) or {}
    except (TypeError, ValueError):
        return None
    start = ev.get("start_url") or ""
    policy = (RobotsPolicy(robots_url_for(start), ev.get("robots_status"), ev.get("robots_txt"))
              if ev.get("robots_txt") else None)
    matrix = {m.get("agent"): m for m in (ev.get("ua_matrix") or []) if isinstance(m, dict)}
    edge, differs = {}, set()
    for f in conn.execute("SELECT check_id, evidence FROM findings WHERE run_id=? AND "
                          "dimension='AIS' AND check_id IN ('edge-blocks-ai-ua','ua-sensitive')",
                          (run_id,)):
        try:
            e = json.loads(f["evidence"] or "{}")
        except (TypeError, ValueError):
            continue
        if f["check_id"] == "edge-blocks-ai-ua":
            edge[e.get("agent")] = e
        else:
            differs.add(e.get("agent"))
    declared = {t.strip() for t in (getattr(site, "ai_edge_blocked_agents", None) or "").split(",")
                if t.strip()}
    rows = []
    for token, ua, klass in UA_MATRIX_AGENTS:
        if klass == "search":
            continue
        if policy is None:
            told = "not read"
        elif not policy.names(token):
            told = "unstated"
        else:
            told = "block" if not policy.allows(start, token) else "allow"
        m = matrix.get(token)
        if ua is None:
            got, shown, state = "n/a", "n/a", "stated" if told == "block" else "unstated"
        elif told == "block":
            got, shown, state = "n/a", "n/a", "stated"
        elif m is None or m.get("sent") is False and ua:
            got, shown = "not assessed", "not assessed"
            state = "edge policy" if token in declared else "not assessed"
        elif token in edge:
            statuses = sorted({r.get("status") for r in edge[token].get("responses") or []
                               if r.get("status") is not None})
            got = "/".join(str(s) for s in statuses) or "refused"
            shown = "—"
            state = "edge policy" if token in declared else "unstated block"
        else:
            statuses = {s for s in [m.get("home_status"), *(m.get("probe_status") or [])] if s}
            got = "/".join(str(s) for s in sorted(statuses)) or "not assessed"
            shown = "differs" if token in differs else ("same" if statuses else "not assessed")
            state = "reachable" if statuses else "not assessed"
        rows.append({"agent": token, "class": klass, "robots_token": ua is None,
                     "told": told, "got": got, "shown": shown, "state": state,
                     "declared": token in declared,
                     "meaning": STATE_WORDS[state]})
    # What a non-rendering reader gets: initial-HTML words over rendered words,
    # on the pages the rendered pass visited. A population, never a bare share.
    from clauditseo.modules.pagefacts import rendered_words
    from clauditseo.persistence.runs import _text_blocks_for_run
    text_blocks = _text_blocks_for_run(conn, run_id) or {}
    shares = []
    for p in ev.get("pages") or []:
        rendered = rendered_words(text_blocks.get(p.get("url") or "") or [])
        if rendered >= 100 and isinstance(p.get("word_count"), int):
            shares.append(min(p["word_count"] / rendered, 1.0))
    shares.sort()
    median = shares[len(shares) // 2] if shares else None
    field_source = (getattr(site, "ai_field_data_source", None) or "").strip() or None
    return {
        "rows": rows,
        "classes": {k: v for k, v in BLOCK_CONSEQUENCE.items()},
        "matrix_ran": bool(matrix),
        "field_source": field_source,
        "render": {"median_share": round(median, 3) if median is not None else None,
                   "pages": len(shares), "below": sum(1 for s in shares if s < 0.5),
                   "threshold": 0.5},
        "llms_txt_status": ev.get("llms_txt_status"),
        "unmeasured": ("Whether any AI system fetches, indexes, cites or summarises this "
                       "site is not observable from a crawl; nothing above claims it is."),
    }


# --- Block 3: the /llms.txt file (step BI, carried by this prompt) ---------

_MD_FENCE = re.compile(r"```markdown[ \t]*\r?\n(.*?)```", re.S)
_LINK_LINE = re.compile(r"^- \[(?P<title>[^\]]+)\]\((?P<url>https?://[^)\s]+)\)(?::\s*(?P<desc>.*))?$")


def _key(url: str) -> str:
    s = urlsplit(url.strip())
    return f"{s.netloc.lower().removeprefix('www.')}{(s.path or '/').rstrip('/') or '/'}"


def llms_inventory(evidence: dict) -> dict[str, str | None]:
    """Every crawled URL, keyed, with the reason it may not be listed or None.
    The prompt's rule: in the inventory, 200, self-canonical, indexable, no noai."""
    out: dict[str, str | None] = {}
    for p in (evidence or {}).get("pages") or []:
        url = p.get("url") or ""
        if not url:
            continue
        robots = " ".join(filter(None, [p.get("meta_robots"), p.get("x_robots_tag")])).lower()
        canon = (p.get("canonical") or "").strip()
        if p.get("status") != 200:
            why = f"returned {p.get('status')}"
        elif canon and _key(canon) != _key(url):
            why = f"canonicalises to {canon}"
        elif "noindex" in robots:
            why = "is noindex"
        elif "noai" in robots:
            why = "carries noai"
        else:
            why = None
        out.setdefault(_key(url), why)
        if p.get("requested_url") and _key(p["requested_url"]) != _key(url):
            out.setdefault(_key(p["requested_url"]), f"redirects to {url}")
    return out


def police_llms_file(parsed, evidence: dict, build: bool) -> None:
    """Take Block 3 off the readable body and keep it only as the prompt allows:
    authored only when the build input is true, every link line's URL a
    crawled, 200, self-canonical, indexable page (a line naming any other URL
    is removed and recorded), and the shape stated where it breaks the
    convention. Stored beside the block, never among the rows."""
    if parsed.ai_surface is None:
        return
    match = _MD_FENCE.search(parsed.body or "")
    if not match:
        return
    parsed.body = (parsed.body[:match.start()] + parsed.body[match.end():]).strip()
    if not build:
        parsed.dropped.append({"row": None, "reason": "Block 3 (/llms.txt) was authored with "
                               "LLMS_TXT_BUILD false, so it is not kept"})
        return
    inventory = llms_inventory(evidence)
    kept, refused, shape = [], [], []
    h1 = 0
    urls = sections = 0
    for line in match.group(1).splitlines():
        stripped = line.rstrip()
        link = _LINK_LINE.match(stripped)
        if link:
            why = inventory.get(_key(link["url"]), "is not in this audit's crawl")
            if why is not None:
                refused.append({"url": link["url"], "reason": why})
                continue
            desc = (link["desc"] or "").strip()
            if not desc:
                shape.append(f"no description: {link['url']}")
            elif len(desc.split()) >= 20:
                shape.append(f"description of {len(desc.split())} words: {link['url']}")
            urls += 1
        elif stripped.startswith("# "):
            h1 += 1
        elif stripped.startswith("## "):
            sections += 1
        elif stripped.startswith("###"):
            shape.append(f"section below H2: {stripped[:60]}")
        elif stripped and not stripped.startswith(">"):
            shape.append(f"line not in the convention's form: {stripped[:60]}")
        if re.search(r"<[a-z][^>]*>", stripped, re.I):
            shape.append(f"HTML in the file: {stripped[:60]}")
        kept.append(line)
    if h1 != 1:
        shape.append(f"{h1} H1 lines; the convention has exactly one")
    parsed.ai_surface["llms_txt_file"] = {
        "text": "\n".join(kept).strip() + "\n", "urls": urls, "sections": sections,
        "refused": refused, "shape": shape}
