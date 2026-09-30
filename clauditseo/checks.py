"""The check registry's questions the contract asks (brief v11 steps AH and
AI): what is a check's registered default severity, and which checks are
a brief's alone? Each module keeps its own table beside its emitters; this
reads them under the full id the briefs use (`ONP/title-length`)."""

from __future__ import annotations


def _word(sev) -> str:
    return sev.value if hasattr(sev, "value") else str(sev)


#: The modules that keep a severity table and a brief-only register, and
#: the dimension code each writes under. Read as a pair rather than
#: discovered, because a module without the two attributes is not a
#: mistake - most have neither - and a silent skip would file a whole
#: dimension's checks as costing nothing (brief v17 step AW).
#: Dimensions that LABEL where a finding came from and own no sweep
#: (item 148). `INT` is the first: `runs.py` writes the contract row's
#: `dimension` straight into the `findings` table, so a prefix is not looked
#: up and validated — it becomes a dimension value in the record. `INT` had to
#: be a string something owns rather than an accident.
#:
#: **Deliberately NOT in `anatomy.DIMENSION_CATEGORIES`.** That map means "this
#: dimension's SWEEP refreshes these categories", so an entry there would put
#: `intl` into the covered set and break
#: `test_analysis_only_categories_really_have_no_sweep` — which is exactly the
#: flaw the item names in the option it rejected. `intl` stays in
#: `ANALYSIS_ONLY`; nothing here claims a sweep.
#:
#: The severity table is empty on purpose. `DEFAULT_SEVERITY` is pinned to what
#: a sweep raises, and no sweep raises these — the brief's own row carries the
#: severity, which is how PRF's five analysis checks already work. Membership in
#: the brief-only half is what makes `check_costs()` price all eleven `model`,
#: and that matters: `check_cost` returns FREE for a check the app has never
#: heard of, so an unregistered id would read as free on the part page,
#: analysis checks included.
LABEL_ONLY_REGISTRIES: list[tuple[str, dict, frozenset]] = [
    ("INT", {}, frozenset({
        "hreflang-missing", "hreflang-reciprocity", "hreflang-self",
        "hreflang-x-default", "hreflang-code", "hreflang-target",
        "hreflang-method-mixed", "hreflang-sitemap-conflict",
        "locale-redirect", "architecture", "consolidation"})),
]


def _registries() -> list[tuple[str, dict, frozenset]]:
    from clauditseo.modules import ais as _ais
    from clauditseo.modules import cnt as _cnt
    from clauditseo.modules import links as _links
    from clauditseo.modules import onp as _onp
    from clauditseo.modules import prf as _prf
    from clauditseo.modules import sec as _sec
    from clauditseo.modules import tec as _tec

    return [(_onp.OnPageModule.code, _onp.DEFAULT_SEVERITY, frozenset(_onp.BRIEF_ONLY_CHECKS)),
            (_links.LinksModule.code, _links.DEFAULT_SEVERITY, _links.BRIEF_ONLY_CHECKS),
            (_cnt.ContentModule.code, _cnt.DEFAULT_SEVERITY, _cnt.BRIEF_ONLY_CHECKS),
            (_tec.TechnicalModule.code, _tec.DEFAULT_SEVERITY, frozenset(_tec.BRIEF_ONLY_CHECKS)),
            # PRF joins for its Speed analysis checks (brief v19 step BC), which
            # only the `speed.md` brief emits; its free checks keep their inline
            # severities, so DEFAULT_SEVERITY is empty.
            (_prf.PerformanceModule.code, _prf.DEFAULT_SEVERITY, frozenset(_prf.BRIEF_ONLY_CHECKS)),
            # SEC (item 143 step BD). Its severity table holds every free check
            # the brief registers, including the ones whose collector is not
            # built yet; `sec.NOT_YET_COLLECTED` is subtracted in `sweep_checks`
            # so a prompt cannot claim one of those as free before it exists.
            (_sec.SecurityModule.code,
             {**_sec.DEFAULT_SEVERITY,
              **{c: _sec.Severity.INFO for c in _sec.BRIEF_ONLY_CHECKS}},
             _sec.BRIEF_ONLY_CHECKS),
            # AIS (item 145, brief v22): the AI surface brief's registry.
            (_ais.AiSurfaceModule.code, _ais.DEFAULT_SEVERITY, _ais.BRIEF_ONLY_CHECKS),
            # Dimensions with no module, so no sweep and no severity table.
            *LABEL_ONLY_REGISTRIES]


