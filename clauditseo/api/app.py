"""FastAPI application. The dashboard reads only from this API.

Auth: open local mode until any token exists; a config token
(CLAUDITSEO_TOKEN) grants full access; per-operator tokens carry
owner/member roles with repository-level scoping (members get 404 on
resources they do not own).
"""

from __future__ import annotations

import collections
import dataclasses
from datetime import datetime as _dt
import ipaddress
import re
import threading
import time as _time
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import clauditseo.modules  # noqa: F401  (register dimensions)
from clauditseo import APP_NAME, ENGINE_VERSION, __version__, anatomy
from clauditseo.analysts.layer import provider_from_settings, run_analyst_layer
from clauditseo.api import chat as chat_module
from clauditseo.config import (PREFIX as config_prefix, ROOT,
                               STALE_TOKEN_DETAIL, settings,
                               stale_legacy_token)
from clauditseo.crawler.crawl import crawl as crawl_site
from clauditseo.scanscope import (
    DEPTHS, SCOPES, crawl_kwargs, depth_settings, tier_for_scope)
from clauditseo.crawler.crawl import crawl_start_url, site_host
from clauditseo.db.connection import connect
from clauditseo.db.migrate import is_current, migrate, migration_names
from clauditseo.engine import registry
from clauditseo.engine.core import run_audit
from clauditseo.engine.types import Site, Tier
from clauditseo.money import amount as money_amount, money
from clauditseo.persistence import repo, runs
from clauditseo import tiers
from clauditseo.providers.base import ProviderHub

DASHBOARD_DIST = ROOT / "dashboard" / "dist"


def actor_of(operator: dict | None, route: str) -> str:
    """What to record as having made a write, in one vocabulary.

    WF-33: the model-price ledger carried sixteen rows with `entered_by =
    NULL`, no commit touching them and no `OPERATOR_ACTIONS.md` row, for
    fifty-five audit reports. The obvious repair — `operator["id"] if operator
    else None` — closes nothing here, because `auth` returns the operator dict
    *or None for full-access contexts*, and this install is one of those: a
    single operator row with no token hash and no `CLAUDITSEO_TOKEN`, so every
    request runs in open local mode with `operator = None`. That repair would
    have written NULL sixteen more times.

    So both answers are recorded rather than one of them being an absence:

    - `operator:<id>` when a person is identified;
    - `api:<route>` when the caller holds full access without being a named
      operator, where naming the route is the honest and useful answer to
      "what changed this row".

    One vocabulary because both writers of `entered_by` use it. A column whose
    two writers disagree about what it holds cannot be read back by anything —
    and, measured by grep across `.py`, `.ts`, `.tsx` and `.sql` at round 089,
    it had two writers and no reader at all, so the vocabulary is settled here
    with no consumer to migrate.
    """
    return f"operator:{operator['id']}" if operator else f"api:{route}"


def bundle_id() -> str | None:
    """Which dashboard build is being served, or None when there is none.

    Vite emits a content-hashed asset name — `index-<hash>.js` — which
    changes exactly when the bundle changes, so reading it back is an
    identity that cannot drift from the thing it identifies. A hand-written
    constant would need remembering; this needs nothing.

    `/api/health` reported only the server's version, and the Admin footer
    drew that same version using whatever JavaScript was on disk, so the two
    could never disagree and an operator had no way to tell which UI they
    were running. Round 020 measured a bundle twelve hours behind the fix it
    was supposed to be showing.
    """
    index = DASHBOARD_DIST / "index.html"
    try:
        html = index.read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r"/assets/index-([A-Za-z0-9_-]+)\.js", html)
    return match.group(1) if match else None


# Optional tools each dimension can use. Dimensions not listed run fully
# offline from the crawl alone.
DIMENSION_PROVIDERS: dict[str, list[str]] = {
    "PRF": ["PageSpeed", "CrUX"],
    "OFP": ["Moz", "OpenPageRank", "DataForSEO"],
}

ANALYST_MODELS = [
    "claude-sonnet-5",
    "claude-fable-5",
    "claude-opus-5",
    "claude-haiku-4-5-20251001",
]

# At most this many audits crawl concurrently; excess launches queue.
_RUN_SEMAPHORE = threading.Semaphore(2)


MAX_IMAGE_HEADS = 30


PLACES_TOOLS = ("gbp-audit", "citations-nap", "review-signals")


def _triage_data(conn, run: dict, site_row, cfg, evidence: dict) -> dict:
    """Assemble the dispatcher's tables. Withheld findings are excluded HERE,
    not by prompt instruction — the model cannot leak what it never saw.
    Prices come from measured history, scaled to this crawl."""
    from clauditseo.analysts.expert import EXPERT_TOOLS
    from clauditseo.playbook import PLAYBOOK

    pages = len([p for p in evidence.get("pages", [])
                 if p.get("status") == 200])
    site_id = site_row["id"]

    # Positive, against the owner in `runs`, and not `!= "accepted-risk"`.
    # The negative form admitted every value added to the vocabulary after it
    # was written: `accepted-risk` at five states (recorded in
    # `compare_runs`' docstring) and `withdrawn` at six, which put a finding
    # the product had retracted into a brief about a client's site. A state
    # missing from `LIVE_STATES` is withheld, which is the safe direction.
    memory = [s for s in runs.site_states(conn, site_id)
              if s["state"] in runs.LIVE_STATES]

    already = {r["tool"]: r for r in runs.expert_report_index(conn, run["id"])}
    # Scoped to THIS site, for the same reason the schedule screen is — UX-77,
    # `QUESTIONS.md` Q-1 answered **per site**. `site_id` was already held two
    # lines up and only `pages` was passed, so the prices the dispatcher model
    # reasoned about inside SPEND NEXT were medians across every client in the
    # install: one client's measured cost recommended as another's, inside the
    # prompt that recommends the spend. A site with no history of a brief now
    # prices it in tokens rather than in another site's dollars, which is the
    # honest answer and the same one the schedule modal already gives.
    estimates = runs.expert_estimates(conn, pages or None, site_id=site_id)
    does = {t.get("expert", t["id"]): t.get("does", "")
            for ph in PLAYBOOK for t in ph["tools"]}
    available = []
    for tool_id in sorted(EXPERT_TOOLS):
        if tool_id == "triage" or tool_id in already:
            continue
        est = estimates.get(tool_id)
        # The frame travels with the price into the prompt, not only onto the
        # screens - UX-74. This string is what the dispatcher model is asked to
        # fit a SPEND NEXT recommendation inside, so a median taken over one of
        # three sampled runs and one taken over three of three are the same
        # sentence to it unless the population is said. No direction is claimed
        # for the same reason `BriefPriceFrame` claims none: an unpriced sample
        # does not push a median either way.
        #
        # UX-83: the words are `N of M runs carried a price`, not `from N of M
        # priced runs`, which is what this said until round 107 and which
        # parses first as *M runs were priced* — the opposite of the fact, and
        # given to the one reader with no second wording to compare against.
        # Kept character-identical to `BriefPriceFrame`'s rendered text by
        # `tests/test_a_partly_priced_median_says_so_unambiguously.py`.
        frame = ""
        if est and est.get("cost") is not None:
            costed, sampled = est.get("cost_samples", 0), est.get("samples", 0)
            if sampled and costed < sampled:
                frame = f" ({costed} of {sampled} runs carried a price)"
        price = ("[PRICE NOT SUPPLIED]" if not est
                 else money(est["cost"]) + frame if est.get("cost") is not None
                 else f"~{est['tokens']:,} tokens (no dollar rate configured)")
        available.append({"tool": tool_id, "price": price,
                          "does": does.get(tool_id, "")})

    return {
        "scores": {"composite": run.get("composite_score"),
                   "subscores": run.get("subscores") or {}},
        "gains": runs.biggest_gains(run.get("subscores") or {}),
        "memory": memory,
        "watch": runs.watch_changes(conn, site_id),
        "available_briefs": available,
        "already_run": sorted(already.values(), key=lambda a: a["tool"]),
        "budget": _budget_status(conn, cfg),
        "pages": pages,
    }


def _next_pass(schedule: str | None, last_run_at: str | None, now,
               intervals: dict, timedelta_cls) -> dict:
    """When the scheduler will next pick this site up, and why not if it will
    not.

    Mirrors `scheduler.due_sites` deliberately, including its refusal to
    auto-crawl a site that has never been audited — the first run sizes the
    site and belongs to the operator. A home screen that promised a pass the
    scheduler would decline to run would be worse than saying nothing.
    """
    interval = intervals.get(schedule or "")
    if not interval:
        return {"schedule_state": "manual", "next_pass_at": None,
                "why": "no schedule set — nothing runs unless you start it"}
    if not last_run_at:
        return {"schedule_state": "waiting", "next_pass_at": None,
                "why": "never audited; the first run is yours to start, so the "
                       "scheduler will not pick this up yet"}
    try:
        started = _dt.fromisoformat(last_run_at.replace("Z", "+00:00")).replace(
            tzinfo=None)
    except ValueError:
        return {"schedule_state": "manual", "next_pass_at": None,
                "why": "last run has an unreadable timestamp"}
    due = started + interval
    overdue_by = (now - due).days
    return {
        "schedule_state": "overdue" if due <= now else "scheduled",
        "next_pass_at": due.isoformat(timespec="minutes"),
        "why": (f"{overdue_by} day(s) past due" if due <= now
                else f"{schedule}, next at {due:%a %d %b %H:%M}"),
    }


def _renderer_available() -> bool:
    from clauditseo.renderer import Renderer
    return Renderer().available()


def _budget_status(conn, cfg) -> dict:
    """This month's spend against the configured caps. Warnings only: a hard
    stop mid-sweep would discard work already paid for.

    **The dollar figure is a floor, and says so in the payload.** `actual_cost`
    is NULL on any entry whose model had no configured price when it was
    written, and `SUM` over a partly-NULL column returns the priced subtotal
    with nothing marking it as one. Measured on the operator's own database
    on 22 August 2026: 48 entries this month, 34 of them unpriced, summing to
    USD 2.18 — a number covering 14 rows, rendered under "spent this month".

    So `usd_entries` and `usd_unpriced` travel with it. They are the frame
    clause of the provenance invariant applied to money: the value alone
    cannot distinguish a total from a floor, and both screens that draw it
    need to.

    `month_usd` is `None`, not `0.0`, when nothing at all is priced. The old
    `float(row["usd"] or 0)` turned "no price is configured" into "no money
    was spent", which is a different and false claim about a month that did
    spend tokens. Both `home.tsx` and `admin.tsx` already had a null branch;
    they were simply never reached.
    """
    row = conn.execute(
        "SELECT SUM(quantity) AS tokens, SUM(actual_cost) AS usd,"
        " COUNT(actual_cost) AS priced,"
        " COUNT(*) - COUNT(actual_cost) AS unpriced"
        " FROM cost_entries WHERE substr(created_at, 1, 7) ="
        " substr(datetime('now'), 1, 7)").fetchone()
    tokens = int(row["tokens"] or 0)
    priced = int(row["priced"] or 0)
    unpriced = int(row["unpriced"] or 0)
    # The cap comparison keeps working on a float, and a floor compared with
    # a cap can only ever under-warn — which is the safe direction, and the
    # reason the frame is rendered rather than the warning being suppressed.
    usd = float(row["usd"] or 0)
    warn = None
    # Which cap wrote the sentence, and it travels with it — UX-78. The two
    # branches below produce one string counting two different quantities, and
    # a consumer cannot re-derive which: both caps can be configured and both
    # be under threshold, so "which cap is set" answers for a warning neither
    # produced. Only the branch that won knows. The tools screen was appending
    # a dollars-priced caveat to whichever sentence this happened to be,
    # framing `quantity` — recorded on every entry, never a floor — with a
    # count of `actual_cost`. One owner, three consumers: the division round
    # 079 chose when `usd_entries` and `usd_unpriced` were put beside every
    # dollar total rather than each screen counting for itself.
    basis = None
    if cfg.monthly_budget_tokens and tokens >= 0.8 * cfg.monthly_budget_tokens:
        warn = (f"{tokens:,} of {cfg.monthly_budget_tokens:,} monthly tokens used"
                + (" — over budget" if tokens >= cfg.monthly_budget_tokens else ""))
        basis = "tokens"
    if cfg.monthly_budget_usd and usd >= 0.8 * cfg.monthly_budget_usd:
        # One currency for the pair, not one each — the frame travels without
        # the repetition reading as two different units, which is the rule
        # `moneyPair` states on the TypeScript side. `money` names it, and the
        # cap goes through `amount` so precision is still decided in one place
        # where the currency word is not repeated (CQ-43).
        warn = (f"{money(usd)} of {money_amount(cfg.monthly_budget_usd)}"
                " monthly budget used"
                + (" — over budget" if usd >= cfg.monthly_budget_usd else ""))
        # Overwritten with the sentence, not set beside it. A basis left
        # behind by the branch that did not win labels a sentence that was
        # never written.
        basis = "usd"
    # Three cases, not two. No entries at all is a genuine zero and must stay
    # `0.0` — a fresh install spent nothing, and reporting that as "unknown"
    # is the same error as this fix in the opposite direction. Entries with no
    # price is the unknown, and only that one gets `None`.
    return {"month_tokens": tokens,
            "month_usd": round(usd, 4) if priced else (
                None if unpriced else 0.0),
            "usd_entries": priced, "usd_unpriced": unpriced,
            "cap_tokens": cfg.monthly_budget_tokens or None,
            "cap_usd": cfg.monthly_budget_usd or None, "warning": warn,
            "warning_basis": basis}

# Briefs currently executing, so a reloaded browser can find out that one is
# still going. A brief is a single blocking call with no progress stream, and
# the client disconnecting does not stop it — so without this the work carried
# on invisibly and the tool list showed it as never run.
#
# Deliberately in memory rather than a table: a row saying "running" outlives a
# crash and has to be aged out, whereas this is simply empty after a restart,
# which is the truth once the process holding the call is gone.
#
# KI-19 made it a lock as well as a display. It was only ever marked, never
# read before running, so two overlapping calls for one `(run_id, tool_id)`
# both reached the provider and both billed: run
# `1d85ff71c29e47eaa9b27e146fca6589` carries two `EXPERT:hreflang` cost rows,
# 09:12:12 and 09:12:29, against the single `expert_reports` row the second
# write left behind — `PRIMARY KEY (run_id, tool_id)` discarded the report the
# first charge paid for. `_claim_in_flight` is the test-and-set that stops it,
# and it is the authority: the client controls that were meant to prevent this
# cannot see each other, and neither can see a second browser at all.
#
# The value carries a claim token as well as a start time. A key held by one
# call must not be removable by another: the old `pop` was unconditional, so a
# sibling call finishing cleared the key belonging to the call still running,
# and the panel fell back to "Not run against this audit yet" on a brief that
# was executing. Release now removes the entry only if the token still there
# is the one that claimed it.
_IN_FLIGHT: dict[tuple[str, str], tuple[float, int]] = {}
_IN_FLIGHT_LOCK = threading.Lock()
_IN_FLIGHT_NEXT_TOKEN = 1


def _claim_in_flight(run_id: str, tool_id: str) -> int | None:
    """Take the slot for this brief, or `None` if another call already holds it.

    Test-and-set under the one lock: the read and the write cannot be split by
    a second request, which is the whole difference from the `_mark_in_flight`
    this replaced.
    """
    import time
    global _IN_FLIGHT_NEXT_TOKEN
    with _IN_FLIGHT_LOCK:
        if (run_id, tool_id) in _IN_FLIGHT:
            return None
        token = _IN_FLIGHT_NEXT_TOKEN
        _IN_FLIGHT_NEXT_TOKEN += 1
        _IN_FLIGHT[(run_id, tool_id)] = (time.time(), token)
        return token


def _release_in_flight(run_id: str, tool_id: str, token: int) -> None:
    """Give the slot back — but only if this caller is the one holding it."""
    with _IN_FLIGHT_LOCK:
        held = _IN_FLIGHT.get((run_id, tool_id))
        if held is not None and held[1] == token:
            del _IN_FLIGHT[(run_id, tool_id)]


def _in_flight_for(run_id: str) -> list[dict]:
    import time
    now = time.time()
    with _IN_FLIGHT_LOCK:
        return [{"tool": tool, "seconds": round(now - started)}
                for (run, tool), (started, _token) in _IN_FLIGHT.items()
                if run == run_id]


def _in_flight_for_site(conn, site_id: str) -> set[str]:
    """The tools running now against any run of this site (item 239 step
    4): a pill reads the site's newest analysis, not one picked run's."""
    with _IN_FLIGHT_LOCK:
        runs_ = {run for (run, _tool) in _IN_FLIGHT}
        pairs = list(_IN_FLIGHT)
    if not runs_:
        return set()
    marks = ",".join("?" * len(runs_))
    mine = {r["id"] for r in conn.execute(
        f"SELECT id FROM audit_runs WHERE site_id=? AND id IN ({marks})", (site_id, *runs_))}
    return {tool for (run, tool) in pairs if run in mine}


def _places_profile(cfg, site_row, inputs: dict | None) -> dict:
    """Look up the public Business Profile for the site under audit.

    Searched by the operator's query where given, otherwise by the bare domain,
    which is what Google indexes a small business under often enough to be
    worth trying. The result carries its own match status; a listing whose
    website does not resolve to this site is returned unconfirmed rather than
    used, because auditing the wrong business is worse than auditing none.
    """
    from clauditseo.providers.google import PlacesProfile

    provider = PlacesProfile(cfg)
    if not provider.available():
        return {}
    domain = (site_row["domain"] or "").replace("https://", "").replace(
        "http://", "").strip("/")
    query = ((inputs or {}).get("PLACE_QUERY") or "").strip() or domain
    if not query:
        return {}
    try:
        # Item 167: the listing the operator confirmed on the site record,
        # chosen by id wherever the search still returns it.
        return provider.lookup(query, expect_domain=domain,
                               confirmed_place_id=site_row.get("gbp_confirmed_place_id") or "")
    except Exception:                        # noqa: BLE001 - absence beats a guess
        return {}


def _remember_places_lookup(conn, site_id: str, places: dict | None) -> None:
    """Keep the latest lookup's candidates on the site (item 167).

    They are what the operator confirms from, and what the confirm route
    checks a pick against, so the stored id is always one Google returned for
    this site. Nothing is written for an empty or failed lookup: the previous
    candidates stay the best list the operator has."""
    if not places or not places.get("candidates"):
        return
    import json as _json

    from clauditseo.persistence.repo import now_iso
    with conn:
        conn.execute("UPDATE sites SET gbp_last_lookup=? WHERE id=?", (_json.dumps({
            "looked_up_at": now_iso(),
            "match": places.get("match"),
            "place_id": places.get("place_id"),
            "candidates": places["candidates"],
            "confirmed_place_id_not_returned": places.get("confirmed_place_id_not_returned"),
        }), site_id))


def _paint_metrics(url: str, cfg) -> dict:
    """Real field and lab timings for the rendering-path brief, where the keys
    allow it. The brief must never state a phase cost as measured without a
    source, so a provider that is absent or fails comes back missing rather
    than approximated — and CrUX legitimately has no data for low-traffic
    URLs, which is an honest absence, not an error."""
    from clauditseo.providers.google import CruxField, CruxHistory, PageSpeedLab

    out: dict[str, dict] = {}
    history = CruxHistory(cfg)
    if history.available():
        try:
            series = history.series(url)
            if series:
                # A single p75 says where the page is; the series says whether
                # it is getting worse — the question a fix plan turns on.
                out["CrUX 25-week trend (weekly p75, real users)"] = {
                    metric: (f"{points[0]:g} -> {points[-1]:g} over "
                             f"{len(points)} weeks (worst {max(p for p in points if p is not None):g})")
                    for metric, points in series.items()
                    if points and points[0] is not None and points[-1] is not None}
        except Exception:                    # noqa: BLE001 - absence beats a guess
            pass
    for label, provider in (("CrUX field data (p75, real users)", CruxField(cfg)),
                            ("PageSpeed lab data (single mobile run)", PageSpeedLab(cfg))):
        if not provider.available():
            continue
        try:
            metrics = provider.metrics(url)
        except Exception:                    # noqa: BLE001 - absence beats a guess
            continue
        if metrics:
            # A single lab run does not resolve to a tenth of a millisecond,
            # and reporting 15246.1 ms invites the brief to reason from
            # precision the measurement does not have.
            out[label] = {k: dataclasses.replace(v, value=round(v.value, 2))
                          if hasattr(v, "value") else v for k, v in metrics.items()}
    return out


def _snapshot_review_metrics(conn, site_id: str, places: dict | None) -> None:
    """Persist the Places rating and review count whenever a confirmed lookup
    happens. Two snapshots make a velocity — the one thing the review brief
    most wants and cannot get from an aggregate."""
    from clauditseo.providers.google import CONFIRMED
    if (places or {}).get("match") not in CONFIRMED:
        return
    from clauditseo.persistence.repo import create_id, now_iso
    stamp = now_iso()
    with conn:
        for key, value in (("gbp.review_count", places.get("review_count")),
                           ("gbp.rating", places.get("rating"))):
            if value is not None:
                conn.execute(
                    "INSERT INTO metric_snapshots (id, site_id, metric_key,"
                    " value, source, confidence, captured_at, tier)"
                    " VALUES (?, ?, ?, ?, 'places', 'high', ?, 'n/a')",
                    (create_id(), site_id, key, float(value), stamp))


def _review_series(conn, site_id: str) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT metric_key, value, captured_at FROM metric_snapshots"
        " WHERE site_id=? AND metric_key IN ('gbp.review_count', 'gbp.rating')"
        " ORDER BY captured_at", (site_id,))]


def _measure_images(page, policy, fetcher) -> dict:
    """HEAD each image to get its real byte weight and content type. The
    image brief must not estimate file sizes, so either we measure them or it
    writes [not retrievable] — a guess is the one unacceptable answer."""
    from urllib.parse import urljoin

    from clauditseo.crawler.types import USER_AGENT
    from clauditseo.modules.pagefacts import extract_facts

    weights: dict[str, dict] = {}
    for image in extract_facts(page).image_details[:MAX_IMAGE_HEADS]:
        src = (image.get("src") or "").split(",")[0].strip().split(" ")[0]
        if not src or src.startswith("data:"):
            continue
        absolute = urljoin(page.url, src)
        if not policy.allows(absolute, USER_AGENT):
            weights[image["src"]] = {"bytes": "[disallowed by robots.txt]"}
            continue
        try:
            response = fetcher._client.head(absolute)  # noqa: SLF001
            length = response.headers.get("content-length")
            weights[image["src"]] = {
                "bytes": int(length) if length and length.isdigit()
                else "[server sent no Content-Length]",
                "content_type": response.headers.get("content-type"),
            }
        except Exception:
            weights[image["src"]] = {"bytes": "[not retrievable]"}
    return weights


def _measure_rendered(crawl, site_row) -> dict:
    """What a browser saw of every image the crawl fetched (brief v15). The
    pass is `imaging.measure_for_run` since item 205, shared with the
    adaptive launcher; this keeps the name its other callers use."""
    from clauditseo import imaging

    record = repo.site_record(site_row) if isinstance(site_row, dict) else {}
    return imaging.measure_for_run(crawl, record or {})[0]


def _trace_perf(crawl, run_id: str) -> tuple[dict, str]:
    """The performance trace pass for this run. Lives in `perf.trace_for_run`
    so the adaptive path takes the same pass (2026-09-14); kept under this
    name because this is where the fixed-tier launcher calls it."""
    from clauditseo import perf
    return perf.trace_for_run(crawl, run_id)


def _narrow_trace(crawl, run_id: str, dims: list[str]) -> tuple[dict, str | None]:
    """The trace a refresh or verification takes, for the dimensions that
    read one (item 159). Before this both built their context with no
    `perf_traces`, so a Speed refresh re-measured nothing in its own
    dimension and - until `_apply_states` learned the instrument axis -
    cleared every trace finding on the page it fetched. Same pass and gate as
    an audit's; a run whose dimensions read no trace takes none."""
    from clauditseo.adaptive import TRACE_DIMS
    if not TRACE_DIMS & set(dims):
        return {}, None
    return _trace_perf(crawl, run_id)


#: The checks whose row states a saving (brief v16 step AU7), and so the
#: images the audit re-encodes. Every one is already a failing row: the
#: probe is a measurement of work the operator has been told to do, not a
#: sweep of the site's assets.
def _reencode_candidates(measured: dict, site_record: dict) -> list[tuple[str, int | None]]:
    """`imaging.reencode_candidates` since item 205; the name is kept for its
    callers."""
    from clauditseo import imaging
    return imaging.reencode_candidates(measured, site_record)


