"""ClauditSEO — a self-hosted SEO audit suite.

The product name lives here and nowhere else. It was written out by hand in
the API title, the crawler's user agent, the report header, the dashboard
shell and the docs, so a rename meant finding every copy and the copies
disagreeing was a question of when.

The Python package is still `clauditseo`. Renaming the directory touches 139
files, breaks the installed entry point and the scheduled task that runs the
server, and buys nothing a user can see — it is a mechanical change worth
doing on its own, with the service stopped, not folded into a product rename.
"""

#: What the product is called. Every user-visible surface reads this.
APP_NAME = "ClauditSEO"

#: How the crawler identifies itself to every site it visits. Public, and the
#: one place the name reaches someone else's server logs.
BOT_NAME = "ClauditSEOBot"

#: Kept in step with the top entry of CHANGELOG.md. This sat at 0.1.0 through
#: thirteen releases, so the CLI banner, /health and the dashboard footer all
#: named the first version of the product while the changelog stood at the
#: thirteenth — a version string nobody can act on is worse than none, since
#: it looks like an answer.
__version__ = "0.14.0"

# Bumped whenever check logic changes in a way that affects findings or
# scores, so runs are comparable like-for-like across history.
# 0.2.0: rate-based scoring with per-check ceilings — scores are NOT
#        comparable with 0.1.0 history.
# 0.3.0: real structured-data validation (required properties, deprecated
#        rich-result types, @id integrity) adds ONP findings.
# Bumped whenever the SHAPE of what a run stores changes — a new key in
# subscores, per-check detail or crawl evidence — not only when scoring
# arithmetic moves. It sat at 0.3.0 across six days while coverage, per-check
# page counts, crawl scope, run kind and per-run expert reports were all
# added, so sixteen runs of materially different shapes all claimed the same
# version. Readers could not ask "does this run have that field?" and guessed
# instead, and a guessed value is indistinguishable from a measured one — the
# route by which "21 of 20 pages" reached a client-facing table.
#
# tests/test_stored_shape.py fails when the shape moves without this moving.
# 0.5.0: duplicate-content now subtracts site chrome and compares
# symmetrically, and A11Y reports without scoring. Both move composite
# scores, so runs either side are not comparable — which is the whole reason
# this constant exists and is stamped on every run.
# 0.6.0: a run now carries `scope` — pages fetched, URLs blocked by robots.txt
# and whether the crawl stopped early — assembled by `get_run` from the
# evidence blob it already stored. A reader of an older run gets `None`, which
# means "this run did not record its scope" and must never be read as zero:
# the whole point of the field is that a crawl which fetched nothing looks
# identical to a full audit without it.
# 0.7.0: 'blocked' joins the run statuses. A run whose crawl obtained no
# eligible page — no 200 with an HTML body — is stored as 'blocked' rather
# than 'complete'. This changes what an older row means as much as what a new
# one does: 'complete' at 0.6.0 and earlier may be a run that fetched nothing
# and scored itself anyway, while 'complete' at 0.7.0 guarantees at least one
# page was read. A reader comparing the two is comparing a measured site
# against one that was never retrieved, and only the version says which.
# 0.10.0: the crawler stops fetching tracking-parameter spellings of a URL it
# already has. `normalise_url` strips `utm_*`, `gclid`, `gbraid`, the `gad_*`
# pair and the other named ad-click keys, so a link an ad platform tagged and
# the clean link beside it are one entry in the frontier and one row in the
# page inventory. Like 0.7.0 above, this changes what an older run means as
# much as what a new one does, and for the same reason it is recorded here:
# `engine_version` is the first term of the metric comparability key that
# `site_trend` builds in `clauditseo/persistence/runs.py`, so without the bump
# a site's `pages_fetched` at 0.9.0 and its `pages_fetched` at 0.10.0 land in
# one frame and the drop reads as the site losing pages. Measured over stored
# run `fe97cc61ab52468ebb0c4bff36ac69f7`: 235 URLs fetched at 0.9.0, 225
# distinct at 0.10.0, every one of the ten collapsing onto a base that same
# crawl already held — so the delta is spelling, not coverage, and only the
# version says so.
# 0.12.0 records each page's heading outline with its region and the words
# after every heading (brief v11 step AJ): the Headings brief reads them.
# 0.16.0 stores each page's JSON-LD blocks as they were served, not only a
# count of them (brief v16a step AT-b). The Structured data picture is a
# graph, and the flattened inventory beside it cannot carry one: it keeps
# two levels and a list's first member, so a reference inside an
# `itemListElement` is invisible to it. Purely additive - it measures
# nothing, changes no score and moves no count - and the bump is here for
# the same reason 0.15.0's `content_hash` and `opening` took one: a reader
# of an older run must be able to tell that the field is absent rather than
# empty, and `test_stored_shape` is the thing that makes them.
# 0.18.0 stores each page's `redirect_statuses` — the status code of every
# redirect hop, parallel to `redirect_chain` (item 137, FEATURES F-13) — which
# is what lets `redirect-temporary` tell a 302 from a 301. Additive and the
# same reason: a reader of an older run sees the field absent (never a
# substituted status), and `redirect-temporary` does not fire there.
# 0.19.0 stores each page's `perf` — the performance trace `clauditseo.perf`
# takes under a fixed device profile (mid-tier mobile, 4G): TTFB/FCP/LCP with
# the LCP element and sub-parts, CLS with shifting elements, TBT and long tasks
# by script, the resource list (bytes, transfer, blocking, cache, compression,
# coverage, whitespace ratio), fonts, and filmstrip frames (item 141, brief
# v19 step BC). Every page record carries the key: the trace, or
# `{"traced": False}` where none was taken. A field the browser could not
# supply is stored `"unavailable"`, never omitted, so a reader of an older run
# sees `perf` absent and a reader of a partial trace sees the field as
# `unavailable` rather than as a measured zero.
#
# 0.20.0 changes `TRACE_KEYS`, which is a named set by design, so this is the
# deliberate bump it exists to force (brief 160 steps 1-3):
#
#   head_html  ->  head_rendered   A RENAME THAT IS THE FIX. It was
#                                  `document.head.outerHTML` read after load --
#                                  the live DOM head -- under a name and a
#                                  comment that both said "as fetched", and the
#                                  comment told callers "the raw served head is
#                                  on the crawl record", which was never true:
#                                  nothing stores raw HTML on the evidence.
#   + head_fetched                 The head the server actually sent, from the
#                                  document request's response body over the
#                                  CDP session this pass already holds.
#   + mobile_render                Document width against the viewport, the
#                                  elements that overflow it, interactive boxes
#                                  under 24 px, and viewport-unit and
#                                  fixed-position elements.
#
# The two heads together are what make `viewport-injected` and
# `viewport-divergent` answerable -- a diff, not a second render pass -- and
# `mobile_render` is item 147's step 8, taken in this pass because `perf.py`
# was already a 412 x 823 Pixel 5 emulation with JavaScript executing three
# days before that step was written.
#
# A run stored under 0.19.0 or earlier has `head_html` and no `mobile_render`.
# Nothing migrates it and nothing reads it: the six checks that need these keys
# are silent on a page whose trace lacks them, which is 3b's shape, and the
# screen says `not_assessed` (item 157) rather than a proxy guessing.
#
# 0.21.0: `title-length` fires at the MOBILE width, 410 px, where it fired at
# desktop 600 (item 152, operator's decision A, 2026-09-13). No stored shape
# moves; what moves is the count. Measured 2026-09-13 over every stored page
# record with a title (646): 69 cut at 600 px, 376 cut at 410 px, so ONP's
# title-length rows rise 5.4x and every score containing them moves. (The
# item measured 35 and 199 over 318 titles on the day it was filed; the store
# has grown since, and the ratio held.) That is exactly the discontinuity
# this constant exists to mark: `engine_version` is the first term of the
# comparability key `site_trend` builds, so the jump reads as a change in the
# measurement rather than as every site regressing at once. Fingerprints are
# unchanged - one finding per string, keyed on the page - so history continues.
#
# 0.22.0: Security & transport is its own dimension, SEC (item 143 step BD),
# weighted 0.04 and taken from TEC (0.22 -> 0.18). Every composite moves, and a
# run now carries a SEC subscore; `TEC/not-https` and `TEC/security-headers`
# are gone (migration 0056). Multiple Set-Cookie headers are kept, one per line.
#
# 0.23.0: SEC measures seven checks it listed as "not collected yet" under
# 0.22.0 (item 143 step BD, 2026-09-14): cors-permissive,
# cross-origin-policies (SaaS sites only), script-inventory, obfuscated-js,
# hidden-content and cloaking. A 0.22.0 run read these as not assessed; a
# 0.23.0 run can raise them, so SEC subscores and composites can move where
# nothing on the site did - the discontinuity this constant marks. The UA
# matrix's Googlebot row gains `bodies` (a title / text length / link-host
# fingerprint per URL), inside the `ua_matrix` evidence key rather than the
# page record, and `access-control-allow-credentials` joins the kept headers.
# twenty22 at T2 raised none of the seven.
#
# 0.24.0: the TLS probe offers h2 by ALPN and reads the leaf certificate's key
# and signature from its DER, so SEC/http2-absent and SEC/cert-key are
# measured (item 143 step BD). The transport evidence gains `alpn`,
# `cert_key_type`, `cert_key_bits` and `cert_signature`. `sec.COLLECTED_SINCE`
# records which version first measured each new SEC check, and a run from
# before it reads that check as not assessed rather than as passing.
#
# 0.25.0: SEC/trackers-before-consent is measured from the performance trace
# (item 143 step BD): a tracking beacon requested, with nothing clicked, on a
# traced page that carries a consent tool (channel 20260914-1415, option A).
# The evidence gains a top-level `consent` block - tools, trackers, cookieless
# analytics - which the Security brief judges against the market where no
# consent tool exists. The page record is unchanged; a 0.24.0 run reads the
# check as not assessed through `COLLECTED_SINCE`.
#
# 0.26.0: TEC/head-divergent reads the head pair every trace already carries
# (item 165) - canonical, meta description, meta robots, hreflang and og:*
# injected, removed or changed by JavaScript - and the page-scoped
# `js-rendering` brief retires with it. Nothing stored moves; a traced run
# from before reads the check as not assessed through `tec.COLLECTED_SINCE`.
#
# 0.27.0: mobile and bot parity are retrieved, not inferred (item 151). A
# sample of each crawl's pages is fetched again as desktop Chrome, iPhone
# Safari and Googlebot-smartphone, and TEC/mobile-parity, TEC/bot-parity and
# TEC/mobile-parity-size are measured from the comparison. The evidence gains
# a top-level `mobile_parity` block - stored when clean too, as "no divergence
# across N pages"; the page record is unchanged. A run from before reads the
# three as not assessed.
ENGINE_VERSION = "0.27.0"
