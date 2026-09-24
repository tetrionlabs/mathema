# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The verification sweep and the one adjudication-outcome gate.

`verify_project` is the library form of `mathema verify`: enumerate
every key the on-disk stores know, re-adjudicate whatever is no longer
fresh, refresh the records, and gate. `gate` is the single policy for
"does this set of adjudicated claims pass": the CLI's check and verify
commands, CI wrappers, and any programmatic caller all apply the same
rules through it.

The gate population is provenance-based: every claim mathema did not
volunteer counts, adopted claims and the built-in structural probes
alike. A suggestion mathema conjectured on its own never gates
(adopting one is the human step that makes it count), and a claim in a
foreign grammar is reported but is another tool's to adjudicate.

(The derive-seam soundness gates; corroboration and stability; live
in `gates.py`; this module gates adjudication OUTCOMES, not evidence.)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from .records import claim_row, classify_verdict


def _claim_fields(c) -> tuple[str, str, dict, str]:
    """Intent:
        One accessor over both claim shapes the gate sees: a live
        Probe and a stored claim dict. Returns (name, verdict, meta,
        note).
    """
    if isinstance(c, dict):
        return (c.get("name") or "", c.get("verdict") or "",
                c.get("meta") or {}, str(c.get("note") or ""))
    return (c.name or "", c.verdict or "", c.meta or {}, str(c.note or ""))


def _volunteered(meta: dict, note: str) -> bool:
    """Intent:
        True when mathema itself conjectured this claim (a suggestion):
        it surfaces in reports but never gates until a human adopts it.
    """
    return (meta.get("mathema.surface") == "mathema"
            or note.startswith("conjectured by mathema"))


@dataclass
class GateReport:
    """One gate application: the failure lines in `problems` (empty
    means pass), and the population counts every caller renders."""
    problems: list[str] = field(default_factory=list)
    proven: int = 0
    holds: int = 0
    falsified: int = 0
    invalidated: int = 0
    unknown: int = 0
    owned: int = 0
    skipped: int = 0
    foreign: list = field(default_factory=list)

    @property
    def refuted(self) -> int:
        """The claims a counterexample stands against, `falsified` and
        `invalidated` together: the `refuted` stance of the claim-row
        vocabulary."""
        return self.falsified + self.invalidated


def summary_counts(counts) -> str:
    """Intent:
        The counts part of a one-line summary, each named by the verdict
        it counts: proven, holds and falsified always, the rarer states
        only when present. Takes a `GateReport` or a mapping carrying
        the same names (`accepted_risk` for the owned unknowns).
    """
    get = ((lambda k: counts.get(k, 0)) if isinstance(counts, dict)
           else (lambda k: getattr(counts, "owned" if k == "accepted_risk"
                                   else k)))
    parts = [f"{get('proven')} proven", f"{get('holds')} holds",
             f"{get('falsified')} falsified"]
    for key, word in (("invalidated", "invalidated"), ("unknown", "unknown"),
                      ("skipped", "skipped"),
                      ("accepted_risk", "accepted risk")):
        if get(key):
            parts.append(f"{get(key)} {word}")
    return ", ".join(parts)


def _record_has_unreadable_claim(entry: dict) -> bool:
    """Intent:
        Whether any claim stored in a verified record fails to parse
        under the current grammar, which is what makes rebuilding that
        record the remedy rather than correcting an authoring surface.
    """
    from .conjecture import InvalidConjecture, claim

    for c in (entry or {}).get("claims") or []:
        statement = c.get("statement")
        if not statement:
            continue
        try:
            claim(statement)
        except InvalidConjecture:
            return True
    return False


def _carry_recorded_verdicts(probes, path: str, key: str) -> None:
    """Intent:
        Give each probe the verdict its record now stores where the
        record layer changed it. A claim that was supported before and
        fails now is written as `invalidated`, and the sweep reports it
        under that name rather than as the fresh `falsified`.

    Notes:
        Only a stored `invalidated` is carried over; every other
        verdict is already the probe's own.
    """
    import yaml

    try:
        with open(path, encoding="utf-8") as fh:
            entry = (yaml.safe_load(fh) or {}).get(key) or {}
    except OSError:
        return
    stored = {c.get("name"): c.get("verdict")
              for c in entry.get("claims") or []}
    for p in probes:
        if classify_verdict(stored.get(p.name) or "") == "invalidated":
            p.verdict = stored[p.name]