def default_severities() -> dict[str, str | dict[str, str]]:
    """Full check id -> severity word, or a word per status (FAIL / WARN)
    where the registry gives one per status."""
    out: dict[str, str | dict[str, str]] = {}
    for code, table, _brief_only in _registries():
        for check_id, sev in table.items():
            if isinstance(sev, dict):
                out[f"{code}/{check_id}"] = {status: _word(s) for status, s in sev.items()}
            else:
                out[f"{code}/{check_id}"] = _word(sev)
    return out


def default_severity(check: str, status: str = "FAIL") -> str | None:
    """The registered default for a check at a status: the status's own
    where the registry gives one per status, else the check's one word;
    PASS-OVERRIDE takes FAIL's."""
    sev = default_severities().get(check)
    if isinstance(sev, dict):
        return sev.get(status) or sev.get("FAIL")
    return sev


def brief_only_checks() -> set[str]:
    return {f"{code}/{c}" for code, _sev, only in _registries() for c in only}

#: Checks that stop the site being reached or rendered at all (brief v17
#: step AX). Triage ranks these first, whatever they score.
#:
#: The membership rule is narrow on purpose: a blocker is a thing that
#: prevents a crawler or an agent getting the page, not a thing that makes
#: the page worse once it has it. A missing H1 is not a blocker however
#: severe; a `robots.txt` that denies GPTBot is, because no content work
#: on that site can be read by the thing it was written for. Kept here
#: rather than in each module because it is a statement about ranking,
#: which is one question asked once - and kept out of the prompt because a
#: model deciding for itself what blocks would decide differently between
#: runs, and the order an operator acts on would move without the site
#: moving.
BLOCKER_CHECKS: frozenset[str] = frozenset({
    # Reachability. (redirect-chain was here until item 137 / brief v18 step BA
    # de-listed it: a chain resolves to a live page, so the page is reached —
    # the difference from robots-missing and sitemap-missing, which block the
    # reach itself. It stays a MEDIUM defect, not a blocker. Channel 20260910-1430.)
    "TEC/robots-missing", "TEC/http-status-error",
    "TEC/sitemap-missing",
    # Indexability: the page is reached and then told not to count. noindex-page
    # became noindex-linked at item 137 (brief v18 step BA) — only a noindex
    # page something links to blocks; a stray noindex page nobody points at is
    # not a blocker. The rename and this edit are one commit: is_blocker matches
    # bare names, so renaming alone would leave the verdict moving unrecorded.
    "TEC/noindex-linked", "TEC/canonical-mismatch", "TEC/canonical-missing-variant",
    # Transport was `TEC/not-https` here until item 143 step BD purged it; the
    # SEC replacement, `http-redirect`, also fires for a redirect with one hop
    # too many, which is not a blocker, so it is not listed by name.
    # The agents this product exists to be read by. Scored under TEC since
    # item 137 (brief v18 step AZ) — a robots.txt rule is a crawl-access
    # failure by cause — beside the other reachability blockers above.
    "TEC/ai-crawler-blocked",
})


def blocker_checks() -> set[str]:
    """The blocker list, as full ids. A function rather than the constant
    so a caller cannot mutate the register it is reading."""
    return set(BLOCKER_CHECKS)


def is_blocker(check: str) -> bool:
    """Whether one check blocks. Accepts a full id or a bare one - the
    record stores both spellings depending on which reader is asking, and
    a rank that depended on which was passed would be a rank that moved
    for no reason."""
    if check in BLOCKER_CHECKS:
        return True
    bare = check.split("/")[-1]
    return any(b.split("/")[-1] == bare for b in BLOCKER_CHECKS)


#: What a check costs to answer (brief v17 step AV1).
#:
#: `free` - the sweep emits it with no model call. `model` - only a brief
#: can, so answering it spends tokens.
FREE, MODEL = "free", "model"


