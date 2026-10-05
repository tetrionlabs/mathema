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

(The derive-seam soundness gates, corroboration and the float companion, live
in `gates.py`; this module gates adjudication OUTCOMES, not evidence.)
"""
from __future__ import annotations

import copy
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


def _claim_statement(c) -> str:
    """A claim's statement, from a live Probe or a stored claim dict."""
    if isinstance(c, dict):
        return str(c.get("statement") or "")
    return str(getattr(c, "statement", "") or "")


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
    # of the proven, the built-in ones mathema adds (dependencies_current)
    builtin_proven: int = 0
    # the unknown claims by name, each with its one-line reason
    unknown_reasons: list = field(default_factory=list)
    # the clauses of the policy rows mathema wrote that do not hold
    unaccounted: list = field(default_factory=list)
    # the clauses of the declared policy rows that are falsified
    policy_problems: list = field(default_factory=list)

    @property
    def refuted(self) -> int:
        """The claims a counterexample stands against, `falsified` and
        `invalidated` together: the `refuted` stance of the claim-row
        vocabulary."""
        return self.falsified + self.invalidated


#: whether the missing-value policy rows mathema writes are gated and
#: counted as claims: a contradicted default or a raise no claim accounts
#: for is then falsified, and fails as any falsified claim does; off, they
#: are reported beside the counts and the function passes
POLICY_ROWS_GATE = True


def _unaccounted_text(report) -> str:
    """One clause per policy row mathema wrote that does not hold:
    `; missing[x]: f drops a missing x (nan in, 1.0 out), the row says
    propagates; change the word or the code`, `; absent[x]: f raised
    TypeError at x = None, and no claim says it may (state
    `absent(f, x) raises(TypeError)`)`, or an empty string."""
    found = getattr(report, "unaccounted", None) or []
    return "".join(f"; {text}" for text in found)


def _policy_clause(name: str, statement: str, pol: dict) -> "str | None":
    """The clause a verify or check line carries for one policy row that
    does not hold, from the row's own meta: the row, what f does, whose
    word it contradicts, and the one next step."""
    import re as _re
    nxt = pol.get("next") or ""
    first = _re.search(r"`([^`]+)`", nxt)
    to_write = first.group(1) if first else None
    if pol.get("sentence"):
        sentence = pol["sentence"]
        if sentence.startswith("f has no single policy"):
            rows = len(_re.findall(r"`[^`]+`", nxt.split("; or ", 1)[0]))
            return (f"{name}: {sentence}" + (f", {rows} rows to state" if rows > 1
                                              else ""))
        if "does not declare it" in sentence:
            return (f"{name}: {sentence}; declare the return type Optional, or return a "
                    f"value")
        tail = (f"; state `{to_write}` or handle None" if pol.get("kind") == "absent"
                and to_write else f"; state `{to_write}` or change f" if to_write else "")
        return f"{name}: {sentence}{tail}"
    reason = pol.get("reason") or ""
    m = _re.search(r"f (\w+) instead: (.+)$", reason)
    lib = _re.match(r"from (\S+)'s own policy row, which f calls; f (.+?) instead at (.+)$",
                    reason)
    if lib:
        return (f"{name}, {lib.group(1)}'s row says {pol.get('behaviour')} "
                f"{_when_words(pol.get('premise') or '')} and f {lib.group(2)} at "
                f"{lib.group(3)}".replace("  ", " ")
                + (f"; state `{to_write}` or change f" if to_write else ""))
    if not m:
        return None
    did, entry = m.group(1), m.group(2)
    kind = pol.get("kind") or "missing"
    param = pol.get("parameter") or "input"
    word = statement.split(") ", 1)[-1] if ") " in statement else pol.get("behaviour")
    whose = ("mathema's default says" if pol.get("source") == "default"
             else "the row says")
    if did == "raises":
        exc = entry.rsplit(", ", 1)[-1].replace("raised ", "")
        slot = _re.match(r"a (\S+) slot in", entry)
        where = (f"at a {slot.group(1)} slot of {param}" if slot
                 else f"at {param} = None" if kind == "absent" else f"at a missing {param}")
        what = f"f raises {exc} {where}"
    else:
        what = (f"f {did} {param} = None ({entry})" if kind == "absent"
                else f"f {did} a missing {param} ({entry})")
    remedy = (f"; write `{to_write}` or change f" if to_write
              else "; change the word or the code")
    return f"{name}, {what} where {whose} {word}{remedy}"


