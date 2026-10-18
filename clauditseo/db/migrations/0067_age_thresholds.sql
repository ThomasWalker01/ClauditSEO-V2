-- Item 239 step 6: when a measurement is old enough to say so. Two ages in
-- days, the operator's, set in Admin: from `age_warn_days` a date is shown
-- in the warning tone ("may be out of date") with its part's re-check beside
-- it; from `age_stale_days` in the danger tone ("out of date"), and the part
-- is marked stale in the parts strip. NULL is the default - 30 and 90, as
-- item 239 states them - so an unset threshold is never read as zero.
ALTER TABLE app_prefs ADD COLUMN age_warn_days INTEGER;
ALTER TABLE app_prefs ADD COLUMN age_stale_days INTEGER;
