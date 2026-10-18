-- Brief v18 step AY: what the client plan reads from the site record
-- beside the run.
--
-- The plan is the only brief whose inputs are decisions rather than
-- measurements. How much effort goes to existing pages rather than new
-- ones, what the horizons are called, which workstreams the client
-- recognises, how much they can absorb in a sprint, and what can be
-- measured at all - none of that is on the site, and none of it can be
-- inferred from a crawl. Registered here so the plan asks the record
-- instead of asking the model to assume.
--
-- Every one of them is registered empty on purpose and the prompt states
-- its own fallback: 60-70 % on existing, Now/Next/Later, content ·
-- entity · structural · technical, no capacity stated. A default that
-- lived in the column would be indistinguishable from the operator
-- having chosen it, and the plan prints its defaults as assumptions -
-- which it can only do while absence stays legible.
--
-- `measure_sources` is the one that changes what the document says. Empty
-- means no analytics is connected, and "How we will know" then measures
-- rows closed on the Record rather than naming a metric nobody can read.
-- Today it is empty for every site, and the plan is written to say so
-- rather than to promise traffic.
--
-- Scalars as text, lists as JSON text. NULL means not set.
ALTER TABLE sites ADD COLUMN optimisation_ratio TEXT;  -- e.g. "60-70" (% on existing pages)
ALTER TABLE sites ADD COLUMN horizons TEXT;            -- JSON list: Now/Next/Later, or 30/60/90
ALTER TABLE sites ADD COLUMN workstreams TEXT;         -- JSON list: content, entity, structural, technical
ALTER TABLE sites ADD COLUMN capacity TEXT;            -- hours or pages per sprint
ALTER TABLE sites ADD COLUMN measure_sources TEXT;     -- JSON list: GSC | GA4; empty means none
