-- The input/output split for a brief, not just the total.
--
-- Both numbers are computed on every call and only their sum was stored, so a
-- stored cost could not be checked against anything: input and output differ
-- by five times in price, and one total cannot be reconstructed into the two
-- figures that produced the money.
--
-- The 23 briefs already stored keep NULL. Their split was never recorded and
-- deriving it from the total would mean inventing a ratio — the exact move
-- this codebase keeps refusing. A cost for those rows stays absent.
ALTER TABLE expert_reports ADD COLUMN tokens_in INTEGER;
ALTER TABLE expert_reports ADD COLUMN tokens_out INTEGER;
