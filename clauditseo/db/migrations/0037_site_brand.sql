-- Brief v11 step AI: the brand a site's copy carries, on the record.
-- The Title & description brief wrote replacement titles with a brand it
-- took from the pages' own title tails; the record held none. NULL means
-- not set, and the runner then falls back to the tails and says so.
ALTER TABLE sites ADD COLUMN brand TEXT;
