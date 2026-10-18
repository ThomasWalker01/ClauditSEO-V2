-- The latest `findings` row for a fingerprint, found without a sort.
--
-- `runs.LATEST_FINDING` is a correlated subquery run once per finding state:
-- the rows of one fingerprint, newest first by `created_at` then `rowid`, the
-- first one on the site. With only `idx_findings_fingerprint` to use, SQLite
-- fetched each fingerprint's rows and sorted them in a temporary B-tree every
-- time. The anatomy view runs it four times per request - open and candidate
-- states, the fix order, `current_state` - at ~9 ms each on twenty22.
--
-- Ordered by (fingerprint, created_at), ascending: an index entry also carries
-- its rowid, so walking it backwards yields `created_at DESC, rowid DESC` and
-- the sort disappears from the plan (9.0 ms -> 1.5 ms on a copy of the
-- operator's database). Declared `created_at DESC` it still sorted the rowid.
--
-- Additive only: no row changes, and `idx_findings_fingerprint` stays - this
-- index would serve its queries too, but dropping one is a separate decision.
CREATE INDEX IF NOT EXISTS idx_findings_fingerprint_created
    ON findings(fingerprint, created_at);