def gate(claims, *, strict: bool,
         accepted_risk: frozenset = frozenset(),
         unresolved=()) -> GateReport:
    """Apply the one gate policy to a set of adjudicated claims (live
    Probes or stored claim dicts, mixed freely).

    Rules: a falsified or invalidated claim fails in every mode; an
    unknown claim fails unless its name is in `accepted_risk` (then it
    is `owned`, and only strict refuses it); strict additionally fails
    skipped claims; an unresolved global name fails in every mode.
    Suggestions mathema volunteered and foreign-grammar claims never
    gate (foreign ones are collected on the report for the caller to
    surface).
    """
    r = GateReport()
    for c in claims:
        name, verdict, meta, note = _claim_fields(c)
        if "mathema.foreign_grammar" in meta:
            r.foreign.append(c)
            continue
        if _volunteered(meta, note):
            continue
        kind = classify_verdict(verdict)
        if verdict == "skipped:unknown_but_accepted":
            # the stored form of an unknown a person accepted as risk
            r.owned += 1
            continue
        if kind == "proven":
            r.proven += 1
        elif kind == "holds":
            r.holds += 1
        elif kind == "falsified":
            r.falsified += 1
        elif kind == "invalidated":
            r.invalidated += 1
        elif kind == "unknown":
            if name in accepted_risk:
                r.owned += 1
            else:
                r.unknown += 1
        elif kind == "skipped":
            r.skipped += 1
    # a falsified or invalidated claim is a failing check, in every
    # mode; strictness only governs structurally-skipped claims, never
    # wrong or undecided ones
    if r.falsified:
        r.problems.append(f"{r.falsified} falsified claim(s)")
    if r.invalidated:
        r.problems.append(f"{r.invalidated} invalidated claim(s)")
    if r.unknown:
        # an unaccepted unknown is an open epistemic gap: it fails in
        # every mode until it is resolved or a human owns the risk
        # (mathema accept --as risk)
        r.problems.append(f"{r.unknown} unknown claim(s)")
    if strict and (r.skipped or r.owned):
        # accepted risk is visible relaxation, not laundering: lenient
        # proceeds past it, strict still refuses it
        if r.skipped:
            r.problems.append(f"{r.skipped} skipped claim(s)")
        if r.owned:
            r.problems.append(f"{r.owned} accepted-risk claim(s)")
    if unresolved:
        r.problems.append(f"unresolved names: {', '.join(unresolved)}")
    return r


def _accepted_risk(entry: dict | None) -> frozenset:
    """Intent:
        The names of this record's claims a human has accepted as risk
        (and whose acceptance is not stale), the one exemption the
        gate grants to an unknown verdict.
    """
    if not entry:
        return frozenset()
    return frozenset(
        c.get("name") for c in entry.get("claims") or []
        if (c.get("accepted") or {}).get("as") == "risk"
        and not (c.get("accepted") or {}).get("stale"))


@dataclass
class VerifyResult:
    """One sweep: the per-key report lines, every problem found (empty
    means the run passes), how many keys were fresh vs re-adjudicated,
    and every claim grammar seen in the project.

    `keys` is the same sweep as structured data rather than prose;
    one entry per key with `why` it was looked at, its gate counts,
    and its claim rows in `records.claim_row()`'s vocabulary. `lines`
    renders from the same facts, so a machine consumer never parses
    the prose.
    """
    lines: list = field(default_factory=list)
    problems: list = field(default_factory=list)
    fresh: int = 0
    adjudicated: int = 0
    grammars_seen: set = field(default_factory=set)
    nothing_declared: bool = False
    keys: list = field(default_factory=list)


def _declared_reference_triples(refs) -> list:
    """Intent:
        A declared entry's references in either authored shape, the
        flat list of `{title, url, via}` dicts, or the nested-by-role
        dict the record itself writes, as `(title, url, via)`
        triples.
    """
    out: list = []

    def add(r, via):
        if not isinstance(r, dict):
            return
        title = (r.get("title") or r.get("url") or "").strip()
        if title:
            out.append((title, r.get("url"), r.get("via") or via))

    if isinstance(refs, dict):
        for via, items in refs.items():
            for r in items or []:
                add(r, via)
    else:
        for r in refs or []:
            add(r, "reference")
    return out


def _heal_concepts(key, fn, facts_now, merged_entry: dict, verified_info,
                   root: str, write_yaml) -> None:
    """Intent:
        Freshness skips re-adjudication, but declared concepts and
        reference links live outside the claims fingerprint (a
        docstring `Concepts:` edit changes neither the form hash nor
        the claim set), so the record's declared-concept and
        reference sections are recomputed and rewritten in place when
        they moved, the same in-place healing the memoization rung
        already gets.
    """
    from .concepts import flat_union, normalize_concept

    if not verified_info:
        return
    entry = verified_info["entry"]
    declared_now = list(getattr(facts_now, "doc_concepts", []) or [])
    for t in (merged_entry.get("meta") or {}).get("concepts") or []:
        t = normalize_concept(str(t))
        if t and t not in declared_now:
            declared_now.append(t)
    from .spec import group_references
    triples = list(getattr(facts_now, "doc_refs", []) or [])
    for triple in _declared_reference_triples(
            merged_entry.get("references")):
        if triple not in triples:
            triples.append(triple)
    refs_now = group_references(triples)

    meta = dict(entry.get("meta") or {})
    sources = dict(meta.get("mathema.concept_sources") or {})
    changed = False
    if sources.get("declared", []) != declared_now:
        if declared_now:
            sources["declared"] = declared_now
        else:
            sources.pop("declared", None)
        meta["mathema.concept_sources"] = sources
        meta["concepts"] = flat_union(sources)
        entry["meta"] = meta
        entry["concepts"] = flat_union(sources)
        changed = True
    if refs_now and (entry.get("references") or {}) != refs_now:
        entry["references"] = refs_now
        changed = True
    if changed:
        recorded_form = (entry.get("identity") or {}).get("form")
        write_yaml(os.path.join(root, verified_info["source"]), {key: entry},
                   header=f"machine record; binds to form {recorded_form}")


