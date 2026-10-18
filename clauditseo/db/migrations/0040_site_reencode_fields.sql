-- Brief v16 step AU7: what "too heavy" means for one image, and what the
-- engine re-encodes at when it measures the saving.
--
-- The page budget (0039) is a budget for a page, so a heavy image below
-- the fold of an otherwise light page is inside it and says nothing. These
-- three are per image: a ceiling in kilobytes, a ceiling in bytes per
-- rendered pixel - a well-encoded photograph is under 0.5, and 1.0 is
-- generous - and the quality the probe encodes at.
--
-- Scalars as text, NULL meaning not set, with the engine's own defaults
-- stated where they are read: 300 KB, 1.0 bytes per pixel, quality 60.
ALTER TABLE sites ADD COLUMN budget_image_kb TEXT;    -- number as text
ALTER TABLE sites ADD COLUMN bytes_per_pixel TEXT;    -- number as text
ALTER TABLE sites ADD COLUMN reencode_quality TEXT;   -- number as text
