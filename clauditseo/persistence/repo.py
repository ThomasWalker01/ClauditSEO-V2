"""Repository layer — the only code that talks to the database.

Every query goes through here so the P9 multi-operator phase (per-operator
scoping) and a potential Postgres port stay localised to this package.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import uuid
from datetime import datetime, timezone


def create_id() -> str:
    return uuid.uuid4().hex


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- operators -------------------------------------------------------------

def ensure_default_operator(conn: sqlite3.Connection, name: str = "Operator") -> str:
    row = conn.execute("SELECT id FROM operators WHERE archived_at IS NULL LIMIT 1").fetchone()
    if row:
        return row["id"]
    op_id = create_id()
    with conn:
        conn.execute(
            "INSERT INTO operators (id, name, role, created_at) VALUES (?, ?, 'owner', ?)",
            (op_id, name, now_iso()),
        )
    return op_id


def create_operator(conn: sqlite3.Connection, name: str, email: str | None = None,
                    role: str = "member") -> tuple[str, str]:
    """Create an operator and return (id, login token). The token is shown
    once and only its sha256 is stored."""
    if role not in ("owner", "member"):
        raise ValueError("role must be owner or member")
    op_id = create_id()
    token = secrets.token_urlsafe(24)
    with conn:
        conn.execute(
            "INSERT INTO operators (id, name, email, role, token_hash, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (op_id, name, email, role, _hash_token(token), now_iso()))
    return op_id, token


def operator_by_token(conn: sqlite3.Connection, token: str) -> dict | None:
    row = conn.execute(
        "SELECT id, name, email, role FROM operators"
        " WHERE token_hash = ? AND archived_at IS NULL",
        (_hash_token(token),)).fetchone()
    return dict(row) if row else None


def any_operator_tokens(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT 1 FROM operators WHERE token_hash IS NOT NULL"
        " AND archived_at IS NULL LIMIT 1").fetchone()
    return row is not None


def list_operators(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT id, name, email, role, created_at,"
        " token_hash IS NOT NULL AS has_token"
        " FROM operators WHERE archived_at IS NULL ORDER BY created_at").fetchall()
    return [dict(r) for r in rows]


# --- clients ---------------------------------------------------------------

def create_client(
    conn: sqlite3.Connection,
    owner_id: str,
    name: str,
    contacts: list[dict] | None = None,
    notes: str = "",
) -> str:
    client_id = create_id()
    with conn:
        conn.execute(
            "INSERT INTO clients (id, owner_id, name, contacts, notes, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (client_id, owner_id, name, json.dumps(contacts or []), notes, now_iso()),
        )
    return client_id


def list_clients(conn: sqlite3.Connection, operator: dict | None = None) -> list[dict]:
    """Owners (and legacy open/config-token mode, operator=None) see every
    client; members see only clients they own."""
    scope, params = "", []
    if operator is not None and operator.get("role") != "owner":
        scope, params = " AND c.owner_id = ?", [operator["id"]]
    rows = conn.execute(
        "SELECT c.*, COUNT(s.id) AS site_count"
        " FROM clients c LEFT JOIN sites s ON s.client_id = c.id AND s.archived_at IS NULL"
        f" WHERE c.archived_at IS NULL{scope} GROUP BY c.id ORDER BY c.name",
        params).fetchall()
    return [_client_dict(r) for r in rows]


def operator_can_access(conn: sqlite3.Connection, operator: dict | None,
                        client_id: str) -> bool:
    if operator is None or operator.get("role") == "owner":
        return True
    row = conn.execute("SELECT owner_id FROM clients WHERE id = ?",
                       (client_id,)).fetchone()
    return bool(row) and row["owner_id"] == operator["id"]


def client_id_for_site(conn: sqlite3.Connection, site_id: str) -> str | None:
    row = conn.execute("SELECT client_id FROM sites WHERE id = ?", (site_id,)).fetchone()
    return row["client_id"] if row else None


def get_client(conn: sqlite3.Connection, client_id: str) -> dict | None:
    row = conn.execute("SELECT *, 0 AS site_count FROM clients WHERE id = ?", (client_id,)).fetchone()
    return _client_dict(row) if row else None


def _client_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "contacts": json.loads(row["contacts"] or "[]"),
        "notes": row["notes"] or "",
        "created_at": row["created_at"],
        "site_count": row["site_count"],
    }


# --- sites -----------------------------------------------------------------

def create_site(
    conn: sqlite3.Connection,
    client_id: str,
    domain: str,
    locale: str = "en-AU",
    business_type: str | None = None,
    target_market: str | None = None,
) -> str:
    site_id = create_id()
    with conn:
        conn.execute(
            "INSERT INTO sites (id, client_id, domain, locale, business_type, target_market, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (site_id, client_id, domain, locale, business_type, target_market, now_iso()),
        )
    return site_id


#: The site record's local-SEO fields (brief v11 step AI): scalars, and
#: the ones stored as JSON text.
SITE_TEXT_FIELDS = ("brand", "gbp_primary_category", "service_area_entity", "title_strategy",
                    # What the Images brief reads (brief v15 step AQ).
                    "platform", "cdn_or_image_pipeline", "budget_lcp_kb", "budget_page_kb",
                    "review_provenance",
                    # What "too heavy" is for one image, and what the
                    # engine re-encodes at to measure the saving (brief
                    # v16 step AU7).
                    "budget_image_kb", "bytes_per_pixel", "reencode_quality",
                    "budget_image_floor_kb",
                    # What the Structured data brief reads (brief v16 step
                    # AS). `nap` is exact - a NAP that differs from the page
                    # by a comma is the finding, and an approximate copy
                    # could not find it.
                    "nap", "locations", "id_page_uri", "canonical_id",
                    # Brief v18 step AY: the client plan's two scalar
                    # inputs. `optimisation_ratio` is a band the operator
                    # writes as they say it ("60-70"), not a number, so it
                    # is text like every other band on this record.
                    "optimisation_ratio", "capacity",
                    # The CDN/WAF in front of the origin (brief v18 step AZ,
                    # task 4). Names where a UA refusal is enforced, so
                    # `ua-server-refusal` has an address to open against.
                    "cdn_or_waf",
                    # The URLs & parameters brief's four thresholds (brief v19
                    # step BB). Numbers, stored as text like the budget fields
                    # above and parsed on use; blank keeps `urlshape`'s defaults.
                    "url_max_chars", "slug_max_words", "max_depth", "rename_inlink_cap",
                    # The Speed brief's vital budgets and the framework (brief
                    # v19 step BC). Numbers stored as text and parsed on use;
                    # blank keeps Google's own thresholds (the gauge bands).
                    # `page_weight_budget` is the existing `budget_page_kb`.
                    "lcp_good", "cls_good", "inp_good", "ttfb_good", "framework",
                    # The Security brief's stack (brief v20 step BD): origin,
                    # edge and CMS, so a header fix names where it is set.
                    "stack",
                    # The held domains' inputs (brief v20 step BD). Recorded,
                    # never acted on in this build - see migration 0058.
                    "active_probing_authorised", "reputation_source",
                    "plugin_directory_feed",
                    # Where real-user vitals come from (brief v19 step BC): a
                    # CrUX key or a Search Console connection. Empty on every
                    # site today, and the Speed part's field bar says so rather
                    # than drawing zeros.
                    "field_data_source",
                    # The AI surface's two inputs (item 145 step BG): the
                    # client's stated policy on AI agents, which sets
                    # `ai-crawler-blocked`'s severity, and where the server's
                    # own per-agent counts come from. See migration 0061.
                    "ai_crawler_policy", "ai_field_data_source",
                    # The agents refused at the edge on purpose (item 145 BG,
                    # migration 0062), a comma-separated list of tokens.
                    "ai_edge_blocked_agents",
                    # The registered entity's legal name where it differs from
                    # `brand` (item 145 BH, migration 0063). Its two list
                    # companions are JSON and sit below.
                    "legal_name")
SITE_JSON_FIELDS = ("neighbourhoods", "entity_variants", "sub_services", "location_pages",
                    "page_types", "breakpoints", "priority_internal_targets",
                    # Two lists and a map (brief v16 step AS), and the two
                    # lists are stored apart because the distinction is the
                    # finding: `sameas_sources` are profiles the entity
                    # controls and belong in `sameAs`; `citation_sources`
                    # are places that mention it and belong in `subjectOf`.
                    # A directory in `sameAs` claims the entity *is* that
                    # page, which is `schema-sameas-misplaced`.
                    "sameas_sources", "citation_sources", "target_rich_results",
                    # Item 145 BH (migration 0063). `registered_ids` are free
                    # strings because the shape differs by jurisdiction and we
                    # never validate one; `external_profiles` are
                    # `{"url", "claimed"}` maps, and `claimed` is the
                    # operator's statement rather than anything measured.
                    # Apart from `sameas_sources` on purpose: that is the pin
                    # list, this is the footprint the pins are judged against.
                    "registered_ids", "external_profiles",
                    # Brief v17 step AX. The two floors are placeholders the
                    # record overrides; `authors` and `proof_assets` are what
                    # a replacement may draw on; the last four are
                    # Benchmark's prerequisites and are empty until an
                    # operator fills them.
                    "word_floors", "mandatory_formats", "authors",
                    "proof_assets", "competitors", "keyword_data",
                    "top10_corpus", "publish_history",
                    # Brief v18 step AY: three of the client plan's five
                    # inputs are lists. `optimisation_ratio` and
                    # `capacity` are scalars and stay out of here.
                    "horizons", "workstreams", "measure_sources",
                    # Brief v18 step BA: the indexability brief's three fields —
                    # two lists and one old->new map, each gating a held
                    # analysis check until it is set.
                    "intended_noindex", "migration_map", "parameter_rules",
                    # Brief v19 step BC: the Speed brief's third-party map, host ->
                    # what it is -> business purpose, read by third-party-policy.
                    "third_party_map")
TITLE_STRATEGIES = ("triple", "neighbourhood")
REVIEW_PROVENANCE = ("confirmed", "unconfirmed")
#: What `ai_crawler_policy` may say; empty is "not stated" (migration 0061).
AI_CRAWLER_POLICIES = ("allow", "block")


def edge_agents() -> tuple[str, ...]:
    """The agents `ai_edge_blocked_agents` may name: every non-search agent
    the UA matrix sends (a robots token has no UA, so no edge can refuse it)."""
    from clauditseo.crawler.ua_matrix import UA_MATRIX_AGENTS
    return tuple(t for t, ua, c in UA_MATRIX_AGENTS if c != "search" and ua)


def edge_blocked_agents(value: str | None) -> set[str]:
    """The stored list as a set of tokens; empty for None or blank."""
    return {t.strip() for t in (value or "").split(",") if t.strip()}
#: One node, or an Organization with a LocalBusiness per site (step AS).
LOCATION_COUNTS = ("one", "many")
#: The widths a `sizes` value is derived from where the record names none.
DEFAULT_BREAKPOINTS = (480, 768, 1024, 1440, 1920)
DEFAULT_BUDGET_LCP_KB = 200
DEFAULT_BUDGET_PAGE_KB = 1000


def site_record(row: dict | None) -> dict | None:
    """A site row with its JSON fields parsed, for the API and the briefs."""
    if row is None:
        return None
    out = dict(row)
    for col in SITE_JSON_FIELDS:
        raw = out.get(col)
        if isinstance(raw, str) and raw:
            try:
                out[col] = json.loads(raw)
            except ValueError:
                out[col] = None
        elif raw in ("", None):
            out[col] = None
    # Item 167: the latest Places lookup's candidates. JSON like the fields
    # above, but written by the brief route rather than the site patch, so it
    # is not in SITE_JSON_FIELDS and never reaches the Site a brief reads.
    raw = out.get("gbp_last_lookup")
    if isinstance(raw, str):
        try:
            out["gbp_last_lookup"] = json.loads(raw) if raw else None
        except ValueError:
            out["gbp_last_lookup"] = None
    return out


def update_site(conn: sqlite3.Connection, site_id: str, *,
                business_type: str | None = None, locale: str | None = None,
                target_market: str | None = None,
                domain: str | None = None, brand: str | None = None,
                **local_seo) -> None:
    """Correct a site's profile after the fact.

    It could only be set when the site was created, and it is the kind of
    thing you get wrong before you have read the site: a lender filed as
    "ecommerce" makes every brief reason about a product catalogue and branch
    locations that do not exist, and says so confidently.

    Only the fields given are written, so clearing one is an explicit
    `business_type=""` rather than an accident of not passing it.

    `domain` is WF-81 and it is the one field here that **cannot** be cleared,
    which is why it is not in the loop below: `val or None` would write NULL
    into the column every run, crawl and deliverable filename is addressed by,
    and the empty-string-clears rule that is right for the other three is
    wrong for this one. The caller normalises — `api/app.py` puts it through
    `crawl.site_host`, the owner — because this function has readers other
    than that route and a second normaliser here would be the fifth copy that
    function's own docstring records.
    """
    sets, args = [], []
    for col, val in (("business_type", business_type), ("locale", locale),
                     ("target_market", target_market), ("brand", brand)):
        if val is not None:
            sets.append(f"{col}=?")
            args.append(val or None)
    # The local-SEO fields (brief v11 step AI): a scalar as given, a list
    # or map as JSON text; an empty value clears the column.
    unknown = set(local_seo) - set(SITE_TEXT_FIELDS) - set(SITE_JSON_FIELDS)
    if unknown:
        raise TypeError(f"update_site() got unexpected fields {sorted(unknown)}")
    for col, val in local_seo.items():
        if val is None:
            continue
        sets.append(f"{col}=?")
        if col in SITE_JSON_FIELDS:
            args.append(json.dumps(val) if val else None)
        else:
            args.append(val or None)
    if domain:
        sets.append("domain=?")
        args.append(domain)
    if not sets:
        return
    with conn:
        conn.execute(f"UPDATE sites SET {', '.join(sets)} WHERE id=?",
                     (*args, site_id))


#: Every table holding a row that belongs to one audit run, deleted before the
#: run itself (item 169). Foreign keys are enforced (`db/connection.py`), so a
#: table missing here makes the run's delete fail rather than leave an orphan;
#: `test_delete_site_cascades_its_history` walks the schema for any it misses.
RUN_TABLES = ("findings", "cost_entries", "expert_reports", "page_advice", "probe_results")
#: And every table holding a row that belongs to one site.
SITE_TABLES = ("finding_states", "metric_snapshots", "reports", "notes", "prechecks",
               "tool_schedules",
               # Item 239: the site's Latest View, its operator judgements
               # and its rebuild log go with it.
               "latest_view", "state_events", "latest_view_log")


def _delete_site_rows(conn: sqlite3.Connection, site_id: str) -> None:
    run_ids = [r["id"] for r in conn.execute(
        "SELECT id FROM audit_runs WHERE site_id=?", (site_id,))]
    for run_id in run_ids:
        for table in RUN_TABLES:
            conn.execute(f"DELETE FROM {table} WHERE run_id=?", (run_id,))
    for table in SITE_TABLES:
        conn.execute(f"DELETE FROM {table} WHERE site_id=?", (site_id,))
    conn.execute("DELETE FROM audit_runs WHERE site_id=?", (site_id,))
    conn.execute("DELETE FROM sites WHERE id=?", (site_id,))


def delete_site(conn: sqlite3.Connection, site_id: str) -> None:
    """Hard-delete one site and every trace of it: runs and everything keyed by
    them, states, snapshots, reports, notes, prechecks and schedules.
    Irreversible; the API fronts it with an explicit confirmation (item 169)."""
    with conn:
        _delete_site_rows(conn, site_id)


def delete_client(conn: sqlite3.Connection, client_id: str) -> None:
    """Hard-delete a client and every trace of it: each site through the same
    cascade `delete_site` uses, then the client. Irreversible; the API fronts
    this with an explicit confirmation."""
    site_ids = [r["id"] for r in conn.execute(
        "SELECT id FROM sites WHERE client_id=?", (client_id,))]
    with conn:
        for site_id in site_ids:
            _delete_site_rows(conn, site_id)
        conn.execute("DELETE FROM clients WHERE id=?", (client_id,))


def get_site(conn: sqlite3.Connection, site_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM sites WHERE id = ?", (site_id,)).fetchone()
    return dict(row) if row else None


def list_sites(conn: sqlite3.Connection, client_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM sites WHERE client_id = ? AND archived_at IS NULL ORDER BY domain",
        (client_id,),
    ).fetchall()
    return [dict(r) for r in rows]


# --- demo seed -------------------------------------------------------------

def seed_demo(conn: sqlite3.Connection) -> dict:
    """Idempotent demo data so a fresh install has something to look at."""
    existing = conn.execute("SELECT COUNT(*) AS n FROM clients").fetchone()["n"]
    if existing:
        return {"seeded": False}
    op_id = ensure_default_operator(conn, "Demo Operator")
    acme = create_client(conn, op_id, "Acme Plumbing",
                         contacts=[{"name": "Alex Chen", "email": "alex@acmeplumbing.example"}],
                         notes="Demo client seeded on install.")
    beacon = create_client(conn, op_id, "Beacon Books",
                           contacts=[{"name": "Sam Rivers", "email": "sam@beaconbooks.example"}],
                           notes="Demo client seeded on install.")
    create_site(conn, acme, "acmeplumbing.example", business_type="local-service",
                target_market="Melbourne, VIC")
    create_site(conn, beacon, "beaconbooks.example", business_type="ecommerce",
                target_market="Australia")
    return {"seeded": True, "operator": op_id}
