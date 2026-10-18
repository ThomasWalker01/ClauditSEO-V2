-- Retire the four lab-proxy PRF checks, and PURGE their stored rows rather
-- than re-homing them (item 141, brief v19 step BC; operator 2026-09-12).
--
-- The four, as the operator's ordering ruling named them: `perf-signals` (a
-- playbook tool whose checks were `slow-response`, the HTML-bytes
-- `page-weight` and `caching-headers`) plus `third-party-scripts` with its two
-- siblings `-none` and `-not-assessed`. The contract Speed brief and its
-- thirteen trace checks supersede them.
--
-- A PURGE, NOT 0049'S RE-HOMING SHAPE, and that is the operator's decision
-- rather than a shortcut. Asked directly, they answered: the stored runs exist
-- only to judge software progress, this is not a live system anyone is reading,
-- and *"I do not want to keep the shape of old data if we have moved forward
-- with what we are recording"* — backward compatibility, declined on purpose.
--
-- Re-homing could not have worked here anyway, which is worth recording
-- because the plan called for it. Measured on twenty22 run `95ac5495`
-- (48 crawled, 45 readable, 12 traced):
--
--   slow-response        33 findings, ALL 33 on pages with no trace
--   page-weight           5 findings,     3 on pages with no trace
--   third-party-scripts   5 findings,     2 on pages with no trace
--   caching-headers       0 findings
--
-- `slow-response` re-homes to `ttfb-slow`, which exists on 12 of 45 pages. So a
-- re-homing migration would have moved 12 rows and orphaned 33 — and the orphan
-- test the plan asked for is exactly what would have failed. `caching-headers`
-- and `third-party-scripts` had no successor at all: the trace's resource list
-- comes from `performance.getEntriesByType("resource")` and excludes the
-- navigation entry, so nothing in the thirteen reads the HTML document's own
-- Cache-Control; and `third-party-weight` is a 50 KB / 50 ms threshold on one
-- page, which cannot make a host inventory's claim or state the true negative
-- `third-party-scripts-none`.
--
-- WHAT THIS COSTS, STATED SO IT IS NOT DISCOVERED LATER. The trace samples one
-- page per template, so most of a crawl carries none — 33 of 45 readable pages
-- on the run above. After this, those pages report nothing on response time,
-- document caching or third-party inventory. The operator was shown that figure
-- and chose retirement: `slow-response` was `Confidence.LOW`, timed from our own
-- single unthrottled fetch on the audit host, and 33 findings of that kind read
-- like signal without being it. The Speed part states its own reach — `traced:
-- one page per template (12 of 45 readable, 12 templates)` — so a sampled audit
-- now says so rather than padding the gap with a proxy.
--
-- `page-weight` IS NOT PURGED and is not retired. The id is shared: the trace
-- emits it as total transfer over budget, which is what it was always meant to
-- be. Only the HTML-bytes reading behind the same id is gone.
--
-- Deleting `findings` rows as well as `finding_states` is deliberate. A state
-- with no finding renders as a row the screen cannot describe, and a finding
-- with no state is invisible but still counted by anything reading the table
-- directly. Both halves or neither.

DELETE FROM finding_states
 WHERE fingerprint IN (
   SELECT fingerprint FROM findings
    WHERE dimension = 'PRF'
      AND check_id IN ('slow-response', 'caching-headers',
                       'third-party-scripts', 'third-party-scripts-none',
                       'third-party-scripts-not-assessed'));

DELETE FROM findings
 WHERE dimension = 'PRF'
   AND check_id IN ('slow-response', 'caching-headers',
                    'third-party-scripts', 'third-party-scripts-none',
                    'third-party-scripts-not-assessed');