def _int_or_none(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _float_or_none(value):
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _measure_savings(measured: dict, site_row) -> None:
    """`imaging.measure_savings` since item 205, on the site row's record."""
    from clauditseo import imaging
    record = repo.site_record(site_row) if isinstance(site_row, dict) else {}
    imaging.measure_savings(measured, record or {})


def _comparable_host(authority: str) -> str:
    """One host string, in the one spelling `_host_matches_site` compares in.

    Two sources meet in that predicate and they disagree about two things. A
    stored `sites.domain` is whatever the operator typed, so it may carry a
    port (`127.0.0.1:55881` — the shape every driven fixture in the suite
    seeds) and, for IPv6, the brackets that make a port unambiguous
    (`[::1]:8080`). A URL's host arrives from `urlsplit().hostname`, which
    strips both. Comparing the two spellings directly is why a site stored at
    `host:port` could not be section-refreshed at all.

    Deliberately not folded into `site_host`: that function's answer is
    dialled by `probes._host_port`, and its docstring records that dropping a
    port there would silently move a probe of `example.com:8443` onto 443.
    This is the comparison's own normalisation and reaches nothing else.
    """
    a = authority.strip().lower()
    if a.startswith("["):
        # `[::1]` or `[::1]:8080` — the bracket is the delimiter, so a colon
        # inside it is part of the address rather than a port separator.
        end = a.find("]")
        return a[1:end] if end != -1 else a
    # A bare IPv6 literal carries colons and no port; only a single colon can
    # be a port separator on a name or an IPv4 literal.
    if a.count(":") == 1:
        return a.split(":", 1)[0]
    return a


def _host_matches_site(host: str, site_domain: str) -> bool:
    """Whether a URL's host is the site under audit, or a subdomain of it.

    Extracted from `_validate_start_url` rather than restated for the refresh
    endpoint (`FEATURES.md` F-06), which needs this half and not the other:
    its URL is a page the operator is already reading on a screen, chosen
    from what a crawl of this site fetched, not an address they typed. The
    loopback/private clause exists for the second case — a start URL pointed
    somewhere it should not be — and applying it here would refuse to refresh
    a page of a staging site the audit itself had just crawled.

    **CQ-98. The reverse direction is bounded to `www.`, and used not to be
    bounded at all.** The clause was `domain.endswith("." + host)`, which
    accepts *every* ancestor of the record's own domain — and a public suffix
    is an ancestor. `_host_matches_site('au', 'www.acme.com.au')` returned
    `True`, as did `('com.au', …)`, `('com', 'example.com')` and
    `('co.uk', 'shop.co.uk')`; `www.acme.com.au` is a row in this install's
    `sites` table, so the input was the operator's own data. Both callers act
    on the answer by fetching: `_validate_start_url` points the crawler, and
    `refresh_section` re-reads a page into this site's findings. Enumerated
    from a grep for the symbol rather than from the finding's list
    (DISCIPLINE rule 3) — those two, plus `tests/`; in-scope link following
    during a crawl does not read this.

    A registrable-domain comparison is the textbook answer and needs a
    public-suffix list, which this repository does not have and which a
    self-hosted install would then have to keep current. A one-label bound
    was measured against the same inputs and rejected: it refuses
    `('au', 'www.acme.com.au')` but still accepts `('com.au',
    'acme.com.au')` and `('co.uk', 'shop.co.uk')`, because a two-label
    public suffix sits exactly one label under an apex record — a partial fix
    that reads as a complete one. `www.` is the only prefix that is an alias
    by convention rather than by guess, it is the case the clause was
    serving, and it is decidable without a list.

    The cost, stated rather than left to be found: a site recorded at a
    non-`www` subdomain (`shop.example.com`) no longer reaches its own apex
    through this predicate. That narrows an off-site guard, which is the safe
    direction, and `refresh_section`'s refusal now names the check that
    failed. Subdomains of the record are untouched.

    **The port is stripped for the comparison only**, which is the half
    `tests/test_crawl_start_url.py:203-221` assigned to this fix by name: a
    site stored `host:port` could not be section-refreshed at all, because
    `urlsplit().hostname` never carries a port and a stored domain may. It is
    stripped here and not in `site_host`, whose own docstring records that
    `_probe_target` dials what it returns — stripping there would move a
    probe of `example.com:8443` onto 443."""
    domain = _comparable_host(site_host(site_domain))
    host = _comparable_host(host)
    if not host or not domain:
        return False
    return (host == domain
            or host.endswith("." + domain)
            # The record carries the `www.` alias and the URL is at the apex.
            or domain == "www." + host)


def _probe_target(conn, run_id: str) -> str | None:
    """The host a probe for this run runs against, read from the database.

    The only place a probe's target is decided (`FEATURES.md` F-05). It is
    deliberately not a parameter anywhere on the wire: the question comes out
    of a brief written by a language model, and the answer is measured
    against the site the run already belongs to, so neither the prose nor the
    request can point a handshake somewhere else.
    """
    run = runs.get_run(conn, run_id)
    site_row = repo.get_site(conn, run["site_id"]) if run else None
    return site_host(site_row["domain"] if site_row else "") or None


def _private_or_loopback(host: str) -> bool:
    """Whether a host string is an IP literal on this machine or a private net.

    One predicate, two callers. This lived inline in `_validate_start_url`
    and the probe path had no equivalent at all (CQ-112): the crawler
    refused `127.0.0.1` while `POST /api/runs/{id}/probes/cert-chain`
    opened a TLS handshake to it and returned 200. Extracted rather than
    copied — two spellings of one address rule is how the two paths came to
    disagree, and a second copy would only move the disagreement.

    A name that is not an IP literal is not judged here. Whether
    `localhost` may be probed is a question about shape, and it is answered
    by the caller that cares.
    """
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    return addr.is_private or addr.is_loopback


def _probe_refusal(host: str) -> str | None:
    """Why a probe may not be handshaken at this host, or None.

    The probe path's counterpart to `_validate_start_url`, and deliberately
    behind the same switch: `CLAUDITSEO_ALLOW_ARBITRARY_START_URL` is how
    the operator audits a staging target, and a setting that freed the
    crawler but not the probe would mean two different things about one
    site.

    There is no host-matches-site clause, because there is no supplied host
    to compare against: `_probe_target` reads the site's own domain, which
    is the property `probes.py`'s module docstring argues from. What is left
    is the address rule the crawler already applies, plus the shape check
    `SiteIn.domain` still does not make — CQ-108 is open, `Field(min_length=3)`
    is the whole of it, and `localhost` is three characters long.

    CQ-117: judge a *parsed* host, the way `_validate_start_url` always has.
    This read the stored string, so `127.0.0.1:443` was neither an IP literal
    nor dotless and walked past both clauses into a real `connect()` to
    loopback — reproduced end to end by the round-059 audit. `probes._host_port`
    splits the port off before dialling, so judging the unsplit string was
    never judging what the socket would reach.
    """
    if settings().allow_arbitrary_start_url:
        return None
    # `or host` carries the one shape urlsplit cannot parse: a bare IPv6
    # literal has no brackets, so `//::1` yields hostname None and the raw
    # string is the better answer. `rstrip` because a trailing dot is a
    # legal absolute-FQDN form that `ip_address` rejects.
    #
    # CQ-120: the *unbalanced* bracket is a different answer again. `//a]b`
    # and `//[::1` raise `ValueError: Invalid IPv6 URL` rather than returning
    # an empty hostname, and this line had nothing catching it -- so a stored
    # domain the route answers 422 for on every shape the tests parametrise
    # crashed it into a 500 with no `detail` instead. The raw string is the
    # right answer here for the same reason it is above: a host that cannot
    # be parsed is not thereby permitted, it is judged by the two clauses
    # below, and neither `ip_address` nor `"." in host` needs a parse.
    # Fixing what may be *stored* is CQ-108 and is gated elsewhere; this
    # function reads rows that already exist and may not assume them.
    try:
        host = (urlsplit(f"//{host}").hostname or host).rstrip(".")
    except ValueError:
        host = host.rstrip(".")
    if _private_or_loopback(host):
        return f"site host {host!r} is a private/loopback address"
    if "." not in host:
        # WF-103's other door, moved with it. This function's own docstring
        # argues the two refusals are behind one switch because "a setting
        # that freed the crawler but not the probe would mean two different
        # things about one site" — and a switch spelled one way at one door
        # and another way at the other is the same defect in the wording.
        # CQ-133 is the recorded case of exactly that.
        return (f"site host {host!r} is not a registrable host; probing a "
                "local target is an install-level setting and is switched "
                "off here")
    return None


def _offered_pages(evidence: dict) -> tuple[str | None, list[dict]]:
    """The pages of a run a page-scoped brief may be pointed at, in the order
    the picker offers them, with the URL the crawl was handed beside them.

    One owner, because the screen that chooses a target and the boundary that
    honours the choice must not disagree about what a page is. They did:
    `run_pages` filtered the evidence here and the expert route did not filter
    it at all, resolving instead to `evidence["start_url"]` — the URL the crawl
    was *handed*, which a run need never have retrieved. WF-89.

    **`start_url` is not a page.** A `Page` object survives a failed fetch, so
    a run can carry a `start_url` and no eligible page at all; run `d6592874`
    in the operator's database is exactly that, one attempt at
    `https://www.acme.com.au./` with `status: 0`.

    **This filter is deliberately not `crawler.types.page_is_eligible`.** That
    one requires `content_type.startswith("text/html")`; this admits any type
    containing "html", so `application/xhtml+xml` is a page to the picker and
    not to the engine. Unifying the two — there are six dict-shaped copies of
    this rule across `expert.py`, `linksuggest.py` and here — is a wider change
    than this one, and swapping this call site to the stricter rule alone would
    make the boundary refuse a page the picker had just offered. What matters
    here is that both ends of *this* decision read one list; the duplication is
    recorded rather than half-fixed.
    """
    start = evidence.get("start_url")
    pages = [{"url": p.get("url"),
              "title": p.get("title"),
              "words": p.get("word_count"),
              "depth": p.get("click_depth")}
             for p in evidence.get("pages", [])
             if p.get("status") == 200 and "html" in (p.get("content_type") or "")]
    pages.sort(key=lambda p: (p["url"] != start, p["depth"] if p["depth"]
                              is not None else 99, p["url"]))
    return start, pages


def _validate_start_url(start_url: str, site_domain: str) -> str | None:
    """The crawler may only be pointed at the site under audit (host equal to
    or a subdomain of the record's domain), and never at loopback/private
    addresses — unless the operator sets CLAUDITSEO_ALLOW_ARBITRARY_START_URL=1
    for staging/local targets. Returns an error string or None."""
    if settings().allow_arbitrary_start_url:
        return None
    try:
        # CQ-133. `_probe_refusal` twelve lines above has had this guard since
        # CQ-120 and this function did not, so the same unparseable string was
        # a readable 422 at one door and an unhandled 500 at four others --
        # and these four are the ones an operator reaches by *typing*. The
        # `rstrip` is CQ-121: a trailing-dot FQDN was normalised on the probe
        # path and not here, so which door you met decided what a host was.
        host = (urlsplit(start_url).hostname or "").rstrip(".")
    except ValueError:
        # Refused, not repaired, and deliberately not `return None`: an
        # exception swallowed into "no problem" would point the crawler
        # off-site, which is the one thing this function exists to prevent.
        return (f"start_url {start_url!r} is not a URL this crawler can "
                "parse; check the host for an unbalanced bracket")
    if _private_or_loopback(host):
        return f"start_url host {host!r} is a private/loopback address"
    if _host_matches_site(host, site_domain):
        return None
    # CQ-98. The same normalisation the comparison just made, so the sentence
    # names the value that was compared rather than the value in the column: a
    # site stored `example.com:8443` is matched on `example.com`, and quoting
    # the port here would send the operator to check a difference that was not
    # the one that failed.
    domain = _comparable_host(site_host(site_domain))
    # WF-103. This sentence is painted into a browser by the "Check this URL"
    # control, so it may not answer with a shell variable and a service
    # restart: the operator reading it is working on a screen, and the
    # product's pattern everywhere else is a control (UX-13), not an env var
    # named in an error. Surfacing the switch as a control was considered and
    # refused on the product's own reasoning — `secrets.MANAGED` is an
    # allowlist whose docstring excludes "settings that are not credentials
    # and have no business being writable from a browser", and this one
    # disables the off-site guard rather than supplying a key. So the message
    # says what is true and where the answer lives, and stops there. The
    # variable is still named in this function's docstring, which is read by
    # whoever can actually set it.
    return (f"start_url host {host.lower()!r} does not match the site domain "
            f"{domain!r}; auditing a staging or off-domain target is an "
            "install-level setting and is switched off here")


class ClientIn(BaseModel):
    name: str = Field(min_length=1)
    notes: str = ""


#: The one definition. `home.tsx` and `views.tsx` each hardcoded their own
#: copy of this list until DISPOSITIONS.md's 18-round cohort item closed —
#: both now read it from `/api/meta` instead. Deliberately narrower than
#: `loc.py`'s `LOCAL_TYPES`: that set classifies which *already-labelled*
#: sites the LOC module treats as local, and widening what a site may be
#: labelled to match it is a product decision about exposing finer local
#: sub-categories in the picker, not a vocabulary-duplication fix.
BUSINESS_TYPES = ("local-service", "ecommerce", "saas", "publisher")


class SiteIn(BaseModel):
    domain: str = Field(min_length=3)
    locale: str = "en-AU"
    business_type: str | None = None
    target_market: str | None = None


def site_of(site_row: dict) -> Site:
    """The site as a brief sees it: profile and the local-SEO record (brief
    v11 step AJ), from a row `repo.site_record` has parsed."""
    return Site(domain=site_row["domain"], locale=site_row["locale"],
                business_type=site_row["business_type"],
                target_market=site_row["target_market"],
                **{k: site_row.get(k) for k in ("brand", *repo.SITE_TEXT_FIELDS, *repo.SITE_JSON_FIELDS)
                   if k != "brand"}, brand=site_row.get("brand"))


class GbpListingIn(BaseModel):
    """The listing the operator confirms (item 167): a candidate's place id,
    or empty to withdraw the confirmation."""
    place_id: str = ""


class SitePatch(BaseModel):
    """Only what is being corrected. Absent means "leave it alone"; empty
    string means "clear it"."""
    business_type: str | None = None
    locale: str | None = None
    target_market: str | None = None
    #: The brand the site's copy carries (brief v11 step AI).
    brand: str | None = None
    #: The local-SEO facts the briefs read (brief v11 step AI). All optional;
    #: an empty value follows each prompt's stated fallback.
    gbp_primary_category: str | None = None
    service_area_entity: str | None = None
    title_strategy: str | None = None
    neighbourhoods: list[str] | None = None
    entity_variants: dict[str, list[str]] | None = None
    #: What the Images brief reads (brief v15 step AQ).
    platform: str | None = None
    cdn_or_image_pipeline: str | None = None
    breakpoints: list[int] | None = None
    budget_lcp_kb: str | None = None
    budget_page_kb: str | None = None
    review_provenance: str | None = None
    priority_internal_targets: list[str] | None = None
    sub_services: list[dict] | None = None
    location_pages: list[dict] | None = None
    page_types: dict[str, str] | None = None
    #: What the Content prompts read (brief v17 step AX). The two floors
    #: override the engine's placeholders; `authors` and `proof_assets`
    #: are what a replacement may draw on; the last four are Benchmark's
    #: prerequisites, and until they are set every Benchmark row is held.
    word_floors: dict[str, int] | None = None
    mandatory_formats: dict[str, list[str]] | None = None
    authors: list[dict] | None = None
    proof_assets: list[dict] | None = None
    competitors: list[str] | None = None
    keyword_data: dict | None = None
    top10_corpus: dict | None = None
    publish_history: dict | None = None
    #: What the client plan reads (brief v18 step AY). Decisions rather
    #: than measurements, so none of them has a default in the column:
    #: the plan prints its own fallback as an assumption, and it can only
    #: tell an assumption from an answer while these stay empty.
    optimisation_ratio: str | None = None
    horizons: list[str] | None = None
    workstreams: list[str] | None = None
    capacity: str | None = None
    measure_sources: list[str] | None = None
    #: The CDN/WAF in front of the origin (brief v18 step AZ, task 4). Naming it
    #: is what opens `ua-server-refusal`: the crawl brief holds the check until
    #: it knows where a UA refusal is enforced.
    cdn_or_waf: str | None = None
    #: The Security brief's stack and the third-party map (brief v20 step BD).
    #: The map is what script-inventory's fix sends the operator to: a host
    #: named here is classified as known rather than unexplained.
    stack: str | None = None
    third_party_map: dict[str, str] | None = None
    #: Held-domain inputs (brief v20 step BD); recorded, never acted on.
    active_probing_authorised: str | None = None
    #: Item 145 step BG: 'allow', 'block' or empty (not stated), and where the
    #: server's per-agent counts come from.
    ai_crawler_policy: str | None = None
    ai_field_data_source: str | None = None
    #: Comma-separated tokens, each one of `repo.edge_agents()`.
    ai_edge_blocked_agents: str | None = None
    #: Item 145 step BH: the entity record the AI surface brief reads. Empty
    #: until the operator sets them, including when they accept a suggestion
    #: read off the site's own schema — a field filled from the markup it is
    #: compared against would make two entity checks self-confirming.
    legal_name: str | None = None
    registered_ids: list[str] | None = None
    external_profiles: list[dict] | None = None
    reputation_source: str | None = None
    plugin_directory_feed: str | None = None
    #: WF-81, carried High since report 063. This field was absent for nine
    #: reports and the column it names is the one every run, crawl, finding
    #: and deliverable filename hangs on — so the only route to a typo was
    #: deleting the client and everything under it, or SQL. One of the three
    #: real sites in the operator's database is stored as
    #: `https://www.13acme.com.au/` because of it - the leading digit is the
    #: typo, and it is kept here because a name that cannot be corrected is
    #: the whole of what this field records.
    #:
    #: **"Clear it" is not on offer here**, unlike the three fields above.
    #: `business_type` empty means "not filed yet", which is a real answer; a
    #: site with no domain is not a site. The route refuses one that
    #: normalises to nothing rather than writing NULL into the column
    #: `site_host` is called on.
    domain: str | None = None


class BrandLogoIn(BaseModel):
    #: The image itself, base64 encoded. Data URI prefixes are stripped by
    #: the client; this wants the payload only.
    data_base64: str


class BrandNameIn(BaseModel):
    #: None or empty clears it back to the product name.
    name: str | None = None


class TierModelIn(BaseModel):
    model: str = Field(min_length=1)


class CurrencyIn(BaseModel):
    currency: str


class AgeThresholdsIn(BaseModel):
    warn_days: int
    stale_days: int


class ProviderKeyIn(BaseModel):
    #: Whitespace is stripped before storage — a key pasted with a trailing
    #: newline is the classic "correct key, 403 anyway".
    value: str = Field(min_length=1)


class ModelPriceIn(BaseModel):
    """$USD per MILLION tokens, the unit every vendor quotes in."""
    model: str = Field(min_length=1)
    input_usd: float = Field(ge=0)
    output_usd: float = Field(ge=0)


class VerifyIn(BaseModel):
    """Module level, not nested in create_app: `from __future__ import
    annotations` makes every annotation a string, and FastAPI resolves them
    against the module namespace — a class defined inside the factory is
    invisible there, and the endpoint answers 422 "field required" for a body
    that was sent correctly."""
    fingerprints: list[str] = Field(default_factory=list)


class RefreshIn(BaseModel):
    """One page, and the section the operator is standing in.

    Deliberately not a dimension and not a page *set*: the covering dimension
    is derived from the section by `anatomy.refresh_for`, from the same table
    the screen's offer is built from, so this endpoint cannot be used to
    configure a run the section never offered. `FEATURES.md` F-06 — "do not
    add a second launcher or a second way to configure a run"."""
    url: str
    section: str


class AuditIn(BaseModel):
    # A11Y is in the default because a scheduled pass sends no dimensions at
    # all, so anything left out here never runs unattended. Adding it changes
    # what a composite is computed over — weights renormalise across whatever
    # ran — so runs from before this point are scored on a different basis.
    # That is a real discontinuity in the trend and is only acceptable while
    # the scores are young.
    # LNK joined on 6 September 2026 (brief v17 step AW) without that
    # discontinuity: it is registered at weight zero, and `composite`
    # excludes a zero-weight dimension from the total it renormalises
    # over, so adding it to a run changes no score.
    # SEC joined at item 143 step BD. Unlike LNK it has a weight, 0.04 taken
    # from TEC, so composites move - marked by ENGINE_VERSION 0.22.0.
    dims: list[str] = Field(default_factory=lambda: ["TEC", "ONP", "A11Y", "PRF",
                                                     "CNT", "OFP", "LOC", "AIS",
                                                     "LNK", "SEC"])
    tier: str = "auto"            # auto (adaptive, default) | T1 | T2 | T3
    # Tri-state, and the third state is the whole of WF-59. `None` means "let
    # the tier decide", which is what every caller that says nothing has
    # always meant: a manual tier runs no analyst, an adaptive one does. This
    # was `bool = False` read as `body.analyst or body.tier == "auto"`, so an
    # adaptive run enabled the layer whatever the caller asked — `false` and
    # "unset" were indistinguishable and there was no way to ask for a bounded
    # auto run at all. An explicit `false` now declines the analysts and
    # leaves the breadth adaptive; `true` still forces them on for a manual
    # tier.
    analyst: bool | None = None
    model: str | None = None      # analyst model override for this run
    start_url: str | None = None  # override for local/staging targets
    # Crawl the entry page and the pages its navigation links to, then stop.
    # Manual tiers only: an adaptive run decides its own breadth, and a mode
    # that fixes the page set would be arguing with it.
    nav_only: bool = False
    # How much of the site, and how hard to look — the two axes `tier` was
    # doing at once. Both optional and both absent by default: an audit that
    # names neither behaves exactly as it did before this existed, which is
    # what keeps every stored run comparable.
    #
    # `scope` sets the page budget and the frontier; `depth` is a name for a
    # combination of `analyst` and the model tier, and an explicit `analyst`
    # or `model` still wins over it.
    scope: str | None = None      # page | nav | site | full
    depth: str | None = None      # quick | standard | deep


class PrecheckIn(BaseModel):
    # Same override the audit takes, for local and staging targets. Validated
    # against the site's own domain by `_validate_start_url`.
    start_url: str | None = None


class ToolScheduleIn(BaseModel):
    tool_id: str
    cadence: str


class ScheduleIn(BaseModel):
    audit_cadence: str | None = None      # None = manual
    tools: list[ToolScheduleIn] = Field(default_factory=list)


class AdviseIn(BaseModel):
    url: str | None = None
    model: str | None = None
    # The Speed part's depth pill (brief v19 step BC): `standard` runs the
    # brief on the templates, `deep` adds the per-page third-party waterfall.
    # A bigger context, not a bigger model - the brief asks for more evidence,
    # not more judgement. Ignored by every other tool.
    depth: str | None = None
    # Operator-supplied brief inputs a crawl cannot derive: the redirect map,
    # intended locales, topic clusters, platform.
    inputs: dict[str, str] = Field(default_factory=dict)
    # Force a fresh call. Needed to compare models honestly: a cached reply
    # reports zero tokens, which would flatter whichever model ran second.
    no_cache: bool = False
    # Who the result is for, where that decides whether it may be written at
    # all (item 178). `client` on the plan brief means "the plan a client report
    # will carry", and the route refuses it before spending while that report
    # is held by the Critical-and-High threshold. Absent is the operator's own
    # reading, which is never held.
    for_audience: str | None = None
    # The category the operator is reading, narrowing the answer to it
    # (FEATURES.md F-03). Absent means the full remit, which is what every
    # caller before this got and still gets.
    scope: str | None = None
    # The finding being asked about (FEATURES.md F-02). Names its own scope,
    # so it overrides `scope` rather than combining with it, and is refused if
    # this tool is not the specialist that judges that check.
    check_id: str | None = None


class ChatIn(BaseModel):
    site_id: str
    question: str = Field(min_length=1)


class StateIn(BaseModel):
    state: str  # open | accepted-risk


class AttemptIn(BaseModel):
    note: str = ""


class ReportIn(BaseModel):
    template: str  # run | run-free | comparison | monthly-trend
    audience: str  # client | internal
    run_ids: list[str] = Field(min_length=1)
    #: The stored deliverable this one replaces, when the request came from
    #: pressing `regenerate` on a row rather than from generating afresh.
    #: `QUESTIONS.md` Q-9. Optional because most generations replace nothing.
    supersedes: str | None = None


#: When this interpreter started serving, stamped at import.
#:
#: Not a request-time value: the question `/api/health` answers is whether the
#: source on disk has moved *since* the process began, so one side of that
#: comparison has to be fixed at the beginning. Module scope rather than inside
#: `create_app`, so a test that builds a second app in the same interpreter
#: still reports the interpreter's own start rather than the app's.
_STARTED_TS = _time.time()
_STARTED_AT = _dt.fromtimestamp(_STARTED_TS).astimezone().isoformat()


def create_app(db_path: Path | None = None) -> FastAPI:
    cfg = settings()
    path = db_path or cfg.db_path
    app = FastAPI(title=APP_NAME, version=__version__)

    # Startup recovery: runs whose worker died with a previous process must
    # not sit at 'running' forever.
    _boot = connect(path)
    migrate(_boot)
    recovered = runs.recover_interrupted(_boot)
    _boot.close()
    if recovered:
        print(f"clauditseo: marked {recovered} interrupted run(s) as failed")

    # What startup migrated to. A request runs the full `migrate` - with its
    # directory read, drift hashes and warnings - only when the ledger lacks
    # one of these: a database replaced under the running service, say. The
    # files themselves are checked at startup, above, and not re-read per
    # request, which cost ~9 ms on every call.
    _migrated_to = migration_names()

    def db():
        conn = connect(path)
        if not is_current(conn, _migrated_to):
            migrate(conn)
        try:
            yield conn
        finally:
            conn.close()

    dep = Depends(db)

    async def auth(request: Request, conn=dep) -> dict | None:
        """Resolve the caller: a specific operator (per-operator token), the
        configured API token (full access, returns None), or open local mode
        when no tokens exist anywhere. Returns the operator dict or None for
        full-access contexts."""
        cfg_token = settings().api_token
        header = request.headers.get("authorization", "")
        token = header[7:].strip() if header.lower().startswith("bearer ") else ""
        if token:
            if cfg_token and token == cfg_token:
                return None
            operator = repo.operator_by_token(conn, token)
            if operator:
                return operator
            raise HTTPException(status_code=401, detail="invalid or missing token")
        if cfg_token or repo.any_operator_tokens(conn):
            raise HTTPException(status_code=401, detail="invalid or missing token")
        # Open local mode is the correct answer only when nobody configured a
        # credential. An install still carrying one under the pre-rename name
        # configured one — closing the lookup must not turn that into no
        # authentication at all.
        if stale_legacy_token():
            raise HTTPException(status_code=401, detail=STALE_TOKEN_DETAIL)
        return None

    guarded = [Depends(auth)]
    op_dep = Depends(auth)

    def check_client(conn, operator: dict | None, client_id: str) -> None:
        # 404, not 403 — a member should not learn which client ids exist.
        if not repo.operator_can_access(conn, operator, client_id):
            raise HTTPException(status_code=404, detail="client not found")

    def check_site(conn, operator: dict | None, site_id: str) -> None:
        client_id = repo.client_id_for_site(conn, site_id)
        if client_id is None:
            raise HTTPException(status_code=404, detail="site not found")
        check_client(conn, operator, client_id)

    def check_run(conn, operator: dict | None, run_id: str) -> dict:
        run = runs.get_run(conn, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="run not found")
        check_site(conn, operator, run["site_id"])
        return run

    def _source_freshness() -> dict:
        """When this process started, and when the source it serves last moved.

        `started_at` is stamped once, here, because a process start does not
        change. `source_mtime` is read per request on purpose: the whole point
        is to notice source changing *after* start-up, which is precisely what
        a value cached at import could never see.
        """
        newest, newest_at = None, None
        root = Path(__file__).resolve().parents[1]
        try:
            for py in root.rglob("*.py"):
                if "__pycache__" in py.parts:
                    continue
                m = py.stat().st_mtime
                if newest_at is None or m > newest_at:
                    newest, newest_at = py, m
        except OSError:
            pass
        return {
            "started_at": _STARTED_AT,
            "source_mtime": (_dt.fromtimestamp(newest_at).astimezone().isoformat()
                             if newest_at else None),
            "source_newest": (newest.relative_to(root).as_posix()
                              if newest else None),
            # Said outright rather than left to the reader to compute from two
            # timestamps, because the whole failure mode is nobody comparing
            # them. A browser can read this; a PowerShell script is not the
            # only thing that should be able to answer it.
            "source_newer_than_process": (
                bool(newest_at and newest_at > _STARTED_TS)),
        }

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": __version__,
                "engine_version": ENGINE_VERSION,
                # Which UI is actually being served. Null means no build is
                # present, which is a different state from a stale one.
                "bundle": bundle_id(),
                # What the staleness check compares, answered by the process
                # itself. Until this existed the only thing that could say
                # whether the running product held the current source was a
                # PowerShell script nothing called, so a machine fourteen
                # files behind looked identical to a current one from every
                # surface an operator or a browser could reach.
                #
                # `started_at` is this process; `source_mtime` is the newest
                # `clauditseo/**.py` on disk *now*. If the second is later
                # than the first, the code answering this request is not the
                # code in the tree.
                **_source_freshness()}

    @app.get("/api/meta", dependencies=guarded)
    def meta(conn=dep):
        c = settings()
        llm = provider_from_settings(c)
        providers = _providers(c)
        models = [c.llm_model] + [m for m in ANALYST_MODELS if m != c.llm_model]
        return {
            # Each dimension names the sections its sweep refreshes, because
            # the launcher picks dimensions and every other screen groups by
            # section — without this the two read as different vocabularies
            # for the same site.
            "dimensions": [{"code": m.code, "name": m.name,
                            "default_weight": m.default_weight,
                            "categories": anatomy.categories_for_dimension(m.code)}
                           for m in registry.all_modules().values()],
            # Sections no sweep populates at all. Running every dimension
            # leaves them untouched, so a zero beside them means "nothing
            # covers this", not "checked and clean".
            "analysis_only": [anatomy.BY_KEY[k].label
                              for k in anatomy.ANALYSIS_ONLY],
            "tiers": ["auto", "T1", "T2", "T3"],
            # The scan scope table, keyed as `scanscope.SCOPES` is. Only the
            # page budget travels: the labels beside it are display copy and
            # the two languages word them differently on purpose, but
            # `max_pages` is the number the crawler enforces, so a screen that
            # types its own copy states a page count the crawl will not visit
            # (CQ-245, UX-100). `null` means "the tier's own budget", which is
            # not a figure this table can resolve.
            "scopes": {key: {"max_pages": sc.max_pages}
                       for key, sc in SCOPES.items()},
            "business_types": list(BUSINESS_TYPES),
            "analyst_available": llm is not None,
            "analyst_budgets": {"T2": c.llm_budget_t2, "T3": c.llm_budget_t3},
            "providers": providers,
            # Which optional tools each dimension can use; absent entries need none.
            "dimension_providers": DIMENSION_PROVIDERS,
            "models": models,
        }

    # `operator=op_dep` rather than `dependencies=guarded`: the same `auth`
    # dependency, bound to a name because the route now needs the operator it
    # authenticated in order to authorise `site_id`. Declaring both would run
    # `auth` twice for one request.
    @app.get("/api/playbook")
    def playbook(site_id: str | None = None, conn=dep, operator=op_dep):
        """The workbench: every tool in working order, with honest status.

        `site_id` is optional and bounds the price population only (UX-77).
        Which tools exist, what they do and which model each resolves to are
        install facts and do not move with it; only `typical_cost`,
        `typical_tokens` and the two population counts beside them do. Given
        one, the prices are this site's own history; given none, they are
        install-wide, which is what a caller genuinely not looking at a site
        wants. Authorised through `check_site` like every other route that
        takes a site, because an unknown or unpermitted id must not silently
        degrade to the install-wide figure it was passed in order to avoid.
        """
        from clauditseo.analysts.expert import EXPERT_TOOLS
        from clauditseo.playbook import resolved, summary
        if site_id:
            check_site(conn, operator, site_id)
        c = settings()
        phases = resolved(c)
        # What each brief has actually cost, so the tier decision is made with
        # the price in view. Measured from this operator's own history rather
        # than estimated: the spread between briefs is more than twentyfold.
        # Tokens are always recorded; dollars only once the operator has
        # supplied rates, so both are returned and the caller shows whichever
        # it has. Never a guessed price.
        #
        # `expert_estimates` and not a second query here (CQ-169). This
        # endpoint used to take `AVG(actual_cost)` over `cost_entries` while
        # the estimator took a median over `expert_reports.cost`, so the Brief
        # panel priced a brief the Schedule modal called unpriced and no
        # screen said which to believe. Measured read-only against
        # `data/clauditseo.db`: `hreflang` 0.0648 here against 0.0633 there,
        # `onpage-hygiene` 0.0356 against 0.0352, `mobile-viewport` 0.0687
        # here against no price at all there.
        #
        # The estimator is the owner rather than the loser of a coin toss, and
        # both divergences say why. (1) `cost_entries` carries a row per
        # *charge*: KI-19's double-billed retry puts two rows against one
        # surviving `expert_reports` row, so the average was the mean of a
        # charge and its own replacement and `runs_costed: 2` described one
        # run. `expert_reports` is one row per (run, tool, **page**) by table
        # constraint — migration 0029 added the page, and the argument is
        # unchanged by it: the table still holds one row per stored RESULT
        # where `cost_entries` holds one per charge, which is the whole of why
        # the estimator owns this number. What the page buys is that a brief
        # read against three pages is now three results rather than one, so
        # the median is taken over the work that was actually billed instead
        # of over the one page that survived the delete (KI-56).
        # (2) `mobile-viewport`'s charge sits against a stored
        # brief of zero tokens; pricing from it is a confident number for work
        # nothing recorded.
        #
        # No `pages`: unscaled is what a caller with no crawl in front of it
        # wants, and that has not changed.
        #
        # The site filter is now the *caller's* to state, and this is the half
        # UX-77 corrected. The comment here used to argue the call was
        # "deliberately not changed" by Q-1's **per site** answer because "this
        # screen shows none" — and that was wrong about its own callers.
        # `dashboard/src/tools.tsx` and `dashboard/src/expert.tsx` both fetch
        # this route with a site already chosen and paint the figure it returns
        # beside a control that spends money, so the reasoning held for the
        # endpoint's name and not for either screen reading it. Passing no
        # `site_id` still means install-wide, so a caller genuinely not looking
        # at a site is unaffected.
        estimates = runs.expert_estimates(conn, site_id=site_id)
        briefs = {}
        for tool_id, spec in EXPERT_TOOLS.items():
            seen = estimates.get(tool_id)
            briefs[tool_id] = {
                "scope": spec["scope"],
                "tier": spec.get("tier", "standard"),
                "model": tiers.settings_for(conn, c).model_for_tier(
                    spec.get("tier", "standard")),
                "inputs": spec.get("inputs", []),
                "typical_cost": seen["cost"] if seen else None,
                "typical_tokens": seen["tokens"] if seen else None,
                # The names were always the honest ones; the values are what
                # move. `runs_costed` counts the briefs the price was actually
                # taken over and `runs_sampled` is what it is a share of — the
                # pair, so neither can be read as the other. Both now count
                # stored briefs rather than charge rows, which is what "runs"
                # says.
                "runs_costed": seen["cost_samples"] if seen else 0,
                "runs_sampled": seen["samples"] if seen else 0,
                # Which population, beside the value, exactly as
                # `GET /api/sites/{id}/schedule` carries it. This endpoint
                # re-serialises the estimator field by field, so a scope that
                # is not named here is a scope that is lost — and now that the
                # same route answers both ways depending on one query
                # parameter, a reader cannot infer it from the path either.
                # `None` means install-wide. CQ-198 asked for a reader and
                # `6a8bb55` shipped one: three screens read this key —
                # `schedule.tsx`, `tools.tsx` and `expert.tsx` — all through
                # `components.tsx`'s `PriceScopeNote`. CQ-216: this comment
                # said the reader was still owed for nineteen reports after
                # it landed, which is the shape a future reader acts on.
                "scoped_to_site": (seen or {}).get("scoped_to_site", site_id),
            }
        return {"phases": phases, "summary": summary(phases), "experts": briefs,
                "model_tiers": {"fast": c.llm_model_fast,
                                "standard": c.llm_model,
                                "deep": c.llm_model_deep}}

    # -- admin --------------------------------------------------------------

    def _providers(c) -> dict:
        from clauditseo.providers.google import SearchConsole
        llm = provider_from_settings(c)
        # Configured-or-not plus WHERE to configure it. Key values never
        # leave the server; these are variable names, not secrets. They are
        # spelled with the current prefix rather than hard-coded, so a
        # rename cannot leave this screen instructing operators to set
        # variables named after a product that no longer exists.
        env = config_prefix
        out = {
            "LLM analyst": {
                "configured": llm is not None,
                "detail": (f"{llm.name} · {llm.model_id}" if llm
                           else "enables the analyst layer, expert analyses and chat"),
                "env": "ANTHROPIC_API_KEY"},
            "PageSpeed": {"configured": bool(c.pagespeed_api_key),
                          "detail": "Core Web Vitals lab data",
                          "env": env + "PAGESPEED_KEY"},
            "CrUX": {"configured": bool(c.crux_api_key),
                     "detail": "Core Web Vitals field data",
                     "env": env + "CRUX_KEY"},
            "Headless renderer": {
                "configured": _renderer_available(),
                "detail": ("post-hydration DOM for the JS-rendering analysis — "
                           "its parity table is provisional without it. "
                           "pip install clauditseo[render], then "
                           "playwright install chromium"),
                "env": "(python package, not a key)"},
            "IndexNow": {"configured": bool(c.indexnow_key),
                         "detail": ("submits URLs for recrawl when a run "
                                    "verifies their findings fixed. Free key; "
                                    "the key file must be hosted at the site "
                                    "root"),
                         "env": env + "INDEXNOW_KEY"},
            "Places": {"configured": bool(c.places_api_key),
                       "detail": ("Business Profile as Google holds it — name, "
                                  "address, phone, categories, hours, rating and "
                                  "review count. Billed per request. Never posts, "
                                  "Q&A, photos or attributes"),
                       "env": env + "PLACES_KEY"},
            "Moz": {"configured": bool(c.moz_token), "detail": "backlink metrics",
                    "env": env + "MOZ_TOKEN"},
            "OpenPageRank": {"configured": bool(c.openpagerank_key),
                             "detail": "domain authority (free tier)",
                             "env": env + "OPENPAGERANK_KEY"},
            "DataForSEO": {"configured": bool(c.dataforseo_login and c.dataforseo_password),
                           "detail": "backlink summary",
                           "env": env + "DATAFORSEO_LOGIN + _PASSWORD"},
            "Search Console": {"configured": SearchConsole(c).available(),
                               "detail": "search analytics (also needs "
                                         "pip install google-auth)",
                               "env": env + "GOOGLE_SA_FILE"},
        }
        # Whether the key panel can set this one, decided here rather than
        # guessed in the browser. Two screens describing the same providers
        # disagreed: this list went on telling operators to `setx` for keys
        # the panel above had already taken over, and the one entry that is
        # not a key at all — the headless renderer, a pip install — was
        # offered a `setx` line that could never work.
        from clauditseo import secrets as secret_store
        stored = secret_store.load()
        for entry in out.values():
            name = entry["env"].split()[0]
            entry["managed"] = name in secret_store.BY_NAME
            # And where the value came from, so this table and the key panel
            # cannot describe the same provider differently. "configured" on
            # its own was true of a key set here, a key in the environment,
            # and a key set here that is overriding one in the environment —
            # three states an operator has to tell apart to debug anything.
            # Only for things that are actually keys. The headless renderer
            # is a pip install, and reporting it as "from your environment"
            # sent an operator looking for a variable that does not exist.
            entry["source"] = (None if not entry["managed"]
                               else "panel" if stored.get(name)
                               else "environment" if entry["configured"]
                               else None)
        return out

    @app.get("/api/admin", dependencies=guarded)
    def admin_overview(conn=dep):
        from clauditseo.persistence import backup as backup_mod
        c = settings()
        return {
            "version": __version__,
            "engine_version": ENGINE_VERSION,
            # The footer drew the server's version using whatever bundle was
            # on disk, so the two could never disagree and a stale UI was
            # indistinguishable from a current one.
            "bundle": bundle_id(),
            "locale": c.default_locale,
            "auth_mode": ("config token" if c.api_token
                          else "per-operator tokens" if repo.any_operator_tokens(conn)
                          else "refusing — token set under the retired name"
                          if stale_legacy_token()
                          else "open local mode"),
            "providers": _providers(c),
            "models": {"fast": c.llm_model_fast, "standard": c.llm_model,
                       "deep": c.llm_model_deep},
            "budgets": {"T2": c.llm_budget_t2, "T3": c.llm_budget_t3,
                        "page": c.llm_budget_page},
            "database": backup_mod.database_stats(conn, path),
            "backups": backup_mod.list_backups(path),
            "spend": runs.monthly_spend(conn),
            "budget": _budget_status(conn, c),
            "restore_steps": backup_mod.restore_instructions(path),
            "operators": repo.list_operators(conn),
        }

    @app.post("/api/admin/backup", dependencies=guarded, status_code=201)
    def admin_backup(conn=dep):
        """Verified snapshot, safe to take while the server is serving."""
        from clauditseo.persistence import backup as backup_mod
        result = backup_mod.create_backup(conn, path)
        if result["status"] != "ok":
            raise HTTPException(status_code=500, detail=result)
        return result

    @app.post("/api/admin/clear-analyst-cache", dependencies=guarded)
    def admin_clear_cache(conn=dep):
        from clauditseo.persistence import backup as backup_mod
        return {"cleared": backup_mod.clear_analyst_cache(conn)}

    # -- clients ------------------------------------------------------------

    @app.get("/api/clients")
    def clients(conn=dep, operator=op_dep):
        return repo.list_clients(conn, operator)

    @app.get("/api/sites")
    def all_sites(conn=dep, operator=op_dep):
        """Every site the operator can see, flattened with its client name.

        The tool-first view picks a target across all clients at once, which
        the per-client listing cannot answer without a request per client.
        Scoped through list_clients so a member still sees only their own.
        """
        out = []
        for client in repo.list_clients(conn, operator):
            for site in repo.list_sites(conn, client["id"]):
                out.append({"id": site["id"], "domain": site["domain"],
                            "client_id": client["id"], "client": client["name"]})
        return out

    @app.post("/api/clients", status_code=201)
    def create_client(body: ClientIn, conn=dep, operator=op_dep):
        owner = operator["id"] if operator else repo.ensure_default_operator(conn)
        client_id = repo.create_client(conn, owner, body.name, notes=body.notes)
        return {"id": client_id}

    @app.get("/api/clients/{client_id}")
    def client_detail(client_id: str, conn=dep, operator=op_dep):
        client = repo.get_client(conn, client_id)
        if not client:
            raise HTTPException(status_code=404, detail="client not found")
        check_client(conn, operator, client_id)
        sites = repo.list_sites(conn, client_id)
        for site in sites:
            # Readings of the site, not every run of it. Both figures below
            # are the site's standing position — "latest score" and "how many
            # audits" — and a verification is neither. Measured before this
            # line changed, on `www.acme.com.au`: this route answered
            # `latest_score: 86.2` from the eight-page verification while
            # `/api/overview` answered `70.52` from the 224-page audit, on the
            # same page load.
            # Every scored audit, whatever its scope, for the count - "how
            # many audits" includes a page scan that ran; the kind is the
            # question asked here, since brief v6 step V2 made the site
            # reading predicate scope-aware and a page scan is no reading.
            site_runs = [r for r in runs.list_runs(conn, site["id"])
                         if runs.is_site_reading(r["kind"])
                         and r["status"] in runs.SCORED_STATUSES]
            # The site's score is the last reading of the site (brief v3 step
            # I, v6 step V2).
            wide = [r for r in site_runs if runs.reads_site(r)]
            site["latest_score"] = wide[0]["composite_score"] if wide else None
            site["run_count"] = len(site_runs)
            states = runs.site_states(conn, site["id"])
            site["open_findings"] = sum(1 for s in states if s["state"] in ("open", "regressed"))
            site["regressions"] = sum(1 for s in states if s["state"] == "regressed")
        client["sites"] = sites
        return client

    @app.delete("/api/clients/{client_id}")
    def delete_client(client_id: str, conn=dep, operator=op_dep):
        if not repo.get_client(conn, client_id):
            raise HTTPException(status_code=404, detail="client not found")
        check_client(conn, operator, client_id)
        repo.delete_client(conn, client_id)
        return {"ok": True}

    @app.delete("/api/sites/{site_id}")
    def delete_site(site_id: str, conn=dep, operator=op_dep):
        """Item 169: a wrong site can be removed without deleting its client."""
        if not repo.get_site(conn, site_id):
            raise HTTPException(status_code=404, detail="site not found")
        check_site(conn, operator, site_id)
        running = conn.execute(
            "SELECT id FROM audit_runs WHERE site_id=? AND status IN ('pending','running') LIMIT 1",
            (site_id,)).fetchone()
        if running:
            raise HTTPException(status_code=409,
                                detail=f"an audit is running against this site ({running['id']}); "
                                       "stop it or wait for it before deleting the site")
        repo.delete_site(conn, site_id)
        return {"ok": True}

    @app.post("/api/clients/{client_id}/sites", status_code=201)
    def create_site(client_id: str, body: SiteIn, conn=dep, operator=op_dep):
        if not repo.get_client(conn, client_id):
            raise HTTPException(status_code=404, detail="client not found")
        check_client(conn, operator, client_id)
        if body.business_type is not None and body.business_type not in BUSINESS_TYPES:
            raise HTTPException(
                status_code=422,
                detail=f"business_type must be one of {list(BUSINESS_TYPES)}")
        site_id = repo.create_site(conn, client_id, body.domain, body.locale,
                                   body.business_type, body.target_market)
        return {"id": site_id}

    # -- sites --------------------------------------------------------------

    @app.get("/api/sites/{site_id}")
    def site_detail(site_id: str, conn=dep, operator=op_dep):
        site = repo.site_record(repo.get_site(conn, site_id))
        if not site:
            raise HTTPException(status_code=404, detail="site not found")
        check_site(conn, operator, site_id)
        states = runs.site_states(conn, site_id)
        site["states"] = states
        site["regressions"] = [s for s in states if s["state"] == "regressed"]
        site["runs"] = runs.list_runs(conn, site_id)
        site["trend"] = runs.site_trend(conn, site_id)
        site["expert_delta"] = runs.expert_delta(conn, site_id)
        site["watch"] = runs.watch_changes(conn, site_id)
        site["crawl_diff"] = runs.crawl_diff(conn, site_id)
        site["notes"] = [dict(r) for r in conn.execute(
            "SELECT id, body, created_at FROM notes WHERE site_id=?"
            " ORDER BY created_at DESC", (site_id,))]
        # The record tab carries a verify button, so it is told what the verify
        # route will accept. Carried rather than re-derived, for the reason
        # `runs.names_a_page` records: the server decides, so a screen cannot
        # offer a control the server would refuse.
        site["verify_page_cap"] = runs.VERIFY_PAGE_CAP
        return site

    @app.put("/api/sites/{site_id}")
    def update_site(site_id: str, body: SitePatch, conn=dep, operator=op_dep):
        """Correct a site's profile.

        Does not touch anything already produced. A brief written while the
        site was filed as "ecommerce" reasoned about a product catalogue, and
        it still says so — the fix is to run it again, not to relabel the
        report. `analyses_before` is how many were produced under the old
        profile, so the caller can say that plainly rather than implying a
        correction reaches backwards.
        """
        site = repo.get_site(conn, site_id)
        if not site:
            raise HTTPException(status_code=404, detail="site not found")
        check_site(conn, operator, site_id)
        if body.business_type not in (None, "", *BUSINESS_TYPES):
            raise HTTPException(
                status_code=422,
                detail=f"business_type must be one of {list(BUSINESS_TYPES)}")
        # Brief v15 step AQ: the one value the record constrains, beside
        # the strategy. An empty provenance is read as unconfirmed, which
        # is what the prompt says, so it needs no rejection.
        if body.review_provenance not in (None, "", *repo.REVIEW_PROVENANCE):
            raise HTTPException(status_code=422,
                                detail=f"review_provenance must be one of "
                                       f"{list(repo.REVIEW_PROVENANCE)}")
        if body.active_probing_authorised not in (None, "", "true"):
            raise HTTPException(status_code=422,
                                detail="active_probing_authorised is 'true' or empty")
        if body.ai_crawler_policy not in (None, "", *repo.AI_CRAWLER_POLICIES):
            raise HTTPException(status_code=422,
                                detail=f"ai_crawler_policy must be one of "
                                       f"{list(repo.AI_CRAWLER_POLICIES)} or empty")
        unknown_agents = sorted(repo.edge_blocked_agents(body.ai_edge_blocked_agents)
                                - set(repo.edge_agents()))
        if unknown_agents:
            raise HTTPException(status_code=422,
                                detail=f"ai_edge_blocked_agents names agents the UA matrix "
                                       f"does not send: {unknown_agents}")
        if body.title_strategy not in (None, "", *repo.TITLE_STRATEGIES):
            raise HTTPException(status_code=422,
                                detail=f"title_strategy must be one of {list(repo.TITLE_STRATEGIES)}")
        for name in ("sub_services", "location_pages"):
            for item in (getattr(body, name) or []):
                if not isinstance(item, dict):
                    raise HTTPException(status_code=422, detail=f"{name} entries are objects")
        patch = body.model_dump()
        # WF-81. Normalised through the owner rather than here: `site_host` is
        # the one place a stored domain becomes the host it names, and its
        # docstring records four call sites that each open-coded the same two
        # lines and each carried the same defect. A fifth copy in this route
        # would be that finding again, in the door built to close it.
        #
        # Before the comparison below, not after. `changed` is what the screen
        # tells the operator moved, and on this field that sentence is "every
        # stored analysis was written against the old domain" — so re-saving
        # the value already showing must report nothing rather than raising a
        # staleness warning about a change that did not happen.
        if patch["domain"] is not None:
            patch["domain"] = site_host(patch["domain"])
            if not patch["domain"]:
                raise HTTPException(
                    status_code=422,
                    detail="domain cannot be cleared: every run, crawl and "
                           "deliverable for this site is addressed by it")
        stored = repo.site_record(site)
        changed = {k: v for k, v in patch.items() if v is not None
                   and ((stored.get(k) or "") if k not in repo.SITE_JSON_FIELDS
                        else (stored.get(k) or None)) != (v if k not in repo.SITE_JSON_FIELDS or v else None)}
        repo.update_site(conn, site_id, **patch)
        stale = conn.execute(
            "SELECT COUNT(*) FROM expert_reports er"
            " JOIN audit_runs a ON a.id = er.run_id WHERE a.site_id=?",
            (site_id,)).fetchone()[0] if changed else 0
        return {**dict(repo.get_site(conn, site_id)),
                "changed": sorted(changed),
                "analyses_before": stale}

    @app.put("/api/sites/{site_id}/gbp-listing")
    def confirm_gbp_listing(site_id: str, body: GbpListingIn, conn=dep, operator=op_dep):
        """The operator confirms which Google listing is this site's (item 167).

        The id must be one of the candidates the latest Places lookup returned
        for this site: the operator picks a listing, and the id is what gets
        stored, so a typo or another site's listing cannot become this site's.
        An empty id withdraws the confirmation. Nothing already produced
        changes; the next Places brief reads the confirmation."""
        site = repo.site_record(repo.get_site(conn, site_id))
        if not site:
            raise HTTPException(status_code=404, detail="site not found")
        check_site(conn, operator, site_id)
        place_id = (body.place_id or "").strip()
        if place_id:
            offered = {c.get("place_id") for c in
                       ((site.get("gbp_last_lookup") or {}).get("candidates") or [])}
            if place_id not in offered:
                raise HTTPException(
                    status_code=422,
                    detail="that listing is not among the candidates the latest "
                           "Google listing lookup returned for this site — run a "
                           "Business Profile, Citations or Reviews brief to look "
                           "the listing up, then confirm one of its candidates")
        with conn:
            conn.execute("UPDATE sites SET gbp_confirmed_place_id=? WHERE id=?",
                         (place_id or None, site_id))
        return repo.site_record(repo.get_site(conn, site_id))

    @app.get("/api/sites/{site_id}/trend")
    def site_trend(site_id: str, metric: str = "composite_score", conn=dep,
                   operator=op_dep):
        check_site(conn, operator, site_id)
        return runs.site_trend(conn, site_id, metric)

    @app.post("/api/sites/{site_id}/states/{fingerprint}")
    def set_state(site_id: str, fingerprint: str, body: StateIn, conn=dep,
                  operator=op_dep):
        check_site(conn, operator, site_id)
        # WF-68. The allow-list was a literal pair here, and `withdrawn` was
        # added to the schema, to `site_states`, to the TypeScript union, to
        # the record's filter and to two screens' rendered text without ever
        # being added to it — so the one state that says "this finding was
        # never true" could be counted and read and never written. The
        # population is `runs.OPERATOR_SETTABLE_STATES` now, which derives from
        # the same constant the model-blindness rule does.
        if body.state not in runs.OPERATOR_SETTABLE_STATES:
            raise HTTPException(
                status_code=422,
                detail="state must be one of "
                       + ", ".join(runs.OPERATOR_SETTABLE_STATES))
        # WF-95: 404 rather than an unconditional ok. Three verbs on the
        # record screen write an operator's judgement onto a client's
        # permanent record through here, and until this line a fingerprint
        # with no row answered 200 having written nothing. `mark_attempt`
        # below has always done it this way for the same resource.
        if not runs.set_state(conn, site_id, fingerprint, body.state):
            raise HTTPException(status_code=404, detail="no such finding state")
        return {"ok": True}

    @app.post("/api/sites/{site_id}/states/{fingerprint}/attempt")
    def mark_attempt(site_id: str, fingerprint: str, body: AttemptIn,
                     conn=dep, operator=op_dep):
        """The fix loop's first half: record that a fix was attempted. The
        next run supplies the verdict — fixed, or still present despite it."""
        check_site(conn, operator, site_id)
        if not runs.mark_attempt(conn, site_id, fingerprint, body.note):
            raise HTTPException(status_code=404, detail="no such finding state")
        return {"ok": True}

    @app.delete("/api/sites/{site_id}/states/{fingerprint}/attempt")
    def clear_attempt(site_id: str, fingerprint: str,
                      conn=dep, operator=op_dep):
        """WF-84, the inverse of the route above. The fix loop's first half
        was write-once: `mark` posted only on the way on, and the button
        reading `clear these marks` reached nothing but browser memory, so a
        mark the operator had just cleared came back on the next load.

        404 on a fingerprint with no row, for the reason WF-95 gives one line
        up: a success this route did not verify is indistinguishable from one
        it did, and this one writes to a client's permanent record too.
        """
        check_site(conn, operator, site_id)
        if not runs.clear_attempt(conn, site_id, fingerprint):
            raise HTTPException(status_code=404, detail="no such finding state")
        return {"ok": True}

    @app.get("/api/overview")
    def overview(conn=dep, operator=op_dep):
        """Every site on one screen: score, movement, open work, freshness of
        the data behind it, and when the next unattended pass is owed.

        The schedule is here rather than on a settings page because "nothing
        is scheduled" is the single most useful thing this screen can say, and
        it was previously visible only as a column reading `manual` that never
        changed.
        """
        from datetime import datetime, timedelta

        from clauditseo.scheduler import CHECK_EVERY_S, INTERVALS

        now = datetime.now()
        out = []
        for client in repo.list_clients(conn, operator):
            for site in repo.list_sites(conn, client["id"]):
                # One row set per concept, because this screen needs both and
                # they disagree. The score and its delta are a comparison
                # between measurements, so they read scored runs only. The
                # last-run date drives "when is the next pass due", which has
                # to match `scheduler.due_sites` — and a blocked crawl is a
                # pass that happened. Sharing one query is what made Home
                # report a stale score, call the site Overdue, and promise an
                # unattended run the scheduler had already decided against.
                #
                # Both filter to `kind='audit'`. `mark_complete` writes a
                # composite onto every run that finishes, whatever it is, so
                # without this the newest narrow run supplied the card: a
                # one-page refresh (F-06) or a two-page verification became
                # "the site's score" and "the site's last run", and the
                # delta beside it compared a page against a site. The trend
                # has been guarded since `0011_run_kind.sql`; this reader was
                # not, and the difference was invisible while `verify` was
                # the only narrow kind and nothing looked.
                # And site-wide (brief v3 step I, WF-08): a one-page scan is
                # an audit by kind, and Home showed its 94.2 as the site.
                scored = conn.execute(
                    "SELECT composite_score, tier FROM audit_runs"
                    f" WHERE site_id=? AND {runs.status_in(runs.SCORED_STATUSES)}"
                    f" AND {runs.kind_is_site_reading()}"
                    f" AND {runs.scope_is_site_wide()}"
                    " ORDER BY started_at DESC, rowid DESC LIMIT 1",
                    (site["id"],)).fetchall()
                # The delta is against the previous audit of the SAME tier
                # (item 180, UI audit 01-3). Against whatever ran before, Home
                # read "up 63.03" for a T2 measured against a T3 that scored
                # 0.0 - a tier change and a broken reading, not an
                # improvement. A 0.0 is no baseline: no site-wide audit that
                # measured anything scores nothing.
                previous = (conn.execute(
                    "SELECT composite_score FROM audit_runs"
                    f" WHERE site_id=? AND {runs.status_in(runs.SCORED_STATUSES)}"
                    f" AND {runs.kind_is_site_reading()}"
                    f" AND {runs.scope_is_site_wide()}"
                    " AND tier=? AND composite_score > 0"
                    # OFFSET 1 skips the newest, which is in this list: it
                    # scored above 0 or this query is not reached.
                    " ORDER BY started_at DESC, rowid DESC LIMIT 1 OFFSET 1",
                    (site["id"], scored[0]["tier"])).fetchone()
                    if scored and scored[0]["composite_score"] else None)
                # What the newest scored reading was when it was not
                # site-wide, so Home can show a page or navigation scan as
                # what it is rather than as nothing.
                # Any scope (item 180, UI audit 01-2). This read
                # `kind_is_site_reading()`, which also requires a site-wide
                # scope since brief v6 step V2 - so it could never find the
                # narrow run it exists to find, and a site whose audits were
                # all page or nav scans read "never audited" on Home while its
                # own screen said "scored 72.77".
                site_kinds = ", ".join(f"'{k}'" for k in runs.SITE_READING_KINDS)
                newest = conn.execute(
                    "SELECT composite_score, scan_scope, crawled_paths, started_at FROM audit_runs"
                    f" WHERE site_id=? AND {runs.status_in(runs.SCORED_STATUSES)}"
                    f" AND kind IN ({site_kinds})"
                    " ORDER BY started_at DESC, rowid DESC LIMIT 1",
                    (site["id"],)).fetchone()
                narrow = (newest if newest and not scored
                          and not runs.is_site_wide(newest) else None)
                latest = conn.execute(
                    "SELECT id, composite_score, started_at, status FROM audit_runs"
                    f" WHERE site_id=? AND {runs.status_in(runs.AUDITED_STATUSES)}"
                    f" AND {runs.kind_is_site_reading()}"
                    " ORDER BY started_at DESC, rowid DESC LIMIT 1",
                    (site["id"],)).fetchall()
                # The standing's own count (item 180, ruling 20260918-0400):
                # coverage notes set aside, as the landing sets them aside.
                counts = {k: v["n"] for k, v in runs.standing_by_state(conn, site["id"]).items()}
                out.append({
                    "client": client["name"], "client_id": client["id"],
                    "site_id": site["id"], "domain": site["domain"],
                    # The profile every brief reasons from. It was settable
                    # only at creation and shown nowhere, so a site filed
                    # wrongly stayed wrong and the reports said so with
                    # confidence.
                    "business_type": site["business_type"],
                    "brand": site.get("brand"),
                    "schedule": site.get("schedule"),
                    "score": scored[0]["composite_score"] if scored else None,
                    "narrow_score": narrow["composite_score"] if narrow else None,
                    "narrow_scope": runs.scope_of(narrow) if narrow else None,
                    # When the narrow reading ran, for Home's order and its tag.
                    "narrow_at": narrow["started_at"] if narrow else None,
                    "delta": (round(scored[0]["composite_score"]
                                    - previous["composite_score"], 2)
                              if scored and previous is not None
                              and scored[0]["composite_score"]
                              and previous["composite_score"] is not None else None),
                    # What the delta is measured against, for the sentence.
                    "delta_tier": scored[0]["tier"] if scored and previous is not None else None,
                    # What the newest audit was, so a blocked crawl is not
                    # silently reported as the previous run's healthy score.
                    "last_run_status": latest[0]["status"] if latest else None,
                    "last_run_at": latest[0]["started_at"] if latest else None,
                    # So the home screen can link straight into the run an
                    # operator was last looking at, rather than a site page
                    # that then makes them choose again.
                    "last_run_id": latest[0]["id"] if latest else None,
                    # Open means outstanding, as on the landing: open and
                    # regressed. `regressed` stays its own field for the flag.
                    "open": counts.get("open", 0) + counts.get("regressed", 0),
                    "notes": counts.get("_notes", 0),
                    "regressed": counts.get("regressed", 0),
                    "candidate": counts.get("candidate", 0),
                    "watch": runs.watch_changes(conn, site["id"]),
                    **_next_pass(site.get("schedule"),
                                 latest[0]["started_at"] if latest else None,
                                 now, INTERVALS, timedelta),
                })
        return {"sites": out, "budget": _budget_status(conn, settings()),
                # So the screen can say how long an overdue site could stay
                # overdue without an operator wondering whether it is stuck.
                "checks_every_minutes": CHECK_EVERY_S // 60}

    # -- audits -------------------------------------------------------------

    @app.get("/api/sites/{site_id}/entity-suggestions")
    def entity_suggestions(site_id: str, conn=dep, operator=op_dep):
        """What the site's own schema says about `legal_name`,
        `registered_ids` and `external_profiles` (item 145 step BH).

        Read-only on purpose. Admin offers each one and the operator accepts
        it; nothing writes the record here, because a field filled from the
        markup it is later compared against makes `entity-unresolvable` and
        `entity-footprint-unlinked` agree with themselves.
        """
        if not repo.get_site(conn, site_id):
            raise HTTPException(status_code=404, detail="site not found")
        check_site(conn, operator, site_id)
        return runs.entity_record_suggestions(conn, site_id)

    @app.post("/api/sites/{site_id}/audits", status_code=202)
    def launch_audit(site_id: str, body: AuditIn, conn=dep, operator=op_dep):
        site_row = repo.get_site(conn, site_id)
        if not site_row:
            raise HTTPException(status_code=404, detail="site not found")
        check_site(conn, operator, site_id)
        dims = [d.upper() for d in body.dims]
        unknown = [d for d in dims if d not in registry.all_modules()]
        if unknown:
            raise HTTPException(status_code=422, detail=f"unknown dimensions: {unknown}")
        if body.tier not in ("auto", "T1", "T2", "T3"):
            raise HTTPException(status_code=422, detail="tier must be auto, T1, T2 or T3")
        if body.scope and body.scope not in SCOPES:
            raise HTTPException(
                status_code=422,
                detail=f"scope must be one of {sorted(SCOPES)}")
        if body.depth and body.depth not in DEPTHS:
            raise HTTPException(
                status_code=422,
                detail=f"depth must be one of {sorted(DEPTHS)}")
        # A named scope already decides the breadth, so `auto` has nothing left
        # to choose and the tier is reduced to its timeouts — which the scope
        # picks, because the operator should not have to know that a Full scan
        # under T2's fifteen-minute wall clock stops on time rather than on
        # pages. An explicitly named tier still wins.
        tier_name = body.tier
        if body.scope and tier_name == "auto":
            tier_name = tier_for_scope(body.scope).value
        if body.nav_only and tier_name == "auto":
            raise HTTPException(
                status_code=422,
                detail="nav_only needs a fixed tier: an adaptive run chooses its "
                       "own breadth, so the two would be deciding the same thing")

        if body.start_url:
            problem = _validate_start_url(body.start_url, site_row["domain"])
            if problem:
                raise HTTPException(status_code=422, detail=problem)

        # Derived once and used for both the recorded flag and the run
        # itself, so what the row claims about the run and what the run does
        # cannot disagree. `is None` rather than a falsy test: `false` is a
        # caller's answer, not the absence of one.
        depth = depth_settings(body.depth)
        # Precedence, stated once: an explicit `analyst` beats the depth's
        # implication, and the depth beats the tier's default. A caller that
        # asked for Deep and `analyst: false` meant the second, and silently
        # overriding it would run a model they declined.
        analyst = (body.analyst if body.analyst is not None
                   else depth.get("analyst") if depth
                   else tier_name == "auto")
        # The depth's model, resolved through the operator's own tier choices
        # rather than a constant: Admin exists so "deep" means whatever they
        # set it to, and a screen that hard-coded a model id would quietly
        # ignore that. An explicit `model` on the request still wins.
        model = body.model
        if model is None and depth.get("model_tier"):
            from clauditseo import tiers as _tiers
            picked = _tiers.settings_for(conn)
            model = {"fast": picked.llm_model_fast,
                     "standard": picked.llm_model,
                     "deep": picked.llm_model_deep}[depth["model_tier"]]
        # Adaptive runs record a placeholder tier and stamp the executed one.
        start_url = body.start_url or crawl_start_url(site_row["domain"])
        # One audit at a time per site. The brief route two thousand lines
        # below has refused a duplicate since KI-19 - "wait for it to finish
        # rather than paying for it twice" - and this, the dearer purchase,
        # accepted a second crawl unconditionally (audit F-03, 2026-09-02).
        # Decided by the stored status rather than an in-memory claim: a
        # crawl outlives a request, and the row is what says it is running.
        # By KIND alone, never by scope (WF-114). Brief v6 step V2 redefined
        # `kind_is_site_reading()` as "a site-reading kind whose scope is
        # site-wide" - correct for the readers asking which run may stand
        # FOR the site, wrong here, where the only question is whether a
        # crawl is already in flight. A nav-scoped audit stopped matching
        # and the refusal stopped firing, so the dearer purchase went back
        # to accepting a second concurrent crawl six weeks after KI-19.
        running = conn.execute(
            "SELECT id FROM audit_runs WHERE site_id=?"
            f" AND {runs.kind_in_site_reading_kinds()} AND status IN ('pending','running') LIMIT 1",
            (site_id,)).fetchone()
        if running:
            raise HTTPException(
                status_code=409,
                detail="an audit is already running against this site - wait "
                       "for it to finish rather than paying for it twice; its "
                       f"run is {running['id']}")
        run_id = runs.create_run(conn, site_id, dims,
                                 "T1" if tier_name == "auto" else tier_name,
                                 analyst_enabled=analyst,
                                 # Always written (brief v3 step I): the
                                 # chooser names its scope; the by-hand
                                 # launcher is a full crawl unless it asked
                                 # for the navigation set.
                                 scan_scope=body.scope
                                            or ("nav" if body.nav_only else "full"),
                                 scan_depth=body.depth,
                                 # Only a page scope is *about* one URL. On any
                                 # other scope this is the entry point, not the
                                 # subject, and storing it there would read as
                                 # "this run was about the homepage".
                                 scan_url=(start_url if body.scope == "page"
                                            else None))
        thread = threading.Thread(
            target=_execute_run,
            args=(path, run_id, site_row, dims, tier_name, analyst,
                  start_url, model, body.nav_only, body.scope),
            daemon=True)
        thread.start()
        return {"run_id": run_id, "status": "running"}

    @app.get("/api/sites/{site_id}/start-url-check")
    def check_start_url(site_id: str, url: str, conn=dep, operator=op_dep):
        """Would this start URL be accepted? Answered without starting
        anything (WF-82).

        `POST .../audits` above validates a start URL and then, if it passes,
        launches — so the only way to learn that a URL is acceptable was to
        buy the crawl that acceptance triggers. `OPERATOR_ACTIONS.md:139`
        records that happening: a trailing-dot control URL, posted to check
        whether CQ-121's `rstrip` had landed, was accepted, and the run it
        created is permanent because there is no route to delete a site's
        history (WF-81). A refusal was already free; it is the *yes* that
        cost a run, which is why this route exists rather than an earlier
        `raise` in the one above.

        It is a GET because it is one: no run row, no fetch, no provider, no
        cost entry, and nothing here touches the network. The answer is a
        judgement about the string and the site's recorded domain, which is
        all the launch route consults before it commits either.

        **The verdict comes from `_validate_start_url` itself, never from a
        second copy of the rule.** This file's history is doors disagreeing
        about what a host is — CQ-121 on the trailing dot, CQ-133 on an
        unparseable string being a readable 422 at one door and a 500 at four
        others — so a checker with its own opinion would be the next entry in
        that list rather than the end of it.
        """
        site_row = repo.get_site(conn, site_id)
        if not site_row:
            raise HTTPException(status_code=404, detail="site not found")
        check_site(conn, operator, site_id)
        # FastAPI already refuses an absent `url`; this is the empty one,
        # refused in the same words the three on-demand page routes use.
        if not url:
            raise HTTPException(status_code=422, detail="url is required")
        problem = _validate_start_url(url, site_row["domain"])
        return {"url": url, "acceptable": problem is None, "problem": problem}

    @app.post("/api/sites/{site_id}/import-crawl", status_code=201)
    async def import_crawl(site_id: str, request: Request, conn=dep,
                           operator=op_dep):
        """Accept a Screaming Frog internal export (raw CSV body). The
        import becomes a completed run with evidence and no score."""
        check_site(conn, operator, site_id)
        body = await request.body()
        if not body:
            raise HTTPException(status_code=422, detail="empty upload")
        from clauditseo.importers import import_crawl as do_import
        try:
            return do_import(conn, site_id,
                             body.decode("utf-8-sig", errors="replace"))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    # -- precheck -----------------------------------------------------------

    @app.post("/api/sites/{site_id}/precheck")
    def run_site_precheck(site_id: str, body: PrecheckIn, conn=dep, operator=op_dep):
        """Read robots, the sitemap and the entry page's navigation. One page.

        Synchronous, unlike `launch_audit`'s 202: this finishes in seconds and
        the caller has nothing to do until it does. POST rather than GET
        because it fetches a third party's server and writes a row — it must
        not be triggered by a link prefetch.
        """
        site_row = repo.get_site(conn, site_id)
        if not site_row:
            raise HTTPException(status_code=404, detail="site not found")
        check_site(conn, operator, site_id)

        if body.start_url:
            problem = _validate_start_url(body.start_url, site_row["domain"])
            if problem:
                raise HTTPException(status_code=422, detail=problem)

        import json as _json

        from clauditseo.persistence.repo import create_id
        from clauditseo.precheck import PrecheckError, run_precheck
        try:
            result = run_precheck(site_row["domain"], body.start_url)
        except PrecheckError as exc:
            # 502, not 500: the failure is the target site's, and the operator
            # needs to know it was not their install that broke.
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        payload = result.to_dict()
        with conn:
            conn.execute(
                "INSERT INTO prechecks (id, site_id, checked_at, entry_url,"
                " took_ms, sitemap_state, payload_json) VALUES (?,?,?,?,?,?,?)",
                (create_id(), site_id, result.checked_at, result.entry_url,
                 result.took_ms, result.sitemap_state, _json.dumps(payload)))
        return payload

    @app.get("/api/sites/{site_id}/record")
    def site_record_route(site_id: str, conn=dep, operator=op_dep):
        """The site record alone - domain, profile and the local-SEO fields
        the briefs read (brief v11 step AI) - for Admin > Sites, which
        edits many sites and needs none of the detail route's states,
        runs and trend."""
        site = repo.site_record(repo.get_site(conn, site_id))
        if not site:
            raise HTTPException(status_code=404, detail="site not found")
        check_site(conn, operator, site_id)
        # What the edge declaration may name, from the agent table, so the
        # screen keeps no copy of the list (item 145 BG).
        from clauditseo.crawler.ua_matrix import agent_class
        site["edge_agents"] = [{"agent": t, "class": agent_class(t)} for t in repo.edge_agents()]
        return site

    @app.get("/api/sites/{site_id}/precheck")
    def latest_site_precheck(site_id: str, conn=dep, operator=op_dep):
        """The newest precheck, or `null`.

        `null` is the scan screen's empty state, and it must stay reachable:
        the screen is required to offer `Run precheck` rather than fall back to
        an estimate, because a measured count is the entire point.
        """
        import json as _json
        check_site(conn, operator, site_id)
        row = conn.execute(
            "SELECT payload_json FROM prechecks WHERE site_id = ?"
            # `rowid` breaks the tie, and it is load-bearing rather than
            # decorative: `checked_at` is stamped to the second, so two
            # prechecks a moment apart carry the same value and ordering on it
            # alone returns either row. Insertion order is the only thing here
            # that is always true about which ran last.
            " ORDER BY checked_at DESC, rowid DESC LIMIT 1", (site_id,)).fetchone()
        return _json.loads(row["payload_json"]) if row else None

    @app.get("/api/sites/{site_id}/precheck/compare")
    def compare_site_precheck(site_id: str, conn=dep, operator=op_dep):
        """The newest precheck beside the one before it (brief v4 Item 2).

        `null` until a precheck has run. The prior is the previous check;
        the first check has none and is compared with the newest audit's
        `crawled_paths`, labelled `crawl`. "The next audit after the prior"
        is read off the run list here rather than written on the precheck
        row: it is a fact about two stamps, and a column would be a second
        place for it to be wrong.
        """
        import json as _json

        from clauditseo.precheck_compare import compare

        check_site(conn, operator, site_id)
        rows = conn.execute(
            "SELECT id, checked_at, payload_json FROM prechecks WHERE site_id = ?"
            " ORDER BY checked_at DESC, rowid DESC LIMIT 2", (site_id,)).fetchall()
        if not rows:
            return None
        now = _json.loads(rows[0]["payload_json"])
        audits = [r for r in runs.site_readings(conn, site_id)
                  if r["status"] in runs.SCORED_STATUSES]
        started = lambda r: r.get("started_at") or r["created_at"]  # noqa: E731
        if len(rows) > 1:
            prior = _json.loads(rows[1]["payload_json"])
            prior_at = rows[1]["checked_at"]
            after = [r for r in audits if started(r) > prior_at and started(r) <= now["checked_at"]]
            nxt = min(after, key=started) if after else None
            before = ({"id": nxt["id"], "started_at": started(nxt), "tier": nxt["tier"]}
                      if nxt else None)
            return compare(now, prior, prior_kind="precheck", prior_at=prior_at,
                           before_audit=before)
        crawled = [r for r in audits if r.get("crawled_paths")]
        if crawled:
            newest = max(crawled, key=started)
            try:
                paths = _json.loads(newest["crawled_paths"])
            except (TypeError, ValueError):
                paths = []
            return compare(now, None, prior_kind="crawl", prior_at=started(newest),
                           before_audit=None, audit_paths=paths)
        return compare(now, None, prior_kind=None, prior_at=None, before_audit=None)

    @app.post("/api/sites/{site_id}/notes", status_code=201)
    def add_note(site_id: str, body: AttemptIn, conn=dep, operator=op_dep):
        check_site(conn, operator, site_id)
        if not body.note.strip():
            raise HTTPException(status_code=422, detail="empty note")
        from clauditseo.persistence.repo import create_id, now_iso
        note_id = create_id()
        with conn:
            conn.execute("INSERT INTO notes (id, site_id, body, created_at)"
                         " VALUES (?, ?, ?, ?)",
                         (note_id, site_id, body.note.strip()[:2000], now_iso()))
        return {"id": note_id}

    @app.delete("/api/sites/{site_id}/notes/{note_id}")
    def delete_note(site_id: str, note_id: str, conn=dep, operator=op_dep):
        check_site(conn, operator, site_id)
        with conn:
            conn.execute("DELETE FROM notes WHERE id=? AND site_id=?",
                         (note_id, site_id))
        return {"ok": True}

    @app.get("/api/sites/{site_id}/dossier")
    def page_dossier(site_id: str, url: str, conn=dep, operator=op_dep):
        """One URL, everything known: crawl history, findings with their
        memory state, and the page-scoped briefs that read it."""
        check_site(conn, operator, site_id)
        dossier = runs.page_dossier(conn, site_id, url)
        if not dossier["seen"]:
            raise HTTPException(status_code=404,
                                detail="no run has ever seen this URL")
        return dossier

    @app.get("/api/sites/{site_id}/schedule")
    def get_schedule(site_id: str, conn=dep, operator=op_dep):
        """What runs unattended for this site: the whole-site audit cadence,
        and any briefs scheduled individually."""
        from clauditseo.analysts.expert import EXPERT_TOOLS
        from clauditseo.scheduler import TOOL_INTERVALS, due_tools

        check_site(conn, operator, site_id)
        site = repo.get_site(conn, site_id)
        rows = conn.execute(
            "SELECT tool_id, cadence, last_run_at FROM tool_schedules"
            " WHERE site_id=? ORDER BY tool_id", (site_id,)).fetchall()
        owed = {j["tool_id"] for j in due_tools(conn, _dt.now())
                if j["site_id"] == site_id}
        # Scoped to this site (UX-77). The copy beside the table says the
        # price is "what that brief has actually cost here before - not an
        # estimate", and until Q-1 was answered the figure under it was a
        # median across every site in the install, fixture sites included
        # (KI-50). The operator answered **per site** on 22 August 2026;
        # this argument is that answer.
        estimates = runs.expert_estimates(conn, site_id=site_id)
        return {
            "audit_cadence": site["schedule"],
            "audit_cadences": ["weekly", "monthly"],
            "tool_cadences": list(TOOL_INTERVALS),
            "tools": [{"tool_id": r["tool_id"], "cadence": r["cadence"],
                       "last_run_at": r["last_run_at"],
                       "due_now": r["tool_id"] in owed} for r in rows],
            # Every brief that could be scheduled, with what it has cost
            # before — a cadence chosen without a price is a guess.
            "available": [
                # The estimate's frame travels with it (UX-74). This
                # endpoint re-serialises `expert_estimates` field by field, so
                # a scope added upstream is dropped here unless it is carried
                # deliberately — the shape that lost the TLS floor between the
                # probe that measured it and the panel that needed it (B-11).
                # The modal multiplies this price by a cadence into an annual
                # forecast, so the scope is what makes that forecast readable.
                {"tool_id": t,
                 "typical_cost": (estimates.get(t) or {}).get("cost"),
                 "typical_tokens": (estimates.get(t) or {}).get("tokens"),
                 "cost_samples": (estimates.get(t) or {}).get("cost_samples", 0),
                 "samples": (estimates.get(t) or {}).get("samples", 0),
                 # What the token figure was computed against, carried rather
                 # than dropped (CQ-169). This endpoint passes no `pages`, so
                 # the answer here is always `None` — a flat median, not a
                 # figure scaled to a crawl. That is a statement the payload
                 # has to make: the same key is non-null on the three surfaces
                 # that do pass `pages`, and a modal multiplying this price by
                 # a cadence cannot tell the two apart without it.
                 "scaled_to_pages": (estimates.get(t) or {}).get(
                     "scaled_to_pages"),
                 # Which population the price was drawn from, carried for the
                 # same reason `cost_samples` and `scaled_to_pages` are: this
                 # endpoint re-serialises the estimator field by field, so the
                 # scope is dropped here unless it is named. `None` would mean
                 # install-wide, which after UX-77 this endpoint never sends -
                 # and a reader can now tell the two apart rather than
                 # inferring it from the route.
                 "scoped_to_site": (estimates.get(t) or {}).get(
                     "scoped_to_site", site_id)}
                for t in sorted(EXPERT_TOOLS)],
        }

    @app.put("/api/sites/{site_id}/schedule")
    def put_schedule(site_id: str, body: ScheduleIn, conn=dep, operator=op_dep):
        """Replace the schedule wholesale. The modal always sends the full
        picture, so a tool absent from the payload is one the operator
        removed — merging would make deletion impossible."""
        from clauditseo.analysts.expert import EXPERT_TOOLS
        from clauditseo.scheduler import INTERVALS, TOOL_INTERVALS

        check_site(conn, operator, site_id)
        if body.audit_cadence not in (None, *INTERVALS):
            raise HTTPException(status_code=422,
                                detail=f"audit cadence must be one of {list(INTERVALS)}")
        for entry in body.tools:
            if entry.cadence not in TOOL_INTERVALS:
                raise HTTPException(
                    status_code=422,
                    detail=f"{entry.tool_id}: cadence must be one of "
                           f"{list(TOOL_INTERVALS)}")
            if entry.tool_id not in EXPERT_TOOLS:
                raise HTTPException(status_code=422,
                                    detail=f"unknown brief: {entry.tool_id}")
        with conn:
            conn.execute("UPDATE sites SET schedule=? WHERE id=?",
                         (body.audit_cadence, site_id))
            keep = {e.tool_id for e in body.tools}
            conn.execute(
                "DELETE FROM tool_schedules WHERE site_id=?"
                + (f" AND tool_id NOT IN ({','.join('?' * len(keep))})" if keep else ""),
                (site_id, *sorted(keep)))
            for entry in body.tools:
                # Preserve last_run_at on an unchanged row so editing one
                # tool's cadence does not reset every other tool's clock.
                conn.execute(
                    "INSERT INTO tool_schedules (site_id, tool_id, cadence)"
                    " VALUES (?, ?, ?)"
                    " ON CONFLICT(site_id, tool_id) DO UPDATE SET cadence=excluded.cadence",
                    (site_id, entry.tool_id, entry.cadence))
        return get_schedule(site_id, conn=conn, operator=operator)

    @app.post("/api/sites/{site_id}/verify")
    def verify_findings(site_id: str, body: VerifyIn, conn=dep, operator=op_dep):
        """Re-crawl only the pages behind these findings, and report what
        actually changed.

        Synchronous on purpose: it fetches a handful of pages and spends no
        model tokens, so waiting a few seconds for the answer beats a
        background job the operator has to come back to. A verification that
        finished silently would leave the same question it was run to settle.

        "A handful" is now enforced rather than assumed. It sized its crawl
        off the untruncated `affected_urls` of every marked finding with no
        ceiling, so one tick on a site-wide finding was one several-hundred-
        page blocking request; `runs.VERIFY_PAGE_CAP` is the ceiling and the
        refusal below is what the operator gets instead.

        It creates a run because the state machine is driven by runs — but a
        run marked `verify`, so a composite computed over two pages never
        reaches the trend, the score, or the run-to-run watch.
        """
        site_row = repo.get_site(conn, site_id)
        if not site_row:
            raise HTTPException(status_code=404, detail="site not found")
        check_site(conn, operator, site_id)

        target = runs.pages_for_findings(conn, site_id, body.fingerprints)
        if not target["found"]:
            raise HTTPException(status_code=404, detail="no such findings")
        if not target["urls"]:
            raise HTTPException(
                status_code=422,
                detail="these findings name no page to re-fetch — they are "
                       "site-level, and are judged by a full audit")
        if not target["dimensions"]:
            raise HTTPException(
                status_code=422,
                detail="these came from an expert analysis, which is verified by "
                       "running the analysis again rather than by a crawl")
        # Above `create_run`, with the other three, and that placement is the
        # finding rather than a tidiness preference: a refusal that has already
        # created the run has already committed to the crawl it exists to
        # decline, and leaves a row on the site's history for a pass nobody
        # made.
        if len(target["urls"]) > runs.VERIFY_PAGE_CAP:
            raise HTTPException(
                status_code=422,
                detail=f"these findings cover {len(target['urls'])} pages and "
                       f"a verification re-crawls at most "
                       f"{runs.VERIFY_PAGE_CAP} while you wait — untick some, "
                       f"or run a full audit, which runs in the background and "
                       f"reports its progress")

        cfg = settings()
        from clauditseo.crawler.types import TIER_BUDGETS
        budget = TIER_BUDGETS[Tier.T2]
        run_id = runs.create_run(conn, site_id, target["dimensions"], "T2",
                                 created_by=operator["id"] if operator else None,
                                 kind="verify")
        try:
            crawled = crawl_site(
                crawl_start_url(site_row["domain"]), Tier.T2,
                budget=dataclasses.replace(budget,
                                           max_pages=max(len(target["urls"]), 1)),
                only_urls=target["urls"])
            traced, trace_rule = _narrow_trace(crawled, run_id,
                                               target["dimensions"])
            result = run_audit(
                site_of(repo.site_record(site_row)),
                crawled, target["dimensions"], Tier.T2,
                # The contract's `PRIOR_RUN` (item 136k), and what it
                # recorded. Supplied here because a module is handed one
                # crawl and this is where the database is; `CNT/stale` asks
                # whether the page is old AND untouched, and only the caller
                # holds the second answer (operator, 2026-09-06).
                #
                # Item 136p: the hashes come from `PRIOR_RUN` and no longer
                # from a second, private notion of "the previous run".
                context={"providers": ProviderHub.from_settings(cfg),
                         "prior_run": (_prior := runs.prior_run(
                             conn, site_row["id"], run_id)),
                         "prior_pages": runs.content_hashes(
                             conn, (_prior or {}).get("run_id")),
                         # The previous run's sitemap size, for the sweep's
                         # `sitemap-regression` (brief v18 step AZ). Same
                         # caller-holds-the-baseline shape as `prior_pages`;
                         # None where there is no prior run, and the check
                         # stays silent rather than green.
                         "prior_sitemap": runs.prior_sitemap(
                             conn, (_prior or {}).get("run_id")),
                         "perf_traces": traced,
                         # So the rendered pass can file its screenshots
                         # under the run that took them (136j Part B).
                         "run_id": run_id})
            from clauditseo.crawler.evidence import snapshot
            runs.store_evidence(conn, run_id,
                                snapshot(crawled, None, traced, trace_rule))
            runs.complete_run(conn, run_id, result)
        except Exception as exc:                      # noqa: BLE001
            runs.fail_run(conn, run_id, str(exc))
            raise HTTPException(status_code=502,
                                detail=f"verification crawl failed: {exc}") from exc

        # WF-69. The same set `_apply_states` cleared from, handed to the
        # function that reports what was decided — not re-derived from
        # `target["urls"]`, which is what was ASKED for. A 503 leaves a page
        # in that list and out of `crawled_paths`, and the difference between
        # the two is the whole finding.
        # WF-100. `seen` is the same derivation `_apply_states` drove the
        # state machine from, taken from one owner rather than re-approximated
        # here — the row bookkeeping this used to read (`changed_by_run`)
        # records a transition, and a finding that was already `fixed` and was
        # re-found takes no transition at all.
        outcomes = runs.verify_outcomes(
            conn, site_id, target["found"], run_id,
            crawled=getattr(result, "crawled_paths", None) or frozenset(),
            seen=runs.emitted_fingerprints(result),
            traced=getattr(result, "traced_paths", None) or frozenset(),
            imaged=getattr(result, "imaged_paths", None) or frozenset())
        cleared = sum(1 for o in outcomes if o["cleared"])
        # Three outcomes. A narrow run may not judge a finding that names no
        # page — `_apply_states` skips it — so counting it into
        # `still_present` told the operator "the page was fetched and the
        # finding was still on it" about a check the run declined to make.
        # WF-63/WF-66, report 053. The set is accepted rather than refused
        # (the 422 above fires only when NO fingerprint names a page), so the
        # count has to carry the distinction the crawl already made.
        # Counted from the word each outcome carries rather than derived a
        # second time here. `still_present` was a subtraction — `len(outcomes)
        # - cleared - not_decided` — and a subtraction has no way to be wrong
        # about one finding without being wrong about the total, which is how
        # WF-100 stayed invisible for as long as it did.
        tally = collections.Counter(o["outcome"] for o in outcomes)
        not_decided = tally["not_checked"]
        from clauditseo.crawler.types import eligible
        return {
            # `pages` is what was read, not what was tried. Both are returned
            # because a caller deciding "did this verification settle
            # anything" needs the first, and one diagnosing why it settled
            # nothing needs the difference.
            "run_id": run_id, "pages": len(eligible(crawled.pages)),
            "pages_attempted": len(crawled.pages),
            "dimensions": target["dimensions"],
            "cleared": cleared,
            "still_present": tally["still_present"],
            # Four words. `unchanged` is "asked about, page read, not
            # re-raised, and it was already fixed before this run" — a real
            # answer that was previously counted as still present.
            "unchanged": tally["unchanged"],
            "not_decided": not_decided,
            "outcomes": outcomes,
        }

    @app.post("/api/sites/{site_id}/refresh")
    def refresh_section(site_id: str, body: RefreshIn, conn=dep, operator=op_dep):
        """Re-measure one page for the dimension that covers one section.

        `FEATURES.md` F-06, and the engine could always be asked for it: the
        verify path above already narrows a crawl with `only_urls` and a run
        with a dimension list, and `AuditModule.run` takes an arbitrary page
        set. What was missing was an entry point and **the rules about what a
        narrow run may claim**, which are the substance of this handler:

        - **A third run kind.** `kind='refresh'`, beside `audit` and
          `verify`. Everything that scores, trends or compares already
          filters to `kind='audit'` (`0011_run_kind.sql`), so those guards
          cover this kind by construction rather than by a list that has to
          be extended.
        - **What it may score: nothing.** One page over one dimension
          measures a different population from the audit it refreshes, and
          the comparability key is
          `(engine_version, scope.basis, tier, scope.dimensions)`.
          `complete_run` writes a snapshot only for an audit, so no composite
          and no `measured_share` reaches the trend. The absence is the
          feature, not a gap to be filled "for completeness".
        - **What it may close: only what it revisited.** The page rule in
          `_apply_states` already refuses to clear a page-scoped finding
          whose page was not fetched — the rule whose `and crawled` once let
          an empty crawl clear a whole site. A refresh inherits it untouched
          and adds one: it may not clear a *site-scoped* finding either,
          because one page is not a reading of the site.
        - **Its tier is inherited, not chosen.** The audit being refreshed
          decides it, and it is recorded on the run. A T2 refresh laid over a
          T3 audit would reintroduce through this endpoint the defect WF-56
          closed at the launcher: two different populations of pages, scored
          as one series.

        **"Section" is the UI's framing; the engine's unit is `(url, dims)`.**
        A refresh of Headings runs ONP against the page, and ONP also emits
        for Title & description, Images, Structured data and Indexability —
        and all of it is recorded. Filtering the module's output down to the
        section would make a finding that was suppressed indistinguishable
        from a finding that no longer fires, which is precisely the
        distinction the resolution rule turns on. The honest control says
        what else refreshed; it does not pretend less happened.

        Synchronous for the verify path's reason: one page, no analyst, a few
        seconds — a background job the operator has to come back to would
        leave the question they ran it to settle still open.
        """
        from clauditseo import anatomy as anat

        site_row = repo.get_site(conn, site_id)
        if not site_row:
            raise HTTPException(status_code=404, detail="site not found")
        check_site(conn, operator, site_id)

        if body.section not in anat.BY_KEY:
            raise HTTPException(status_code=422,
                                detail=f"unknown section {body.section!r}")
        offer = anat.refresh_for(body.section)
        if not offer:
            raise HTTPException(
                status_code=422,
                detail=f"no automatic check refreshes {anat.BY_KEY[body.section].label} — "
                       "it is filled by an expert analysis, which is refreshed "
                       "by running that analysis again")
        # UX-39: refused here and not only left unoffered by the screen. The
        # screen is one caller; a route that will crawl a page and call a
        # provider for a dimension it knows no page can move is the defect
        # itself, and hiding the button leaves it payable by anything that
        # posts. Measured before the refusal existed: this returned 200 with
        # `recorded: 1, cleared: 0` for `backlinks`, having bought a crawl.
        if not offer["per_page"]:
            raise HTTPException(
                status_code=422,
                detail=f"{anat.BY_KEY[body.section].label} is not measured "
                       f"page by page — {offer['dimension']} reads the domain "
                       "rather than any page of it, so re-reading one page "
                       "cannot change it. Re-run "
                       f"{offer['dimension']} for the site instead")
        if not _host_matches_site(urlsplit(body.url).hostname or "",
                                  site_row["domain"]):
            # CQ-98. The message used to read "a refresh re-reads a page the
            # audit already crawled", which is a check this route does not
            # make — it compares hosts and never asks whether any run fetched
            # this URL. An operator correcting a refusal has to be told what
            # was actually compared, so it names the two hosts.
            raise HTTPException(
                status_code=422,
                detail=f"{body.url!r} is not a page of this site — its host "
                       f"{urlsplit(body.url).hostname or ''!r} is not "
                       f"{_comparable_host(site_host(site_row['domain']))!r} "
                       "or a subdomain of it")

        # The tier is the refreshed audit's, read from the run rather than
        # chosen here. `AUDITED_STATUSES` and `kind='audit'` are the same
        # pair the anatomy screen uses to decide which run it is showing, so
        # the tier inherited is the tier of the run whose findings are on
        # screen. Adaptive runs stamp the tier they executed at
        # (`runs.set_tier`), so this reads what actually ran.
        prior = conn.execute(
            "SELECT id, tier FROM audit_runs WHERE site_id=?"
            f" AND {runs.status_in(runs.AUDITED_STATUSES)}"
            f" AND {runs.kind_is_site_reading()}"
            " ORDER BY started_at DESC, rowid DESC LIMIT 1",
            (site_id,)).fetchone()
        if not prior:
            raise HTTPException(
                status_code=422,
                detail="this site has no audit to refresh from — a refresh "
                       "re-measures one page of an audit, and the first run "
                       "is a full one")
        try:
            tier = Tier(prior["tier"])
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"the last audit recorded tier {prior['tier']!r}, which "
                       "is not a tier this engine can run") from None

        cfg = settings()
        from clauditseo.crawler.types import TIER_BUDGETS
        dim = offer["dimension"]
        run_id = runs.create_run(conn, site_id, [dim], tier.value,
                                 created_by=operator["id"] if operator else None,
                                 kind="refresh")
        try:
            crawled = crawl_site(
                crawl_start_url(site_row["domain"]), tier,
                budget=dataclasses.replace(TIER_BUDGETS[tier], max_pages=1),
                only_urls=[body.url])
            traced, trace_rule = _narrow_trace(crawled, run_id, [dim])
            result = run_audit(
                site_of(repo.site_record(site_row)),
                crawled, [dim], tier,
                # The contract's `PRIOR_RUN` (item 136k), and what it
                # recorded. Supplied here because a module is handed one
                # crawl and this is where the database is; `CNT/stale` asks
                # whether the page is old AND untouched, and only the caller
                # holds the second answer (operator, 2026-09-06).
                #
                # Item 136p: the hashes come from `PRIOR_RUN` and no longer
                # from a second, private notion of "the previous run".
                context={"providers": ProviderHub.from_settings(cfg),
                         "prior_run": (_prior := runs.prior_run(
                             conn, site_row["id"], run_id)),
                         "prior_pages": runs.content_hashes(
                             conn, (_prior or {}).get("run_id")),
                         # The previous run's sitemap size, for the sweep's
                         # `sitemap-regression` (brief v18 step AZ). Same
                         # caller-holds-the-baseline shape as `prior_pages`;
                         # None where there is no prior run, and the check
                         # stays silent rather than green.
                         "prior_sitemap": runs.prior_sitemap(
                             conn, (_prior or {}).get("run_id")),
                         "perf_traces": traced,
                         # So the rendered pass can file its screenshots
                         # under the run that took them (136j Part B).
                         "run_id": run_id})
            from clauditseo.crawler.evidence import snapshot
            runs.store_evidence(conn, run_id,
                                snapshot(crawled, None, traced, trace_rule))
            runs.complete_run(conn, run_id, result)
        except Exception as exc:                      # noqa: BLE001
            runs.fail_run(conn, run_id, str(exc))
            raise HTTPException(status_code=502,
                                detail=f"refresh crawl failed: {exc}") from exc

        moved = {r["state"]: r["n"] for r in conn.execute(
            "SELECT state, COUNT(*) n FROM finding_states"
            " WHERE site_id=? AND changed_by_run=? GROUP BY state",
            (site_id, run_id))}
        from clauditseo.crawler.types import eligible
        return {
            "run_id": run_id, "url": body.url, "section": body.section,
            "dimension": dim, "tier": tier.value,
            # What else moved, from the same table the offer was built from.
            # The control said this before the click; the answer repeats it
            # rather than leaving the operator to remember.
            "also": offer["also"],
            # Read, not attempted — the same distinction the verify path
            # draws, for the same diagnostic reason.
            "pages": len(eligible(crawled.pages)),
            "pages_attempted": len(crawled.pages),
            "recorded": len(result.findings),
            "cleared": moved.get("fixed", 0),
            "regressed": moved.get("regressed", 0),
            "opened": moved.get("open", 0),
            # Stated rather than left to be inferred from a missing key: a
            # narrow run measures a different population, so it has no
            # composite to contribute and the site's trend does not move.
            "scored": False,
        }

    @app.get("/api/sites/{site_id}/reports")
    def site_reports(site_id: str, conn=dep, operator=op_dep):
        """Every brief produced for this site, across every run, with what it
        cost. The deliverables were reachable one run at a time and nothing
        totalled them."""
        check_site(conn, operator, site_id)
        return runs.site_reports(conn, site_id)

    @app.get("/api/sites/{site_id}/anatomy")
    def site_anatomy_response(site_id: str, page: str | None = None, conn=dep,
                              operator=op_dep):
        """The anatomy payload, assembled and sent the fast way.

        Two costs removed without touching what is built, both measured on
        twenty22. Every payload below read the run's 1.8 MB evidence for
        itself; inside `one_evidence_read` the database is asked once. And the
        view is JSON-native already - dicts, lists, strings, numbers - so
        FastAPI's `jsonable_encoder`, which walked all 22,000 of its values to
        convert nothing, is skipped: `JSONResponse` is what the default path
        renders with after that walk, so the bytes are the same.
        """
        from fastapi.responses import JSONResponse
        with runs.one_evidence_read(conn):
            view = site_anatomy(site_id, page, conn, operator)
        return JSONResponse(view)

    def site_anatomy(site_id: str, page: str | None,
                     conn, operator):
        """Open work sorted by how a page is built, rather than by the
        dimension that raised it. A re-sort of the same finding states the
        rest of the app counts, so the categories sum to the same total."""
        check_site(conn, operator, site_id)
        from clauditseo import analyses as an
        from clauditseo import anatomy as anat
        from clauditseo.analysts.expert import EXPERT_TOOLS
        from clauditseo.modules.onp import GUIDELINES

        view = runs.anatomy_view(conn, site_id, page)

        # Whether anything has read each category, and what could. A count
        # says how much is wrong; this says whether anyone has looked — and
        # "99 images nobody has analysed" is a different situation from "99
        # images a specialist has already been through".
        # Item 239 step 4 (amendment 10): the newest run of each tool on this
        # site, from the Latest View - the rule the rows beneath the pills
        # already read - and not the picked audit's. Each pill carries the
        # run its report is on, so none opens to a 404.
        # Item 239 step 5: the header's audit picker is retired, and a run
        # named in the address is ignored here - the site screen is the
        # current view. What still reads one audit (the header's headline,
        # populations and not-assessed lines, until step 6) reads the newest
        # reading of the site. A run's own record is the Audits tab's
        # history view, which reads the run itself.
        latest = conn.execute(
            f"SELECT id FROM audit_runs WHERE site_id=?"
            f" AND {runs.status_in(runs.AUDITED_STATUSES)}"
            f" AND {runs.kind_is_site_reading()}"
            " ORDER BY started_at DESC, rowid DESC LIMIT 1",
            (site_id,)).fetchone()
        status = an.tool_status()
        from clauditseo.persistence import latest_view as _lvs
        # The header's plain text (item 239 step 5, amendment 8): the current
        # audit's score, tier and date, from the Latest View's composite.
        view["current_audit"] = _lvs._get(conn, site_id, "composite", "current")
        newest = _lvs.analyses(conn, site_id)
        running = _in_flight_for_site(conn, site_id)
        for cat in view["categories"]:
            covers = [t for t in cat["tools"] if t in EXPERT_TOOLS]
            ran = [t for t in covers if t in newest]
            cat["analysed_by"] = sorted(ran)
            cat["analysed"] = [
                {"tool": t, "run_id": newest[t]["run_id"], "at": newest[t].get("at"),
                 "crawl_at": newest[t].get("crawl_at"),
                 "audits_since": runs._audits_since(conn, site_id, newest[t]["run_id"])}
                for t in sorted(ran)]
            cat["analysing"] = sorted(t for t in covers if t in running)
            # Only what can actually be started: a sweep runs as part of every
            # audit and has no endpoint, and offering it produced a red
            # "unknown tool" once already.
            cat["can_run"] = sorted(t for t in covers
                                    if t not in ran and t not in running)
            # What is left over, and what kind of thing it is.
            #
            # The section used to end with an "Investigate" row of every tool
            # in its catalogue entry, rendered as links to the tools screen.
            # Most were already above it as a read or a run pill — the same
            # tool, a third control, a different verb — and the rest had no
            # endpoint at all, so following one led to a screen that could
            # not run it either. Classified here so the UI never has to guess
            # which kind it is holding.
            shown = set(cat["analysed_by"]) | set(cat["analysing"])                 | set(cat["can_run"])
            cat["investigate"] = [
                {"tool": t,
                 # "page":    its own endpoint, one page at a time, spends.
                 # "planned": in the catalogue, not built.
                 # "needs_key": built, but dark without a provider key.
                 # "sweep":   ran inside the audit; there is nothing to start.
                 # Item 238: a tool the playbook has no status for is not
                 # a sweep - "runs in every audit" was said of tools that
                 # were never built.
                 "action": ("page" if t in anat.PAGE_PANELS
                            else status.get(t) if status.get(t) in
                            ("planned", "needs_key")
                            else "planned" if status.get(t) is None
                            else "sweep")}
                for t in cat["tools"] if t not in shown]
        # How deep the crawl had to go, on the part whose subject is
        # reachability (brief v16b). Attached here rather than inside
        # `anatomy_view` for the reason the item states: it is "for the audit
        # the pane is reading", and the picker's run is resolved at this point
        # and not at that one. One part carries it - a histogram of clicks
        # from the home page is not a shape Images or Headings could draw.
        # Item 239 step 2: every crawl-relative block reads its reference
        # crawl from the Latest View - the newest reading of the whole site
        # that measured it, with the instrument it needs - and not the run
        # the picker holds. Twenty22's picked run was an ONP-only T2 that
        # weighed no images: the Images chart read it and drew nothing.
        from clauditseo.persistence import latest_view as _lv
        ref = {k: _lv.reference_run(conn, site_id, k)
               for k in ("TEC", "ONP", "A11Y", "CNT", "SEC", "images", "trace")}
        depth = runs.crawl_depth_payload(conn, ref["TEC"])
        # The Crawl part's site-level "now" (brief v18 step AZ): the four
        # counts, their venn, and the UA matrix when the run captured one.
        # Beside depth and for the same reason — the picker's run is resolved
        # here, not inside `anatomy_view`.
        crawl_now = runs.crawl_now_payload(conn, ref["TEC"])
        # The Indexability part's "now" (brief v18 step BA): the canonical map
        # and the headline counts, beside the crawl block and for the same
        # reason.
        idx_now = runs.indexability_now_payload(conn, ref["TEC"])
        # The URLs & parameters part's "now" (brief v19 step BB): the four-count
        # strip, the convention, and the pattern table and parameter inventory.
        urls_now = runs.urls_now_payload(conn, ref["TEC"])
        # The Speed part's site-level "now" (brief v19 step BC): the
        # per-template vitals strip and the five pictures beneath it, read back
        # off the performance traces the browser pass stored. Beside the other
        # three and for the same reason — the picker's run is resolved here.
        # The instrument's block, else the newest reading that could have
        # used it, so a site nothing has traced says so rather than showing
        # nothing (`latest_view.reference_run`).
        speed_run = _lv.reference_run(conn, site_id, "trace", "PRF", "TEC")
        speed_now = runs.speed_now_payload(conn, speed_run)
        # The three headline numbers, each with its denominator (brief v23 step
        # BJ): what was audited, how much of the site that was (coverage over
        # site size), how much has been through (assessed). Site-scoped, so
        # it sits on the view, not a category; resolved to the picker's run here.
        view["headline"] = runs.headline_numbers(conn, latest["id"] if latest else None)
        # The three populations a count may be counted over, and the page's own
        # scope (item 155). Beside the headline and for the same reason: the
        # crawl population is the picker's run, which is resolved here and not
        # inside `anatomy_view`. Prevalence is affected of assessed, so the
        # crawl's own path set travels with its size — the numerator has to be
        # intersected with it or a record accumulated across runs reports more
        # affected pages than the run fetched.
        view["populations"] = runs.populations_payload(
            conn, latest["id"] if latest else None,
            record_pages=len(view["pages"]), page_url=view.get("page"))
        # Item 157. THE RULE is stated in `playbook.py`: a check may be reported
        # as passing only if the run measured it; absence of a finding is not a
        # pass. Two fields carry the answer for this view, from two different
        # kinds of fact, and keeping them apart is the point:
        #
        # `not_assessed` is HISTORICAL, read from the run's own dimension list
        # and stored evidence. Those checks are unmeasured on that run forever.
        # The config is deliberately not consulted: deriving it from what is
        # installed today would let tomorrow's `pip install clauditseo[render]`
        # silently rewrite what a June run claims to have measured, which is the
        # same class of lie this item exists to fix (channel 20260912-0940).
        #
        # `unclaimed_checks` is STATIC - which of a part's checks no playbook
        # tool names at all (53 across the briefs). Declared rather than left to
        # absence, because a check missing from the gating map must not read as
        # "gated and live".
        #
        # The join's third state, `dark`, is NOT read here. It answers "can this
        # fire on this install now", which is the workbench's question and is
        # config-derived; on a stored run it would carry the same rewriting
        # problem as above. Same vocabulary, two call sites, different inputs.
        checks_by_part = {c["key"]: c.get("brief_checks") or []
                          for c in view["categories"]}
        not_assessed = runs.not_assessed_payload(
            conn, latest["id"] if latest else None,
            checks_by_part=checks_by_part)
        # Imported under another name on purpose: this module has a route
        # function called `playbook` (the /api/playbook handler), so the bare
        # name here would be that function, not the module.
        from clauditseo import playbook as _playbook
        # One read of the settings for every part: `settings()` re-reads the
        # environment and the secrets file on each call, eighteen times here.
        _cfg = settings()
        gating = {part: _playbook.gating_for(checks, _cfg)
                  for part, checks in checks_by_part.items()}
        # Item 148 G6: why a gated brief was NOT dispatched, derived on read from
        # the run's own evidence. Nothing stores a refusal and nothing needs to --
        # the gate is a pure function of that evidence, so reading it again
        # cannot go stale, where a stored copy could disagree with a later fix
        # to the gate. `na` is settled; `not_assessed` is not (brief 160 step 6).
        gate_state = None
        if latest:
            from clauditseo.analysts.expert import ABSENT as _ABSENT
            from clauditseo.analysts.expert import _hreflang_applies
            _raw = runs.evidence_text(conn, latest["id"])
            if _raw:
                # Narrow on purpose. This block was `except Exception` first,
                # with `json` never imported at module level in this file, so
                # `json.loads` raised NameError, the handler swallowed it, and
                # the gate read None on every site. On a multi-locale site None
                # is also the RIGHT answer, which is why a live check could not
                # see it was broken. Only malformed stored evidence is
                # tolerated; a programming error must surface.
                try:
                    _ev = runs.parsed_evidence(_raw)
                except (TypeError, ValueError):
                    _ev = None
                # Evidence stored without a start URL cannot be gated: the
                # locale read is relative to it. Such evidence exists (older
                # rows and the test fixtures), and indexing it unguarded took
                # the whole anatomy payload down with a KeyError, not just the
                # gate. No gate is the honest answer there.
                if isinstance(_ev, dict) and _ev.get("start_url"):
                    _refusal = _hreflang_applies(_ev, {"TARGET_LOCALES": _ABSENT})
                    if isinstance(_refusal, dict):
                        gate_state = {"state": _refusal.get("state"),
                                      "reason": _refusal.get("reason") or ""}
        # Which of each part's checks were measured only on TRACED pages, and
        # how many pages that is (item 155, brief 160). A clean line that lumps
        # them with the parse checks under "every page this run fetched (45
        # crawled)" states a denominator they were never measured over: on
        # twenty22 four of Mobile's ten clean checks had been read on 12 traced
        # pages. The population stays the crawl; only the word and the number
        # move, which is what `count()`'s basis override exists for.
        from clauditseo.modules import prf as _prf_mod
        from clauditseo.modules import tec as _tec_mod
        _trace_bare = _prf_mod.TRACE_DERIVED_CHECKS | _tec_mod.TRACE_DERIVED_CHECKS
        traced_pages = None
        # Whether the page in scope was itself traced. None with no page in
        # scope, or where the stored evidence does not list it.
        page_traced = None
        if latest:
            _raw = runs.evidence_text(conn, latest["id"])
            if _raw:
                try:
                    _pgs = (runs.parsed_evidence(_raw).get("pages") or [])
                except (TypeError, ValueError):
                    _pgs = []
                def _was_traced(_p):
                    return (isinstance(_p.get("perf"), dict)
                            and _p["perf"].get("traced") is not False
                            and bool(_p["perf"].get("device_profile")))
                traced_pages = sum(1 for _p in _pgs if _was_traced(_p))
                if page:
                    _hit = next((_p for _p in _pgs if _p.get("url") == page), None)
                    if _hit is not None:
                        page_traced = _was_traced(_hit)
        for cat in view["categories"]:
            cat["trace_derived"] = [c for c in (cat.get("brief_checks") or [])
                                    if c.split("/")[-1] in _trace_bare]
            cat["traced_pages"] = traced_pages
            cat["not_assessed"] = dict(not_assessed.get(cat["key"], {}))
            if cat["key"] == "security":
                # The layer cards (143 addendum): each domain's layer and
                # checks, from the one constant the sweep's checks are filed by.
                from clauditseo.modules.sec import DOMAINS as _sec_domains
                cat["sec_domains"] = _sec_domains
            # Page mode (brief v23 step BK) and item 157 together. Rung 2
            # is RUN-level: a run that traced any page leaves the trace
            # checks measured. On one page that is false wherever the trace
            # sampled other pages - twenty22 /about/ read "12 checks pass on
            # this page" including tap-target, on a page never rendered. So a
            # page in scope that was not traced owes its reason too.
            if page_traced is False:
                for _full in cat["trace_derived"]:
                    cat["not_assessed"].setdefault(
                        _full, "this page was not among the pages this run "
                               "traced, which is what these are measured from")
            if cat["key"] == "intl":
                cat["gate"] = gate_state
                # Where the gate says `na` the brief will NEVER run here, so
                # "no brief has run for this part yet" is false -- the "yet"
                # promises a run the gate refuses. The checks take the gate's
                # own settled reason instead, and the screen words the line
                # "not applicable" rather than "not assessed" (brief 160 step 6:
                # `na` is settled and a zero under it is honest). Found on
                # twenty22, where the gate card and the line beneath it
                # contradicted each other.
                if gate_state and gate_state.get("state") == "na":
                    cat["not_assessed"] = {
                        full: "hreflang does not apply: this site presents one locale"
                        for full in (cat.get("brief_checks") or [])}
            cat["unclaimed_checks"] = sorted(
                ch for ch, g in gating.get(cat["key"], {}).items()
                if g["state"] == "unclaimed")
            if cat["key"] == "crawl":
                cat["depth"] = depth
                if crawl_now:
                    cat["crawl_now"] = crawl_now
            if cat["key"] == "indexability" and idx_now:
                cat["indexability_now"] = idx_now
            if cat["key"] == "urls" and urls_now:
                cat["urls_now"] = urls_now
            if cat["key"] == "ai-surface" and latest:
                # The AI surface part's reachability "now" (item 145 BH), read
                # off the picker's run and the site record, like the others.
                from clauditseo.analysts.ai_surface import reachability_payload
                ai_now = reachability_payload(
                    conn, latest["id"], site_of(repo.site_record(repo.get_site(conn, site_id))))
                if ai_now:
                    cat["ai_now"] = ai_now
            if cat["key"] == "speed" and speed_now:
                cat["speed_now"] = speed_now
                # The filmstrip's frames are files, so the part page needs the
                # run to address them. One field rather than absolute URLs on
                # every frame: the route is `/api/runs/{run_id}/frames/{name}`
                # and a payload carrying it forty times would be forty copies
                # of one fact.
                cat["speed_now"]["run_id"] = speed_run
        # And what the site's images weigh against what they are drawn at
        # (brief v16c), on the one part whose subject that is. Attached
        # beside the depth block and for the same reason: the picker's run
        # is resolved here and not inside `anatomy_view`.
        # The fix order (brief v16e Block 1), on the one part whose subject
        # is what to do first. Site scope: it reads OPEN instances across the
        # site, and takes the run only for its denominator - how many pages
        # each kind of check assessed, which is 227 for the static ones and 5
        # for `axe-*` on the same run.
        order = runs.fix_order_payload(conn, site_id, ref["A11Y"])
        # And, when one page is in scope, that page's barriers and the
        # picture to draw them on (Block 2). Attached only where a page is
        # named: the overlay is a page-scope block and computing it for the
        # site view would be work nothing reads.
        # Item 239 step 3: a page-scope block reads the run that last
        # measured that page for its dimension, not the picked audit.
        barriers = (runs.a11y_page_payload(
            conn, site_id, _lv.field_run(conn, site_id, page, "a11y"), page, order)
            if page else None)
        for cat in view["categories"]:
            if cat["key"] == "a11y":
                cat["fix_order"] = order
                if barriers:
                    cat["barriers"] = barriers
        # The Content overlay's weighed text (brief v16j Tab 1), on the page
        # in scope. Same placement and reason as the barriers above: a
        # page-scope block, computed only where a page is named.
        if page and view.get("facts"):
            content_run = _lv.field_run(conn, site_id, page, "word_count")
            cb = runs.content_blocks_payload(conn, content_run, page)
            if cb:
                view["facts"]["content_blocks"] = cb
            pv = runs.page_entity_verdict(conn, content_run, page)
            if pv:
                view["facts"]["entity_verdict"] = pv
        # The entity matrix (brief v16j Tab 4), site scope, on the Content
        # part. Resolved against the run the pane reads.
        _srow = repo.site_record(repo.get_site(conn, site_id))
        matrix = runs.entity_matrix_payload(
            conn, ref["CNT"], site_of(_srow) if _srow else None)
        for cat in view["categories"]:
            if cat["key"] == "content":
                cat["entity_matrix"] = matrix
        # What every fetched page's response headers say (brief v16h), on
        # the one part whose subject that is. Same placement and the same
        # reason as the two blocks above.
        hg = runs.security_headers_payload(conn, ref["SEC"])
        for cat in view["categories"]:
            if cat["key"] == "security":
                cat["headers_grid"] = hg
        budget = runs.image_budget_payload(
            conn, _lv.reference_run(conn, site_id, "images", "ONP"))
        for cat in view["categories"]:
            if cat["key"] == "images":
                cat["images"] = budget
        # And which heading fault each page carries (brief v16d), on the
        # Headings part. Attached here for the third time and the same
        # reason: the run the pane is reading is resolved at this point.
        # Only the shape - the client groups it by template with the
        # function it already has, so this screen and the check group line
        # above it cannot disagree about what a template is.
        # Every page's title and description width (brief v16i Part C), on
        # the Title & description part. Site-scope, resolved against the run
        # the pane reads, like the four payloads above it.
        lengths = runs.title_lengths_payload(conn, ref["ONP"])
        for cat in view["categories"]:
            if cat["key"] == "title-desc":
                cat["title_lengths"] = lengths
        shapes = runs.heading_shapes_payload(conn, ref["ONP"])
        for cat in view["categories"]:
            if cat["key"] == "headings":
                cat["shapes"] = shapes
        # And which of the site's canonical chains are not the healthy case
        # (brief v16g), on the one part whose subject is which URL owns a
        # page. Attached here for the fourth time and the same reason as the
        # three above: the run the pane is reading is resolved at this point
        # and not inside `anatomy_view`. Only the chains that are not `ok` -
        # a card per self-canonical page is 226 identical loops on Acme.
        chains = runs.canonical_chains_payload(conn, ref["TEC"])
        for cat in view["categories"]:
            if cat["key"] == "indexability":
                cat["chains"] = chains
        view["latest_run"] = latest["id"] if latest else None
        # The second screen holding a verify button. Both are told, because
        # they read different payloads and a cap carried on one is a screen
        # offering what the server refuses — CQ-82's shape, one rule with two
        # implementations, is what carrying it avoids.
        view["verify_page_cap"] = runs.VERIFY_PAGE_CAP

        # Shipped with the view so the facts panel grades a title by the
        # threshold that scores it, rather than by a second copy that drifted.
        view["guidelines"] = GUIDELINES
        return view

    @app.get("/api/sites/{site_id}/link-suggestions")
    def link_suggestions(site_id: str, conn=dep, operator=op_dep):
        """Deterministic internal-link suggestions from the latest crawl's
        own graph. Free to compute, so free to browse."""
        from clauditseo.linksuggest import suggest_links
        check_site(conn, operator, site_id)
        # The latest reading of the site, not the latest run: internal-link
        # suggestions are computed from the crawl's own graph, and the graph
        # a verification or a refresh records is the handful of pages it was
        # sent to. Suggesting links across a site from an eight-page subgraph
        # is the same over-claim the score filters already refuse.
        row = conn.execute(
            f"SELECT id, crawl_evidence FROM audit_runs WHERE site_id=?"
            f" AND {runs.status_in(runs.SCORED_STATUSES)}"
            f" AND {runs.kind_is_site_reading()}"
            " AND crawl_evidence IS NOT NULL"
            " ORDER BY started_at DESC, rowid DESC LIMIT 1",
            (site_id,)).fetchone()
        if not row:
            return {"suggestions": [], "reason": "no completed crawl"}
        import json as _json
        evidence = _json.loads(row["crawl_evidence"])
        suggestions = suggest_links(evidence)
        return {"run_id": row["id"], "suggestions": suggestions,
                "reason": (None if suggestions else
                           "no under-linked pages with enough topical overlap"
                           if evidence.get("pages") else "no pages in evidence")}

    @app.get("/api/sites/{site_id}/export/findings.md")
    def export_findings(site_id: str, conn=dep, operator=op_dep):
        """Open work as a markdown checklist — the bridge to whatever the
        client uses to track work, without integrating with any of it."""
        from fastapi.responses import PlainTextResponse
        site = repo.get_site(conn, site_id)
        check_site(conn, operator, site_id)
        states = [s for s in runs.site_states(conn, site_id)
                  if s["state"] in ("open", "regressed")]
        order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
        states.sort(key=lambda s: (order.get(s["severity"], 9), s["check_id"]))
        lines = [f"# Open findings — {site['domain']}", "",
                 f"{len(states)} item(s), worst first. Regressed items were "
                 "fixed once and have come back.", ""]
        for s in states:
            urls = " ".join(s["affected_urls"][:3])
            mark = " **REGRESSED**" if s["state"] == "regressed" else ""
            attempted = (" _(fix attempted"
                         + (f": {s['attempt_note']}" if s.get("attempt_note") else "")
                         + ")_" if s.get("attempted_at") else "")
            lines.append(f"- [ ] `{s['severity']}` **{s['check_id']}**{mark} — "
                         f"{s['summary']}{attempted} {urls}".rstrip())
        return PlainTextResponse("\n".join(lines) + "\n",
                                 media_type="text/markdown; charset=utf-8")

    @app.get("/api/runs/{run_id}/screens/{name}")
    def run_screenshot(run_id: str, name: str, conn=dep, operator=op_dep):
        """One page's screenshot from the rendered pass (136j Part B).

        The only route in this API that serves a file from `data/`, and the
        only one that needs to - everything else the product stores is a
        row. `check_run` first, so a picture is behind the same operator
        check as the findings it is drawn under: a screenshot of a client's
        site is client data.

        `name` is validated rather than trusted. It is built by
        `axe.page_hash`, so it is 32 hex characters and a `.png`; anything
        else is refused before it reaches the filesystem, because a name
        that reaches `Path` unchecked is a path traversal and this is the
        one place where that is reachable.
        """
        from fastapi.responses import FileResponse

        from clauditseo import axe
        check_run(conn, operator, run_id)
        stem = name[:-4] if name.endswith(".png") else ""
        if len(stem) != 32 or not all(c in "0123456789abcdef" for c in stem):
            raise HTTPException(status_code=404, detail="no such screenshot")
        path = axe.screens_dir(run_id) / f"{stem}.png"
        if not path.is_file():
            raise HTTPException(
                status_code=404,
                detail="no screenshot for that page on this run - the rendered "
                       "pass samples the crawl, and runs taken before this "
                       "feature have none at all")
        return FileResponse(path, media_type="image/png", headers={
            # The name is a hash of the URL and the file is written once, so
            # it can never change under a cache. A revisit costs nothing.
            "Cache-Control": "public, max-age=31536000, immutable"})

    @app.get("/api/runs/{run_id}/frames/{name}")
    def run_perf_frame(run_id: str, name: str, conn=dep, operator=op_dep):
        """One filmstrip frame from the performance pass (brief v19 step BC,
        visual 4).

        The second route in this API that serves a file from `data/`, and it
        follows the first one's rules exactly (`run_screenshot` above): the
        same `check_run` first, because a frame of a client's page painting is
        client data, and the same validate-rather-than-trust on `name`,
        because a name that reaches `Path` unchecked is a path traversal.

        `name` is written by `perf._stop_screencast` as
        `<32 hex page hash>-frame<n>.jpg`, so that is the only shape accepted —
        no separators, no dots beyond the extension, `n` a small integer.
        """
        import re

        from fastapi.responses import FileResponse

        from clauditseo import axe
        check_run(conn, operator, run_id)
        if not re.fullmatch(r"[0-9a-f]{32}-frame\d{1,3}\.jpg", name):
            raise HTTPException(status_code=404, detail="no such frame")
        path = axe.screens_dir(run_id) / "perf" / name
        if not path.is_file():
            raise HTTPException(
                status_code=404,
                detail="no filmstrip frame by that name on this run - the "
                       "performance pass runs only where it was asked for, and "
                       "runs taken before it existed have none at all")
        return FileResponse(path, media_type="image/jpeg", headers={
            # Written once under a name derived from the page and the frame
            # order, so it can never change under a cache.
            "Cache-Control": "public, max-age=31536000, immutable"})

    @app.get("/api/runs/{run_id}")
    def run_detail(run_id: str, conn=dep, operator=op_dep):
        run = check_run(conn, operator, run_id)
        run["biggest_gains"] = runs.biggest_gains(run.get("subscores") or {})
        # How much of the intended audit this run's composite rests on, read
        # back from the row `_snapshot_metrics` wrote beside it. The score is
        # half the fact: a T1 pulse over a tenth of the weight and a full T3
        # both print two digits, and this is the only stored figure that
        # separates them. It had a writer and no reader for twelve rounds.
        #
        # Assembled here rather than in `get_run`, and the choice is not a
        # convenience. `test_stored_shape.py` pins `get_run`'s key set as a
        # per-version compatibility surface and fires on any addition, and its
        # 0.6.0 precedent — `scope`, also assembled rather than stored — took a
        # version bump. This one does not belong there: the figure lives in
        # another table, no stored column changed, and the three other callers
        # of `get_run` do not want it. `generate.py` in particular deliberately
        # does not — `render.py:_breadth_phrase` states why a client is shown
        # the raw page ratio instead — `check_run` hands the same dict to eight
        # other routes, and `_probe_site_host` reads one field off it. Bumping
        # ENGINE_VERSION would mark the operator's next audit incomparable with
        # their whole history, since `site_trend` keys comparability on it, to
        # record a change that stores nothing. So it goes where the run
        # screen's other three assembled fields already are.
        run["measured_share"] = runs.run_measured_share(conn, run)
        run["deterministic_findings"] = [f for f in run["findings"]
                                         if f["source"] == "deterministic"]
        # `_analyst_section` excludes `EXP:*` from the document's "Analyst
        # insights"; this listed every model-judgement row, so the operator
        # reviewed one list on screen and sent a document whose section of
        # that name held a shorter one — or, where the only model findings
        # came from a brief, no such section at all. Briefs keep their own
        # index at /api/runs/{id}/expert and their own document section.
        run["analyst_findings"] = [
            f for f in run["findings"]
            if f["source"] == "model-judgement"
            and not (f.get("dimension") or "").startswith("EXP:")]
        return run

    @app.get("/api/runs/{run_id}/expert")
    def expert_index(run_id: str, conn=dep, operator=op_dep):
        """Which briefs have been run against this run, and what they found.

        Read-only and free: browsing a tool list must never spend tokens, so
        this returns what is stored and nothing else.
        """
        run = check_run(conn, operator, run_id)
        evidence = runs.get_evidence(conn, run_id)
        pages = len([p for p in evidence.get("pages", []) if p.get("status") == 200])
        # Which model each brief WOULD use, and the tier that decided it.
        # The choice was invisible at launch: one run of this site returned 49
        # usable observations from a deep model and another returned a single
        # platitude from a fast one, with nothing at choose-time saying which
        # was being bought.
        from clauditseo.analysts.expert import EXPERT_TOOLS, model_for_tool, tier_of
        cfg_now = tiers.settings_for(conn)
        picks = tiers.brief_choices(conn)
        plan = {tid: {"tier": tier_of(tid),
                      "model": model_for_tool(cfg_now, tid, chosen=picks)}
                for tid in EXPERT_TOOLS}
        return {"results": runs.expert_report_index(conn, run_id),
                "pages_crawled": pages,
                "model_plan": plan,
                "in_flight": _in_flight_for(run_id),
                "budget": _budget_status(conn, settings()),
                # A run belongs to exactly one site, so there is no sense in
                # which this route is install-wide — UX-77. `check_run` already
                # resolved the run in order to authorise it and its `site_id`
                # was being thrown away.
                "estimates": runs.expert_estimates(conn, pages or None,
                                                   site_id=run["site_id"])}

    @app.get("/api/runs/{run_id}/client-report-hold")
    def run_client_report_hold(run_id: str, conn=dep, operator=op_dep):
        """Whether a client report may go out for this run (item 178).

        The one answer every surface that reaches Reports draws - the strip's
        Client report step, the nav and Generate - so none of them can say
        "done" or offer a live Generate while another says held (UI audit
        08-3). The same function the plan route and the generator refuse on.
        """
        run = check_run(conn, operator, run_id)
        # Item 239 step 7: the site's open Critical and High, whichever of
        # its runs asks - a client report is a copy of the running record.
        severe = runs.open_severe(conn, run["site_id"])
        return {"run_id": run_id, "held": bool(severe["count"]),
                "count": severe["count"], "critical": severe["critical"],
                "high": severe["high"],
                "reason": runs.client_report_hold(conn, run["site_id"])}

    @app.get("/api/runs/{run_id}/fingerprints")
    def run_fingerprints_route(run_id: str, conn=dep, operator=op_dep):
        """The fingerprints this run raised, and nothing else (item 207).

        The record narrows to them when a figure that counted one audit opens
        it. `/api/runs/{id}` carries the same field inside every finding -
        1.7 MB on a real twenty22 audit before its two filtered copies - and a
        narrowing that needs one field should not fetch all of them."""
        check_run(conn, operator, run_id)
        return {"run_id": run_id, "fingerprints": runs.run_fingerprints(conn, run_id)}

    @app.get("/api/runs/{run_id}/analyses")
    def run_analyses(run_id: str, conn=dep, operator=op_dep):
        """Every analysis, split into what is free to read and what would
        spend, with one state and one verb each.

        Computed here rather than in each screen. Tools, the workbench, the
        run page and the client screen previously each derived this for
        themselves and disagreed — including a control that read as "open the
        stored report" and in fact re-ran it at full price.
        """
        from clauditseo import analyses as an
        from clauditseo.analysts.expert import EXPERT_TOOLS

        run = check_run(conn, operator, run_id)
        cfg = settings()
        evidence = runs.get_evidence(conn, run_id)
        pages = len([p for p in evidence.get("pages", []) if p.get("status") == 200])

        stored = {r["tool"]: r for r in runs.expert_report_index(conn, run_id)}
        in_flight = {f["tool"] for f in _in_flight_for(run_id)}
        briefs = {t: {"scope": spec["scope"], "tier": spec.get("tier", "standard"),
                      "inputs": spec.get("inputs", [])}
                  for t, spec in EXPERT_TOOLS.items()}

        # Which model each row would run on. `tier` already travels with the
        # brief; the model it resolves to depends on configuration, so it can
        # only be answered here.
        from clauditseo.analysts.expert import model_for_tool
        cfg_now = tiers.settings_for(conn)
        prices_now = {r["model"]: (r["input_usd"], r["output_usd"])
                      for r in conn.execute(
                          "SELECT model, input_usd, output_usd FROM model_prices")}
        # Site-scoped for the same reason `expert_index` is — UX-77. `run` is
        # in hand from `check_run` above.
        out = an.lanes(stored,
                       runs.expert_estimates(conn, pages or None,
                                             site_id=run["site_id"]),
                       in_flight, briefs)
        picks = tiers.brief_choices(conn)
        for row in (*out["ready"], *out["available"]):
            row["model"] = model_for_tool(cfg_now, row["tool"], chosen=picks)
            # The estimate at the model that would run it (brief v4 Item
            # 3f): `est_cost` is the median of what past runs cost at
            # whatever ran them, and a batch total taken over it was the
            # cheapest-model floor. Priced here under `INPUT_SHARE`.
            row["est_cost_default"] = an.cost_at(row.get("est_tokens"),
                                                 prices_now.get(row["model"]))
        batch = [r["est_cost_default"] for r in out["available"]
                 if r.get("est_cost_default") is not None and r.get("type") != "page"]
        out["outstanding_cost_default"] = round(sum(batch), 4) if batch else None
        # The catalogue's batch, summed once, here (item 180, ruling
        # 20260918-0405): what "Run all" runs - not run, not page-scoped, and a
        # section of the site (triage and the client plan write to none) - and
        # the two remainders named rather than folded in, so the landing and
        # the catalogue read the same three numbers instead of summing twice.
        partless = {"none", "report"}
        listed = [r for r in out["available"]
                  if r.get("type") != "triage" and r.get("part") not in partless]
        # What "Run all" runs, by the button's own rule: not page-scoped AND
        # `not_run`. `state` was missing from this predicate until 2026-09-18
        # (audit F4), so `count` was 22 on twenty22 while the button ran 21 -
        # the difference being `migration-redirects`, whose state is
        # `needs_input` and whose row reads "needs context a crawl cannot
        # supply". The landing quoted that 22 as a promise about a press, and
        # on Birch it quoted it with a price: "USD 0.63 to run 22".
        runs_all = [r for r in listed
                    if r.get("type") != "page" and r.get("state") == "not_run"]
        # The remainders, each named rather than folded in, so five readers of
        # this one set cannot word it five ways:
        #   listed = count + need_page + needs_input + read
        need_page = [r for r in listed if r.get("type") == "page"]
        needs_input = [r for r in listed
                       if r.get("type") != "page" and r.get("state") == "needs_input"]
        read = [r for r in listed
                if r.get("type") != "page"
                and r.get("state") not in ("not_run", "needs_input")]
        priced = [r["est_cost_default"] for r in runs_all if r.get("est_cost_default") is not None]
        out["batch"] = {
            "listed": len(listed),
            "count": len(runs_all),
            "cost": round(sum(priced), 4) if priced else None,
            "priced": len(priced),
            "need_page": len(need_page),
            # Named on the screen beside the other two: an analysis the
            # catalogue's own row calls "needs context a crawl cannot supply"
            # is not something a batch can run.
            "needs_input": len(needs_input),
            "read": len(read),
            "partless": [{"tool": r["tool"], "name": r.get("name"),
                          "est_cost_default": r.get("est_cost_default")}
                         for r in out["available"]
                         if r.get("type") != "triage" and r.get("part") in partless],
        }
        out["input_share"] = an.INPUT_SHARE
        # What the engine answers without a model at all (brief v17 step
        # AV5). The Analyse tile leads with it: an operator looking at
        # "13 not run" is owed the other half of the sentence, which is
        # that ninety-nine questions were already answered for nothing.
        # Counted here rather than on the screen, because the part pages
        # split on the same registry and two derivations of it would
        # disagree the first time a check changed hands.
        from clauditseo.checks import check_costs
        out["free_checks"] = sum(1 for v in check_costs().values() if v == "free")
        # What a single launch may be pointed at. Sent with the rows so the
        # choice is made where the money is committed, rather than on another
        # screen before the operator knows which brief they are running.
        out["models"] = [
            {"model": m, "price": prices_now.get(m)}
            for m in tiers.known_models(conn, cfg_now)]

        # The ranking, computed here rather than purchased (item 196, the
        # operator's decision (b)). What stood here read the newest stored
        # `triage` report for this site, which meant the ranking could be
        # absent (never bought), stale (bought against an older audit), or
        # both — and the screens carried a staleness warning and a re-run
        # button to deal with it. A sort that costs money and goes out of
        # date is the loop the operator described: "they will more than
        # likely spend on trying to get a consistent result across the
        # sections".
        #
        # Ranked over the SITE's live states rather than this run's findings,
        # because that is the population every count beside it is taken over:
        # open state is site-scoped, so a finding raised by an older audit and
        # never fixed is still work, and a finding this run happened to re-see
        # is not new work. `regressed` and `open` only — `accepted-risk` and
        # `withdrawn` are decisions already taken, and `candidate` has been
        # seen once and not confirmed, so none of the three is the next thing
        # to look at.
        site_id = run["site_id"]
        live = [f for f in runs.site_states(conn, site_id)
                if f.get("state") in ("regressed", "open")]
        out["triage"] = an.audit_ranking(
            live,
            run.get("finished_at") or run.get("started_at"),
            run_id,
            # Only what this audit can actually start, and what it has
            # already produced — otherwise a row offers a run button for a
            # sweep with no endpoint behind it.
            runnable={r["tool"] for r in out["available"]},
            already={r["tool"] for r in out["ready"]})
        out["budget"] = _budget_status(conn, cfg)
        return out

    @app.get("/api/runs/{run_id}/expert/{tool_id}")
    def stored_expert(run_id: str, tool_id: str, conn=dep, operator=op_dep):
        check_run(conn, operator, run_id)
        stored = runs.expert_report(conn, run_id, tool_id)
        if not stored:
            raise HTTPException(status_code=404,
                                detail="this analysis has not been run against this audit")
        return stored

    @app.get("/api/runs/{run_id}/pages")
    def run_pages(run_id: str, conn=dep, operator=op_dep):
        """Crawled URLs, homepage first, for choosing what a page-scoped brief
        should read. Kept separate from the run detail because that response is
        already large and this is wanted on its own."""
        check_run(conn, operator, run_id)
        start, pages = _offered_pages(runs.get_evidence(conn, run_id))
        return {"start_url": start, "pages": pages}

    @app.delete("/api/runs/{run_id}")
    def delete_run(run_id: str, conn=dep, operator=op_dep):
        check_run(conn, operator, run_id)
        runs.delete_run(conn, run_id)
        return {"ok": True}

    @app.get("/api/compare")
    def compare(a: str, b: str, conn=dep, operator=op_dep):
        for run_id in (a, b):
            check_run(conn, operator, run_id)
        try:
            return runs.compare_runs(conn, a, b)
        except ValueError as exc:
            # Cross-site pairs. The refusal lives in `compare_runs` so the
            # deliverable path inherits it; this is the mapping every other
            # route here already applies to a request it cannot honour.
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/runs/{run_id}/advise")
    def advise_page(run_id: str, body: AdviseIn, conn=dep, operator=op_dep):
        """On-demand page advisory: one page, one judgement, budget-capped."""
        run = check_run(conn, operator, run_id)
        site_row = repo.get_site(conn, run["site_id"])
        if not body.url:
            raise HTTPException(status_code=422, detail="url is required")
        problem = _validate_start_url(body.url, site_row["domain"])
        if problem:
            raise HTTPException(status_code=422, detail=problem)
        c = settings()
        site = Site(domain=site_row["domain"], locale=site_row["locale"],
                    business_type=site_row["business_type"],
                    target_market=site_row["target_market"])
        from clauditseo.analysts.page_advisor import advise_url
        # Recommending the heading IS the product: deliberative work.
        return advise_url(conn, run_id, body.url, site, c,
                          provider_from_settings(c, body.model
                                                 or c.model_for_tier("deep")),
                          scope=body.scope, check_id=body.check_id)

    @app.get("/api/runs/{run_id}/advice")
    def read_page_advice(run_id: str, url: str, scope: str | None = None,
                         check_id: str | None = None, conn=dep, operator=op_dep):
        """Advice already produced for this page, without producing any (F-04).

        The read costs nothing: no fetch, no provider, no cost entry. It is a
        GET because it is one — the panel calls it when it mounts, so
        re-entering a section shows what was already paid for instead of
        offering to buy it again. `status: none` means nothing is stored and
        the panel offers to generate.

        `scope` and `check_id` narrow or refuse exactly as they do on the
        POST; they share the resolver, so the two paths cannot disagree about
        which section a finding is answered in.
        """
        check_run(conn, operator, run_id)
        if not url:
            raise HTTPException(status_code=422, detail="url is required")
        from clauditseo.analysts.page_advisor import stored_advice
        return stored_advice(conn, run_id, url, scope=scope, check_id=check_id)

    @app.get("/api/runs/{run_id}/probes")
    def run_probes(run_id: str, conn=dep, operator=op_dep):
        """Every `[TO CONFIRM: …]` this run's briefs raised, and what has been
        measured against them (F-05).

        Free, and it has to be: the brief calls this when it renders, so an
        item already settled shows its answer rather than offering to go and
        get one. Nothing here touches the network — running a probe is the
        POST below, and it is the operator's click.

        The parse lives here rather than in the screen so there is one owner
        for which items name a runnable probe. Two implementations of that
        rule would eventually disagree, and the disagreement would show up as
        a button offering a measurement the server would then refuse.
        """
        check_run(conn, operator, run_id)
        from clauditseo.probes import confirm_items
        items: dict[str, dict] = {}
        for text in runs.expert_report_texts(conn, run_id):
            for item in confirm_items(text):
                items.setdefault(item["text"], item)
        return {"target": _probe_target(conn, run_id),
                "items": list(items.values()),
                "results": runs.probe_results(conn, run_id)}

    @app.post("/api/runs/{run_id}/probes/{probe_id}")
    def run_probe_now(run_id: str, probe_id: str, conn=dep, operator=op_dep):
        """Run one registered probe against this run's own site, and keep it.

        There is no target in the request. `probe_id` selects Python from a
        fixed registry and the host is read from the database, so neither
        half of what runs is supplied by the caller — a brief is prose from a
        language model, and the path from it to a socket must not be one an
        operator can redirect.
        """
        check_run(conn, operator, run_id)
        from clauditseo.probes import PROBES, run_probe
        if probe_id not in PROBES:
            raise HTTPException(status_code=404,
                                detail=f"no probe {probe_id} — this product "
                                       "cannot measure that")
        target = _probe_target(conn, run_id)
        if not target:
            raise HTTPException(status_code=422,
                                detail="this run has no site host to probe")
        # Reading the target and being allowed to reach it are two questions,
        # and only the first was ever asked (CQ-112). The site record is not a
        # trusted source of hosts: nothing validates `SiteIn.domain` on the way
        # in, so "the target is never supplied by the caller" was true of the
        # request and false of the path — a site created with domain
        # `127.0.0.1` handshook this machine and reported it as a measurement.
        refusal = _probe_refusal(target)
        if refusal:
            raise HTTPException(status_code=422, detail=refusal)
        measured = run_probe(probe_id, target).as_dict()
        return runs.store_probe_result(conn, run_id, measured)

    @app.post("/api/runs/{run_id}/stop")
    def stop_run(run_id: str, conn=dep, operator=op_dep):
        """Ask a running crawl to stop at its next page boundary.

        Relay item 136a: a 145-page crawl the operator did not ask for
        should be stoppable at page four. Answered at a page boundary
        rather than mid-fetch - a half-read page is not evidence, and
        killing the worker would leave the row `running` for ever.

        The reply is immediate and says what was asked, not what happened:
        the worker acts on it within one page, and the run's own status is
        what reports the outcome. Saying "cancelled" here would be
        answering for a thread that has not looked yet.
        """
        run = check_run(conn, operator, run_id)
        if run["status"] not in ("pending", "running"):
            raise HTTPException(
                status_code=409,
                detail=f"run {run_id} is {run['status']}, so there is nothing "
                       "to stop")
        runs.request_stop(run_id)
        return {"run_id": run_id, "stopping": True,
                "note": "the crawl stops at its next page boundary; what it "
                        "fetched is kept"}

    @app.post("/api/runs/{run_id}/expert/{tool_id}")
    def expert_tool(run_id: str, tool_id: str, body: AdviseIn | None = None,
                    conn=dep, operator=op_dep):
        """Run one operator-authored expert brief against this run's stored
        crawl evidence. Page-scoped tools re-fetch the one page they need."""
        from clauditseo.analysts.expert import (EXPERT_TOOLS, BriefInputError,
                                               model_for_tool, run_expert)
        if tool_id not in EXPERT_TOOLS:
            raise HTTPException(status_code=404, detail=f"unknown tool {tool_id}")
        run = check_run(conn, operator, run_id)
        # Brief v6 step V3: not against a nav or page scan. A page-scoped
        # brief with a page named is the exception - it reads that page,
        # whatever the run crawled.
        refusal = runs.narrow_run_refusal(run)
        if refusal and not (EXPERT_TOOLS[tool_id].get("scope") == "page" and body and body.url):
            raise HTTPException(status_code=409, detail=refusal)
        # Item 178: the client report's guard, before anything is claimed or
        # spent. The document generator refuses a held client report; without
        # this the Reports screen paid for the plan first and was refused
        # after (UI audit 08-2). 422, the status `/api/reports` gives the same
        # sentence.
        if tool_id == "plan" and body and body.for_audience == "client":
            hold = runs.client_report_hold(conn, run["site_id"])
            if hold:
                raise HTTPException(status_code=422, detail=hold)
        # KI-19. Read the register before running, not only mark it: two
        # overlapping calls for one brief both billed, and the second
        # report then overwrote the one the first charge had paid for.
        # Claimed here rather than beside the provider call so the Places
        # lookup, the Search Console read and the page fetch below are
        # inside the gate too — those are what a second call spends before
        # a model is ever resolved.
        token = _claim_in_flight(run_id, tool_id)
        if token is None:
            raise HTTPException(
                status_code=409,
                detail=f"{tool_id} is already running against this audit "
                       "— wait for it to finish rather than paying for it "
                       "twice; its result appears here when it lands")
        try:
            site_row = repo.site_record(repo.get_site(conn, run["site_id"]))
            c = settings()
            site = site_of(site_row)
            evidence = runs.get_evidence(conn, run_id)

            extra: dict = {}
            if tool_id == "speed":
                asked = (body.depth if body else None) or "standard"
                if asked not in ("standard", "deep"):
                    raise HTTPException(
                        status_code=400,
                        detail=f"unknown depth {asked!r} - the Speed analysis runs "
                               "at `standard` or `deep`")
                extra["depth"] = asked
            if tool_id == "triage":
                extra["triage_data"] = _triage_data(conn, run, site_row, c, evidence)
            if tool_id in PLACES_TOOLS:
                extra["places"] = _places_profile(c, site_row,
                                                  body.inputs if body else None)
                _snapshot_review_metrics(conn, site_row["id"], extra["places"])
                _remember_places_lookup(conn, site_row["id"], extra["places"])
                extra["review_series"] = _review_series(conn, site_row["id"])
            if tool_id in ("freshness", "content-gap"):
                # Optional enhancer: fetched only when the service account is
                # configured, silent otherwise — the briefs already say plainly
                # what they cannot see without it.
                from clauditseo.providers.google import SearchConsole
                sc = SearchConsole(c)
                if sc.available():
                    try:
                        extra["gsc"] = sc.page_decay(site_row["domain"])
                    except Exception:            # noqa: BLE001 - absence beats a guess
                        extra["gsc"] = None
            if EXPERT_TOOLS[tool_id]["scope"] == "page":
                url = body.url if body else None
                if not url:
                    # WF-89. This read `or evidence.get("start_url")`, and
                    # `start_url` is the URL the crawl was handed rather than one
                    # it retrieved — `_validate_start_url` then judged the host and
                    # nothing else, so a run that fetched no page at all billed a
                    # brief against a URL nobody had ever read, and the stored
                    # envelope named that URL as the brief's source.
                    #
                    # The client omits `url` exactly when its own picker resolved
                    # to nothing (`tools.tsx`'s single-brief `run` and its sweep spread
                    # `pageUrl ? { url: pageUrl } : {}`), which is the same state,
                    # so the two ends met at the one case neither covered.
                    #
                    # Resolve it the way the picker does, from the same list:
                    # the handed URL when the run actually fetched it, else the
                    # first page it offers. Refuse only when there is no page.
                    start, offered = _offered_pages(evidence)
                    url = (start if any(p["url"] == start for p in offered)
                           else (offered[0]["url"] if offered else None))
                    if not url:
                        raise HTTPException(
                            status_code=422,
                            detail=f"run {run_id} retrieved no page an analysis can "
                                   f"read, so there is nothing for {tool_id} to "
                                   "report on — re-run the crawl, or choose a run "
                                   "that fetched pages")
                # A `url` supplied by the caller is still checked for host alone.
                # Report 072 scopes this fix to the fallback and assigns the
                # class-level answer to storing the crawl's *resolved* start URL,
                # which is gated on an open question; no caller naming an unfetched
                # page has been observed. Left as a decision on the record.
                problem = _validate_start_url(url, site_row["domain"])
                if problem:
                    raise HTTPException(status_code=422, detail=problem)
                from clauditseo.crawler.fetch import Fetcher
                from clauditseo.crawler.robots import RobotsPolicy, robots_url_for
                from clauditseo.crawler.types import USER_AGENT
                with Fetcher(timeout_s=20) as fetcher:
                    robots_page = fetcher.fetch(robots_url_for(url))
                    policy = RobotsPolicy(robots_page.url, robots_page.status or None,
                                          robots_page.content)
                    if not policy.allows(url, USER_AGENT):
                        return {"status": "unavailable",
                                "reason": "robots.txt disallows fetching this page"}
                    page = fetcher.fetch(url)
                    # The refusal both sibling on-demand page routes already make
                    # (`page_advisor`, `schema_advisor`), in the same words.
                    # `Fetcher.fetch` does not raise: a transport failure comes
                    # back as `Page(status=0, error=...)` and an HTTP refusal as a
                    # status with no error, so without this the object was assigned
                    # into `extra["page"]` and a model was resolved and billed on a
                    # page the server never retrieved — and the stored envelope
                    # named that page as its source (CQ-147).
                    if page.error or page.status != 200:
                        return {"status": "unavailable",
                                "reason": f"could not fetch the page "
                                          f"({page.error or page.status})"}
                    extra["page"] = page

                    if tool_id == "render-blocking":
                        extra["field_metrics"] = _paint_metrics(url, c)
            # The operator's tier choice, then any per-run override on top of
            # it. Resolved here rather than trusted from the row that was
            # rendered: the screen may have been open since before the choice
            # changed, and the model that runs is the one that bills.
            model = model_for_tool(tiers.settings_for(conn, c), tool_id,
                                   body.model if body else None,
                                   chosen=tiers.brief_choices(conn))
            try:
                return run_expert(conn, run_id, tool_id, evidence, site, c,
                                  provider_from_settings(c, model),
                                  operator_inputs=(body.inputs if body else None),
                                  use_cache=not (body.no_cache if body else False),
                                  **extra)
            except BriefInputError as e:
                # A conforming brief the engine could not fill (brief v10
                # step AF): a load error naming the placeholder, before any
                # model is billed.
                raise HTTPException(status_code=422, detail=str(e)) from e
        finally:
            _release_in_flight(run_id, tool_id, token)

    @app.post("/api/runs/{run_id}/schema-audit")
    def schema_audit(run_id: str, body: AdviseIn, conn=dep, operator=op_dep):
        """On-demand structured-data audit: findings first, then corrected
        JSON-LD, validated against Google's current requirements."""
        run = check_run(conn, operator, run_id)
        site_row = repo.get_site(conn, run["site_id"])
        if not body.url:
            raise HTTPException(status_code=422, detail="url is required")
        problem = _validate_start_url(body.url, site_row["domain"])
        if problem:
            raise HTTPException(status_code=422, detail=problem)
        c = settings()
        site = Site(domain=site_row["domain"], locale=site_row["locale"],
                    business_type=site_row["business_type"],
                    target_market=site_row["target_market"])
        from clauditseo.analysts.schema_advisor import audit_schema
        # Google policy judgement over Schema.org permissiveness: deliberative.
        return audit_schema(conn, run_id, body.url, site, c,
                            provider_from_settings(c, body.model
                                                   or c.model_for_tier("deep")))

    # -- reports ------------------------------------------------------------

    @app.get("/api/sites/{site_id}/client-reports")
    def list_client_reports(site_id: str, conn=dep, operator=op_dep):
        """Deliverables already generated for this site.

        They were written to disk and recorded, and nothing listed them — the
        client rail said "Client report ✓ 2 generated" while both files were
        unreachable from the app that made them.
        """
        check_site(conn, operator, site_id)
        return {"reports": runs.client_reports(conn, site_id)}

    @app.get("/api/client-reports/{report_id}")
    def read_client_report(report_id: str, conn=dep, operator=op_dep):
        """One deliverable, scoped like every other resource.

        This resolved on the report id alone and took `operator` without
        using it, while `list_client_reports` six lines above scoped the same
        data — the one hole in an otherwise uniform authorisation layer, on
        the endpoint that returns the document a client is actually sent.
        404 rather than 403, matching `check_client`: a member should not
        learn which report ids exist.
        """
        got = runs.client_report(conn, report_id)
        if not got:
            raise HTTPException(status_code=404, detail="no such report")
        check_site(conn, operator, got["site_id"])
        return got

    @app.post("/api/reports", status_code=201)
    def create_report(body: ReportIn, conn=dep, operator=op_dep):
        from clauditseo.reporting.checks import ReportCheckError
        from clauditseo.reporting.generate import generate
        for run_id in body.run_ids:
            check_run(conn, operator, run_id)
        # Scoped like every other resource this route can be handed. 404
        # rather than 403, matching `check_client` and `read_client_report`
        # eighteen lines above: a member should not learn which report ids
        # exist by watching the status code change. `generate()` re-checks
        # that the two are on one site, because it has two other callers.
        if body.supersedes is not None:
            replaced = runs.client_report(conn, body.supersedes)
            if not replaced:
                raise HTTPException(status_code=404, detail="no such report")
            check_site(conn, operator, replaced["site_id"])
        # The blocked-run refusal lives in `generate()` so every caller
        # inherits it, and arrives here as the ValueError below — still a 422,
        # still carrying the same sentence. It applies to `client` only: an
        # internal document for a blocked run is the account of why it was
        # blocked, and this route is where the operator asks for it (WF-05).
        try:
            return generate(conn, body.template, body.audience, body.run_ids,
                            supersedes=body.supersedes)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        except ReportCheckError as exc:
            raise HTTPException(status_code=500,
                                detail=f"report failed honesty checks: {exc.problems}")

    @app.post("/api/admin/providers/check")
    def check_providers(conn=dep, operator=op_dep):
        """Ask each configured provider whether it actually answers.

        `configured` only ever meant "a key string exists", and that is what
        the screen showed: OpenPageRank read green while every audit silently
        recorded no backlink data, because the key was being rejected with a
        403. A key that is present and refused is the one state neither the
        screen nor the report could express.

        Deliberately on demand. It makes real network calls, and a page that
        probed every provider on load would spend an operator's quota to
        render a dashboard.
        """
        from clauditseo.providers.backlinks import (DataForSEOBacklinks,
                                                    MozBacklinks, NotConfigured,
                                                    OpenPageRank)
        from clauditseo.providers.google import CruxField, PageSpeedLab

        c = settings()
        # A domain and URL that certainly exist, so a failure is the
        # provider's and not the fixture's.
        probes = (
            ("OpenPageRank", OpenPageRank(c), lambda p: p.snapshot("example.com")),
            ("Moz", MozBacklinks(c), lambda p: p.snapshot("example.com")),
            ("DataForSEO", DataForSEOBacklinks(c), lambda p: p.snapshot("example.com")),
            ("CrUX", CruxField(c), lambda p: p.metrics("https://www.google.com/")),
            ("PageSpeed", PageSpeedLab(c), lambda p: p.metrics("https://example.com/")),
        )
        # Providers this cannot ask, and why — listed rather than omitted. A
        # button called "ask every provider" that quietly asked three of ten
        # was the same defect this check exists to fix: an operator sets a
        # key, presses the button, sees no row, and cannot tell "refused"
        # from "never tried". Two reasons for not asking, both real: a probe
        # that spends money, and a probe whose only call has a side effect.
        unprobed = {
            "Places": "asks about a named business, so there is no neutral "
                      "lookup to make — and it is billed per request",
            "LLM analyst": "spends tokens — not asked; the analyst layer "
                           "reports its own errors on a run",
            "IndexNow": "submitting a URL is an action, not a test",
            "Search Console": "needs a verified property, so there is no "
                              "neutral URL to ask about",
            "Headless renderer": "a Python package, not a key — its status "
                                 "above is the install check",
        }
        out = []
        for name, prov, call in probes:
            row = {"provider": name, "configured": bool(prov.available())}
            if not row["configured"]:
                row["state"] = "not configured"
                out.append(row)
                continue
            try:
                answer = call(prov)
                row["state"] = "answering" if answer else "answered empty"
            # Both branches redact, and both go through the same helper the
            # hub uses. This is the second place that builds a provider
            # failure detail; round 034 fixed the first and added `_redact`
            # for this one, and then never walked to it — `grep -rn "_redact"`
            # returned only the definition for a whole round. Two of these
            # five probes put a live key in a query string, and `admin.tsx`
            # renders `detail` verbatim, so "check providers" was the one
            # operator action that could show a credential on screen.
            #
            # `NotConfigured` carries a message this codebase writes, so it is
            # clean today. It is redacted anyway: a branch left raw because
            # its current text happens to be safe is exactly how the first
            # builder came to leak.
            except NotConfigured as exc:
                row["state"] = "not configured"
                row["detail"] = ProviderHub._redact(str(exc))[:200]
            except Exception as exc:                     # noqa: BLE001
                status = getattr(getattr(exc, "response", None),
                                 "status_code", None)
                row["state"] = "refusing"
                row["status"] = status
                row["detail"] = ProviderHub._redact(
                    str(exc).split("\n")[0])[:200]
            out.append(row)
        configured = _providers(c)
        for name, why in unprobed.items():
            entry = configured.get(name) or {}
            out.append({"provider": name,
                        "configured": bool(entry.get("configured")),
                        "state": "not checked", "detail": why})
        return {"providers": out,
                "note": ("`configured` means a key is present. `answering` "
                         "means it was asked just now and replied. Only the "
                         "second is worth relying on. `not checked` means "
                         "this screen cannot ask without spending your money "
                         "or causing a side effect — the reason is given.")}

    # -- the operator's own name and mark -------------------------------------

    @app.get("/api/brand")
    def read_brand(conn=dep, operator=op_dep):
        """What a client sees on a document produced here."""
        from clauditseo import brand as branding
        return branding.get(conn)

    @app.put("/api/brand/name")
    def set_brand_name(body: BrandNameIn, conn=dep, operator=op_dep):
        from clauditseo import brand as branding
        try:
            branding.set_name(conn, body.name)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        return branding.get(conn)

    @app.post("/api/brand/logo")
    def upload_brand_logo(body: BrandLogoIn, conn=dep, operator=op_dep):
        """Store a logo for client-facing documents.

        Base64 in a JSON body rather than a multipart upload. Multipart would
        pull in `python-multipart`, and the runtime dependencies here are
        three on purpose — a logo capped at 2 MB does not justify a fourth.

        Validated by content rather than by the name the browser sent: a file
        called `logo.png` that is not a PNG fails silently in a document and
        loudly in front of a client.
        """
        import base64

        from clauditseo import brand as branding
        try:
            raw = base64.b64decode(body.data_base64, validate=True)
        except Exception:                                # noqa: BLE001
            raise HTTPException(status_code=422,
                                detail="not valid base64 image data")
        try:
            return branding.set_logo(conn, raw,
                                     settings().db_path.parent / "brand")
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    @app.delete("/api/brand/logo")
    def delete_brand_logo(conn=dep, operator=op_dep):
        from clauditseo import brand as branding
        branding.clear_logo(conn)
        return branding.get(conn)

    @app.get("/api/brand/logo")
    def serve_brand_logo(conn=dep, operator=op_dep):
        from fastapi.responses import FileResponse

        from clauditseo import brand as branding
        got = branding.get(conn)
        if not got["logo_path"]:
            raise HTTPException(status_code=404, detail="no logo set")
        return FileResponse(got["logo_path"], media_type=got["logo_mime"])

    # -- which model each tier runs on ---------------------------------------

    @app.get("/api/models/tiers")
    def model_tiers(conn=dep, operator=op_dep):
        base = settings()
        eff = tiers.settings_for(conn, base)
        prices = {r["model"]: (r["input_usd"], r["output_usd"])
                  for r in conn.execute(
                      "SELECT model, input_usd, output_usd FROM model_prices")}
        chosen = tiers.chosen(conn)
        return {
            "tiers": [{
                "tier": t,
                "purpose": tiers.TIER_PURPOSE[t],
                "model": eff.model_for_tier(t),
                # Chosen here, or still coming from the environment. Without
                # this an operator cannot tell whether the screen is showing
                # their decision or the deployment's.
                "chosen": t in chosen,
                "recommended": tiers.RECOMMENDED.get(t),
                "price": prices.get(eff.model_for_tier(t)),
            } for t in tiers.TIERS],
            "models": [{"model": m, "price": prices.get(m)}
                       for m in tiers.known_models(conn, base)],
            "recommended": tiers.RECOMMENDED,
        }

    @app.get("/api/models/briefs")
    def model_briefs(conn=dep, operator=op_dep):
        """One row per brief: its tier, the model it runs on by default and
        whether that is the operator's choice or the tier's, why the tier
        suits it, and how many sites have a report from it (brief v4 Item
        3g). The choosable models are the priced ones."""
        from clauditseo import analyses as an
        from clauditseo.analysts.expert import EXPERT_TOOLS, model_for_tool, tier_of

        eff = tiers.settings_for(conn)
        picks = tiers.brief_choices(conn)
        prices = {r["model"]: (r["input_usd"], r["output_usd"])
                  for r in conn.execute(
                      "SELECT model, input_usd, output_usd FROM model_prices")}
        used = {r["tool_id"]: r["n"] for r in conn.execute(
            "SELECT er.tool_id AS tool_id, COUNT(DISTINCT r.site_id) AS n"
            " FROM expert_reports er JOIN audit_runs r ON r.id = er.run_id"
            " GROUP BY er.tool_id")}
        names = {t: row["name"] for t, row in an._catalogue().items()}
        labels = an.part_labels()
        rows = []
        # The catalogue's order (brief v10 step AD): the sidebar's, so this
        # table, the drawer and the confirm panel list the same briefs the
        # same way.
        # A brief writing to no part goes last - the dispatcher and, from
        # brief v18 step AY, the client plan. Both are here rather than in
        # the drawer: an operator sets their default model like any other
        # brief, and both spend tokens.
        for tool, spec in sorted(
                EXPERT_TOOLS.items(),
                key=lambda kv: (kv[1].get("part") in an.brief_catalogue.PARTLESS,
                                an.brief_catalogue.by_id()[kv[0]].order)):
            model = model_for_tool(eff, tool, chosen=picks)
            rows.append({
                "tool": tool, "name": names.get(tool, tool),
                "part": spec.get("part"), "part_label": labels.get(spec.get("part")),
                "tier": tier_of(tool), "scope": spec.get("scope"),
                "model": model, "chosen": tool in picks,
                "why": tiers.TIER_PURPOSE.get(tier_of(tool), ""),
                "used_by": used.get(tool, 0),
                "price": prices.get(model),
            })
        return {"briefs": rows,
                "models": [{"model": m, "price": prices.get(m)}
                           for m in tiers.priced_models(conn)]}

    @app.put("/api/models/briefs/{tool}")
    def set_model_brief(tool: str, body: TierModelIn, conn=dep, operator=op_dep):
        try:
            tiers.set_brief(conn, tool, body.model,
                            operator["id"] if operator else None)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        return {"ok": True, "tool": tool, "model": body.model}

    @app.delete("/api/models/briefs/{tool}")
    def clear_model_brief(tool: str, conn=dep, operator=op_dep):
        tiers.clear_brief(conn, tool)
        return {"ok": True, "tool": tool}

    @app.put("/api/models/tiers/{tier}")
    def set_model_tier(tier: str, body: TierModelIn, conn=dep, operator=op_dep):
        try:
            tiers.set_tier(conn, tier, body.model,
                           operator["id"] if operator else None)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        return {"ok": True, "tier": tier, "model": body.model}

    @app.post("/api/models/tiers/recommended")
    def recommend_model_tiers(conn=dep, operator=op_dep):
        return tiers.use_recommended(conn, operator["id"] if operator else None)

    @app.delete("/api/models/tiers")
    def clear_model_tiers(conn=dep, operator=op_dep):
        """Hand the decision back to the environment."""
        tiers.clear(conn)
        return {"ok": True}

    # -- money --------------------------------------------------------------

    @app.get("/api/rates")
    def rates(conn=dep, operator=op_dep):
        """What the cost figures are built from, and how old each part is.

        Model prices and exchange rates are kept apart because only one of
        them is a lookup: nobody publishes a machine-readable model price, so
        those are entered by the operator, while exchange rates come from the
        ECB with a real observation date.
        """
        from clauditseo.providers import fx, model_prices
        want = fx.display_currency(conn)
        return {
            "display_currency": want,
            "currencies": list(fx.CURRENCIES),
            "rate": fx.rate_for(conn, want),
            # Not `SELECT * FROM fx_rates`. The list a screen may state is
            # a narrower thing than the table: it excludes the base currency,
            # whose row is arithmetic rather than an observation, and it is
            # bounded by `CURRENCIES` so an upstream feed's response body does
            # not decide the size of the operator's panel. Both rules live in
            # `fx` because they hold for every reader, and this route was the
            # second half of the seam CQ-19 names.
            "stored": fx.reference_rates(conn),
            "model_prices": [dict(r) for r in conn.execute(
                "SELECT * FROM model_prices ORDER BY model")],
            # Stated rather than left to be discovered: an operator who sees
            # tokens everywhere should be told what would make them money.
            "note": ("Costs show as tokens until a model price is known. "
                     "Claude prices can be read from Anthropic's published "
                     "pricing page; anything else is entered by hand. Either "
                     "way the source and date are recorded, and a fetch never "
                     "overwrites a price you typed."),
            "prices_url": model_prices.PRICES_URL,
        }

    @app.get("/api/prefs/age")
    def age_thresholds(conn=dep, operator=op_dep):
        """When a measurement's date says it may be, or is, out of date (item
        239 step 6): the operator's two ages in days, and the defaults."""
        from clauditseo.persistence import age
        return age.thresholds(conn)

    @app.put("/api/prefs/age")
    def set_age_thresholds(body: AgeThresholdsIn, conn=dep, operator=op_dep):
        from clauditseo.persistence import age
        try:
            return age.set_thresholds(conn, body.warn_days, body.stale_days)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    @app.put("/api/rates/currency")
    def set_currency(body: CurrencyIn, conn=dep, operator=op_dep):
        from clauditseo.providers import fx
        try:
            fx.set_display_currency(conn, body.currency)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        return {"display_currency": fx.display_currency(conn),
                "rate": fx.rate_for(conn, body.currency)}

    @app.get("/api/keys", dependencies=guarded)
    def provider_keys():
        """Which credentials are set, where each came from, and nothing more.

        The values never leave the server. What comes back is the last four
        characters, which is enough to tell one key from another when
        deciding whether to replace it and useless for anything else.

        `env_present` is reported alongside `stored` because the store wins:
        an operator who cannot see that a variable is also set in their
        environment has no way to explain why removing the stored key changes
        behaviour rather than disabling the provider.
        """
        from clauditseo import secrets as secret_store
        from clauditseo.config import from_environment
        stored = secret_store.load()
        out = []
        for managed in secret_store.MANAGED:
            in_env = bool(from_environment(managed.name))
            value = stored.get(managed.name, "")
            out.append({
                "name": managed.name,
                "provider": managed.provider,
                "detail": managed.detail,
                "obtain": managed.obtain,
                "stored": bool(value),
                "masked": secret_store.mask(value) if value else None,
                "env_present": bool(in_env),
                "overriding_env": bool(value and in_env),
                "configured": bool(value or in_env),
            })
        return {
            "keys": out,
            "file": str(secret_store.path()),
            # None, not False, when nothing has been stored yet. There is no
            # file to protect before the first save, and reporting that as a
            # failed protection warns an operator about a store they have not
            # created — an alarm with nothing behind it teaches them to
            # ignore the one that matters.
            "protected": (secret_store.harden()
                          if secret_store.path().exists() else None),
            "note": ("Keys are stored beside the database, not in it, so a "
                     "database backup carries no credentials. The file is "
                     "plaintext, restricted to your user account. A key set "
                     "here is used in preference to the same variable in "
                     "your environment."),
        }

    @app.put("/api/keys/{name}", dependencies=guarded)
    def set_provider_key(name: str, body: ProviderKeyIn):
        from clauditseo import secrets as secret_store
        try:
            secret_store.put(name, body.value)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"{name} is not a managed key")
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        except OSError as exc:
            # Disk or permission failure. Said plainly, because the operator
            # would otherwise see a key that reads as saved and is not.
            raise HTTPException(status_code=500,
                                detail=f"could not write the key store: {exc}")
        return {"name": name, "stored": True,
                "masked": secret_store.mask(body.value.strip()),
                "protected": secret_store.harden()}

    @app.delete("/api/keys/{name}", dependencies=guarded)
    def clear_provider_key(name: str):
        """Forget a stored key. Any environment value takes over again."""
        from clauditseo import secrets as secret_store
        from clauditseo.config import from_environment
        if name not in secret_store.BY_NAME:
            raise HTTPException(status_code=404, detail=f"{name} is not a managed key")
        try:
            removed = secret_store.drop(name)
        except OSError as exc:
            raise HTTPException(status_code=500,
                                detail=f"could not write the key store: {exc}")
        return {"name": name, "removed": removed,
                "falls_back_to_env": bool(from_environment(name))}

    @app.post("/api/rates/refresh")
    def refresh_rates(conn=dep, operator=op_dep):
        """Fetch today's ECB rates. Reports failure rather than raising: the
        operator pressed a button and is owed an answer either way, and a
        blip must not lose the rate already stored."""
        from clauditseo.providers import fx
        return fx.refresh(conn)

    @app.post("/api/rates/fetch-prices")
    def fetch_model_prices(conn=dep, operator=op_dep):
        """Read the published Claude prices and store them.

        Operator-entered rows are left alone — a negotiated rate is a fact
        about this customer that list price does not know.
        """
        from clauditseo.providers import model_prices
        return model_prices.refresh(
            conn, entered_by=actor_of(operator, "fetch-prices"))

    @app.put("/api/rates/model-price")
    def set_model_price(body: ModelPriceIn, conn=dep, operator=op_dep):
        """Store a price the operator typed, filed as theirs.

        CQ-200: `source` and `source_url` are set on **both** halves of the
        upsert, and the update half is the half that matters. A model nobody
        had fetched was always filed correctly, by the column's
        `NOT NULL DEFAULT 'operator'` — but an existing row kept whatever it
        already had, so a typed figure landed under the vendor's name holding
        the vendor's URL, and the next fetch destroyed it, because `refresh`
        keeps rows by `WHERE source='operator'` and the row never claimed to
        be one. On this install every one of the sixteen rows was in that
        state, so the easy case to try by hand was the only one that worked.

        `QUESTIONS.md` Q-11 asked whether the row should change hands here or
        the panel should refuse the overwrite and hold "published" and "yours"
        as two rows. The operator answered **one row that changes hands**: the
        schema forbids two — `model` is the PRIMARY KEY — and clearing the
        vendor URL costs no divergence figure, because `refresh` compares a
        kept price against the prices it has just fetched rather than against
        a published figure held on file.

        The literal `'operator'` is the same string as
        `providers/model_prices.py`'s keep filter and migration 0014's column
        default. Three sites, and they have to agree; the defect above was
        exactly what their disagreeing looks like.
        """
        from clauditseo.persistence.repo import now_iso
        with conn:
            conn.execute(
                "INSERT INTO model_prices (model, input_usd, output_usd,"
                " entered_at, entered_by, source, source_url)"
                " VALUES (?, ?, ?, ?, ?, 'operator', NULL)"
                " ON CONFLICT(model) DO UPDATE SET input_usd=excluded.input_usd,"
                " output_usd=excluded.output_usd, entered_at=excluded.entered_at,"
                " entered_by=excluded.entered_by,"
                " source=excluded.source, source_url=excluded.source_url",
                (body.model, body.input_usd, body.output_usd, now_iso(),
                 actor_of(operator, "set-model-price")))
        return {"ok": True, "model": body.model}

    @app.delete("/api/rates/model-price/{model}")
    def clear_model_price(model: str, conn=dep, operator=op_dep):
        with conn:
            conn.execute("DELETE FROM model_prices WHERE model=?", (model,))
        return {"ok": True}

    # -- history chat -------------------------------------------------------

    @app.post("/api/chat")
    def history_chat(body: ChatIn, conn=dep, operator=op_dep):
        if not repo.get_site(conn, body.site_id):
            raise HTTPException(status_code=404, detail="site not found")
        check_site(conn, operator, body.site_id)
        return chat_module.answer(conn, body.site_id, body.question)

    if DASHBOARD_DIST.exists():
        app.mount("/", StaticFiles(directory=DASHBOARD_DIST, html=True), name="dashboard")

    return app


