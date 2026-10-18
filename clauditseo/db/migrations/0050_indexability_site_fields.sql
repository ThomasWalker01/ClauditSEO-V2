-- Item 137 (brief v18 step BA): the three site-record fields the Indexability
-- & canonicals brief reads. All three gate one of its analysis checks, and all
-- three are NULL (not stated) by default, which is what makes those checks hold
-- rather than guess.
--
--   intended_noindex  — the URL patterns a noindex is deliberate on. Empty, and
--                       every `noindex-intent` row is held: the sweep can see a
--                       page is noindexed and linked, not whether that was the
--                       operator's intent. A JSON list of patterns.
--   migration_map     — legacy → new URL pairs from a site move. Empty, and
--                       `redirect-map-correctness` is not_assessable: without
--                       the intended destinations there is nothing to check a
--                       redirect against. A JSON object of old → new.
--   parameter_rules   — which query parameters canonicalise and which make a
--                       distinct page. Empty, and `parameter-policy` proposes a
--                       policy as WARN rows rather than grading against one. A
--                       JSON list of rules.
--
-- Stored as TEXT holding JSON, the shape `SITE_JSON_FIELDS` reads, like the
-- other list and map fields on this record.
ALTER TABLE sites ADD COLUMN intended_noindex TEXT;
ALTER TABLE sites ADD COLUMN migration_map TEXT;
ALTER TABLE sites ADD COLUMN parameter_rules TEXT;
