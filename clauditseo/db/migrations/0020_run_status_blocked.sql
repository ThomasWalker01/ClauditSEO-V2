-- Add 'blocked' to the run status vocabulary.
--
-- A crawl that fetched zero pages — a blanket Disallow, a 5xx on robots.txt,
-- an unreachable host — currently stores as 'complete', which is how a site
-- that was never retrieved acquired a scored client deliverable. 'blocked' is
-- a terminal status meaning the crawl reached a definite answer and that
-- answer was "you may not look". It is not a failure: the run has real
-- site-level findings and often the most valuable one an audit can return.
--
-- This migration widens the CHECK constraint and nothing else. No code writes
-- 'blocked' yet, so applying it changes no behaviour and no stored row moves.
--
-- SQLite cannot alter a CHECK constraint, so the table is rebuilt by the
-- procedure in the SQLite docs' "Making Other Kinds Of Table Schema Changes":
-- create the replacement under a new name, copy, drop the original, rename.
-- The order matters. Renaming the ORIGINAL out of the way first would be the
-- obvious move and is the wrong one: since 3.25 an ALTER TABLE ... RENAME
-- rewrites references to that table in every other table's foreign keys, so
-- `audit_runs` -> `audit_runs_old` would silently repoint findings,
-- cost_entries, expert_reports and finding_states at the table about to be
-- dropped. Renaming `audit_runs_new` -> `audit_runs` rewrites nothing,
-- because nothing references the new name.
--
-- foreign_keys must be OFF for the DROP. Enforcement is ON for every
-- connection (see db/connection.py), and DROP TABLE performs an implicit
-- DELETE FROM: expert_reports.run_id is ON DELETE CASCADE, so dropping the
-- original with enforcement on would take every stored brief with it. The
-- pragma is a no-op inside a transaction, which is why the BEGIN comes after
-- it; `executescript` commits any open transaction before running this file,
-- so it takes effect.
PRAGMA foreign_keys = OFF;

BEGIN;

CREATE TABLE audit_runs_new (
    id              TEXT PRIMARY KEY,
    site_id         TEXT NOT NULL REFERENCES sites(id),
    dimensions      TEXT NOT NULL,  -- JSON list of dimension codes, e.g. ["ONP","TEC"]
    tier            TEXT NOT NULL CHECK (tier IN ('T1','T2','T3')),
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','running','complete','failed',
                                      'cancelled','blocked')),
    engine_version  TEXT NOT NULL,
    analyst_enabled INTEGER NOT NULL DEFAULT 0,
    composite_score REAL,           -- 0-100; NULL until scored, and NULL when
                                    -- no dimension carried measurable weight
    subscores       TEXT,           -- JSON {dimension: {score, weight, applicable}}
    started_at      TEXT,
    finished_at     TEXT,
    created_by      TEXT REFERENCES operators(id),
    created_at      TEXT NOT NULL,
    -- Added by 0002, 0003, 0004 and 0011 respectively. Spelled out here
    -- rather than left to ALTER, because a rebuild is the one moment the
    -- whole shape is visible in one place.
    progress        TEXT,
    error           TEXT,
    crawl_evidence  TEXT,
    kind            TEXT NOT NULL DEFAULT 'audit'
);

-- Columns named explicitly: a bare INSERT ... SELECT * silently depends on
-- column order matching, and the four ALTERed columns arrived in an order no
-- one chose.
INSERT INTO audit_runs_new (
    id, site_id, dimensions, tier, status, engine_version, analyst_enabled,
    composite_score, subscores, started_at, finished_at, created_by,
    created_at, progress, error, crawl_evidence, kind
)
SELECT
    id, site_id, dimensions, tier, status, engine_version, analyst_enabled,
    composite_score, subscores, started_at, finished_at, created_by,
    created_at, progress, error, crawl_evidence, kind
FROM audit_runs;

DROP TABLE audit_runs;

ALTER TABLE audit_runs_new RENAME TO audit_runs;

-- Indexes do not survive the drop. This is the one from 0011; the primary
-- key's implicit index is recreated by the PRIMARY KEY declaration above.
CREATE INDEX IF NOT EXISTS idx_audit_runs_kind
    ON audit_runs(site_id, kind, started_at DESC);

COMMIT;

PRAGMA foreign_keys = ON;
