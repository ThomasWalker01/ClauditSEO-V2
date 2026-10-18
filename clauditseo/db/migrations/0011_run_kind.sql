-- A verification pass is not an audit, and must not be scored as one.
--
-- Verifying a fix re-crawls only the pages behind the findings being checked
-- — two or four pages, not a hundred. That is exactly what makes it cheap and
-- exactly what makes its composite score meaningless: a score computed over
-- two pages is not comparable with one computed over the site, and letting it
-- into the trend would put a cliff in the chart every time someone ticked a
-- box.
--
-- Worse, two things compare consecutive runs directly. `watch_changes` reads
-- the last two crawls and would compare a 2-page verification against a full
-- audit — the same shape as the sitemap-total bug, where a partial crawl's
-- numbers were read as the site changing. And `current_state` reports what
-- "the last audit" opened and closed, which a verification would answer for
-- with a handful of pages.
--
-- So runs carry what they are. Everything that scores, trends or compares
-- filters to kind='audit'; the verification still applies state transitions,
-- which is the whole point of running it.
ALTER TABLE audit_runs ADD COLUMN kind TEXT NOT NULL DEFAULT 'audit';

CREATE INDEX IF NOT EXISTS idx_audit_runs_kind
    ON audit_runs(site_id, kind, started_at DESC);
