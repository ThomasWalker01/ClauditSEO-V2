-- Brief v11 step AI: the local-SEO facts the Title & description and
-- Headings briefs read from the site record. Scalars as text; lists and
-- maps as JSON text. NULL means not set, and each prompt states its own
-- fallback for an empty value.
ALTER TABLE sites ADD COLUMN gbp_primary_category TEXT;
ALTER TABLE sites ADD COLUMN service_area_entity TEXT;
ALTER TABLE sites ADD COLUMN title_strategy TEXT;       -- triple | neighbourhood
ALTER TABLE sites ADD COLUMN neighbourhoods TEXT;       -- JSON list of names
ALTER TABLE sites ADD COLUMN entity_variants TEXT;      -- JSON map: entity -> [variants]
ALTER TABLE sites ADD COLUMN sub_services TEXT;         -- JSON list of {name, url}
ALTER TABLE sites ADD COLUMN location_pages TEXT;       -- JSON list of {url, location_entity}
ALTER TABLE sites ADD COLUMN page_types TEXT;           -- JSON map: url -> location|service|blog|other
