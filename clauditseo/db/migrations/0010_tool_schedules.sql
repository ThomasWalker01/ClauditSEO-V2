-- Per-tool schedules.
--
-- sites.schedule already says "audit this site weekly", which runs the whole
-- deterministic sweep. That is the wrong granularity for the expert briefs:
-- they cost money per run, and an operator wants the cheap dispatcher weekly
-- and an expensive site-wide brief quarterly, not all of them or none.
--
-- last_run_at is stored rather than derived. A brief's stored result is
-- keyed to an audit run, and runs get deleted with their client, so deriving
-- "when did this last fire" from results would silently reset a cadence.

CREATE TABLE IF NOT EXISTS tool_schedules (
    site_id     TEXT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    tool_id     TEXT NOT NULL,
    cadence     TEXT NOT NULL,          -- weekly | fortnightly | monthly | quarterly
    last_run_at TEXT,                   -- set when the scheduler fires it
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (site_id, tool_id)
);

CREATE INDEX IF NOT EXISTS idx_tool_schedules_site ON tool_schedules(site_id);