def _apply_declared_extras(rec, merged_entry: dict) -> None:
    """Intent:
        Entry-level declared extras from the claims file join the
        record: `meta.concepts` unions into the declared provenance
        (concepts are tags), and `references` append with their stated
        `via` (references are links, evidence, analysis, policy).
        Both authoring surfaces, docstring and declared spec,
        land identically.
    """
    from .concepts import Concept, flat_union, normalize_concept

    entry_meta = merged_entry.get("meta") or {}
    tokens = [normalize_concept(str(t))
              for t in entry_meta.get("concepts") or []]
    tokens = [t for t in tokens if t]
    if tokens:
        sources = dict((rec.meta or {}).get("mathema.concept_sources") or {})
        declared = list(sources.get("declared") or [])
        for t in tokens:
            if t not in declared:
                declared.append(t)
                rec.concepts.append(Concept(t, "declared"))
        sources["declared"] = declared
        rec.meta = {**(rec.meta or {}),
                    "concepts": flat_union(sources),
                    "mathema.concept_sources": {k: v for k, v in
                                                sources.items() if v}}
    for title, url, via in _declared_reference_triples(
            merged_entry.get("references")):
        triple = (title, url, via)
        if triple not in rec.facts.doc_refs:
            rec.facts.doc_refs.append(triple)




def _drop_retired_declared(key: str, current_claims: list,
                           verified_entry: dict,
                           source: "str | None") -> "tuple[list, list]":
    """Intent:
        A claim accepted as a discovery is a genuine exit, but an
        authoring surface can lag behind the decision (a docstring
        cannot be rewritten by an acceptance at all): the same law
        would re-adjudicate and regenerate the falsification a human
        already dispositioned, silently, on the next real sweep. Any
        declared claim whose name AND canonical law match a retired
        discovery row is dropped here with a non-fatal note naming the
        remedy; a different law under the same name is new authorship
        and adjudicates normally.
    """
    from .acceptance import _same_law_as, honoured_retirements
    discoveries = honoured_retirements(verified_entry, "discoveries")
    if not discoveries or not current_claims:
        return current_claims, []
    matchers = []
    for row in discoveries:
        if not row.get("name"):
            continue
        stmt = row.get("statement") or row.get("law") or ""
        # a statement-less retired row (an older record's shape) cannot
        # be law-compared and retires its name outright
        matchers.append((row["name"], _same_law_as(stmt) if stmt else None))
    if not matchers:
        return current_claims, []
    kept: list = []
    notes: list = []
    where = f"in {source}" if source else "on its authoring surface"
    for c in current_claims:
        stmt = c.get("statement") or c.get("law") or ""
        name = c.get("name")
        if any(n == name and (same is None or same(stmt))
               for n, same in matchers):
            notes.append(
                f"note {key}: claim {name!r} is still declared {where} "
                "but retired as a discovery; remove it or restate it "
                "(not adjudicated)")
        else:
            kept.append(c)
    return kept, notes


def _born_falsified_hint(key: str, probes: list,
                         verified_entry: dict) -> list:
    """Intent:
        The one-time teaching line for a claim that falsified on its
        FIRST adjudication: a failed authoring experiment, which the
        store keeps until a human signs it off, since membership never
        silently shrinks. Names the exits and the cheap path that
        writes nothing. A claim the record already knew is
        re-falsifying, which is a regression, not an experiment, and
        gets no line.
    """
    from .records import classify_verdict
    known = {c.get("name") for c in (verified_entry.get("claims") or [])
             if c.get("name")}
    known |= {d.get("name") for d in (verified_entry.get("discoveries") or [])
              if d.get("name")}
    fresh = [p for p in probes
             if classify_verdict(getattr(p, "verdict", "")) == "falsified"
             and getattr(p, "name", None) not in known]
    if not fresh:
        return []
    names = ", ".join(sorted(str(p.name) for p in fresh))
    return [f"note {key}: {names} falsified on first adjudication. A "
            f"declared claim is kept until a human decides it (fix the "
            f"code, `mathema accept {key} <claim> --as discovery`, or "
            f"supersede it). To try a spelling first, "
            f"`mathema check {key} --claim \"...\"` adjudicates it and "
            f"writes nothing."]