def _when_words(premise: str) -> str:
    if premise.endswith(">= 1"):
        return "when values remain"
    if premise.endswith("== 0"):
        return "when every slot is missing"
    return ""


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
    builtin = (counts.get("builtin_proven", 0) if isinstance(counts, dict)
               else getattr(counts, "builtin_proven", 0))
    proven = f"{get('proven')} proven"
    if builtin and get("proven") > builtin:
        mine = get("proven") - builtin
        proven += (f" ({mine} claim{'s' if mine != 1 else ''}, {builtin} "
                   f"built-in)")
    parts = [proven, f"{get('holds')} holds", f"{get('falsified')} falsified"]
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
        A stored `invalidated` is carried over, and so is the accepted
        level of a trusted row the sweep could not settle
        (`mathema.trusted_unsettled`) or settled only more weakly
        (`mathema.strongest_evidence`, with the row's note), with that
        marker; every other verdict is already the probe's own.
    """
    import yaml

    try:
        with open(path, encoding="utf-8") as fh:
            entry = (yaml.safe_load(fh) or {}).get(key) or {}
    except OSError:
        return
    stored = {c.get("name"): c.get("verdict")
              for c in entry.get("claims") or []}
    trusted = {c.get("name"): c for c in entry.get("claims") or []
               if {"mathema.trusted_unsettled", "mathema.strongest_evidence"}
               & set(c.get("meta") or {})}
    for p in probes:
        if classify_verdict(stored.get(p.name) or "") == "invalidated":
            p.verdict = stored[p.name]
        elif p.name in trusted:
            row = trusted[p.name]
            p.verdict = stored[p.name]
            p.meta = {**(p.meta or {}), **{
                k: v for k, v in (row.get("meta") or {}).items()
                if k in ("mathema.trusted_unsettled",
                         "mathema.strongest_evidence")}}
            if "mathema.strongest_evidence" in (row.get("meta") or {}):
                p.note = row.get("note") or p.note


#: the short name a summary line gives a falsified gate claim
_GATE_LABELS = {"is_missing_safe": "gate", "is_absent_safe": "gate",
                "is_empty_safe": "empty"}


def gate(claims, *, strict: bool,
         accepted_risk: frozenset = frozenset(),
         unresolved=(), key: "str | None" = None) -> GateReport:
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
    gate_fails: list = []
    claims = list(claims)
    # a line under a claim mathema suggested is part of the suggestion
    suggested = {_claim_fields(c)[0] for c in claims
                 if _volunteered(_claim_fields(c)[2], _claim_fields(c)[3])}
    for c in claims:
        name, verdict, meta, note = _claim_fields(c)
        if "mathema.foreign_grammar" in meta:
            r.foreign.append(c)
            continue
        statement = _claim_statement(c)
        label = next((lab for rel, lab in _GATE_LABELS.items()
                      if statement.startswith(rel + "(")), None)
        parent = meta.get("mathema.companion_of")
        if parent is not None and parent in suggested:
            continue
        if label and classify_verdict(verdict) == "falsified":
            reason = ((meta.get("mathema.gate") or {}).get("reason")
                      or (c.get("counterexample") if isinstance(c, dict)
                          else getattr(c, "counterexample", None)) or "")
            under = f" under {parent}" if parent else ""
            line = (f"{label} ({statement}{under}) falsified: {reason}"
                    + (f"; mathema claims {key} prints the rows to state"
                       if key and label == "gate" else ""))
            if line not in gate_fails:
                gate_fails.append(line)
        pol = meta.get("mathema.policy")
        if pol and classify_verdict(verdict) == "falsified":
            clause = _policy_clause(name, _claim_statement(c), pol)
            if clause and _volunteered(meta, note) and not POLICY_ROWS_GATE:
                if clause not in r.unaccounted:
                    r.unaccounted.append(clause)
            elif clause:
                r.policy_problems.append(clause)
        if _volunteered(meta, note) and not (pol and POLICY_ROWS_GATE):
            continue
        kind = classify_verdict(verdict)
        if verdict == "skipped:unknown_but_accepted":
            # the stored form of an unknown a person accepted as risk
            r.owned += 1
            continue
        if kind == "proven":
            r.proven += 1
            if meta.get("mathema.surface") == "builtin":
                r.builtin_proven += 1
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
                r.unknown_reasons.append((name, _first_sentence(note)))
        elif kind == "skipped":
            r.skipped += 1
    # a falsified or invalidated claim is a failing check, in every
    # mode; strictness only governs structurally-skipped claims, never
    # wrong or undecided ones
    if r.falsified:
        # a falsified gate names itself and its reason, and the policy
        # rows under it are the same fact; else the policy rows name
        # themselves and the one-word edit; any other falsified claim is
        # counted
        r.problems.extend(gate_fails)
        if r.policy_problems and not gate_fails:
            n = len(r.policy_problems)
            r.problems.append(f"{n} policy row{'s' if n != 1 else ''} to settle: "
                              + "; ".join(r.policy_problems)
                              + (f" (mathema claims {key})" if key else ""))
        others = r.falsified - len(r.policy_problems) - len(gate_fails)
        if others > 0:
            r.problems.append(f"{others} falsified claim(s)")
    if r.invalidated:
        r.problems.append(f"{r.invalidated} invalidated claim(s)")
    if r.unknown:
        # an unaccepted unknown is an open epistemic gap: it fails in
        # every mode until it is resolved or a human owns the risk
        # (mathema accept --as risk)
        named = [f"{n} unknown: {why}" if why else f"{n} unknown"
                 for n, why in r.unknown_reasons]
        r.problems.append("; ".join(named) if named else
                          f"{r.unknown} unknown claim(s)")
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


def _entry_at(path: str, key: str) -> dict:
    """Intent:
        The record entry stored under `key` in the YAML file at `path`,
        or an empty mapping when the file cannot be read.
    """
    import yaml
    try:
        with open(path, encoding="utf-8") as fh:
            return (yaml.safe_load(fh) or {}).get(key) or {}
    except OSError:
        return {}


def _first_sentence(note) -> str:
    """A note's first clause, short enough for a summary line: `x = nan
    gives nan, nothing to compare`."""
    text = (note or "").strip()
    head = text.split(". ", 1)[0].split("; ", 1)[0]
    head = head.replace("the only listed point, ", "")
    head = head.replace(", gives", " gives").replace(", raises", " raises")
    head = head.replace(" back, so there is no value to compare with",
                        ", nothing to compare with")
    return head[:120]


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

    `authoring_errors` lists the problems that are the author's to fix
    on an authoring surface (a declared claim that does not parse),
    which the CLI exits 2 on rather than 1.

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
    authoring_errors: list = field(default_factory=list)


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
        matchers.append((row["name"], _same_law_as(stmt, key) if stmt else None))
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
             and getattr(p, "name", None) not in known
             and (getattr(p, "meta", None) or {}).get("mathema.surface") != "mathema"]
    if not fresh:
        return []
    lines = []
    for p in list(fresh):
        gate_meta = (getattr(p, "meta", None) or {}).get("mathema.gate") or {}
        if gate_meta.get("reason"):
            lines.append(f"note {key}: gate ({p.statement}) falsified on first "
                         f"adjudication: {gate_meta['reason']}. State the rows mathema "
                         f"claims {key} prints, or change f; the claim is kept until "
                         f"you do.")
            fresh.remove(p)
            continue
        pol = (getattr(p, "meta", None) or {}).get("mathema.policy") or {}
        clause = _policy_clause(p.name, p.statement, pol) if pol else None
        if clause:
            lines.append(f"note {key}: {p.name} falsified on first adjudication; "
                         + clause[len(str(p.name)):].lstrip(":,").strip().replace(
                             "; change the word or the code",
                             ". Change the word in the claims file, or change f."))
            fresh.remove(p)
    if not fresh:
        return lines
    names = ", ".join(sorted(str(p.name) for p in fresh))
    return lines + [f"note {key}: {names} falsified on first adjudication. A "
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
            if (getattr(p, "meta", None) or {}).get("mathema.companion_of") \
                    or (getattr(p, "meta", None) or {}).get("mathema.surface") == "mathema":
                # a retired float companion is respawned by every proof of
                # its parent, and a retired policy row by every check;
                # retirement is the standing disposition
                continue
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
        fields so it keeps being adjudicated. A law retired as a
        discovery and a name accepted as historical never resurrect; a
        live row under a superseded name is the superseding version,
        and a live row stating a different law under a discovered name
        is new authorship, so both are membership like any other.
        Suggestion rows (surface mathema) and rows with no statement
        are not membership.

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
    from .acceptance import _same_law_as, honoured_retirements
    historical = {r.get("name") for r in
                  honoured_retirements(verified_entry, "historical")}
    discovered = []
    for r in honoured_retirements(verified_entry, "discoveries"):
        law = r.get("statement") or r.get("law") or ""
        discovered.append((r.get("name"), _same_law_as(law) if law else None))
    for row in verified_entry.get("claims") or []:
        name = row.get("name")
        statement = row.get("statement") or row.get("law")
        if not name or not statement or name in have or name in historical:
            continue
        if any(n == name and (same is None or same(statement))
               for n, same in discovered):
            continue
        meta = row.get("meta") or {}
        if meta.get("mathema.surface") in ("mathema", "builtin",
                                                "types"):
            continue
        if name == "dependencies_current":
            # the per-record dependency freshness probe is synthesized
            # each sweep, never a declared claim
            continue
        if meta.get("mathema.companion_of"):
            # a float companion is spawned by its parent's proof on every
            # adjudication, never a declared claim of its own
            continue
        # the row's statement is the canonical text, self-contained,
        # and the structured fields ride beside it; reconstruction
        # reads them directly, never a rendered condition (`condition`
        # is the region the EVIDENCE covered, which on the derive
        # route may be narrower than the claim's own domain)
        from .spec import authored_route
        rebuilt = {"name": name, "statement": statement,
                   "route": authored_route(row)}
        for field_name in ("domain", "grammar", "tolerance"):
            if row.get(field_name) is not None:
                rebuilt[field_name] = row[field_name]
        rebuilt.setdefault("meta", {})["mathema.membership"] = \
            "repopulated-from-verified"
        out.append(rebuilt)
    return out


def verify_project(root: str = ".", *, all: bool = False,
                   strict: bool = True,
                   trials_downscale: float | None = None,
                   only: "list | None" = None,
                   files: "list | None" = None,
                   trials_scale: float | None = None) -> VerifyResult:
    """The test-runner sweep as a library call: for every key the
    declared/verified stores know, re-adjudicate if the function's form
    hash, claims fingerprint, or a dependency changed (`all=True`
    forces everything), rewrite the record, and gate each key's
    adjudicated claims through `gate`. `only` restricts the sweep to the
    given dotted keys (the single-key re-verify the reconcile workflow
    points at); None sweeps the whole population. `files` names claims
    files whose every entry is adjudicated up front, whether or not the
    project calls it (`claims_file_entries`); with `files` the sweep is
    restricted to their entries plus any `only` keys.

    Notes:
        `dependencies_current` claims are settled AFTER the whole sweep
        has written its records, so a caller adjudicated before its
        callee in the same run still reads the callee's fresh record;
        the sweep's outcome does not depend on key order.
    """
    from .probing import resolve_trials_downscale
    trials_scale = resolve_trials_downscale(trials_downscale, trials_scale)
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
                             trials_scale=trials_scale, only=only,
                             files=files)


def resolve_claims_file(target: str, root: str = ".") -> "str | None":
    """Intent:
        The claims file a `mathema verify` target names, or None when
        the target is not a path to one (a dotted key). A path is read
        as given, then under `root`; `mathema/compendium/...`, the
        spelling a record gives a bundled file, names the file mathema
        ships.
    """
    import os
    if not target.endswith((".yaml", ".yml")):
        return None
    from .compendium import _bundled_dir
    candidates = [target, os.path.join(root, target)]
    prefix = os.path.join("mathema", "compendium") + os.sep
    if target.replace("/", os.sep).startswith(prefix):
        candidates.append(os.path.join(
            _bundled_dir(), target.replace("/", os.sep)[len(prefix):]))
    for path in candidates:
        if os.path.isfile(path):
            return os.path.abspath(path)
    return None


def _defines_only(entry) -> bool:
    """Whether a claims-file entry only states its runtime's definitions
    (`defines:`) and no claim: a key with nothing to adjudicate."""
    return (isinstance(entry, dict) and bool(entry.get("defines"))
            and not entry.get("claims"))


def claims_file_entries(path: str, root: str,
                        library_claims: dict) -> "tuple[dict, bool, list]":
    """Intent:
        The entries of one claims file as the sweep adjudicates them:
        `(entries, is_library, lines)`, `entries` mapping each key to
        `{"entry", "source"}`, `is_library` whether the file declares
        `compendium:`, and `lines` the one-line notes the sweep prints.
        A compendium file's key takes the entry that applies to it
        (`load_library_claims`, where a project file shadows a bundled
        one), else the file's own, stamped as compendium testimony.

    Notes:
        A compendium file whose library is not importable, or is
        installed outside the file's `versions` range, contributes no
        entries and one line saying which; so does one naming the
        project's own package.
    """
    from .compendium import (_display_path, _installed_version,
                             applicable_tag, mark_row_versions,
                             names_own_package, pop_library_fields)
    from .spec import read_claims_file, stamp_library_rows
    where = _display_path(path, root)
    data = read_claims_file(path, where) or {}
    file_grammar = data.pop("grammar", None)
    library, versions, aliases = pop_library_fields(data)
    entries: dict = {}
    if library is None:
        for key, entry in data.items():
            if isinstance(entry, dict) and not _defines_only(entry):
                entry = dict(entry)
                if file_grammar:
                    entry.setdefault("grammar", file_grammar)
                entries[key] = {"entry": entry, "source": where}
        return entries, False, []
    if names_own_package(library, root) and not where.startswith(
            os.path.join("mathema", "compendium")):
        return {}, True, [
            f"note {where}: `compendium: {library}` names this project's "
            f"own package; nothing in it was adjudicated"]
    tag = applicable_tag(library, versions, aliases)
    lines: list = []
    if tag is None:
        installed = _installed_version(library, aliases)
        if installed is None:
            return {}, True, [f"note {where}: {library} is not importable "
                              f"here; nothing in it was adjudicated"]
        # installed outside the file's range: every row is adjudicated
        # against the installed version and marked outside its range,
        # so it is recorded and never used as a fact
        tag = f"compendium:{library}-{'.'.join(installed.split('.')[:2])}"
        for entry in data.values():
            for row in (entry.get("claims") or []
                        if isinstance(entry, dict) else []):
                if isinstance(row, dict):
                    row.setdefault("versions", versions)
        lines.append(
            f"note {where}: {library} {installed} is outside the file's "
            f"range {versions}; its rows are adjudicated against "
            f"{library} {installed} and never used as facts here (`mathema "
            f"compendium export {library}` writes the rows that hold into "
            f"a project compendium for this version)")
    stamp_library_rows(data, tag)
    mark_row_versions(data, library, aliases)
    for key, entry in data.items():
        if not isinstance(entry, dict) or _defines_only(entry):
            continue
        info = library_claims.get(key)
        if info and lines:
            # the key's applicable rows stay; this file's rows join them
            names = {r.get("name") for r in info["entry"].get("claims") or []}
            merged = dict(info["entry"])
            merged["claims"] = list(info["entry"].get("claims") or []) + [
                r for r in entry.get("claims") or []
                if r.get("name") not in names]
            entries[key] = {"entry": merged, "source": info["source"]}
            continue
        entries[key] = ({"entry": info["entry"], "source": info["source"]}
                        if info else {"entry": entry, "source": where})
    return entries, True, lines


