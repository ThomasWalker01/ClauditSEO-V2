-- What a run WAS, in the words it was chosen with.
--
-- `scan_` prefixed, and the prefix is load-bearing: `get_run` has assembled a
-- key called `scope` since 0.10.0's predecessor 0.6.0 meaning the CRAWL's
-- scope — pages fetched and URLs reached — and a column of the same name would
-- have shadowed it silently in the assembled row. Two different meanings of
-- one word in one dict is a defect that reads as working.
--
-- A run row recorded `tier` and a dimension list, so a completed audit could
-- only describe itself as "T1 — TEC, ONP, A11Y, PRF, CNT, LOC, AIS". That is
-- the vocabulary of the engine, not of the person who pressed the button, and
-- it does not say the one thing they would ask first: how much of the site was
-- this, and how hard did it look?
--
-- Both are NULL for every run made before the chooser existed, and NULL is
-- the honest value: those runs were not chosen on these axes and inventing a
-- scope for them would put a claim in the record that nobody made. The screen
-- falls back to the tier line for those, which is what they were actually
-- described by at the time.

ALTER TABLE audit_runs ADD COLUMN scan_scope TEXT;  -- page | nav | site | full
ALTER TABLE audit_runs ADD COLUMN scan_depth TEXT;  -- quick | standard | deep
-- The single URL a `page` scope read. Kept beside the scope rather than
-- derived from the crawl, because a run that fetched nothing still knows what
-- it was pointed at, and "which page was this?" is unanswerable afterwards
-- from an empty page list.
ALTER TABLE audit_runs ADD COLUMN scan_url TEXT;
