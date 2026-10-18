-- Expert brief results, stored against the run they were produced for.
--
-- Until now a report existed only in analyst_cache, which is keyed on the
-- evidence rather than the run, so "show me the latest result for this tool on
-- this site" was unanswerable and a report vanished from the UI as soon as the
-- page was closed. Findings were already run-scoped; the prose was not.
--
-- One row per (run, tool): re-running a brief replaces its result rather than
-- accumulating versions, which matches how the findings are written.
CREATE TABLE IF NOT EXISTS expert_reports (
    run_id      TEXT NOT NULL REFERENCES audit_runs(id) ON DELETE CASCADE,
    tool_id     TEXT NOT NULL,
    model_id    TEXT,
    page_url    TEXT,              -- page-scoped briefs: which page was read
    report      TEXT NOT NULL,
    findings    TEXT NOT NULL DEFAULT '[]',
    figures     TEXT NOT NULL DEFAULT '[]',
    tokens      INTEGER,
    cost        REAL,              -- null unless the operator supplied rates
    truncated   INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (run_id, tool_id)
);

CREATE INDEX IF NOT EXISTS idx_expert_reports_run ON expert_reports(run_id);
