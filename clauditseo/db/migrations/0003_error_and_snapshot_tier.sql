-- Failure reasons get their own column (they were stuffed into subscores),
-- and metric snapshots record the tier that produced them so a trend can
-- distinguish a 3-page pulse from a 500-page deep crawl.
ALTER TABLE audit_runs ADD COLUMN error TEXT;
ALTER TABLE metric_snapshots ADD COLUMN tier TEXT;
