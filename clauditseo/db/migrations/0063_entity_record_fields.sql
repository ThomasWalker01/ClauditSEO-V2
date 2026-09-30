-- Item 145 (brief v22 step BH): the three record fields `ai-surface.md` names
-- and this product's site record did not hold. The brief treats the record as
-- authoritative and states an empty field as absent, so until now three of its
-- entity checks could only ever come back `not_assessable` naming a field the
-- operator had no way to set.
--
--   legal_name        - the registered trading entity's legal name, where it
--       differs from `brand`. The ID page is expected to state both, and
--       `entity-unnamed` reads the pair.
--   registered_ids    - a JSON list of registered identifiers (ABN, ACN, VAT,
--       company number), each as a free string, because the shape differs by
--       jurisdiction and the product never validates one. `sameAs` pins to
--       these, which is what `entity-unresolvable` judges pins against.
--   external_profiles - a JSON list of `{"url": ..., "claimed": true|false}`
--       for branded profiles the operator controls. `claimed` is the
--       operator's statement, never measured: an unclaimed profile is a
--       different fix from an unlinked one. `sameas_sources` stays as it is —
--       it is the pin list, and this is the footprint with its claimed state,
--       which is what `entity-footprint-unlinked` reads.
--
-- Empty on every site on arrival. Populated only by the operator, including
-- when they accept a suggestion read off the site's own schema: a field
-- filled from the markup it is later compared against would make
-- `entity-footprint-unlinked` and `entity-unresolvable` self-confirming.
ALTER TABLE sites ADD COLUMN legal_name TEXT;
ALTER TABLE sites ADD COLUMN registered_ids TEXT;
ALTER TABLE sites ADD COLUMN external_profiles TEXT;
