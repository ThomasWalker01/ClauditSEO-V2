-- Item 239 step 7 (the operator's ruling, 2026-09-24): "The client report is
-- a frozen copy of The Latest View taken at generation, stored with the
-- report, with every section's dates." The document is already a file that
-- never changes; this is what it was built over - the composite, each
-- block's reference crawl, each analysis's newest run, the page items and
-- the open findings, each dated - kept beside it, because the Latest View
-- itself moves on with the next run. JSON; NULL on every report made before.
ALTER TABLE reports ADD COLUMN latest_view_copy TEXT;
