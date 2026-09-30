-- AuditDeck initial schema.
--
-- Multi-operator readiness: `operators` exists from day one and every
-- client row carries owner_id. v1 runs single-operator (one seeded owner,
-- token auth); P9 adds real accounts/roles without a schema rewrite.

CREATE TABLE operators (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    email       TEXT,
    role        TEXT NOT NULL DEFAULT 'owner',  -- owner | member (P9 enforces)
    token_hash  TEXT,                           -- sha256 of the login token; never the token itself
    created_at  TEXT NOT NULL,
    archived_at TEXT
);

CREATE TABLE clients (
    id          TEXT PRIMARY KEY,
    owner_id    TEXT NOT NULL REFERENCES operators(id),
    name        TEXT NOT NULL,
    contacts    TEXT,   -- JSON list of {name, email, phone}
    notes       TEXT,
    created_at  TEXT NOT NULL,
    archived_at TEXT
);

CREATE TABLE sites (
    id            TEXT PRIMARY KEY,
    client_id     TEXT NOT NULL REFERENCES clients(id),
    domain        TEXT NOT NULL,
    locale        TEXT NOT NULL DEFAULT 'en-AU',
    business_type TEXT,   -- e.g. local-service | ecommerce | saas | publisher
    target_market TEXT,
    created_at    TEXT NOT NULL,
    archived_at   TEXT
);

CREATE TABLE audit_runs (
    id              TEXT PRIMARY KEY,
    site_id         TEXT NOT NULL REFERENCES sites(id),
    dimensions      TEXT NOT NULL,  -- JSON list of dimension codes, e.g. ["ONP","TEC"]
    tier            TEXT NOT NULL CHECK (tier IN ('T1','T2','T3')),
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','running','complete','failed','cancelled')),
    engine_version  TEXT NOT NULL,
    analyst_enabled INTEGER NOT NULL DEFAULT 0,
    composite_score REAL,           -- 0-100; NULL until scored
    subscores       TEXT,           -- JSON {dimension: {score, weight, applicable}}
    started_at      TEXT,
    finished_at     TEXT,
    created_by      TEXT REFERENCES operators(id),
    created_at      TEXT NOT NULL
);

-- Cost log for any paid API or LLM call made during a run.
CREATE TABLE cost_entries (
    id         TEXT PRIMARY KEY,
    run_id     TEXT NOT NULL REFERENCES audit_runs(id),
    provider   TEXT NOT NULL,   -- e.g. pagespeed | dataforseo | anthropic
    operation  TEXT NOT NULL,
    units      TEXT NOT NULL,   -- e.g. calls | tokens
    quantity   REAL NOT NULL,
    est_cost   REAL,            -- estimate shown before spend, if any
    actual_cost REAL,
    created_at TEXT NOT NULL
);

CREATE TABLE findings (
    id             TEXT PRIMARY KEY,
    run_id         TEXT NOT NULL REFERENCES audit_runs(id),
    dimension      TEXT NOT NULL,
    check_id       TEXT NOT NULL,
    severity       TEXT NOT NULL
                   CHECK (severity IN ('critical','high','medium','low','info')),
    source         TEXT NOT NULL DEFAULT 'deterministic'
                   CHECK (source IN ('deterministic','model-judgement')),
    model_id       TEXT,           -- set when source = model-judgement
    confidence     TEXT,           -- high | medium | low
    summary        TEXT NOT NULL,
    affected_urls  TEXT,           -- JSON list
    evidence       TEXT,           -- JSON payload; analyst findings must cite evidence ids
    recommendation TEXT,
    fingerprint    TEXT NOT NULL,  -- hash(dimension + check_id + normalised subject)
    created_at     TEXT NOT NULL
);
CREATE INDEX idx_findings_run ON findings(run_id);
CREATE INDEX idx_findings_fingerprint ON findings(fingerprint);

-- Lifecycle of a fingerprint on a site. Regression = previously fixed, seen again.
CREATE TABLE finding_states (
    site_id            TEXT NOT NULL REFERENCES sites(id),
    fingerprint        TEXT NOT NULL,
    state              TEXT NOT NULL
                       CHECK (state IN ('open','fixed','regressed','accepted-risk')),
    changed_by_run     TEXT REFERENCES audit_runs(id),
    updated_at         TEXT NOT NULL,
    PRIMARY KEY (site_id, fingerprint)
);

-- Time-series backbone for trend charts.
CREATE TABLE metric_snapshots (
    id          TEXT PRIMARY KEY,
    site_id     TEXT NOT NULL REFERENCES sites(id),
    metric_key  TEXT NOT NULL,   -- e.g. composite_score | tec.subscore | prf.lcp_ms
    value       REAL,
    value_text  TEXT,            -- for non-numeric metrics; exactly one of value/value_text set
    source      TEXT NOT NULL,   -- e.g. engine | pagespeed-api | crux
    confidence  TEXT NOT NULL,   -- high | medium | low
    captured_at TEXT NOT NULL
);
CREATE INDEX idx_snapshots_site_metric ON metric_snapshots(site_id, metric_key, captured_at);

CREATE TABLE reports (
    id         TEXT PRIMARY KEY,
    site_id    TEXT NOT NULL REFERENCES sites(id),
    run_ids    TEXT NOT NULL,   -- JSON list of the run(s) the report covers
    template   TEXT NOT NULL,   -- run | comparison | monthly-trend
    audience   TEXT NOT NULL CHECK (audience IN ('client','internal')),
    path       TEXT NOT NULL,   -- rendered file on disk
    created_at TEXT NOT NULL
);

-- Analyst result cache: (task, model, evidence-bundle hash) -> result.
-- Re-opening a run or re-rendering a report spends zero tokens.
CREATE TABLE analyst_cache (
    task        TEXT NOT NULL,
    model_id    TEXT NOT NULL,
    bundle_hash TEXT NOT NULL,
    result      TEXT NOT NULL,   -- JSON list of findings as returned
    tokens_in   INTEGER NOT NULL DEFAULT 0,
    tokens_out  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (task, model_id, bundle_hash)
);
