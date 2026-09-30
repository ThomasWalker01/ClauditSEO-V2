-- Page advice, stored against the run and the page so it can be read back.
--
-- The judgement already survived in analyst_cache, but that table is keyed on
-- task#cache_version + model_id + bundle_hash, and the bundle is assembled
-- from a live fetch of the page. Whether a hit exists is therefore unknowable
-- without performing the fetch and the assembly -- which is most of what
-- POST /api/runs/{id}/advise does -- so "has this page been advised" had no
-- cheap answer and the panel offered to generate advice that already existed.
--
-- Worse for the workflow: the hash changes the moment the operator edits the
-- page in response to the advice, which is the point of producing it. A
-- read-back keyed on the evidence would go blank exactly when the advice was
-- acted on.
--
-- Keyed on (run_id, url) instead, following expert_reports (0005): one row per
-- page per run, and re-advising the same page in the same run replaces its
-- row rather than accumulating history -- which matches how that table and
-- the findings behave.
CREATE TABLE IF NOT EXISTS page_advice (
    run_id      TEXT NOT NULL REFERENCES audit_runs(id) ON DELETE CASCADE,
    url         TEXT NOT NULL,
    model_id    TEXT,
    -- Always the full remit. A scope narrows the answer on the way out
    -- (F-03), so what is stored must be wider than any one section's view or
    -- re-entering a different section would read a truncated judgement.
    advice      TEXT NOT NULL,
    tokens      INTEGER,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (run_id, url)
);

CREATE INDEX IF NOT EXISTS idx_page_advice_run ON page_advice(run_id);