def _strip_retired_probes(key: str, probes: list, verified_entry: dict,
                          already_noted: set) -> "tuple[list, list]":
    """Intent:
        The function-attached surfaces (docstring, decorator) reach
        adjudication inside `check()` itself, past the declared-set
        filter, so a retired law re-entering from there is stripped
        again on the way out, before gating and the record write. The
        note is emitted once per name per key.
    """
    from .acceptance import _same_law_as, honoured_retirements
    discoveries = honoured_retirements(verified_entry, "discoveries")
    if not discoveries or not probes:
        return probes, []
    matchers = []
    for row in discoveries:
        if not row.get("name"):
            continue
        stmt = row.get("statement") or row.get("law") or ""
        matchers.append((row["name"], _same_law_as(stmt) if stmt else None))
    if not matchers:
        return probes, []
    kept: list = []
    notes: list = []
    for p in probes:
        name = getattr(p, "name", None)
        stmt = getattr(p, "statement", "") or ""
        if any(n == name and (same is None or same(stmt))
               for n, same in matchers):
            if name not in already_noted:
                notes.append(
                    f"note {key}: claim {name!r} is still declared on its "
                    "authoring surface but retired as a discovery; remove "
                    "it or restate it (not adjudicated)")
                already_noted.add(name)
        else:
            kept.append(p)
    return kept, notes


def _auto_claim_name(row: dict) -> "str | None":
    """Intent:
        The name an unnamed declared claim row resolves to when parsed,
        or None when the row does not parse.
    """
    from .conjecture import InvalidConjecture
    from .spec import entry_claims
    try:
        (cj,) = entry_claims({"claims": [row]})
    except (InvalidConjecture, ValueError):
        return None
    return cj.name


def _union_verified_membership(current_claims: list,
                               verified_entry: dict) -> list:
    """Intent:
        The declared claim set, widened with every verified claim not
        present by name, reconstructed from its recorded statement and
        fields so it keeps being adjudicated. Rows already superseded
        (discoveries) or accepted as historical never resurrect;
        suggestion rows (surface mathema) and rows with no
        statement are not membership.

    Notes:
        A declared claim with no written name is present under the name
        its statement auto-names to, the name its verified row carries;
        the row's statement is the canonical spelling, which need not
        match the text the author wrote.
    """
    if not verified_entry:
        return current_claims
    have = {c.get("name") or _auto_claim_name(c) for c in current_claims}
    out = list(current_claims)
    from .acceptance import RETIREMENT_SECTIONS, honoured_retirements
    retired = {r.get("name") for section in RETIREMENT_SECTIONS
               for r in honoured_retirements(verified_entry, section)}
    for row in verified_entry.get("claims") or []:
        name = row.get("name")
        statement = row.get("statement") or row.get("law")
        if not name or not statement or name in have or name in retired:
            continue
        meta = row.get("meta") or {}
        if meta.get("mathema.surface") in ("mathema", "builtin",
                                                "types"):
            continue
        if name == "dependencies_current":
            # the per-record dependency freshness probe is synthesized
            # each sweep, never a declared claim
            continue
        # the row's statement is the canonical text, self-contained,
        # and the structured fields ride beside it; reconstruction
        # reads them directly, never a rendered condition (`condition`
        # is the region the EVIDENCE covered, which on the derive
        # route may be narrower than the claim's own domain)
        route = (row.get("route") or "best").split(":", 1)[0]
        rebuilt = {"name": name, "statement": statement,
                   "route": route if route in ("derive", "probe")
                   else "best"}
        for field_name in ("domain", "grammar", "tolerance"):
            if row.get(field_name) is not None:
                rebuilt[field_name] = row[field_name]
        rebuilt.setdefault("meta", {})["mathema.membership"] = \
            "repopulated-from-verified"
        out.append(rebuilt)
    return out


def verify_project(root: str = ".", *, all: bool = False,
                   strict: bool = True,
                   trials_scale: float = 1.0,
                   only: "list | None" = None) -> VerifyResult:
    """The test-runner sweep as a library call: for every key the
    declared/verified stores know, re-adjudicate if the function's form
    hash, claims fingerprint, or a dependency changed (`all=True`
    forces everything), rewrite the record, and gate each key's
    adjudicated claims through `gate`. `only` restricts the sweep to the
    given dotted keys (the single-key re-verify the reconcile workflow
    points at); None sweeps the whole population.

    Notes:
        `dependencies_current` claims are settled AFTER the whole sweep
        has written its records, so a caller adjudicated before its
        callee in the same run still reads the callee's fresh record;
        the sweep's outcome does not depend on key order.
    """
    import warnings

    from .analysis import StateDependenceWarning
    with warnings.catch_warnings():
        # analyze()'s state-outside warning is real, useful signal on a
        # single function, but a sweep would print it per stateful key
        # (twice: the freshness analyze and the battery's own) and
        # drown the report, whose rows and gate lines already carry the
        # same fact. Same reasoning, same fix, as audit's and
        # inventory's own analyze shields; only this category is
        # silenced, every other warning still surfaces.
        warnings.simplefilter("ignore", StateDependenceWarning)
        return _verify_sweep(root, all=all, strict=strict,
                             trials_scale=trials_scale, only=only)


