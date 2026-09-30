-- Item 167: the operator confirms which Google listing is this site's.
--
--   gbp_confirmed_place_id - the Places id (`ChIJ...`, never a CID) of the
--       listing the operator confirmed. Picked from a lookup's candidates,
--       never typed. Every later Places lookup chooses the candidate with
--       this id and marks it `confirmed by operator`. A search that stops
--       returning it clears nothing: the lookup falls back and says so.
--   gbp_last_lookup - JSON: the most recent lookup's candidates, match and
--       time. What the confirm control lists, and what the confirm route
--       checks a pick against, so a stored id is always one Google returned.
--       Written by the brief route; not an operator-edited field.
ALTER TABLE sites ADD COLUMN gbp_confirmed_place_id TEXT;
ALTER TABLE sites ADD COLUMN gbp_last_lookup TEXT;
