-- The precheck: what a site says about itself, read before a scan is chosen.
--
-- One row per run, not one per site. The newest row is what the scan screen
-- reads, and the history is kept because navigation churn is itself a signal:
-- a header that lost four links between two prechecks is worth seeing, and a
-- table that overwrote itself could never show it.
--
-- `payload_json` rather than a column per figure. The shape is still settling
-- (the `site` scope's cap is an open question at the time of writing), and a
-- migration per field while a feature finds its shape is how a schema ends up
-- carrying columns nothing reads. The figures the product filters or sorts on
-- get promoted to columns when there are any; today it reads the newest row
-- whole.

CREATE TABLE IF NOT EXISTS prechecks (
    id          TEXT PRIMARY KEY,
    site_id     TEXT NOT NULL,
    checked_at  TEXT NOT NULL,
    entry_url   TEXT NOT NULL,
    took_ms     INTEGER,
    -- Denormalised out of the payload so "has this site ever had a readable
    -- sitemap" is answerable without parsing every row.
    sitemap_state TEXT NOT NULL,
    payload_json  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_prechecks_site_time
    ON prechecks (site_id, checked_at DESC);
