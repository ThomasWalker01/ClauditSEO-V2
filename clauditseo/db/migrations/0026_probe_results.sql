-- What a probe measured, kept against the run whose brief raised the question.
--
-- A brief's `[TO CONFIRM: ...]` item is a question the analyst declined to
-- answer. F-05 lets the operator settle the ones this product can actually
-- measure, and an answer that is not stored settles nothing: the item would
-- read as confirmed until the panel unmounted and offer itself again on the
-- next visit, which is the defect F-04 removed for advice.
--
-- Keyed on (run_id, probe_id, target) following expert_reports (0005) and
-- page_advice (0024): one row per question per run, and re-running replaces
-- it rather than accumulating history. Re-running is the point -- a chain
-- fixed between two readings should show the fix, not sit under it.
--
-- Against the *run*, not the site, because that is what the acceptance
-- signal says: "records the result against that run". A measurement taken
-- today is not evidence about a crawl from last month, and a later run
-- asking the same question asks it again rather than inheriting an answer
-- whose subject may have changed underneath it.
--
-- `status` is measured | failed. A failure is stored deliberately: a
-- timeout is a fact about the attempt and the operator should see that it
-- was tried, but only `measured` renders the item as settled -- a probe
-- that could not reach the host has not confirmed anything.
--
-- Numbered 0026, and it drops before it creates. Both are because of the
-- same thing, and it is worth writing down rather than leaving as two odd
-- decisions.
--
-- An earlier, abandoned attempt at F-05 exists as a git stash (`ffca91d`,
-- 19 Aug 17:27, untracked files only). It carried its own
-- `0025_probe_results.sql` with a different shape -- keyed on
-- (run_id, tool_id, item_key) rather than (run_id, probe_id, target) -- and
-- it was applied to the operator's live database before the work was set
-- aside. So on that machine `probe_results` already existed, incompatibly,
-- and `0025_probe_results.sql` was already recorded in `schema_migrations`.
--
-- That combination is silent and total: a same-named migration is skipped
-- by filename, `CREATE TABLE IF NOT EXISTS` is skipped by name, and every
-- test passes because a fresh database has neither. The failure surfaced
-- only at the running product, as `no column named target` on the first
-- real probe.
--
-- Dropping is safe and is a rename rather than a deletion: the table had
-- never been written to -- 0 rows, because the feature that would write to
-- it is this one. A migration that assumed data would have to migrate it;
-- there is none, and saying so here is what stops a later reader adding a
-- copy step for rows that never existed.
DROP TABLE IF EXISTS probe_results;

CREATE TABLE IF NOT EXISTS probe_results (
    run_id      TEXT NOT NULL REFERENCES audit_runs(id) ON DELETE CASCADE,
    probe_id    TEXT NOT NULL,
    -- The host the probe ran against, resolved from the run's own site. It
    -- is stored because the answer is only about that host, and a site whose
    -- domain is later corrected must not appear to have measured the new one.
    target      TEXT NOT NULL,
    status      TEXT NOT NULL,
    -- One sentence, the operator's answer.
    value       TEXT NOT NULL,
    -- Where the answer came from, shown beside it. The item renders settled
    -- only with this attached: a measurement with no provenance is the thing
    -- the [TO CONFIRM] marker exists to prevent.
    source      TEXT NOT NULL,
    -- JSON: the full observation behind the sentence.
    detail      TEXT,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (run_id, probe_id, target)
);

CREATE INDEX IF NOT EXISTS idx_probe_results_run ON probe_results(run_id);