def _execute_run(db_path: Path, run_id: str, site_row: dict, dims: list[str],
                 tier_name: str, analyst: bool, start_url: str,
                 model: str | None = None, nav_only: bool = False,
                 scope: str | None = None) -> None:
    """Background worker: own DB connection, never shares the request's."""
    conn = connect(db_path)
    cfg = settings()
    try:
        _RUN_SEMAPHORE.acquire()
        # The whole site record, not four of its fields: the checks read
        # record inputs through `context["site"]` (`ai_crawler_policy`, the
        # URL thresholds), and a Site built from domain, locale, business type
        # and market handed every one of them its default. Found by item 145
        # BG's twenty22 acceptance run, where a stated `block` policy still
        # raised HIGH.
        site = site_of(repo.site_record(site_row))
        if tier_name == "auto":
            from clauditseo.adaptive import run_adaptive
            # The operator's scope goes to both paths. It was handed to
            # the by-hand branch below and not to this one, so an adaptive
            # run escalated its way from one page to a hundred and
            # forty-five (relay item 136a).
            run_adaptive(conn, run_id, site, site_row["id"], start_url, cfg,
                         dims, model=model, analyst=analyst, scope=scope,
                         should_stop=lambda: runs.stop_requested(run_id))
            return

        def note(label: str, replace_last: bool = False) -> None:
            runs.add_progress(conn, run_id, label, replace_last)

        tier = Tier(tier_name)
        kw = crawl_kwargs(scope, tier, start_url)
        # A named scope decides the frontier, so it also decides what the
        # progress line calls the crawl. Saying "T2" while fetching one page
        # is how the old control came to mean two things.
        how = (SCOPES[scope].label.lower() if scope
               else "the navigation" if nav_only else tier.value)
        note(f"Crawling {how}")
        crawl_result = crawl_site(start_url, tier,
                                  security_paths="SEC" in dims,
                                  # Item 151: sampled, or every page where
                                  # the site's previous run diverged.
                                  mobile_parity=runs.parity_mode(
                                      conn, site_row["id"], run_id),
                                  nav_only=kw.pop("nav_only", nav_only),
                                  # The audit's own crawl buys the UA matrix,
                                  # as the adaptive deep crawl does; `crawl`
                                  # still runs it only on a site scope at T2+.
                                  # A chosen scope (Site, Full) crawled without
                                  # it, so every such audit left the matrix,
                                  # and edge-blocks-ai-ua, unmeasured.
                                  ua_matrix=True,
                                  on_progress=lambda n: note(
                                      f"Crawling {how}: {n} page(s) fetched",
                                      replace_last=n > 1),
                                  should_stop=lambda: runs.stop_requested(run_id),
                                  **kw)
        # The operator changed their mind. What was fetched is kept and the
        # run says so; nothing is scored, because a crawl somebody stopped
        # is not a measurement of the site (relay item 136a).
        if crawl_result.truncated_by == "cancelled":
            note(f"Stopped by the operator after {len(crawl_result.pages)} "
                 "page(s) fetched")
            from clauditseo.crawler.evidence import snapshot
            runs.store_evidence(conn, run_id, snapshot(crawl_result))
            runs.cancel_run(conn, run_id, len(crawl_result.pages))
            return
        if nav_only:
            note(f"Navigation crawl: {len(crawl_result.pages)} page(s) — the "
                 "entry page and what its menu links to")
        # The measurements only a browser can take (brief v15), before the
        # checks rather than after: the sweep judges an image against the
        # width it renders at and the weight it arrives with, so it has to
        # be handed the same numbers the stored inventory keeps. The audit
        # is the run that takes them - a verification and a section refresh
        # re-crawl a few pages to answer a narrower question, and a browser
        # pass on those would cost the operator time for a number nobody
        # asked for. Absent where Playwright is not installed, and both the
        # sweep and the inventory then say so rather than carrying a value
        # nobody took.
        # One pass for both launchers (item 205), and whether it ran.
        from clauditseo import imaging
        measured, images_state = imaging.measure_for_run(
            crawl_result, (repo.site_record(site_row) if isinstance(site_row, dict) else {}) or {},
            note)
        # The performance trace (brief v19 step BC): a separate browser pass
        # under the fixed device profile (mid-tier mobile, 4G), so its
        # throttling does not move the image numbers above. On by default since
        # the depth-pill stage; `CLAUDITSEO_TRACE_PERF=0` turns it off, and the
        # Speed free checks then read `{"traced": False}` and say the trace was
        # not taken rather than reporting a value nobody measured.
        #
        # The sample is announced BEFORE the pass, not after: it is the one
        # thing about this step an operator watching the run would otherwise
        # have to infer from how long it takes.
        from clauditseo import perf
        note("Tracing performance in a throttled browser" if perf.available()
             else "No renderer installed: performance not traced")
        traced, trace_rule = _trace_perf(crawl_result, run_id)
        note(f"Traced {len(traced)} page(s) - {trace_rule}")
        note(f"Running deterministic checks ({len(dims)} dimension(s))")
        result = run_audit(site, crawl_result, dims, tier,
                           context={"providers": ProviderHub.from_settings(cfg),
                                    # `PRIOR_RUN` and what it recorded
                                    # (items 136k, 136p). One notion of
                                    # "the previous run", not two.
                                    "prior_run": (_prior := runs.prior_run(
                                        conn, site_row["id"], run_id)),
                                    "prior_pages": runs.content_hashes(
                                        conn, (_prior or {}).get("run_id")),
                                    # Brief v18 step AZ: sitemap-regression's
                                    # baseline, silent when there is no prior.
                                    "prior_sitemap": runs.prior_sitemap(
                                        conn, (_prior or {}).get("run_id")),
                                    "image_measurements": measured,
                                    "perf_traces": traced,
                                    "run_id": run_id})
        from clauditseo.crawler.evidence import snapshot
        evidence = snapshot(crawl_result, measured, traced, trace_rule)
        evidence["images_measured"] = images_state
        runs.store_evidence(conn, run_id, evidence)
        outcome = run_analyst_layer(conn, run_id, site.domain, result, crawl_result,
                                    cfg, enabled=analyst, announce=note,
                                    provider=provider_from_settings(cfg, model))
        if outcome.ran:
            result.findings.extend(outcome.security_findings)
            result.findings.extend(outcome.findings)
        note("Saving results and updating finding states")
        runs.complete_run(conn, run_id, result)
    except Exception as exc:  # persisted, surfaced in the dashboard
        runs.fail_run(conn, run_id, str(exc))
    finally:
        _RUN_SEMAPHORE.release()
        conn.close()
