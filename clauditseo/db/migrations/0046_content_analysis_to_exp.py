"""Move Content's analysis rows from `CNT` to `EXP:<brief>` (Q-56, item
137-answer).

A conforming brief's rows are stored under the sweep's own check ids, so
Content's four analysis briefs wrote their model rows under `CNT` - the
check's dimension. That put them where `_analyst_section` renders them, as
analyst prose whose numbers G7 must ground against one run's deterministic
evidence. But a content-analysis figure is about the Record and spans runs -
"22 indexable pages are absent", "3 of 9 services carry no cost page" - so it
is ungroundable there, and the whole client document was refused.

Stored under `EXP:<brief>` those rows render in `_expert_section` instead,
which caveats an ungroundable figure with `[TO CONFIRM]` rather than refusing
the document (brief v18 step AY's provenance rule). The eight FREE content
checks stay under `CNT`: that is the Free/Analysis split (brief v17 step AV)
applied to storage, decided by the check's own cost, in
`runs.contract_storage_dimension` - the one rule this migration and the
recorder both read, so a row this moves and a row a later run stores land on
the same dimension and the same fingerprint.

**The fingerprint changes, and the standing moves with it.** A contract row's
identity is `brief:<dimension>|<check>|<path>` (`brief_fingerprint`), so the
dimension change gives every moved row a new id. `finding_states` is keyed on
that id, so its row is renamed in step with the finding - the state, the
attempt note and the history follow the finding to its new identity, which is
what "the standing position must reconcile exactly" requires. The part page
is unaffected because it buckets by check id (`anatomy.categorise`), not by
dimension, and the check id does not change.

**Reversible by computation, nothing stored to undo it.** The inverse is the
same map read backwards: `dimension='CNT'`,
`fingerprint=brief_fingerprint('CNT', check_id, page)`. A row is moved only
when its stored fingerprint is the one `brief_fingerprint('CNT', ...)`
reproduces from the row's own recorded page - so a fingerprint this migration
cannot reproduce is never rewritten, and the move is exact where it acts.
"""

import json
import logging

LOG = logging.getLogger(__name__)


def apply(conn) -> None:
    from clauditseo.persistence.runs import (brief_fingerprint,
                                             contract_storage_dimension)

    rows = conn.execute(
        "SELECT f.id, f.check_id, f.fingerprint, f.evidence, a.site_id"
        " FROM findings f JOIN audit_runs a ON a.id = f.run_id"
        " WHERE f.dimension='CNT' AND f.source='model-judgement'"
        "   AND json_extract(f.evidence, '$.contract')=1"
    ).fetchall()

    # (site_id, old_fingerprint) -> new_fingerprint. One finding_states row
    # backs every finding of an id across runs, so the rename is per distinct
    # (site, id), deduplicated here.
    fp_map: dict[tuple[str, str], str] = {}
    moved = skipped = 0
    for r in rows:
        ev = json.loads(r["evidence"] or "{}")
        brief = ev.get("from_brief")
        if not brief:
            continue
        new_dim = contract_storage_dimension(brief, r["check_id"], "CNT")
        if new_dim == "CNT":
            continue  # a free content check — stays under CNT by the split.
        page = ev.get("page")
        # Only rewrite a fingerprint we can reproduce from the row's own
        # recorded page: this is the guard that the page derivation matches
        # what the recorder used, so a rename cannot silently point the
        # standing at the wrong row.
        if brief_fingerprint("CNT", r["check_id"], page) != r["fingerprint"]:
            LOG.warning(
                "0046: finding %s (check %s) has a fingerprint its recorded "
                "page does not reproduce; left under CNT", r["id"], r["check_id"])
            skipped += 1
            continue
        new_fp = brief_fingerprint(new_dim, r["check_id"], page)
        conn.execute("UPDATE findings SET dimension=?, fingerprint=? WHERE id=?",
                     (new_dim, new_fp, r["id"]))
        fp_map[(r["site_id"], r["fingerprint"])] = new_fp
        moved += 1

    for (site_id, old_fp), new_fp in fp_map.items():
        # OR REPLACE for the identity change; the new id is fresh (no EXP row
        # carried this check before this migration), so nothing is displaced.
        conn.execute(
            "UPDATE OR REPLACE finding_states SET fingerprint=?"
            " WHERE site_id=? AND fingerprint=?", (new_fp, site_id, old_fp))

    LOG.info("0046: moved %d content analysis findings to EXP:<brief> "
             "(%d finding_states renamed, %d left under CNT)",
             moved, len(fp_map), skipped)