def _defaults_moved(fn, merged_entry: dict, verified_entry: dict) -> bool:
    """Intent:
        Whether a library function's calls would now pass a different
        value than the record states (`mathema.defaults` on each row,
        per function the claim calls): a default the installed library
        changed, a parameter added or removed. Such a record is stale even though the claims and the
        form are not.
    """
    from .conjecture import claim_defaults
    from .spec import entry_claims
    try:
        current = entry_claims(merged_entry or {})
    except Exception:
        return False
    now: dict = {}
    for cj in current:
        resolved = claim_defaults(fn, cj)
        if resolved:
            now[cj.name] = resolved
    names = {cj.name for cj in current}
    recorded = {c.get("name"): (c.get("meta") or {}).get("mathema.defaults")
                for c in (verified_entry or {}).get("claims") or []
                if c.get("name") in names
                and (c.get("meta") or {}).get("mathema.defaults")}
    return now != recorded


def _pseudo_infinity_moved(fn, facts, merged_entry: dict,
                           verified_entry: dict) -> bool:
    """Intent:
        Whether the operational infinity a claim's computation runs to
        would now differ from what the record states
        (`mathema.pseudo_infinity` on the claim's rows): a changed or
        removed `MATHEMA_PSEUDO_INFINITY`, entry field or `let |inf|
        be`, compared only where it bounds an unbounded direction (P8).
        Such a record is stale, its claims unchanged (P7).
    """
    from dataclasses import replace

    from .conjecture import pseudo_infinity_stamp
    from .records import resolve_pseudo_infinity
    from .spec import entry_claims
    from .types import domain_from_signature
    try:
        current = entry_claims(merged_entry or {})
        parent = domain_from_signature(fn)
    except Exception:
        return False
    function_level = (merged_entry or {}).get("pseudo_infinity")
    now: dict = {}
    for cj in current:
        resolved = replace(cj, resolved_pseudo_infinity=resolve_pseudo_infinity(
            cj.pseudo_infinity, function_level))
        stamp = pseudo_infinity_stamp(resolved, facts, parent)
        if stamp is not None:
            now[cj.name] = stamp
    names = {cj.name for cj in current}
    recorded: dict = {}
    for c in (verified_entry or {}).get("claims") or []:
        meta = c.get("meta") or {}
        # a companion row belongs to the claim it was spawned from
        base = meta.get("mathema.companion_of") or c.get("name") or ""
        stamp = meta.get("mathema.pseudo_infinity")
        if base in names and stamp:
            recorded[base] = stamp
    return now != recorded