def check_costs() -> dict[str, str]:
    """Every check the app knows, with what it costs to answer.

    **Derived, not a second hand-list, and that is the design.** The
    registry already records which checks only a brief can emit; "costs a
    model call" and "only a brief emits it" are the same fact, and writing
    it twice would give the app two answers to "is this free" the first
    time somebody edited one list. AV1 asks for `cost` on every check; this
    is that field, computed from the one place the distinction is already
    kept.

    The rule AV1 states about a check with both sources falls out of that:
    a check the sweep emits is not in the brief-only register, so it is
    `free` whether or not a brief also corroborates it. The brief adds
    reading to a finding that already exists; it does not create it.

    Held-only checks are `model` for the same reason - the sweep cannot
    raise one at all, so nothing about them is free.
    """
    from clauditseo.anatomy import CHECK_CATEGORY
    from clauditseo.modules.onp import HELD_ONLY_CHECKS, OnPageModule

    code = OnPageModule.code if hasattr(OnPageModule, "code") else "ONP"
    only_brief = brief_only_checks() | {f"{code}/{c}" for c in HELD_ONLY_CHECKS}
    bare = {full.split("/")[-1] for full in only_brief}
    out: dict[str, str] = {full: MODEL if full in only_brief else FREE
                           for full in default_severities()}
    # Every categorised check, not only the ones with a registered
    # severity: the other dimensions keep no severity table, and a check
    # the part page lists needs a cost whether or not ONP registered it.
    registered = {k.split("/")[-1] for k in out}
    for check_id in CHECK_CATEGORY:
        if check_id not in registered:
            out[check_id] = MODEL if check_id in bare else FREE
    return out


def check_cost(check: str) -> str:
    """One check's cost, by full id or bare id. `free` where the app has
    never heard of it: an unknown check is not a reason to tell an operator
    something will be charged for."""
    costs = check_costs()
    return costs.get(check) or costs.get(check.split("/")[-1]) or FREE


#: Check ids the engine emits under a name it makes up at run time, so no
#: register can enumerate them. `axe.py` spells its ids `f"axe-{rule}"` from
#: whatever axe-core reported, which is the whole point of running axe: the
#: rule set is theirs and it moves.
DYNAMIC_CHECK_PREFIXES = ("axe-",)

#: Checks the engine emits from outside a registry module, so the scrape in
#: `sweep_checks` cannot see them. `adaptive.py` is not a dimension; it is
#: the escalation policy, and it raises one INFO note to say it escalated a
#: dimension and another to say it declined to (item 238 named the first,
#: which this list had missed; both are coverage notes, `runs.ENGINE_RUN_NOTES`).
#:
#: Listed rather than left out: the record holds 79 rows under these two
#: names, and a validity test that did not know them would have called the
#: engine's own findings invalid.
ENGINE_EXTRA_CHECKS = frozenset({"TEC/adaptive-no-escalation", "TEC/adaptive-escalation"})


def known_check(code: str) -> bool:
    """Whether the app has this check at all, in either spelling.

    The one answer to "is this a real check id", so a caller validating
    stored rows and a caller validating a brief's output cannot disagree.

    Accepts a bare id or a full one, because the record stores both
    depending on which reader is asking; a test that depended on which
    spelling was used would reject good rows. Accepts the dynamic families
    above, which no register can list.
    """
    if not code:
        return False
    bare = code.split("/")[-1]
    if any(bare.startswith(pre) for pre in DYNAMIC_CHECK_PREFIXES):
        return True
    known = set(check_costs()) | set(ENGINE_EXTRA_CHECKS)
    return code in known or any(full.split("/")[-1] == bare for full in known)


def sweep_checks() -> set[str]:
    """The bare check ids the engine's own modules emit.

    Read off the modules rather than off the playbook, and the difference
    matters: the playbook is a status board, and its Images entry became a
    *brief* at v15 while still listing the sweep's check ids. A board that
    describes the product is not the product.

    Two sources beyond the regex, both because the id is not a literal at
    the emit site: the schema rules name theirs from a table, and a brief's
    own checks are the model's rather than a module's.

    This is what AV2's rule is checked against: a prompt may read a `free`
    check and may override it, but may not introduce one, because a free
    check nothing emits is a row on a part page that no run can produce.
    """
    import inspect
    import re

    from clauditseo.engine import registry

    out: set[str] = set()
    for module in registry.all_modules().values():
        out.update(re.findall(r'check_id="([a-z0-9-]+)"', inspect.getsource(type(module))))
    # And where a module declares its checks rather than spelling each id
    # at its own call site, the declaration is read. LNK raises all eight
    # of its checks through one helper, so the regex above finds none of
    # them; its severity table minus its brief-only register is the same
    # set, said once. Scraping stays for the modules that declare neither.
    from clauditseo.modules.sec import NOT_YET_COLLECTED
    for code, table, only in _registries():
        out.update(check for check in table
                   if check not in only
                   and not (code == "SEC" and check in NOT_YET_COLLECTED))
    from clauditseo.schema_rules import audit_entities, parse_blocks
    sample, _ = parse_blocks([
        '[{"@type":"FAQPage"},{"@type":"Product"},{"name":"untyped"},'
        ' {"@type":"Organization","@id":"x"},{"@type":"Organization","@id":"x"}]'])
    out.update(f"schema-{i['kind']}" for i in audit_entities(sample))
    return out
