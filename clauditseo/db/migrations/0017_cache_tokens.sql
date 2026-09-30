-- What the prompt cache did for a brief.
--
-- The evidence bundle is resent on every round of the tool loop, so a
-- multi-round brief paid for it once per round at full input price. It is now
-- cached, which introduces two token buckets the API bills separately: writes
-- at 1.25x the base input rate and reads at 0.1x.
--
-- Recorded rather than folded into `tokens`, because the saving is only
-- visible as a ratio between them. A brief whose `cache_read` stays zero
-- across runs is not saving anything, and without the column there is no way
-- to notice.
ALTER TABLE expert_reports ADD COLUMN cache_write INTEGER;
ALTER TABLE expert_reports ADD COLUMN cache_read INTEGER;