def _unsettled_library_hints(key: str, claims: list) -> list:
    """Intent:
        For each library row this sweep left unsettled (declared,
        unknown or skipped), the line naming both ways to settle it:
        accept it as trusted, or let verify adjudicate it against the
        installed library.
    """
    from .compendium import _compendium_hint
    out: list = []
    for c in claims:
        name, verdict, meta, _note = _claim_fields(c)
        if meta.get("mathema.surface") != "compendium":
            continue
        if classify_verdict(verdict) not in ("declared", "unknown",
                                             "skipped"):
            continue
        out.append(_compendium_hint(
            meta.get("mathema.compendium") or "a compendium", name, key,
            verdict))
    return out


def _no_applicable_file_note(key: str, entry: dict, root: str) -> str:
    """Intent:
        The line for a recorded library key no applicable claims file
        states rows for: the library and installed version, each claims
        file about the library with its range, and that the record is
        kept as it is.
    """
    from .compendium import _installed_version
    from .compendium.status import _library_files
    from .spec import read_claims_file
    library = key.split(".")[0]
    files = _library_files(root).get(library, [])
    aliases: list = []
    for f in files:
        aliases += list(f.get("aliases") or ())
    installed = _installed_version(library, aliases)
    have = (f"{library} {installed}" if installed
            else f"{library}, which is not installed here")

    def states_key(f: dict) -> bool:
        path = f["source"]
        if path.startswith(os.path.join("mathema", "compendium") + os.sep):
            from .compendium import _bundled_dir
            path = os.path.join(_bundled_dir(),
                                os.path.relpath(path, os.path.join(
                                    "mathema", "compendium")))
        else:
            path = os.path.join(root, path)
        try:
            return key in (read_claims_file(path, f["source"]) or {})
        except Exception:
            return False
    ranges = "; ".join(f"{f['source']} states it for {f['versions']}"
                       for f in files if states_key(f))
    return (f"note {key}: no claims file about {key} applies to {have}"
            + (f" ({ranges})" if ranges else "")
            + "; its record is kept as it is and not re-adjudicated")


