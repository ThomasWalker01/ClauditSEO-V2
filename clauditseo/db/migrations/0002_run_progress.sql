-- Live progress for running audits: JSON list of {label, at} steps written
-- by the worker as it moves through crawl → plan → checks → analysts → save.
ALTER TABLE audit_runs ADD COLUMN progress TEXT;
