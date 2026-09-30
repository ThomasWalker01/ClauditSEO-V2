-- Item 170 ("find and deliver: finish the fold"), channel ruling
-- 20260917-0250: what a client report was built over, recorded when it was
-- built.
--
-- The Deliver chapter has to say whether a report went out ahead of the
-- assessing it describes. `finding_states` keeps one current row per
-- fingerprint and no history, so that cannot be reconstructed afterwards: the
-- honest version is to write it down at generation. The counts use the one
-- existing rule - unassessed is state `open`, on the run's fingerprints
-- (`runs.unassessed_severe`, `runs.run_assessed`) - so the stored numbers and
-- the live integrity line cannot mean different things.
--
--   unassessed_severe  Critical and High still open when the report was built.
--                      Zero for every client report since 1efbe9a (2026-09-13),
--                      which refuses to build one otherwise.
--   unassessed_total   every finding still open, any severity. Minus the
--                      above, it is what went out unassessed BELOW the guard:
--                      the threshold is Critical and High only, deliberately.
--   assessed_pct       the run's assessed share at that moment.
--
-- NULL on every row written before this migration, and on documents adopted
-- from disk (`adopt_orphans`), which were not generated here. NULL means "not
-- recorded", never zero.
ALTER TABLE reports ADD COLUMN unassessed_severe INTEGER;
ALTER TABLE reports ADD COLUMN unassessed_total INTEGER;
ALTER TABLE reports ADD COLUMN assessed_pct INTEGER;