def _library_population(root: str, verified: dict, declared: dict,
                        library_claims: dict) -> dict:
    """Intent:
        The library claim keys this sweep adjudicates, mapped to the
        claims file each one's rows come from: every key a swept
        function calls (through its import aliases, `np.sqrt` is
        `numpy.sqrt`), every key a swept claim names as a premise
        (`assuming numpy.clip.clip_lower holds`, or the bare row name),
        and every key already in the verified store. A project that
        never calls a library adjudicates none of its keys.
    """
    from . import analyze
    from .compendium import _referenced_names, library_keys_called
    from .conjecture import _resolve_func_ref

    if not library_claims:
        return {}
    by_row: dict = {}
    for lkey, info in library_claims.items():
        for c in info["entry"].get("claims") or []:
            if c.get("name"):
                by_row.setdefault(c["name"], set()).add(lkey)
    wanted: set = {k for k in verified if k in library_claims}
    for key in set(verified) | set(declared):
        if key in library_claims:
            continue
        rows = list(((declared.get(key) or {}).get("entry") or {})
                    .get("claims") or [])
        rows += list(((verified.get(key) or {}).get("entry") or {})
                     .get("claims") or [])
        fn = _resolve_func_ref(key, root=root)
        if fn is not None:
            try:
                facts = analyze(fn)
                wanted |= library_keys_called(fn, facts,
                                              library_claims=library_claims)
                from .definitions import called_keys
                wanted |= called_keys(fn, facts) & set(library_claims)
                from .authoring import resolve_declared
                rows += list(resolve_declared(fn, file_entry={})
                             .get("claims") or [])
            except Exception:
                pass
        for name in _referenced_names(rows):
            head, _, row = name.rpartition(".")
            if head in library_claims:
                wanted.add(head)
            wanted |= by_row.get(name, set())
    return {k: library_claims[k]["source"] for k in sorted(wanted)}


