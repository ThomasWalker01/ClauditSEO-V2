-- A metric snapshot names the run that wrote it.
--
-- `metric_snapshots` has carried no run column since it was created, and
-- `(site_id, captured_at)` has been the only handle on a row ever since. That
-- handle is second-resolution: two runs of one site finishing in the same
-- second are one group in it, which `_recoverable_dimension_sets` already
-- documents refusing to merge and `run_measured_share` already documents
-- joining around. Every one of those readers is working out which run a row
-- belongs to from a stamp, and none of them can do it exactly.
--
-- Brief v16f needs it exactly. A trend point now says which earlier run it
-- reads against — `partner_run_id` — and the Runs table's comparison link is
-- built from that answer, so a stamp shared by two runs would not merely blur
-- a chart, it would offer the operator a comparison against the wrong audit or
-- silently offer none.
--
-- The backfill claims only what it can prove. A row whose stamp names exactly
-- one run of its site is that run's; a row whose stamp names two, or none,
-- keeps NULL and is read back through the stamp join at the rung below, where
-- the same refusal applies. Nothing is guessed, so a database migrated by this
-- file says exactly what it said before about every ambiguous row.
ALTER TABLE metric_snapshots ADD COLUMN run_id TEXT REFERENCES audit_runs(id);

CREATE INDEX IF NOT EXISTS idx_metric_snapshots_run ON metric_snapshots(run_id);

UPDATE metric_snapshots
   SET run_id = (SELECT r.id FROM audit_runs r
                  WHERE r.site_id = metric_snapshots.site_id
                    AND r.finished_at = metric_snapshots.captured_at)
 WHERE run_id IS NULL
   AND (SELECT COUNT(*) FROM audit_runs r
         WHERE r.site_id = metric_snapshots.site_id
           AND r.finished_at = metric_snapshots.captured_at) = 1;
