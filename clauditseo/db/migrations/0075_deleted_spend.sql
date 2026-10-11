-- Spend on runs since deleted (channel ruling 20261011-0746, screen audits
-- round 3, Admin IP-01).
--
-- Deleting a run, a site or a client deletes its `cost_entries`, so the
-- month's total, the per-client rows and the cap warning all fell by tokens
-- that were billed. Every delete path now adds the doomed rows to this tally
-- first, by the operator-local month each was spent in. It names no client,
-- site or run: a delete still removes every trace of what was deleted, and
-- the money it cost stays counted.
--
--   month     YYYY-MM, the operator's local month of each cost row
--   tokens    quantity summed
--   usd       actual_cost summed over the priced rows
--   priced    rows with an actual_cost
--   unpriced  rows without one
--   entries   rows in all
--
-- Not derived from rows that still exist, so a rebuild (item 239) leaves it
-- alone. Spend deleted before this migration is gone and cannot be rebuilt.
CREATE TABLE deleted_spend (
    month    TEXT PRIMARY KEY,
    tokens   REAL    NOT NULL DEFAULT 0,
    usd      REAL    NOT NULL DEFAULT 0,
    priced   INTEGER NOT NULL DEFAULT 0,
    unpriced INTEGER NOT NULL DEFAULT 0,
    entries  INTEGER NOT NULL DEFAULT 0
);