def _verify_sweep(root: str = ".", *, all: bool = False,
                  strict: bool = True,
                  trials_scale: float = 1.0,
                  only: "list | None" = None,
                  files: "list | None" = None) -> VerifyResult:
    """Intent:
        The sweep body of `verify_project`, which shields it from the
        per-key state-dependence warning chatter.
    """
    from . import analyze, check
    from .compendium import external_premises as _external_premises
    from .compendium import install as _install_compendium
    from .compendium import load_library_claims
    _install_compendium(root)
    library_claims = load_library_claims(root)
    stub_premises = _external_premises(root, library_claims=library_claims)
    from .authoring import resolve_declared
    from .conjecture import (GRAMMAR, InvalidConjecture,
                             _resolve_func_ref)
    from .inventory import function_dependencies
    from .spec import (_dependency_state, claims_fingerprint,
                       dependencies_current_probe, entry_claims,
                       load_declared, load_verified, record as write_record,
                       write_yaml)

    out = VerifyResult()
    # claims whose record differs from what is written only because the
    # canonical text moved in one release, reported once for the run
    release_moved: list = []
    from .spec import foreign_grammar_warnings
    out.lines.extend(foreign_grammar_warnings(root))
    from .compendium import own_package_compendium_files
    for where, library in own_package_compendium_files(root):
        out.lines.append(
            f"note {where}: `compendium: {library}` names this project's "
            f"own package, so the file is ignored; its claims are the "
            f"project's own, stated in its ordinary claims files")
    integrity_warned: set = set()
    from .auth import acceptance_policy_problems, load_policy
    from .locks import load_locks, lock_state
    policy = load_policy(root)
    locks = load_locks(root)
    verified = load_verified(root)
    declared = {key: info for key, info in load_declared(root).items()
                if not _defines_only((info or {}).get("entry"))}
    from .spec import unreadable_verified
    broken = unreadable_verified(root)
    # the library functions this project calls or rests a premise on
    # join the population with their library claims, so each is
    # adjudicated against the installed library; project-declared keys
    # keep their own entry
    library = _library_population(root, verified, declared, library_claims)
    # a project's own compendium file is adjudicated in full: each of
    # its keys is a library key
    for lkey in declared:
        info = library_claims.get(lkey)
        if info is not None and not info.get("bundled"):
            library.setdefault(lkey, info["source"])
    for lkey in sorted(library):
        for gone in (library_claims.get(lkey) or {}).get("shadowed") or []:
            out.lines.append(
                f"note {lkey}: {library_claims[lkey]['source']} shadows "
                f"the rows {', '.join(gone['rows'])} of {gone['source']}, "
                f"which are not used here; restate them in "
                f"{library_claims[lkey]['source']} to keep them")
    for lkey in library:
        if lkey not in declared:
            info = library_claims[lkey]
            declared[lkey] = {"entry": copy.deepcopy(info["entry"]),
                              "source": info["source"]}
    # a claims file named up front: every entry in it is adjudicated,
    # a library's whether or not the project calls it
    eager: set = set()
    for path in files or []:
        entries, is_library, notes = claims_file_entries(
            path, root, library_claims)
        out.lines.extend(notes)
        for fkey, info in entries.items():
            eager.add(fkey)
            if is_library:
                library.setdefault(fkey, info["source"])
            if fkey not in declared:
                declared[fkey] = {"entry": copy.deepcopy(info["entry"]),
                                  "source": info["source"]}
    if files is not None:
        only = list(only or []) + sorted(eager)
        if not only:
            return out
    # a library key recorded here whose rows no claims file states for
    # the installed library any more (its file left its range, or is
    # gone): the record is kept as it is, never re-adjudicated as if the
    # library function were the project's own
    from .compendium import is_library_record
    kept_records = False
    for key in sorted(set(verified) - set(declared) - set(broken)):
        entry = (verified[key] or {}).get("entry") or {}
        if key in library_claims or not is_library_record(entry):
            continue
        verified = {k: v for k, v in verified.items() if k != key}
        out.lines.append(_no_applicable_file_note(key, entry, root))
        kept_records = True
    # library keys first, so a premise resting on one sees the verdict
    # this run records for it
    keys = sorted(set(verified) | set(declared) | set(broken),
                  key=lambda k: (k not in library, k))
    # a function can be locked before it has any record or claims; its
    # lock is still checked
    lock_only = sorted(set(locks) - set(keys))
    if only:
        want = set(only)
        keys = [k for k in keys if k in want]
        lock_only = [k for k in lock_only if k in want]
    if not keys and not lock_only:
        out.nothing_declared = not kept_records
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
    # key -> claim name -> the pending re-authored text, for the rows
    supersessions: dict = {}
    # key -> {claim name: new grammar} for a claim verified under
    # mathema that now declares another grammar
    grammar_changes: dict = {}
    # an orphan record (its key no longer resolves) whose form hash
    # matches a function with no record: old key -> new keys, and the
    # reverse, so both sides of a likely move name the rename remedy
    from .moved import find_moved, rename_command
    moved = find_moved(root, {k: v for k, v in verified.items()
                              if k not in broken}, declared,
                       lambda k: _resolve_func_ref(k, root=root))
    moved_here: dict = {}
    for old_key, new_keys in moved.items():
        for new_key in new_keys:
            moved_here.setdefault(new_key, []).append(old_key)

    def _fail(key: str, msg: str) -> None:
        out.problems.append(msg)
        out.lines.append(f"FAIL {msg}")
        key_problems.setdefault(key, []).append(msg)

    pending: list = []   # (key, why, claims_for_gate, rec_or_none,
                         #  deps, accepted, unresolved, source_line)
    for key in keys:
        if key in broken:
            # a record that does not read is never re-adjudicated or
            # written over: that would replace the history it holds
            # with a fresh record. The key fails and names the repair.
            src, reason = broken[key]["source"], broken[key]["reason"]
            _fail(key, f"{key}: the verified record {src} {reason}; "
                       f"nothing was adjudicated or written for this key. "
                       f"Repair it (after a merge, keep every discoveries, "
                       f"historical and superseded row from both sides), "
                       f"or restore it with `git restore {src}`, and "
                       f"re-run verify")
            out.keys.append({"key": key, "why": "unreadable-record",
                             "passed": False,
                             "problems": list(key_problems[key]),
                             "counts": {}, "claims": []})
            continue
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
        if fn is None and key in eager and key in library:
            out.lines.append(f"note {key}: not importable from the "
                             f"installed library; nothing adjudicated")
            continue
        if fn is None:
            from .compendium import is_library_record
            if is_library_record(verified_entry):
                # a compendium key whose library is not importable
                # here: testimony, never a sweep failure. Its rows
                # still resolve premises at their recorded verdicts;
                # adjudicating them again needs the library.
                out.lines.append(
                    f"note {key}: library claims only, the library is "
                    f"not importable here; accept rows --as trusted, or "
                    f"install the library for the sweep to adjudicate "
                    f"them")
                continue
            msg = f"{key}: cannot resolve to a live function"
            out.problems.append(msg)
            line = (f"FAIL {key}: cannot resolve to a live function "
                    f"(declared in {source})")
            row = {"key": key, "why": "unresolvable", "passed": False,
                   "problems": ["cannot resolve to a live function"],
                   "counts": {}, "claims": []}
            if key in moved:
                remedies = [rename_command(n, key) for n in moved[key]]
                line += (f"; its form hash matches "
                         f"{', '.join(moved[key])}, which has no record. "
                         f"If it moved, a human keeps its history with: "
                         + " (or) ".join(remedies))
                row["moved_to"] = list(moved[key])
                row["remedy"] = remedies
            out.lines.append(line)
            # never reaches `pending`, so it gets its own structured
            # entry, nothing may be visible in prose alone
            out.keys.append(row)
            continue
        if key in moved_here and not verified_entry:
            # a fresh record here would start the history over while the
            # orphan still holds it; nothing is adjudicated or written
            # for this key until a human renames the record or removes
            # the orphan
            remedies = [rename_command(key, o) for o in moved_here[key]]
            _fail(key, f"{key}: no record yet, and its form hash matches "
                       f"the orphan record {', '.join(moved_here[key])}; "
                       f"nothing was adjudicated or written for this key. "
                       f"If it moved, a human keeps its history with: "
                       + " (or) ".join(remedies)
                       + "; if it is a different function, remove the "
                         "orphan record instead")
            out.keys.append({"key": key, "why": "moved-pending",
                             "passed": False,
                             "problems": list(key_problems[key]),
                             "moved_from": list(moved_here[key]),
                             "remedy": remedies,
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
                if conflict.get("kind") == "release-move":
                    release_moved.append((key, conflict["claim"]))
                    continue
                if conflict.get("kind") == "supersession":
                    supersessions.setdefault(key, {})[conflict["claim"]] = \
                        conflict["authored"]
                    msg = (f"{key}: claim {conflict['claim']!r} was "
                           f"re-authored but is already verified, the "
                           f"verified version keeps adjudicating; adopt the "
                           f"change with `mathema accept {key} "
                           f"{conflict['claim']} --as superseded`")
                else:
                    msg = (f"{key}: claim {conflict['claim']!r} differs "
                           f"between the docstring and the declared file, "
                           f"run `mathema docsync` to resolve (neither "
                           f"version is adjudicated until then)")
                _fail(key, msg)
            # a claim whose two surfaces disagree has no single meaning
            # to record, so neither version is adjudicated or written
            withheld = {c["claim"] for c in _conflicts
                        if c.get("kind") == "authoring"}
            merged_entry = resolve_declared(fn, file_entry=file_entry)
            current_claims = [c for c in merged_entry.get("claims") or []
                              if c.get("name") not in withheld]
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
            current_fp = claims_fingerprint(current_claims, entry_grammar, fn)
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
                out.authoring_errors.append(msg)
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
        if state in ("removed-outside", "moved-outside"):
            # the meta entry no longer matches the record's lock stamp
            # without `mathema unlock` having run. The record, stamp
            # included, is left exactly as it was, so the finding
            # stands on every sweep until the lock is put right.
            if state == "removed-outside":
                msg = (f"{key}: the verified record carries a lock stamp "
                       f"but .mathema/meta/locks.yaml has no entry; a "
                       f"lock is only removed by a human running "
                       f"`mathema unlock {key}` (restore the entry, or "
                       f"unlock properly)")
            else:
                stamped = (verified_entry.get("locked") or {}).get("form")
                lk = locks.get(key) or {}
                msg = (f"{key}: .mathema/meta/locks.yaml pins form "
                       f"{lk.get('form')} but the record was locked at "
                       f"{stamped}; the lock was moved without `mathema "
                       f"unlock {key}`, and the record is unchanged "
                       f"(restore the entry, or a human unlocks and "
                       f"re-locks)")
            out.problems.append(msg)
            lock_messages[key] = msg
            pending.append((key, "lock-" + state,
                            verified_entry.get("claims") or [], None, None,
                            _accepted_risk(verified_entry), (),
                            verified_info))
            continue
        from .compendium import premise_state as _premise_state
        premise_now = _premise_state(current_claims, stub_premises)
        recorded_premises = (verified_entry.get("meta") or {}).get(
            "mathema.premise_state")
        defaults_moved = _defaults_moved(fn, merged_entry, verified_entry)
        from .definitions import definition_state
        try:
            definitions_now = definition_state(fn, facts_now, root)
        except TimeoutError:
            raise
        except Exception:
            definitions_now = {}
        definitions_moved = definitions_now != ((verified_entry.get("meta")
                                                 or {}).get(
            "mathema.definition_rows") or {})
        pinf_moved = _pseudo_infinity_moved(fn, facts_now, merged_entry,
                                            verified_entry)
        is_fresh = (bool(recorded_form) and facts_now.form == recorded_form
                    and recorded_fp == current_fp and not defaults_moved
                    and not pinf_moved and not definitions_moved
                    and (premise_now == (recorded_premises or {})
                         if premise_now or recorded_premises else True))
        deps_now = function_dependencies(fn, facts_now) if is_fresh else None
        dependency_changed = is_fresh and any(
            _dependency_state(d, verified) in ("stale", "invalidated")
            for d in deps_now or [])
        if is_fresh and not dependency_changed:
            # a callee's form stored when this record was adjudicated
            # against the callee's live form: a change re-adjudicates
            # whether or not the callee has a record of its own
            stored_forms = {d.get("key"): d.get("form") for d in
                            verified_entry.get("dependencies") or []
                            if d.get("kind") == "function"
                            and d.get("key") and d.get("form")}
            dependency_changed = any(
                d.get("key") in stored_forms and d.get("form")
                and d.get("form") != stored_forms[d.get("key")]
                for d in deps_now or [] if d.get("kind") == "function")
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
        rec = check(fn, claims=claims if claims else [],
                    trials_downscale=trials_scale,
                    known_premises=stub_premises,
                    pseudo_infinity=merged_entry.get("pseudo_infinity"),
                    runtime_types=merged_entry.get("runtime_types"))
        rec.probes = [p for p in rec.probes
                      if getattr(p, "name", None) not in withheld]
        rec.probes, late_notes = _strip_retired_probes(
            key, rec.probes, verified_entry or {}, retired_noted)
        out.lines.extend(late_notes)
        out.lines.extend(_born_falsified_hint(key, rec.probes,
                                              verified_entry or {}))
        _apply_declared_extras(rec, merged_entry)
        moved = _grammar_changes(rec.probes, verified_entry or {})
        if moved:
            grammar_changes[key] = moved
        rec.probes.append(dependencies_current_probe(rec.dependencies,
                                                     root=root))
        why = ("dependency changed" if dependency_changed
               else "defaults changed" if defaults_moved
               and facts_now.form == recorded_form
               and recorded_fp == current_fp
               else "pseudo-infinity changed" if pinf_moved
               and facts_now.form == recorded_form
               and recorded_fp == current_fp
               else "definition rows changed" if definitions_moved
               and facts_now.form == recorded_form
               and recorded_fp == current_fp
               else "forced (--all)" if all and is_fresh
               else "targeted re-verify" if only and is_fresh
               else "no baseline record" if not recorded_form
               else "claims changed" if facts_now.form == recorded_form
               else "form changed")
        rec.meta = {**(getattr(rec, "meta", None) or {}),
                    "mathema.premise_state": premise_now}
        if definitions_now:
            rec.meta["mathema.definition_rows"] = definitions_now
        written = write_record(rec, key=key, root=root,
                               claims=current_claims,
                               declared_intent=merged_entry.get("intent"),
                               grammar=entry_grammar, fn=fn)
        _carry_recorded_verdicts(rec.probes, written, key)
        # the record just written carries each acceptance forward or
        # marks it stale (a changed form), so the gate reads the
        # accepted risk from it, never from the record it replaced
        accepted = _accepted_risk(_entry_at(written, key))
        out.adjudicated += 1
        if key in library:
            # this key's rows now resolve premises at their local verdict
            stub_premises = _external_premises(
                root, library_claims=library_claims)
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
            stored_dc["note"] = dc_now.note
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
            stored_dc.note = dc_now.note
            stored_dc.sketch = dc_now.sketch
            stored_dc.counterexample = dc_now.counterexample
            entry = settled.get(key)
            if entry is not None:
                for c in entry["entry"].get("claims") or []:
                    if c.get("name") == "dependencies_current":
                        c["verdict"] = dc_now.verdict
                        c["note"] = dc_now.note
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
        is_library = key in library
        if is_library:
            # a library's missing-value posture is its compendium's own
            # policy rows; the rows mathema writes for a user function
            # are not asked of it
            claims_for_gate = [c for c in claims_for_gate
                               if not (_claim_fields(c)[2].get("mathema.policy")
                                       and _claim_fields(c)[2].get("mathema.surface")
                                       == "mathema")]
        # a library key gates like the project's own claims: a row
        # neither verified here nor accepted (`--as trusted`) fails.
        # The unresolved-global-name check is the one rule it skips:
        # that check reads the analysed body of the project's own
        # function, and a library's body is not what its rows are about
        report = gate(claims_for_gate, strict=strict,
                      accepted_risk=accepted,
                      unresolved=() if is_library else unres, key=key)
        hints = (_unsettled_library_hints(key, claims_for_gate)
                 if is_library and report.problems else [])
        standing = [
            f"{name} stays trusted at its accepted level ({verdict}): the "
            f"sweep could not settle it ({meta['mathema.trusted_unsettled']})"
            for name, verdict, meta, _n in map(_claim_fields, claims_for_gate)
            if meta.get("mathema.trusted_unsettled")]
        standing += [
            f"{name} trusted as: {verdict}, strongest evidence seen: "
            f"{meta['mathema.strongest_evidence']}"
            for name, verdict, meta, _n in map(_claim_fields, claims_for_gate)
            if meta.get("mathema.strongest_evidence")]
        state = "FAIL" if report.problems or key_problems.get(key) else "ok"
        if key in lock_messages:
            # the record is left as it was, so its counts describe code
            # that no longer exists: the row is the lock failure alone
            line = f"FAIL {lock_messages[key]}"
            if report.problems:
                line += "; " + "; ".join(report.problems)
        elif why == "fresh":
            line = f"{state:4} {key}: fresh"
            if is_library:
                line += f"; library claims from {library[key]}"
            line += _unaccounted_text(report)
            if report.problems:
                line += "; " + "; ".join(report.problems + hints)
        else:
            line = (f"{state:4} {key}: "
                    + (f"library claims from {library[key]}; "
                       if is_library else "")
                    + f"{why}; {summary_counts(report)}"
                    + _unaccounted_text(report))
            if report.foreign:
                grammars = sorted({_claim_fields(p)[2]
                                   ["mathema.foreign_grammar"]
                                   for p in report.foreign})
                line += (f", {len(report.foreign)} not this grammar "
                         f"({', '.join(grammars)})")
            if standing:
                line += "; " + "; ".join(standing)
            if report.problems:
                line += "  <- " + "; ".join(report.problems + hints)
        out.problems.extend(f"{key}: {p}" for p in report.problems)
        out.lines.append(line)
        out.lines.extend(
            f"     warning: claim {name} of {key} was verified under "
            f"mathema; its grammar is now {grammar!r}, so mathema no "
            f"longer adjudicates it"
            for name, grammar in grammar_changes.get(key, {}).items())
        out.keys.append({
            "key": key,
            "why": why,
            "passed": (not report.problems and key not in lock_messages
                       and not key_problems.get(key)),
            "problems": ([lock_messages[key]] if key in lock_messages
                         else []) + key_problems.get(key, [])
                        + list(report.problems),
            "integrity_mismatch": key in integrity_warned,
            **({"library_claims": library[key]} if is_library else {}),
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
            "claims": [_with_grammar_change(_with_supersession(
                           claim_row(c, accepted_risk=accepted), key,
                           supersessions.get(key, {})),
                           grammar_changes.get(key, {}))
                       for c in claims_for_gate],
        })
    if release_moved:
        from .sync import IDENTITY_RELEASE
        out.lines.append(
            f"note: fingerprints move once in {IDENTITY_RELEASE}: the rendered "
            f"domain now states what it admits, so {len(release_moved)} "
            f"claim{'s' if len(release_moved) != 1 else ''} recorded by an "
            f"earlier release {'are' if len(release_moved) != 1 else 'is'} "
            f"re-recorded under the new text; nothing the author wrote "
            f"changed")
    return out


def _grammar_changes(probes, verified_entry: dict) -> dict:
    """Intent:
        The claims skipped this run as another grammar's that carry a
        real verdict (proven, holds, falsified) recorded under
        mathema's own grammar, `{claim name: the grammar it declares
        now}`.
    """
    recorded = {c.get("name"): c for c in (verified_entry.get("claims")
                                          or []) if isinstance(c, dict)}
    out: dict = {}
    for p in probes:
        grammar = (getattr(p, "meta", None) or {}).get(
            "mathema.foreign_grammar")
        prior = recorded.get(getattr(p, "name", None))
        if grammar is None or prior is None:
            continue
        if prior.get("verdict") in ("proven", "holds", "falsified") and \
                prior.get("grammar") in (None, "mathema") and \
                "mathema.foreign_grammar" not in (prior.get("meta") or {}):
            out[p.name] = grammar
    return out


def _with_grammar_change(row: dict, changes: dict) -> dict:
    """Intent:
        A claim row with `grammar_changed: {from: "mathema", to: ...}`
        when the claim was verified under mathema and now declares
        another grammar.
    """
    moved = changes.get(row.get("claim"))
    if moved is not None:
        row["grammar_changed"] = {"from": "mathema", "to": moved}
    return row


def _with_supersession(row: dict, key: str, pending: dict) -> dict:
    """Intent:
        A claim row with its pending supersession, when the claim was
        re-authored after it was verified: `supersession` holds the
        re-authored text and the command that adopts it, while the
        verified version keeps adjudicating.
    """
    authored = pending.get(row.get("claim"))
    if authored is not None:
        row["supersession"] = {
            "authored": authored,
            "adopt": f"mathema accept {key} {row['claim']} --as superseded"}
    return row
