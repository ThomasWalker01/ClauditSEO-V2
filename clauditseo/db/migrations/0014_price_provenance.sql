-- Where a model price came from.
--
-- The first version of this table assumed every price was typed in by an
-- operator, on the reasoning that no vendor publishes a machine-readable
-- price feed. That was wrong: Anthropic serves
-- `/docs/en/about-claude/pricing.md` as text/markdown, and the model table in
-- it parses cleanly.
--
-- It matters because a hand-typed price goes stale silently. The operator's
-- own entry for claude-sonnet-5 was $3/$15 within an hour of the published
-- figure being $2/$10 — the introductory rate had become the standard one.
-- A wrong price does not announce itself; it just quietly misprices every
-- brief in the estimate table.
--
-- 'operator' rows are never overwritten by a fetch. A negotiated or
-- enterprise rate is a fact about the customer that list price does not know,
-- and clobbering it with the public number would be the same class of error
-- in the other direction.
ALTER TABLE model_prices ADD COLUMN source TEXT NOT NULL DEFAULT 'operator';
ALTER TABLE model_prices ADD COLUMN source_url TEXT;
