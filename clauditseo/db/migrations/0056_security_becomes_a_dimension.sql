-- Security & transport becomes its own dimension, SEC (item 143, brief v20
-- step BD), and the two TEC checks it replaces are PURGED, not re-homed
-- (question channel 2026-09-13, answered; the operator's "no backward
-- compatibility" ruling of 2026-09-12).
--
-- `TEC/security-headers` was one coarse check over three headers; SEC's B
-- domain is eleven fine ones, and mapping one stored finding onto any of them
-- would invent a measurement the run never made - the rule item 157 exists to
-- keep. `TEC/not-https` is close to `SEC/http-redirect` but not the same check
-- (served over http, against http redirecting to https). The next sweep
-- raises the SEC rows fresh and `watch_changes` reports them as new.
DELETE FROM finding_states WHERE fingerprint IN (
    SELECT fingerprint FROM findings
    WHERE dimension = 'TEC' AND check_id IN ('not-https', 'security-headers'));
DELETE FROM findings
    WHERE dimension = 'TEC' AND check_id IN ('not-https', 'security-headers');
