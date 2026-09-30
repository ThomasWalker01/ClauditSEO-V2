# Vendored third-party assets

## axe.min.js

| | |
|---|---|
| Package | [axe-core](https://www.npmjs.com/package/axe-core) by Deque Systems |
| Version | 4.13.0 |
| Licence | MPL-2.0 — full text in `axe-core-LICENSE.txt` |
| Size | 580,491 bytes |
| SHA-256 | `c24f097bd2f451d4f933e8bc7d8d539f8672a2ebcb5cc9f9f3eec8ca9470a0c1` |
| Obtained | `npm pack axe-core@4.13.0`, `axe.min.js` from the tarball, unmodified |

### Why it is committed rather than installed

It runs inside a page that Playwright has already loaded, on the operator's
own machine. Fetching it from a CDN at audit time would mean a network
dependency in the middle of a crawl, a version that changes underneath stored
findings without anything recording that it did, and a request that a
site's own CSP could refuse. A committed file with a recorded hash means an
audit run in a year's time can be explained.

It is the largest file in this repository by an order of magnitude. That is
the price of the only accessibility checks that need a rendered page —
contrast against resolved styles, focus order, reading order — none of which
can be decided from HTML.

### Upgrading

```
npm pack axe-core@<version>
tar -xzf axe-core-<version>.tgz
cp package/axe.min.js clauditseo/vendor/axe.min.js
cp package/LICENSE clauditseo/vendor/axe-core-LICENSE.txt
```

Then update the version, size and hash in this table, and run
`pytest tests/test_axe.py` — it asserts the file on disk matches what is
recorded here, so a silent swap fails the build.

Rule IDs appear in stored findings as `axe-<rule-id>`, so a major upgrade
that renames or removes rules will retire the old fingerprints and open new
ones. That is a real history event and worth a note in CHANGELOG.md when it
happens.