def _verify_sweep(root: str = ".", *, all: bool = False,
                  strict: bool = True,
                  trials_scale: float = 1.0,
                  only: "list | None" = None) -> VerifyResult:
    """Intent:
        The sweep body of `verify_project`, which shields it from the
        per-key state-dependence warning chatter.
    """
    from . import analyze, check
    from .compendium import external_premises as _external_premises
    from .compendium import install as _install_compendium
    from .compendium import materialize_referenced_entries
    _install_compendium(root)
    stub_premises = _external_premises(root)
    from .authoring import resolve_declared
    from .conjecture import (GRAMMAR, InvalidConjecture,
                             _resolve_func_ref)
    from .inventory import function_dependencies
    from .spec import (_dependency_state, claims_fingerprint,
                       dependencies_current_probe, entry_claims,
                       load_declared, load_verified, record as write_record,
                       write_yaml)

    out = VerifyResult()
    integrity_warned: set = set()
    from .auth import acceptance_policy_problems, load_policy
    from .locks import load_locks, lock_state
    policy = load_policy(root)
    locks = load_locks(root)
    verified = load_verified(root)
    declared = load_declared(root)
    keys = sorted(set(verified) | set(declared))
    # a function can be locked before it has any record or claims; its
    # lock is still checked
    lock_only = sorted(set(locks) - set(keys))
    if only:
        want = set(only)
        keys = [k for k in keys if k in want]
        lock_only = [k for k in lock_only if k in want]
    if not keys and not lock_only:
        out.nothing_declared = True
        return out

    # phase 1: freshness + adjudication + record writes. Gating waits
    # until every record is written (see the docstring note).
    lock_messages: dict = {}   # key -> the tripped-lock failure line
    for key in lock_only:
        fn = _resolve_func_ref(key, root=root)
        if fn is None:
            msg = (f"{key}: locked, but no function of that name resolves; "
                   f"restore it, or a human runs: mathema unlock {key}")
        elif lock_state(key, (form := analyze(fn).form), locks,
                        {}) == "changed":
            lk = locks.get(key) or {}
            msg = (f"{key}: locked at form {lk.get('form')} but the code "
                   f"is now {form}; there is no record to "
                   f"compare. Restore the function, or a human runs: "
                   f"mathema unlock {key}")
        else:
            continue
        out.problems.append(msg)
        out.lines.append(f"FAIL {msg}")
        out.keys.append({"key": key, "why": "locked-changed",
                         "passed": False, "problems": [msg],
                         "integrity_mismatch": False, "counts": {},
                         "claims": []})
    key_problems: dict = {}   # key -> failure lines raised outside the gate

    def _fail(key: str, msg: str) -> None:
        out.problems.append(msg)
        out.lines.append(f"FAIL {msg}")
        key_problems.setdefault(key, []).append(msg)

    pending: list = []   # (key, why, claims_for_gate, rec_or_none,
                         #  deps, accepted, unresolved, source_line)
    for key in keys:
        # the freshness baseline comes from the verified layer alone; a
        # declared entry (claims/*.yaml, claimspec.yaml, ...) never
        # carries an identity, so it must never be read for this
        verified_info = verified.get(key)
        verified_entry = verified_info["entry"] if verified_info else {}
        # the CI half of the acceptance policy: a standing acceptance
        # the policy would refuse to write today fails the sweep, so an
        # unverified sign-off cannot ride in through the record file
        for msg in acceptance_policy_problems(key, verified_entry, policy):
            _fail(key, msg)
        from .acceptance import unaccepted_retirements
        for section, name in unaccepted_retirements(verified_entry):
            _fail(key, f"{key}: the {section} row {name!r} carries no "
                       f"acceptance, and only `mathema accept` retires a "
                       f"claim, so it retires nothing; remove the row, or "
                       f"accept the claim with `mathema accept {key} "
                       f"{name} --as ...`")
        recorded_form = (verified_entry.get("identity") or {}).get("form")
        declared_info = declared.get(key)
        source = (declared_info or verified_info)["source"]
        fn = _resolve_func_ref(key, root=root)
        if fn is None:
            rows = verified_entry.get("claims") or []
            # `all` is this function's own --all flag here, so the
            # builtin is spelled via any()
            if rows and not any((r.get("meta") or {}).get(
                    "mathema.surface") != "compendium" for r in rows):
                # a compendium key whose package is not importable
                # here: testimony pending acceptance, never a sweep
                # failure. Its rows still resolve premises once
                # accepted; reverification needs the library.
                out.lines.append(
                    f"note {key}: stub testimony only, library not "
                    f"importable here; accept rows --as trusted, or "
                    f"install the package for the sweep to reverify")
                continue
            msg = f"{key}: cannot resolve to a live function"
            out.problems.append(msg)
            out.lines.append(f"FAIL {key}: cannot resolve to a live function "
                             f"(declared in {source})")
            # never reaches `pending`, so it gets its own structured
            # entry, nothing may be visible in prose alone
            out.keys.append({"key": key, "why": "unresolvable",
                             "passed": False,
                             "problems": ["cannot resolve to a live function"],
                             "counts": {}, "claims": []})
            continue
        # file-declared claims win per claim name over decorator/
        # docstring claims on the live function (spec.declare()/
        # authoring.py's three-surface precedence), merge before
        # adjudicating or fingerprinting, so both see the same,
        # complete claim set
        from .spec import integrity_diagnosis, integrity_matches
        if integrity_matches(verified_entry) is False:
            integrity_warned.add(key)
            diagnosis = integrity_diagnosis(key, verified_entry, root)
            if policy.get("require_verification"):
                # under a policy that requires human-verified sign-offs
                # the record's own contents are part of the evidence,
                # so a mismatch fails the sweep rather than warning
                _fail(key, diagnosis.replace("WARN ", "", 1)
                      + " This project's policy requires verification, "
                        "so the mismatch fails the run.")
            else:
                out.lines.append(diagnosis)
        file_entry = declared_info["entry"] if declared_info else {}
        # a record the running version cannot parse (a claim whose
        # statement no longer reads as a law) is a per-key finding
        # with a named remedy, never a sweep-wide abort: the store
        # is committed evidence, and every other key still deserves
        # its verdict
        try:
            from .sync import apply_verified_wins, claim_conflicts
            _conflicts = claim_conflicts(fn, file_entry, verified_entry or None)
            for conflict in _conflicts:
                if conflict.get("kind") == "supersession":
                    msg = (f"{key}: claim {conflict['claim']!r} was "
                           f"re-authored but is already verified, the "
                           f"verified version keeps adjudicating; adopt the "
                           f"change with `mathema accept {key} "
                           f"{conflict['claim']} --as superseded`")
                else:
                    msg = (f"{key}: claim {conflict['claim']!r} differs "
                           f"between the docstring and the declared file, "
                           f"run `mathema docsync` to resolve")
                _fail(key, msg)
            merged_entry = resolve_declared(fn, file_entry=file_entry)
            current_claims = merged_entry.get("claims") or []
            if verified_entry:
                # the record never gets silently rewritten by a
                # re-authored claim: pending supersessions adjudicate the
                # VERIFIED version until accepted
                current_claims = apply_verified_wins(
                    current_claims, _conflicts, verified_entry)
            # the verified layer is append-only in MEMBERSHIP: a claim
            # removed from every authoring surface is repopulated from
            # its verified row (statement/route reconstruct it), so the
            # adjudication set never silently shrinks and acceptance/
            # verdict history are never dropped. The exits are
            # supersession (discoveries) and human acceptance
            # (historical), never deletion.
            current_claims = _union_verified_membership(
                current_claims, verified_entry)
            current_claims, retired_notes = _drop_retired_declared(
                key, current_claims, verified_entry,
                (declared_info or {}).get("source"))
            out.lines.extend(retired_notes)
            retired_noted = {ln.split("'")[1] for ln in retired_notes}
            merged_entry = dict(merged_entry)
            merged_entry["claims"] = current_claims
            entry_grammar = merged_entry.get("grammar", GRAMMAR)
            out.grammars_seen.update(c.get("grammar", entry_grammar)
                                     for c in current_claims)
            current_fp = claims_fingerprint(current_claims)
        except InvalidConjecture as e:
            if _record_has_unreadable_claim(verified_entry):
                msg = (f"{key}: a claim in this function's verified "
                       f"record does not parse under the current "
                       f"grammar ({e}); rebuild the record: delete "
                       f".mathema/verified/{key}.yaml and re-run verify")
            else:
                where = ((declared_info or {}).get("source")
                         or "its docstring or claims file")
                msg = (f"{key}: a claim declared in {where} does not "
                       f"parse ({e}); correct it there and re-run verify")
            out.problems.append(msg)
            out.lines.append(f"FAIL {msg}")
            out.keys.append({"key": key, "why": "unreadable-record",
                             "passed": False, "problems": [msg],
                             "counts": {}, "claims": []})
            continue
        recorded_fp = (verified_entry.get("identity") or {}).get(
            "claims_fingerprint")
        facts_now = analyze(fn)
        state = lock_state(key, facts_now.form, locks, verified_entry)
        if state == "changed":
            # the lock's whole point: the record is left exactly as it
            # was (no re-adjudication, no baseline drift onto code a
            # human never sanctioned), and the run fails naming the
            # remedy. Restoring the function, or a human unlocking,
            # are the two ways forward.
            lk = locks.get(key) or {}
            msg = (f"{key}: locked at form {lk.get('form')} but the code "
                   f"is now {facts_now.form}; the record is unchanged. "
                   f"Restore the function, or a human runs: "
                   f"mathema unlock {key}")
            out.problems.append(msg)
            lock_messages[key] = msg
            stored = verified_entry.get("claims") or []
            pending.append((key, "locked-changed", stored, None, None,
                            _accepted_risk(verified_entry), (),
                            verified_info))
            continue
        if state == "removed-outside":
            # the record still says locked; the meta entry is gone
            # without `mathema unlock` having run
            msg = (f"{key}: the verified record carries a lock stamp but "
                   f".mathema/meta/locks.yaml has no entry; a lock is "
                   f"only removed by a human running `mathema unlock "
                   f"{key}` (restore the entry, or unlock properly)")
            _fail(key, msg)
        from .compendium import premise_state as _premise_state
        premise_now = _premise_state(current_claims, stub_premises)
        recorded_premises = (verified_entry.get("meta") or {}).get(
            "mathema.premise_state")
        is_fresh = (bool(recorded_form) and facts_now.form == recorded_form
                    and recorded_fp == current_fp
                    and (premise_now == (recorded_premises or {})
                         if premise_now or recorded_premises else True))
        deps_now = function_dependencies(fn, facts_now) if is_fresh else None
        dependency_changed = is_fresh and any(
            _dependency_state(d, verified) in ("stale", "invalidated")
            for d in deps_now or [])
        if is_fresh and not dependency_changed:
            # a module-level constant is compared by VALUE against this
            # record's own stored dependency entry, the form hash
            # cannot see a global change, so this check is what keeps
            # an inlined constant honest
            stored_deps = {d.get("name"): d for d in
                           verified_entry.get("dependencies") or []
                           if d.get("kind") == "constant"}
            live_consts = {d["name"]: d for d in deps_now or []
                           if d.get("kind") == "constant"}
            dependency_changed = (set(stored_deps) != set(live_consts)
                                  or any(stored_deps[n].get("value")
                                         != live_consts[n].get("value")
                                         for n in stored_deps))
        accepted = _accepted_risk(verified_entry)

        # a key the user NAMED is always re-adjudicated: freshness is
        # an optimisation for a whole-store sweep, and silently
        # skipping the one key someone asked about is what made the
        # integrity warning's own remedy a no-op
        if is_fresh and not dependency_changed and not all and not only:
            out.fresh += 1
            _heal_concepts(key, fn, facts_now, merged_entry, verified_info,
                           root, write_yaml)
            # a lock set through the library (no CLI stamp) still
            # becomes tamper-evident at the next sweep: the record's
            # reflection is healed to match the meta entry, so the
            # fresh path cannot leave a lock invisible to the
            # removed-outside check
            if state == "held" and verified_info:
                lk = locks.get(key) or {}
                want = {k: lk[k] for k in ("form", "at", "by") if k in lk}
                entry_now = verified_info["entry"]
                if entry_now.get("locked") != want:
                    entry_now["locked"] = want
                    if key not in integrity_warned:
                        from .spec import integrity_checksum
                        entry_now.setdefault("identity", {})["integrity"] = \
                            integrity_checksum(entry_now)
                    write_yaml(os.path.join(root, verified_info["source"]),
                               {key: entry_now},
                               header=f"machine record; binds to form "
                                      f"{recorded_form}")
            stored = verified_entry.get("claims") or []
            pending.append((key, "fresh", stored, None, deps_now, accepted,
                            (), verified_info))
            continue

        claims = entry_claims(merged_entry)
        # declared claims only: verify never adjudicates suggestions
        # (an empty declared set means no claims, not "go conjecture")
        from .spec import attach_recorded_pins
        attach_recorded_pins(claims, verified_entry or None)
        if materialize_referenced_entries(root, claims, stub_premises):
            # a referenced compendium row just entered the verified store at
            # declared status; re-resolve so this key's notes and any
            # later key's premises see it
            stub_premises = _external_premises(root)
        rec = check(fn, claims=claims if claims else [],
                    trials_scale=trials_scale,
                    known_premises=stub_premises)
        rec.probes, late_notes = _strip_retired_probes(
            key, rec.probes, verified_entry or {}, retired_noted)
        out.lines.extend(late_notes)
        out.lines.extend(_born_falsified_hint(key, rec.probes,
                                              verified_entry or {}))
        _apply_declared_extras(rec, merged_entry)
        rec.probes.append(dependencies_current_probe(rec.dependencies,
                                                     root=root))
        why = ("dependency changed" if dependency_changed
               else "forced (--all)" if all and is_fresh
               else "targeted re-verify" if only and is_fresh
               else "no baseline record" if not recorded_form
               else "claims changed" if facts_now.form == recorded_form
               else "form changed")
        rec.meta = {**(getattr(rec, "meta", None) or {}),
                    "mathema.premise_state": premise_now}
        written = write_record(rec, key=key, root=root,
                               claims=current_claims,
                               declared_intent=merged_entry.get("intent"))
        _carry_recorded_verdicts(rec.probes, written, key)
        out.adjudicated += 1
        pending.append((key, why, list(rec.probes), rec, rec.dependencies,
                        accepted, rec.facts.unresolved, verified_info))

    # phase 2: every record is on disk, settle each key's
    # dependencies_current against the completed store, patching the
    # record where the verdict moved (the memoization rung's verdict
    # depends on the STORE, never on this function's own form)
    settled = load_verified(root)
    from .spec import integrity_checksum
    for key, why, claims_for_gate, rec, deps, _accepted, _unres, vinfo in pending:
        if deps is None:
            continue
        stored_dc = next(
            (c for c in claims_for_gate
             if _claim_fields(c)[0] == "dependencies_current"), None)
        if stored_dc is None:
            continue
        dc_now = dependencies_current_probe(deps, root=root)
        _, old_verdict, _, _ = _claim_fields(stored_dc)
        if dc_now.verdict == old_verdict:
            continue
        if isinstance(stored_dc, dict):
            stored_dc["verdict"] = dc_now.verdict
            stored_dc["sketch"] = dc_now.sketch
            stored_dc["counterexample"] = dc_now.counterexample
            entry = vinfo["entry"] if vinfo else None
            if entry is not None:
                recorded_form = (entry.get("identity") or {}).get("form")
                if key not in integrity_warned:
                    # restamp only a record that matched before this
                    # write, so settling never clears a mismatch
                    entry.setdefault("identity", {})["integrity"] = \
                        integrity_checksum(entry)
                write_yaml(os.path.join(root, vinfo["source"]), {key: entry},
                           header=f"machine record; binds to form "
                                  f"{recorded_form}")
        else:
            stored_dc.verdict = dc_now.verdict
            stored_dc.sketch = dc_now.sketch
            stored_dc.counterexample = dc_now.counterexample
            entry = settled.get(key)
            if entry is not None:
                for c in entry["entry"].get("claims") or []:
                    if c.get("name") == "dependencies_current":
                        c["verdict"] = dc_now.verdict
                        c["sketch"] = dc_now.sketch
                        c["counterexample"] = dc_now.counterexample
                recorded_form = (entry["entry"].get("identity") or {}).get("form")
                entry["entry"].setdefault("identity", {})["integrity"] = \
                    integrity_checksum(entry["entry"])
                write_yaml(os.path.join(root, entry["source"]),
                           {key: entry["entry"]},
                           header=f"machine record; binds to form "
                                  f"{recorded_form}")

    # phase 3: gate every key through the one policy and render lines
    for key, why, claims_for_gate, rec, deps, accepted, unres, _vinfo in pending:
        report = gate(claims_for_gate, strict=strict,
                      accepted_risk=accepted, unresolved=unres)
        state = "FAIL" if report.problems or key_problems.get(key) else "ok"
        if why == "locked-changed":
            # the record is left as it was, so its counts describe code
            # that no longer exists: the row is the lock failure alone
            line = f"FAIL {lock_messages[key]}"
            if report.problems:
                line += "; " + "; ".join(report.problems)
        elif why == "fresh":
            line = f"{state:4} {key}: fresh"
            if report.problems:
                line += "; " + "; ".join(report.problems)
        else:
            line = f"{state:4} {key}: {why}; {summary_counts(report)}"
            if report.foreign:
                grammars = sorted({_claim_fields(p)[2]
                                   ["mathema.foreign_grammar"]
                                   for p in report.foreign})
                line += (f", {len(report.foreign)} not this grammar "
                         f"({', '.join(grammars)})")
            if report.problems:
                line += "  <- " + "; ".join(report.problems)
        out.problems.extend(f"{key}: {p}" for p in report.problems)
        out.lines.append(line)
        out.keys.append({
            "key": key,
            "why": why,
            "passed": (not report.problems and key not in lock_messages
                       and not key_problems.get(key)),
            "problems": ([lock_messages[key]] if key in lock_messages
                         else []) + key_problems.get(key, [])
                        + list(report.problems),
            "integrity_mismatch": key in integrity_warned,
            "counts": {"proven": report.proven, "holds": report.holds,
                       "refuted": report.refuted,
                       "falsified": report.falsified,
                       "invalidated": report.invalidated,
                       "unknown": report.unknown,
                       "accepted_risk": report.owned,
                       "skipped": report.skipped,
                       "foreign_grammar": len(report.foreign)},
            # claim_row reads a live Probe or a stored claim dict alike,
            # so fresh and re-adjudicated keys serialize identically
            "claims": [claim_row(c, accepted_risk=accepted)
                       for c in claims_for_gate],
        })
    return out
