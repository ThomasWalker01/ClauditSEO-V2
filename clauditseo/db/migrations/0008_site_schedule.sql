-- Recurring audits. History only accumulates if runs happen, and every
-- memory feature is only as good as the runs behind it.
-- schedule: 'weekly' | 'monthly' | NULL (manual only).
ALTER TABLE sites ADD COLUMN schedule TEXT;
