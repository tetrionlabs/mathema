# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Acceptance: the human decision layer over adjudicated evidence.

A verdict states what the machine established; acceptance states what a
person decided to do about it, and lives in the verified record beside
the verdict it addresses. The vocabulary is deliberately small:

- `holds` accepts as **evidence**: this much empirical support is
  enough. The acceptance records the sample size, confidence, and the
  function's form hash at the moment of the decision, a later weaker
  run warns, and a changed form makes the acceptance stale outright
  (it was a decision about a different function).
- `unknown` accepts as **risk**: the claim couldn't be established and
  someone owns that. The verdict becomes `skipped:unknown_but_accepted`;
  strict mode still refuses it, lenient mode lets work proceed.
- `skipped` accepts as **risk**: the structural blocker is understood.
- `falsified` (or `invalidated`) accepts only as a **discovery**: the
  claim was wrong about the world. Accepting it retires the claim into
  the record's `discoveries` section with its counterexample kept as
  the witness, whatever the claim's shape. A corrected claim is
  declared alongside only when it is VERIFIED first: the author's own
  `--corrected` statement, or, for a bare single relation, a
  mechanically sound inverse; either is adjudicated against the live
  function at acceptance time, and only a holding candidate (or a
  stated one that does not falsify) is written. Nothing is invented:
  a chained comparison, an `assuming` premise, a `let` section, or a
  candidate that fails adjudication leaves the discovery recorded
  with no replacement, `superseded_by` absent.
  There is no "accept as bug": a bug is overcome by changing the code
  until the claim stops falsifying, with the recorded counterexample
  replayed on every later run; either way, a falsification is only
  ever overcome by a new claim.
- `proven` needs no acceptance: the proof is the acceptance.

Acceptance is a human act. The CLI verb prompts and prints exactly what
it will write; nothing here is exposed to agent tooling."""
from __future__ import annotations

import datetime
import os
import subprocess

from .grammar import split_relation
from .identity import namespaced_form, same_form
from .routes import safety_predicates
from .spec import classify_verdict, write_yaml

ACCEPT_AS = ("evidence", "risk", "discovery", "historical", "superseded",
             "trusted", "reconciled")

_INVERTED_RELATION = {"==": "!=", "~=": "!=", "!=": "==",
                      ">=": "<", "<=": ">", ">": "<=", "<": ">="}


class AcceptanceError(ValueError):
    """Raised when an acceptance request doesn't fit the vocabulary:
    the wrong `as` for the claim's verdict, a claim or record that
    doesn't exist, or a statement the discovery path can't invert."""


class UnknownAcceptanceTarget(AcceptanceError):
    """Raised when the named record or claim does not exist, a target
    that does not resolve rather than a request the rules refuse."""


def default_identity() -> str | None:
    """The accepting identity when none is given: `git config
    user.name` if available, else None (the annotation simply omits
    `by`)."""
    try:
        out = subprocess.run(["git", "config", "user.name"],
                             capture_output=True, text=True, timeout=5)
        name = out.stdout.strip()
        return name or None
    except Exception:
        return None


def mismatched_records(root: str = ".") -> list:
    """The verified records whose contents no longer match their stored
    integrity checksum: the ones a reconcile (or a re-verify) addresses
    after a merge, rebase, or a declared-claim edit."""
    from .spec import integrity_matches, load_verified
    out = []
    for key, info in load_verified(root).items():
        if integrity_matches(info.get("entry") or {}) is False:
            out.append(key)
    return sorted(out)


def reconcile_all(root: str, keys: list, by: "str | None" = None,
                  note: "str | None" = None) -> list:
    """Intent:
        Reconcile several records in ONE human act: re-stamp each key's
        integrity over its current contents and re-anchor it to HEAD, so a
        merge or rebase is cleared without going record by record. The
        human gate (a configured PIN, the policy) is taken once for the
        whole batch, then applied to every record. Returns the keys done.
    """
    from . import auth
    from .spec import _git_commit, load_verified
    verified = load_verified(root)
    attestation = auth.require_human(
        f"accept --as reconciled ({len(keys)} records)")
    auth.enforce_policy(attestation, root)
    head = _git_commit(root)
    done = []
    for key in keys:
        info = verified.get(key)
        if not info:
            continue
        entry = info["entry"]
        rec: dict = {"at": datetime.date.today().isoformat(), "by": by}
        if note:
            rec["note"] = note
        if attestation:
            rec["verified_by"] = dict(attestation)
        entry.setdefault("lineage", {})["commit"] = head
        entry.setdefault("identity", {})["reconciled"] = rec
        _restamp_integrity(entry)
        write_yaml(os.path.join(root, info["source"]), {key: entry},
                   header=f"machine record; reconciled {key}")
        done.append(key)
    return done


def invert_conjecture(statement: str, claim_name: str) -> "tuple[str | None, str | None]":
    """Intent:
        The mechanically sound inverse of a falsified claim's
        statement, as `(corrected_text, None)`, or `(None, reason)`
        when no sound inverse exists. The statement is PARSED first,
        never string-flipped: a chained comparison, an `assuming`
        premise, a `let` section, an `=> outcome`, or an
        already-negated form has no single relation whose flip means
        anything, so each refuses with its reason stated. A bare
        predicate claim inverts through the grammar's `not` form; a
        bare relational claim flips its one relation with the
        quantifier prefix carried intact. A refusal never blocks
        recording the discovery itself; it only means the corrected
        claim is the author's to state (`--corrected`).
    """
    from .conjecture import InvalidConjecture
    from .conjecture import claim as _claim

    text = (statement or "").strip()
    if not text:
        return None, "the claim has no statement to invert"
    if text.startswith("let ") or ", let " in text:
        return None, ("a `let` section binds names; flipping anything in "
                      "it would corrupt a binding, not correct the claim")
    try:
        cj = _claim(text, name=claim_name.split("[", 1)[0] or None)
    except InvalidConjecture as e:
        return None, f"the statement does not parse as a single claim ({e})"
    except Exception as e:
        return None, f"the statement does not parse ({e})"
    if getattr(cj, "links", None):
        return None, ("a chained comparison is a conjunction of relations; "
                      "no single flip is its inverse")
    if getattr(cj, "assuming", ""):
        return None, ("an `assuming` premise conditions the claim; what "
                      "holds under the premise is the author's to state")
    if getattr(cj, "outcome", ""):
        return None, "an `=> outcome` claim has no mechanical inverse"
    if getattr(cj, "negated", False):
        return None, ("already a negated form; its falsification means the "
                      "original positive claim, restate by hand")
    if cj.relation in _INVERTED_RELATION:
        # refusals above guarantee the first top-level relation IS the
        # assertion's own, so the split is sound and keeps the
        # quantifier prefix on the left side verbatim
        lhs, _rel, rhs = split_relation(text)
        return f"{lhs} {_INVERTED_RELATION[cj.relation]} {rhs}", None
    if cj.relation in safety_predicates():
        prefix, sep, call = text.rpartition(", ")
        if call.startswith(f"{cj.relation}("):
            inverted = f"not {call}"
            return (f"{prefix}{sep}{inverted}" if sep else inverted), None
        return None, (f"cannot place the grammar's `not` form on the "
                      f"recorded spelling {text!r}; restate by hand")
    return None, f"relation {cj.relation!r} has no mechanical inverse"


def _adjudicate_candidate(root: str, key: str, statement: str,
                          route: "str | None", tolerance=None):
    """Intent:
        Dry-run one candidate corrected claim against the live
        function, under `tolerance` when one is given, every line of it
        (the claim's row and its computation row, `NAME[float]`):
        `(probe, None)` when it adjudicated, the probe being the first
        line that falsifies, else the first that neither holds nor is
        proven, else the claim's own row; `(None, reason)` when it
        could not run (function unresolvable, statement rejected).
        Read-only; the plan stays a true preview.
    """
    from .conjecture import _resolve_func_ref, check_conjectures
    from .conjecture import claim as _claim
    try:
        fn = _resolve_func_ref(key, root=root)
    except Exception as e:
        return None, f"cannot resolve {key} to a live function ({e})"
    if fn is None:
        return None, f"cannot resolve {key} to a live function"
    base_route = (route or "best").split(":", 1)[0]
    if base_route not in ("probe", "derive"):
        base_route = "best"
    try:
        cj = _claim(statement, name="corrected_candidate", route=base_route,
                    tolerance=tolerance)
        probes = check_conjectures(fn, [cj], float_companions=True)
    except TimeoutError:
        raise
    except Exception as e:
        return None, f"the candidate could not be checked ({e})"
    if not probes:
        return None, "the candidate could not be checked"
    bases = [classify_verdict(p.verdict) for p in probes]
    for probe, base in zip(probes, bases):
        if base == "falsified":
            return probe, None
    for probe, base in zip(probes, bases):
        if base not in ("proven", "holds"):
            return probe, None
    return probes[0], None


RETIREMENT_SECTIONS = ("discoveries", "historical", "superseded")


def honoured_retirements(entry: dict, section: str) -> list:
    """Intent:
        The rows of one retirement section (`discoveries`, `historical`
        or `superseded`) that retire a claim: those carrying an
        `accepted` block, which every acceptance writes as it moves a
        row there. A row without one did not come through `mathema
        accept` and retires nothing.
    """
    return [r for r in (entry or {}).get(section) or []
            if isinstance(r, dict) and isinstance(r.get("accepted"), dict)]


def unaccepted_retirements(entry: dict) -> list:
    """Intent:
        The retirement rows that carry no `accepted` block, as
        `(section, name)` pairs: rows `honoured_retirements` leaves
        out, which the sweep reports.
    """
    out = []
    for section in RETIREMENT_SECTIONS:
        for r in (entry or {}).get(section) or []:
            if not (isinstance(r, dict)
                    and isinstance(r.get("accepted"), dict)):
                name = r.get("name") if isinstance(r, dict) else None
                out.append((section, name))
    return out


def _same_law_as(statement: str, key: "str | None" = None, root: str = "."):
    """Intent:
        A canonical-law comparator over claim spellings: two texts
        match when they parse to the same fingerprint form, so the
        record's canonical rendering and an author's hand spelling of
        the same law compare equal. With the function's `key`, each
        side's bindings are completed from its annotations first, as
        its record states them. An unparseable side never matches.
    """
    from .sync import _identity
    fn = None
    if key is not None:
        from .conjecture import _resolve_func_ref
        try:
            fn = _resolve_func_ref(key, root=root)
        except Exception:
            fn = None

    def canon(text: str):
        try:
            return _identity(text, None, fn)
        except Exception:
            return None

    base = canon(statement)

    def same(other: str) -> bool:
        return base is not None and canon(other) == base

    return same


def _declared_claim_files(root: str, key: str, claim_name: str,
                          statement: str) -> list:
    """Intent:
        The claims files that declare `claim_name` under `key` with
        the SAME law as `statement` (compared canonically). The
        discovery cleanup rewrites exactly these; a claim declared
        only on a code surface (docstring, decorator) appears in none
        of them, and a different law under the same name is new
        authorship and is left alone.
    """
    import yaml

    from .spec import _SKIP_DIRS, _is_claim_file
    same = _same_law_as(statement, key, root)
    hits = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for name in sorted(filenames):
            if not _is_claim_file(dirpath, name):
                continue
            path = os.path.join(dirpath, name)
            try:
                data = yaml.safe_load(open(path)) or {}
            except Exception:
                continue
            entry = data.get(key)
            if not isinstance(entry, dict):
                continue
            for c in entry.get("claims") or []:
                if c.get("name") == claim_name and                         same(c.get("statement") or c.get("law") or ""):
                    hits.append(os.path.relpath(path, root))
                    break
    return hits


def _apply_declared_edit(root: str, rel: str, key: str, claim_name: str,
                         corrected: "dict | None") -> None:
    """Rewrite one claims file: the retired claim's stanza is replaced
    by the corrected one when a correction was declared, removed
    otherwise. The file is re-emitted from its parsed form, so the
    entry keeps its meaning while hand formatting does not survive;
    the plan's printed action named the rewrite before it happened."""
    import yaml
    path = os.path.join(root, rel)
    try:
        data = yaml.safe_load(open(path)) or {}
    except Exception:
        return
    entry = data.get(key)
    if not isinstance(entry, dict):
        return
    kept = [c for c in entry.get("claims") or []
            if c.get("name") != claim_name]
    if corrected:
        kept.append(dict(corrected))
    entry["claims"] = kept
    from .spec import atomic_write_text
    atomic_write_text(path, yaml.safe_dump(
        data, sort_keys=False, default_flow_style=False, allow_unicode=True))


def _load_record(root: str, key: str):
    from .spec import find_record, record_file_name, verified_dir
    path = find_record(verified_dir(root), key)
    if path is None:
        path = os.path.join(verified_dir(root), record_file_name(key))
        raise UnknownAcceptanceTarget(f"no verified record for {key!r} at {path}, "
                              "run `mathema verify` (or `check`) first; "
                              "acceptance annotates the evidence verify recorded")
    from .spec import read_verified_file
    doc, reason = read_verified_file(path)
    if reason is not None or doc is None:
        raise AcceptanceError(f"{path} {reason}; repair it (or restore it "
                              f"from git) before accepting anything in it")
    if key not in doc:
        raise AcceptanceError(f"{path} holds no entry for {key!r}")
    return path, doc



def _restamp_integrity(entry: dict) -> None:
    """Intent:
        An acceptance write is mathema's own hand: the integrity
        checksum restamps so the next sweep never mistakes it for
        outside tampering.
    """
    from .spec import integrity_checksum, pin_summary
    entry.setdefault("identity", {})["pin"] = pin_summary(entry)
    entry["identity"]["integrity"] = integrity_checksum(entry)


def _claims_fingerprint_now(root: str, key: str,
                            verified_entry: dict) -> "str | None":
    """Intent:
        The claims fingerprint `mathema verify` would compute for `key`
        right now, from the claims files on disk, the live function and
        `verified_entry`, or None when it cannot be computed (the
        function does not resolve, a claim does not parse).
    """
    import copy

    from .conjecture import _resolve_func_ref
    from .spec import load_declared
    from .sync import claim_conflicts
    from .verify import _defines_only, claims_now
    try:
        fn = _resolve_func_ref(key, root=root)
        if fn is None:
            return None
        info = load_declared(root).get(key)
        if info is None or _defines_only(info.get("entry")):
            from .compendium import load_library_claims
            info = load_library_claims(root).get(key) or {}
        file_entry = copy.deepcopy(info.get("entry") or {})
        record = copy.deepcopy(verified_entry)
        conflicts = claim_conflicts(fn, file_entry, record or None)
        return claims_now(key, fn, file_entry, record, conflicts,
                          info.get("source"))["fingerprint"]
    except TimeoutError:
        raise
    except Exception:
        return None


def _refresh_claims_fingerprint(root: str, key: str, entry: dict) -> None:
    """Intent:
        Set the record's claims fingerprint to the one `mathema verify`
        computes from the claims as the acceptance leaves them, so the
        next sweep finds the function unchanged. A fingerprint that
        cannot be computed leaves the recorded one, and the next sweep
        checks the function.
    """
    fp = _claims_fingerprint_now(root, key, entry)
    if fp is not None:
        entry.setdefault("identity", {})["claims_fingerprint"] = fp


def _another_claim_holds(claims: list, target: dict) -> bool:
    """Intent:
        Whether a live claim other than `target`, one a person or a
        claims file stated, is proven or holds. Built-in, suggested and
        float-companion rows are mathema's own and do not count.
    """
    for c in claims:
        if c is target:
            continue
        meta = c.get("meta") or {}
        if meta.get("mathema.surface") in ("builtin", "mathema", "types") \
                or meta.get("mathema.companion_of"):
            continue
        if classify_verdict(c.get("verdict") or "") in ("proven", "holds"):
            return True
    return False


def computation_line_refusal(key: str, row: str, parent: str,
                             found: "dict | None",
                             whole: bool = False) -> str:
    """Intent:
        Why a falsified computation line `row` (the computation of the
        claim `parent`) is not accepted alone, and the ways out. It is
        accepted alone only where its recorded conditioning says the
        loss is inherent; `found` is that record, None where none was
        read at the witness (a raise, a NaN or an inf, not a miss of
        the relation). A loss the conditioning does not explain is the
        code's; one not known to be inherent counts as the code's.
        `whole` is whether `parent` is proven, so that it can be
        accepted whole as a discovery with this line.
    """
    from ._conditioning import command_word
    cause = (found or {}).get("words") or (
        "no conditioning was read at its witness, so whether the loss is "
        "inherent is not decided")
    whose = ("the code's" if (found or {}).get("inherent") is False
             else "not known to be inherent, which counts as the code's")
    accept_whole = (f"accept the whole claim as a discovery, keeping both "
                    f"lines, run: mathema accept {key} "
                    f"{command_word(parent)} --as discovery; "
                    if whole else "")
    return (f"{row} is the computation of {parent}, falsified: {cause}. A "
            f"computation line is accepted alone only where its loss is "
            f"inherent (no float64 computation could do better there); "
            f"this loss is {whose}. The ways out: fix the code, and the "
            f"recorded counterexample replays until the line holds; "
            f"{accept_whole}or "
            f"narrow the claim's domain knowingly: edit {parent}, then run: "
            f"mathema accept {key} {command_word(parent)} --as superseded")


def plan_acceptances(root: str, key: str, requests: list,
                     by: str | None = None, note: str | None = None,
                     corrected: str | None = None) -> list:
    """Intent:
        One plan per `(claim_name, as_)` request on `key`, all sharing
        one loaded record, so `apply_acceptances` writes them in one
        act. A claim named twice is planned once, as first requested.

    Raises:
        AcceptanceError: as `plan_acceptance`, for the first request it
        refuses; nothing is planned for the others then.
    """
    record = _load_record(root, key)
    kinds = dict(reversed(list(requests)))
    names = list(dict.fromkeys(name for name, _ in requests))
    return [plan_acceptance(root, key, name, kinds[name], by=by, note=note,
                            corrected=corrected, record=record)
            for name in names]


def apply_acceptances(plans: list) -> list:
    """Intent:
        Execute several plans from `plan_acceptances` under one human
        gate: a configured PIN is asked for once, and each plan is then
        written in order. Returns each plan's summary.
    """
    if not plans:
        return []
    from . import auth
    attestation = auth.require_human(
        f"accept --as {plans[0]['as']}"
        + (f" ({len(plans)} claims)" if len(plans) > 1 else ""))
    auth.enforce_policy(attestation, plans[0].get("root", "."))
    return [_apply_attested(plan, attestation) for plan in plans]


def _event(as_: str, by: str | None, verdict: str, note: str | None) -> dict:
    event = {"at": datetime.date.today().isoformat(), "as": as_,
             "verdict": verdict}
    if by:
        event["by"] = by
    if note:
        event["note"] = note
    return event


# the natural acceptance for each unaccepted verdict, so a first-time user
# can omit --as and be guided rather than made to learn the vocabulary.
_VERDICT_TO_AS = {"holds": "evidence", "unknown": "risk", "skipped": "risk",
                  "falsified": "discovery", "invalidated": "discovery"}
_AS_REASON = {"evidence": "the claim holds, and this much support is enough",
              "risk": "the gap is understood and someone owns it",
              "discovery": "the claim was wrong about the code; accepting it "
                           "declares the corrected claim"}


def suggest_acceptance(root: str, key: str, claim_name: str) -> tuple:
    """Intent:
        The natural `--as` for one claim, read from its verdict, plus a
        one-line reason, so `mathema accept KEY CLAIM` with no `--as` can
        guide a newcomer. Returns `(kind, verdict, reason)`.

    Raises:
        AcceptanceError: a proven claim (its proof is the acceptance), a
        missing claim, or a verdict with no natural default.
    """
    _path, doc = _load_record(root, key)
    claims = doc[key].get("claims") or []
    target = next((c for c in claims if c.get("name") == claim_name), None)
    if target is None:
        names = ", ".join(sorted(filter(None, (c.get("name") for c in claims)))) \
            or "none"
        raise UnknownAcceptanceTarget(f"{key} has no claim named {claim_name!r} "
                              f"(recorded claims: {names})")
    base = classify_verdict(target.get("verdict") or "")
    if base == "proven":
        raise AcceptanceError(f"{claim_name} is proven; a proof is its own "
                              "acceptance, there is nothing to accept")
    kind = _VERDICT_TO_AS.get(base)
    if not kind:
        raise AcceptanceError(f"{claim_name}: verdict {base!r} has no default "
                              "acceptance, state `--as` explicitly")
    return kind, base, _AS_REASON.get(kind, "")


def plan_rename(root: str, new_key: str, old_key: str,
                by: "str | None" = None, note: "str | None" = None,
                confirm_form_change: bool = False) -> dict:
    """Intent:
        Plan the record rename a moved function needs: `old_key`'s
        verified record, whose key no longer resolves, becomes
        `new_key`'s, carrying every claim row, its acceptance history,
        the retirement sections, the lineage and any lock. The plan
        states whether the record's form hash matches the live
        function at `new_key`; `apply_acceptance` writes it only when
        it does, or when `confirm_form_change` records that a human
        accepted the difference.

    Raises:
        UnknownAcceptanceTarget: `old_key` has no record, or `new_key`
            does not resolve to a live function.
        AcceptanceError: `old_key` still resolves (a copy, not a move),
            or `new_key` already has a record.
    """
    from . import analyze
    from .conjecture import _resolve_func_ref
    from .locks import load_locks
    from .spec import find_record, record_file_name, verified_dir
    if new_key == old_key:
        raise AcceptanceError("--from names the same key; a rename needs "
                              "two different keys")
    old_path, doc = _load_record(root, old_key)
    fn = _resolve_func_ref(new_key, root=root)
    if fn is None:
        raise UnknownAcceptanceTarget(
            f"{new_key} does not resolve to a live function; the rename "
            f"target is the function's new dotted key")
    if _resolve_func_ref(old_key, root=root) is not None:
        raise AcceptanceError(
            f"{old_key} still resolves to a live function, so it has not "
            f"moved; a rename would leave that function without its "
            f"record")
    existing = find_record(verified_dir(root), new_key)
    new_path = existing or os.path.join(verified_dir(root),
                                        record_file_name(new_key))
    if existing is not None:
        raise AcceptanceError(
            f"{new_key} already has a record ({os.path.relpath(new_path, root)}); "
            f"a rename never writes over one. Remove it first if the "
            f"orphan's history is the one to keep")
    entry = doc[old_key]
    recorded = (entry.get("identity") or {}).get("form")
    live = analyze(fn).form
    matches = same_form(recorded, live)
    actions = [f"rename the record {old_key} to {new_key}, carrying its "
               f"claims, acceptance history, lineage and sign-offs",
               f"remove {os.path.relpath(old_path, root)}",
               "re-stamp the integrity and re-anchor it to HEAD"]
    if not matches:
        actions.insert(0, f"the record's form hash {namespaced_form(recorded)} differs from "
                          f"{new_key}'s {live}: it may not be the same "
                          f"function, and the next verify checks it again")
    if old_key in load_locks(root):
        actions.append(f"move the lock on {old_key} to {new_key}")
    return {"path": old_path, "new_path": new_path, "doc": doc,
            "key": new_key, "from": old_key, "root": root,
            "as": "reconciled", "by": by, "note": note, "claim": None,
            "verdict": None, "recorded_form": recorded, "live_form": live,
            "form_matches": matches,
            "confirm_form_change": confirm_form_change,
            "new_name": getattr(fn, "__name__", None), "actions": actions}


def _require_form_confirmed(plan: dict) -> None:
    """Intent:
        Refuse a rename whose recorded form hash differs from the live
        function's unless a human confirmed the difference.

    Raises:
        AcceptanceError: the forms differ and nothing confirmed it.
    """
    if not plan["form_matches"] and not plan.get("confirm_form_change"):
        raise AcceptanceError(
            f"{plan['from']}'s record has form {plan['recorded_form']} but "
            f"{plan['key']} is {plan['live_form']}; confirm the rename at "
            f"the prompt, or pass --accept-form-change")


def _apply_rename(plan: dict, attestation: "dict | None") -> str:
    """Intent:
        Write a `plan_rename` result: the record under its new key with
        `identity.reconciled` naming where it came from, the old file
        removed, the lock moved.

    Raises:
        AcceptanceError: the form hashes differ and no human confirmed
            the difference.
    """
    from .spec import _git_commit
    _require_form_confirmed(plan)
    old_key, new_key = plan["from"], plan["key"]
    entry = plan["doc"][old_key]
    if plan.get("new_name"):
        entry["name"] = plan["new_name"]
    rec: dict = {"at": datetime.date.today().isoformat(),
                 "by": plan.get("by"), "from": old_key}
    if plan.get("note"):
        rec["note"] = plan["note"]
    if not plan["form_matches"]:
        rec["form_changed"] = {"recorded": plan["recorded_form"],
                               "live": plan["live_form"]}
    if attestation:
        rec["verified_by"] = dict(attestation)
    root = plan.get("root", ".")
    entry.setdefault("lineage", {})["commit"] = _git_commit(root)
    entry.setdefault("identity", {})["reconciled"] = rec
    _restamp_integrity(entry)
    write_yaml(plan["new_path"], {new_key: entry},
               header=f"machine record; reconciled {new_key} from {old_key}")
    os.remove(plan["path"])
    from .locks import _write_locks, load_locks
    locks = load_locks(root)
    if old_key in locks:
        locks[new_key] = locks.pop(old_key)
        _write_locks(root, locks)
    who = ((rec.get("verified_by") or {}).get("key") or plan.get("by")
           or "unpinned")
    return f"reconciled: {old_key} renamed to {new_key} (by {who})"


def _is_equivalence(row: "dict | None") -> bool:
    """Whether a record row states a function equivalence `f =:= g`."""
    if not row:
        return False
    try:
        _lhs, relation, _rhs = split_relation(row.get("statement") or "")
    except ValueError:
        # a predicate row (`absent(f, x)`) has no relation of its own
        return False
    return relation == "=:="


#: the `=:=` computation row's default (`equivalence._values_agree`,
#: twice `_allowance.allowance`) as the kind a `~=` correction states:
#: `2e-7 * m + 2e-9` for values of magnitude m of at least 1e-2, the
#: default exactly there; below 1e-2 the default's absolute part
#: shrinks with m (`4e-7 * m`, and 2e-9 at or below 1e-9) while this
#: kind keeps its floor
DEFAULT_CORRECTION_TOLERANCE = {"rel": 2e-7, "floor": 2e-9}


def _approximate_correction(root: str, key: str, row: dict) -> tuple:
    """Intent:
        The correction a falsified mathematics line of `f =:= g` offers,
        as `(statement, tolerance, None)`: the same claim with `f(x) ~=
        g(x)` in place of `f =:= g`, over f's parameters, at the
        tolerance its computation compared under, as a claim writes it:
        a declared number or kind as written, or, with none declared,
        `DEFAULT_CORRECTION_TOLERANCE`. `(None, None, reason)` when
        none can be stated: a function or statement mathema cannot
        read.
    """
    from ._tolerance import read_tolerance, written_tolerance
    from .conjecture import _effective_facts, _resolve_func_ref
    try:
        declared = read_tolerance(row.get("tolerance"))
    except ValueError as e:
        return None, None, f"its tolerance does not read ({e})"
    if declared is None:
        tolerance = dict(DEFAULT_CORRECTION_TOLERANCE)
    elif isinstance(declared, (int, float)) \
            and not isinstance(declared, bool):
        tolerance = float(declared)
    else:
        tolerance = written_tolerance(declared)
        if not isinstance(tolerance, dict):
            return None, None, f"its tolerance {declared!r} is not a number"
    if not _is_equivalence(row):
        return None, None, "the statement does not read as `f =:= g`"
    lhs, relation, rhs = split_relation(row.get("statement") or "")
    if not lhs.rstrip().endswith("f") \
            or not rhs.strip().isidentifier():
        return None, None, "the statement does not read as `f =:= g`"
    try:
        params = list(_effective_facts(_resolve_func_ref(key, root=root)).params)
    except Exception as e:
        return None, None, f"cannot read {key}'s parameters ({e})"
    args = ", ".join(params)
    prefix = lhs.rstrip()[:-1]
    return (f"{prefix}f({args}) ~= {rhs.strip()}({args})", tolerance, None)


def tolerance_words(tolerance) -> str:
    """A tolerance for a line a person reads: a number as `:g` writes
    it (`0.01`), a kind as a claims file writes it (`{rel: 2e-7,
    floor: 2e-9}`)."""
    from ._tolerance import read_tolerance
    if isinstance(tolerance, dict):
        return read_tolerance(tolerance).text()
    return f"{tolerance:g}"


def _whole_claim_discovery(root: str, key: str, claims: list, target: dict,
                           as_: str) -> "dict | None":
    """Intent:
        What a discovery that retires a claim with its computation line
        changes in its plan, or None when `target` is no such claim or
        `as_` is not `discovery`. Two claims retire whole. An `f =:= g`
        claim is a discovery when either of its lines is falsified, and
        its computation row `NAME[float]` alone is never accepted. A
        value claim whose own row is proven is a discovery when its
        computation line is falsified. Either retires with both rows:
        `{"base": "falsified", "witness": the falsified line's witness,
        "moves_with": [its computation row], "correction": (statement,
        tolerance, reason) or None, "equivalence": whether it states
        `f =:= g`}`. The correction is offered where the mathematics
        line of `f =:= g` is falsified and the computation holds
        (`_approximate_correction`); a falsified computation offers
        none, the replacement being the author's to state.

    Raises:
        AcceptanceError: a discovery on the computation row of an
        `f =:= g` claim alone.
    """
    if as_ != "discovery":
        return None
    parent_name = (target.get("meta") or {}).get("mathema.companion_of")
    if parent_name is not None:
        parent = next((c for c in claims if c.get("name") == parent_name),
                      None)
        if _is_equivalence(parent):
            raise AcceptanceError(
                f"{target.get('name')} is the computation of {parent_name}, "
                f"an equivalence, and the computation is what runs, so "
                f"{parent_name} cannot stand where it fails: accept the "
                f"whole claim as a discovery (mathema accept {key} "
                f"{parent_name} --as discovery, keeping both lines), or "
                f"replace it with a claim true of the running code "
                f"(--corrected \"<law>\")")
        return None
    name = target.get("name")
    computation = _computation_row(claims, name)
    main = classify_verdict(target.get("verdict") or "")
    computed = classify_verdict((computation or {}).get("verdict") or "")
    if not _is_equivalence(target):
        # a value claim retires whole where its mathematics is proven
        # and its computation line falsified
        if _proven_row(target) and computed == "falsified":
            return {"base": "falsified",
                    "witness": computation.get("counterexample"),
                    "moves_with": [computation], "correction": None,
                    "equivalence": False}
        return None
    if main in ("falsified", "invalidated"):
        witness = target.get("counterexample")
    elif computed == "falsified":
        witness = computation.get("counterexample")
    else:
        return None
    correction = None
    if main == "falsified" and str(target.get("route") or "").startswith(
            "derive") and computed in ("holds", "proven"):
        correction = _approximate_correction(root, key, target)
    return {"base": "falsified", "witness": witness,
            "moves_with": [computation] if computation else [],
            "correction": correction, "equivalence": True}


def _proven_row(row: "dict | None") -> bool:
    """Whether a record row's own verdict is a proof."""
    return classify_verdict((row or {}).get("verdict") or "") in (
        "proven", "derived")


def _computation_row(claims: list, name: "str | None") -> "dict | None":
    """The computation line of the claim `name` among a record's claim
    rows (`name[float]`, or the line a probe keeps), None when it has
    none."""
    from .gates import computation_line_of
    return next((c for c in claims
                 if name is not None
                 and computation_line_of(c.get("meta")) == name), None)


def plan_acceptance(root: str, key: str, claim_name: str, as_: str,
                    by: str | None = None, note: str | None = None,
                    corrected: str | None = None,
                    record: "tuple | None" = None) -> dict:
    """Intent:
        Resolve one acceptance request against the verified record and
        return everything the write WOULD do, the annotation, any
        verdict change, any generated discovery claim, without
        writing. The CLI prints this and asks; `apply_acceptance`
        executes it. Split so the prompt can never drift from the act.
        `record` is a `(path, doc)` pair already loaded, so several
        plans on one key share one record document.

    Raises:
        AcceptanceError: for every vocabulary violation, with the rule
        stated (notably: a falsified claim accepts only as a discovery;
        there is no accepting a bug, code changes until the claim
        stops falsifying).
    """
    if as_ not in ACCEPT_AS:
        raise AcceptanceError(f"--as must be one of {', '.join(ACCEPT_AS)}")
    path, doc = record if record is not None else _load_record(root, key)
    entry = doc[key]
    if as_ == "reconciled":
        # a record-level vow: the human confirms the current contents are
        # correct (after a merge, rebase, or a declared-claim edit) and
        # re-stamps the integrity over them. It adjudicates nothing, so it
        # takes no claim name; the human gate still applies at apply time.
        return {"path": path, "doc": doc, "key": key, "root": root,
                "as": "reconciled", "by": by, "note": note,
                "claim": None, "verdict": None,
                "actions": [f"re-stamp {key}'s integrity over its current "
                            f"contents and re-anchor it to HEAD"]}
    claims = entry.get("claims") or []
    target = next((c for c in claims if c.get("name") == claim_name), None)
    if target is None:
        names = ", ".join(sorted(filter(None, (c.get("name") for c in claims)))) or "none"
        raise UnknownAcceptanceTarget(f"{key} has no claim named {claim_name!r} "
                              f"(recorded claims: {names})")
    verdict = target.get("verdict") or ""
    base = classify_verdict(verdict)
    form = (entry.get("identity") or {}).get("form")

    plan = {"path": path, "doc": doc, "key": key, "claim": target,
            "root": root,
            "as": as_, "by": by, "note": note, "verdict": verdict,
            "claim_name": claim_name, "n": target.get("n"),
            "witness": target.get("counterexample"),
            "others_hold": _another_claim_holds(claims, target),
            "actions": []}
    whole = _whole_claim_discovery(root, key, claims, target, as_)
    if whole is not None:
        base = whole["base"]
        plan["witness"] = whole["witness"]
        plan["moves_with"] = whole["moves_with"]
    if as_ == "trusted":
        # external testimony (a compendium row) accepted at the
        # level the row claims: the row's verdict becomes that
        # level, provenance meta marks it testimony, and premises
        # resting on it cap at that level, never higher
        meta = target.get("meta") or {}
        if meta.get("mathema.surface") != "compendium" \
                or base not in ("declared", "unknown", "skipped"):
            raise AcceptanceError(
                f"{claim_name} is {verdict!r}"
                + ("" if meta.get("mathema.surface") == "compendium"
                   else " and not compendium-sourced")
                + ": --as trusted applies to a compendium row verify "
                  "could not settle (verdict declared, unknown or "
                  "skipped); anything else is either already evidence "
                  "or needs the ordinary flow")
        claimed = meta.get("mathema.compendium_claimed", "holds")
        # a row claimed proven within float64 is adopted at that
        # strength: its route caps whatever rests on it
        capped = str(meta.get("mathema.compendium_route") or "")
        capped = capped if capped.endswith(":within_float64") else ""
        written, versions = written_row(root, key, claim_name)
        plan["accepted"] = {"as": "trusted",
                            "at": datetime.date.today().isoformat(),
                            "level": claimed,
                            "source": meta.get("mathema.compendium", ""),
                            "statement": written, "versions": versions}
        if capped:
            plan["accepted"]["route"] = capped
            plan["new_route"] = capped
        if by:
            plan["accepted"]["by"] = by
        if note:
            plan["accepted"]["note"] = note
        plan["new_verdict"] = claimed
        plan["actions"].append(
            f"trust {claim_name} at its claimed level ({claimed}"
            + (f", capped at within_float64 by its route {capped}"
               if capped else "")
            + "), on "
            f"the word of {meta.get('mathema.compendium') or 'its compendium entry'}; "
            f"when `mathema verify` checks this key again, a local "
            f"verdict replaces the testimony")
        return plan
    if as_ == "superseded":
        pass       # any verdict may be superseded, handled below
    elif base in ("proven", "derived"):
        raise AcceptanceError(f"{claim_name} is {verdict}: a proof is its own "
                              "acceptance, there is nothing to decide")
    if as_ == "superseded":
        # a deliberate re-authoring of a verified claim: the record's
        # version moves to the append-only superseded: section (with
        # the commit its truth held at) and the authored version takes
        # over as the live claim on the next verify. Any verdict may
        # be superseded; the human is changing WHAT is claimed, not
        # disputing the old adjudication.
        meta = target.get("meta") or {}
        plan["accepted"] = {"as": "superseded",
                            "at": datetime.date.today().isoformat(),
                            "form": form,
                            "commit": meta.get(
                                "mathema.last_supported_commit")}
        if by:
            plan["accepted"]["by"] = by
        if note:
            plan["accepted"]["note"] = note
        plan["actions"].append(
            f"supersede the verified {claim_name!r} with the authored "
            f"version; the old row is retained under superseded:, the "
            f"new statement is checked on the next verify")
        return plan
    if as_ == "historical":
        # a claim the code has moved past (a parameter renamed or
        # removed, its variables no longer matching the signature):
        # the human accepts it as no-longer-valid. The row leaves the
        # live claims for the append-only `historical:` section,
        # carrying the commit its last valid adjudication saw.
        if base not in ("skipped", "unknown", "invalidated"):
            raise AcceptanceError(
                f"{claim_name} is {verdict}: only a claim the code has "
                f"moved past (skipped/unknown/invalidated, typically a "
                f"signature change) can be accepted as historical")
        meta = target.get("meta") or {}
        plan["accepted"] = {"as": "historical",
                            "at": datetime.date.today().isoformat(),
                            "form": form,
                            "commit": meta.get(
                                "mathema.last_supported_commit")}
        if by:
            plan["accepted"]["by"] = by
        if note:
            plan["accepted"]["note"] = note
        plan["actions"].append(
            f"move {claim_name} to the historical section (no longer "
            f"valid for the current signature; last supported at commit "
            f"{meta.get('mathema.last_supported_commit') or 'unknown'})")
        return plan
    if base == "holds":
        if as_ != "evidence":
            raise AcceptanceError(f"{claim_name} holds: accept it as evidence "
                                  "(--as evidence), nothing else applies")
        accepted = {"as": "evidence",
                    "at": datetime.date.today().isoformat(),
                    "n": target.get("n"),
                    "confidence": (target.get("meta") or {}).get("mathema.confidence"),
                    "form": form}
        if by:
            accepted["by"] = by
        if note:
            accepted["note"] = note
        plan["accepted"] = accepted
        plan["actions"].append(
            f"annotate {claim_name} as accepted evidence at n={target.get('n')} "
            f"(bound to form {str(form)[:12]}...)")
        return plan
    if base in ("unknown", "skipped"):
        if as_ != "risk":
            raise AcceptanceError(f"{claim_name} is {verdict}: accepting it "
                                  "means owning the risk of not checking "
                                  "(--as risk)")
        accepted = {"as": "risk", "at": datetime.date.today().isoformat(),
                    "form": form}
        if by:
            accepted["by"] = by
        if note:
            accepted["note"] = note
        plan["accepted"] = accepted
        if base == "unknown":
            plan["new_verdict"] = "skipped:unknown_but_accepted"
            plan["actions"].append(
                f"reclassify {claim_name}: unknown -> skipped:unknown_but_accepted "
                "(strict mode still refuses it; lenient proceeds)")
        else:
            plan["actions"].append(f"annotate {claim_name} as accepted risk")
        return plan
    if base in ("falsified", "invalidated"):
        if as_ == "risk":
            raise AcceptanceError(
                f"{claim_name} is {verdict}: a falsification is never accepted "
                "as risk, diagnose it (--as discovery), or fix the code "
                "until it stops falsifying")
        if as_ != "discovery":
            raise AcceptanceError(
                f"{claim_name} is {verdict}: there is no accepting a bug. "
                "If the code is wrong, change it, the recorded "
                "counterexample replays until the claim proves. If the CLAIM "
                "was wrong about the world, accept it as a discovery "
                "(--as discovery), optionally stating what is true with "
                "--corrected")
        parent = (target.get("meta") or {}).get("mathema.companion_of")
        from .gates import computation_line_of
        if computation_line_of(target.get("meta")):
            found = (target.get("meta") or {}).get("mathema.conditioning")
            if not (found and found.get("inherent") is True):
                owner = next((c for c in claims if c.get("name") == parent),
                             None)
                raise AcceptanceError(computation_line_refusal(
                    key, claim_name, parent, found,
                    whole=_proven_row(owner)))
        accepted = {"as": "discovery", "at": datetime.date.today().isoformat(),
                    "form": form}
        if by:
            accepted["by"] = by
        if note:
            accepted["note"] = note
        plan["accepted"] = accepted
        plan["companion_of"] = parent
        if parent:
            # a float companion is no authored law: nothing declares it
            # and no corrected statement replaces it; retiring it records
            # that the computation does not carry the proven law there
            plan["actions"].append(
                f"{claim_name!r} is the float companion of {parent!r}, "
                f"spawned by its proof; the discovery records where the "
                f"computation fails the proven law, and verify leaves "
                f"it retired while the law stands")
            return plan
        # the discovery itself is always recordable, whatever the
        # claim's shape. A corrected claim exists only when it is
        # VERIFIED here and now: the author's --corrected statement, or
        # a mechanically sound inverse, each adjudicated against the
        # live function before anything may be written
        c_tolerance = None
        offered = "its mechanical inverse"
        if corrected is not None:
            candidate, why_not, stated = corrected, None, True
        elif whole is not None and not whole["equivalence"]:
            candidate, why_not, stated = None, (
                f"{claim_name} is proven, so no inverse of it can hold; "
                f"what the running code does is the author's to state"), False
        elif whole is not None:
            candidate, c_tolerance, why_not = (
                whole["correction"] or (None, None, (
                    "an equivalence has no mechanical inverse, and its "
                    "computation does not hold, so no `~=` correction "
                    "at its tolerance can")))
            stated = False
            offered = "its `~=` correction"
        else:
            candidate, why_not = invert_conjecture(
                target.get("statement") or "", claim_name)
            stated = False
        c_verdict = c_n = None
        if candidate:
            probe, err = _adjudicate_candidate(root, key, candidate,
                                               target.get("route"),
                                               tolerance=c_tolerance)
            if probe is None:
                if stated:
                    raise AcceptanceError(
                        f"--corrected {candidate!r} cannot be checked: "
                        f"{err}")
                candidate, why_not = None, err
            else:
                base_c = classify_verdict(probe.verdict)
                line = (f" on its computation line {probe.name}"
                        if "[" in (probe.name or "") else "")
                if base_c == "falsified":
                    if stated:
                        raise AcceptanceError(
                            f"--corrected {candidate!r} itself falsifies"
                            f"{line} (counterexample: "
                            f"{probe.counterexample}); a correction that "
                            "is wrong too is never written")
                    candidate, why_not = None, (
                        f"{offered} falsifies too{line} "
                        f"(counterexample: {probe.counterexample})")
                elif not stated and base_c not in ("proven", "holds"):
                    candidate, why_not = None, (
                        f"{offered} comes out "
                        f"{probe.verdict!r}{line}, not a holding verdict")
                else:
                    c_verdict = probe.verdict
                    c_n = getattr(probe, "n", None)
        plan["actions"].append(
            f"move {claim_name} to the record's discoveries section"
            + (f" (superseded_by: {claim_name}_corrected)" if candidate
               else "")
            + ", keeping its counterexample as the witness")
        for row in plan.get("moves_with") or ():
            plan["actions"].append(
                f"move its computation line {row.get('name')!r} "
                f"({row.get('verdict')}) to the discoveries section with it")
        if candidate:
            plan["corrected_statement"] = candidate
            plan["corrected_name"] = f"{claim_name}_corrected"
            plan["corrected_verdict"] = c_verdict
            if c_tolerance is not None:
                plan["corrected_tolerance"] = c_tolerance
            if c_n:
                plan["corrected_n"] = c_n
            kind = ("stated" if stated else "approximate"
                    if whole is not None else "inverted")
            plan["actions"].append(
                f"declare the {kind} corrected "
                f"claim {plan['corrected_name']!r}: {candidate!r}"
                + (f" with tolerance {tolerance_words(c_tolerance)}"
                   if c_tolerance is not None else "")
                + f", checked now: {c_verdict}"
                + (f" over {c_n} trials" if c_n else ""))
        else:
            plan["actions"].append(
                "no corrected claim is written ("
                + (why_not or "no candidate")
                + '); state what is true with --corrected "<law>"')
        # the authoring surface must stop restating the retired law, or
        # the next real adjudication regenerates the falsification a
        # human just dispositioned. Claims files are rewritten as part
        # of the acceptance; a code surface (docstring, decorator)
        # cannot be, and verify notes the leftover until it changes
        edits = _declared_claim_files(root, key, claim_name,
                                      target.get("statement") or "")
        plan["declared_edits"] = edits
        for rel in edits:
            if candidate:
                plan["actions"].append(
                    f"rewrite {rel}: replace declared claim {claim_name!r} "
                    f"with {plan['corrected_name']!r}")
            else:
                plan["actions"].append(
                    f"rewrite {rel}: remove declared claim {claim_name!r} "
                    "(retired as a discovery)")
        if not edits:
            plan["actions"].append(
                f"{claim_name!r} is not declared in any claims file (a "
                "docstring or decorator surface); verify will note it as "
                "retired until that source changes")
        return plan
    raise AcceptanceError(f"{claim_name} has verdict {verdict!r}, which the "
                          "acceptance vocabulary doesn't cover")


def apply_acceptance(plan: dict) -> str:
    """Intent:
        Execute a `plan_acceptance` (or `plan_rename`) result: mutate
        the record document and write it back, appending the acceptance-history event so
        every classification change stays tracked.
    """
    # the human gate: when a PIN is configured, nothing below runs
    # without a person at a terminal, and the record says which
    # credential authorised it. Every acceptance path funnels through
    # an apply function, so gating here (not at the CLI prompts)
    # covers the JSON and scripted paths too.
    if plan.get("from"):
        _require_form_confirmed(plan)
    from . import auth
    attestation = auth.require_human(f"accept --as {plan['as']}")
    auth.enforce_policy(attestation, plan.get("root", "."))
    return _apply_attested(plan, attestation)


def _apply_attested(plan: dict, attestation) -> str:
    """Intent:
        Write one plan once the human gate has passed, `attestation`
        being what the gate returned (None without a PIN).
    """
    doc, key, target = plan["doc"], plan["key"], plan["claim"]
    entry = doc[plan.get("from") or key]
    if plan["as"] == "reconciled" and plan.get("from"):
        return _apply_rename(plan, attestation)
    if plan["as"] == "reconciled":
        # re-stamp the integrity over the current contents and re-anchor
        # to HEAD, recording who vouched (and whether a pin backed it, so
        # an unpinned reconcile stays visible as such)
        from .spec import _git_commit
        rec: dict = {"at": datetime.date.today().isoformat(),
                     "by": plan.get("by")}
        if plan.get("note"):
            rec["note"] = plan["note"]
        if attestation:
            rec["verified_by"] = dict(attestation)
        entry.setdefault("lineage", {})["commit"] = _git_commit(
            plan.get("root", "."))
        entry.setdefault("identity", {})["reconciled"] = rec
        _restamp_integrity(entry)
        write_yaml(plan["path"], doc,
                   header=f"machine record; reconciled {key}")
        who = ((rec.get("verified_by") or {}).get("key") or plan.get("by")
               or "unpinned")
        return (f"reconciled: {key} re-stamped over its current contents "
                f"(by {who})")
    event = _event(plan["as"], plan.get("by"), plan["verdict"], plan.get("note"))
    if attestation:
        plan["accepted"]["verified_by"] = dict(attestation)
        event["verified_by"] = dict(attestation)
    if plan["as"] == "superseded":
        entry = doc[plan["key"]]
        claims = entry.get("claims") or []
        target["accepted"] = plan["accepted"]
        target.setdefault("acceptance_history", []).append(event)
        target["superseded_by"] = target.get("name")
        claims.remove(target)
        entry.setdefault("superseded", []).append(target)
        _restamp_integrity(doc[plan["key"]])
        write_yaml(plan["path"], doc,
                   header=f"machine record; supersession of "
                          f"{target.get('name')}")
        return (f"superseded: {target.get('name')}, the authored "
                f"version is checked on the next verify")
    root = plan.get("root", ".")
    fresh_before = _claims_fingerprint_now(root, key, entry) == \
        (entry.get("identity") or {}).get("claims_fingerprint")
    if plan["as"] == "historical":
        entry = doc[plan["key"]]
        claims = entry.get("claims") or []
        target["accepted"] = plan["accepted"]
        target.setdefault("acceptance_history", []).append(event)
        claims.remove(target)
        entry.setdefault("historical", []).append(target)
        if fresh_before:
            _refresh_claims_fingerprint(root, key, entry)
        _restamp_integrity(doc[plan["key"]])
        write_yaml(plan["path"], doc,
                   header=f"machine record; historical acceptance of "
                          f"{target.get('name')}")
        return f"accepted historical: {target.get('name')}"
    target.setdefault("acceptance_history", []).append(event)
    target["accepted"] = plan["accepted"]
    if plan.get("new_verdict"):
        meta = dict(target.get("meta") or {})
        meta["mathema.previous_verdict"] = target.get("verdict")
        target["meta"] = meta
        target["verdict"] = plan["new_verdict"]
    if plan.get("new_route"):
        target["route"] = plan["new_route"]
    if (plan.get("accepted") or {}).get("as") == "discovery":
        claims = entry.get("claims") or []
        claims.remove(target)
        if plan.get("corrected_name"):
            target["superseded_by"] = plan["corrected_name"]
        entry.setdefault("discoveries", []).append(target)
        for row in plan.get("moves_with") or ():
            # a line of the claim retires with it, under the same
            # acceptance
            if row in claims:
                claims.remove(row)
                row.setdefault("acceptance_history", []).append(dict(event))
                row["accepted"] = dict(plan["accepted"])
                entry["discoveries"].append(row)
        if plan.get("corrected_statement"):
            meta = {"mathema.surface": "declared",
                    "mathema.discovered_from": target["name"],
                    "mathema.supporting_witness": target.get("counterexample")}
            accepted_by = (plan.get("accepted") or {}).get("by")
            if accepted_by:
                # the acceptance IS the declaration, so the accepting
                # identity is the claim's author
                meta["mathema.authored"] = {"by": accepted_by}
            witness_args = (target.get("meta") or {}).get(
                "mathema.counterexample_args")
            if witness_args:
                meta["mathema.counterexample_args"] = witness_args
            new_claim = {
                "name": plan["corrected_name"],
                "statement": plan["corrected_statement"],
                "verdict": plan.get("corrected_verdict") or "declared",
                "route": target.get("route") or "best",
                "note": "declared by accepting the falsification of "
                        f"{target['name']!r} as a discovery; checked "
                        "at acceptance",
                "meta": meta,
            }
            if plan.get("corrected_n"):
                new_claim["n"] = plan["corrected_n"]
            if plan.get("corrected_tolerance") is not None:
                new_claim["tolerance"] = plan["corrected_tolerance"]
            claims.append(new_claim)
        entry["claims"] = claims
    if plan.get("declared_edits"):
        stub = corrected_stub(plan)
        for rel in plan["declared_edits"]:
            _apply_declared_edit(plan["root"], rel, plan["key"],
                                 target["name"], stub)
    if fresh_before:
        _refresh_claims_fingerprint(root, key, entry)
    _restamp_integrity(entry)
    write_yaml(plan["path"], doc,
               header=f"machine record; binds to form "
                      f"{(entry.get('identity') or {}).get('form')}")
    return "; ".join(plan["actions"])


_KIND_PHRASE = {"evidence": "evidence", "risk": "a risk",
                "discovery": "a discovery", "historical": "historical",
                "superseded": "superseded", "trusted": "trusted"}


def _verdict_line(plan: dict) -> "str | None":
    """The verdict being accepted, with its witness when it was
    falsified, or its computation line's when a proven claim retires
    with that falsified line, and its trial count when it holds."""
    verdict = plan.get("verdict") or ""
    base = classify_verdict(verdict)
    falsified_line = next(
        (r for r in plan.get("moves_with") or ()
         if classify_verdict(r.get("verdict") or "") == "falsified"), None)
    if base in ("proven", "derived") and falsified_line is not None \
            and plan.get("witness"):
        return (f"{base}; its computation line {falsified_line.get('name')} "
                f"falsified at {plan['witness']}")
    if base in ("falsified", "invalidated") and plan.get("witness"):
        return f"{base} at {plan['witness']}"
    if base == "holds" and plan.get("n"):
        return f"holds over {plan['n']} trials"
    return f"verdict {verdict}" if verdict else None


def _discovery_lines(plan: dict) -> list:
    """The move a discovery makes, then its correction when one
    applies."""
    moved = ("the claim moves to discoveries with that witness"
             if plan.get("witness") else "the claim moves to discoveries")
    parent = plan.get("companion_of")
    if parent:
        return [f"{moved}; as the float companion of {parent}, it stays "
                f"retired while {parent} stands"]
    for row in plan.get("moves_with") or ():
        moved += f", with its computation line {row.get('name')}"
    edits = plan.get("declared_edits") or []
    if edits:
        moved += ", out of " + " and ".join(edits)
    else:
        moved += ("; a docstring or decorator declares it, and verify "
                  "notes it as retired until that source changes")
    lines = [moved]
    if plan.get("corrected_statement"):
        checked = plan.get("corrected_verdict") or "declared"
        if plan.get("corrected_n"):
            checked += f" over {plan['corrected_n']} trials"
        stub = corrected_stub(plan) or {}
        tolerance = (f" with tolerance {tolerance_words(stub['tolerance'])}"
                     if stub.get("tolerance") is not None else "")
        lines.append(f"the corrected claim takes its place: "
                     f"{stub.get('name')} [{stub.get('route')}]: "
                     f"{stub.get('statement')}{tolerance}, checked now: "
                     f"{checked}")
    elif not plan.get("others_hold"):
        lines.append('no corrected claim; pass --corrected "<law>" to state '
                     "what is true")
    return lines


def describe_acceptance(plan: dict) -> list:
    """Intent:
        The text a person confirms before an acceptance is written: a
        header naming the key, the claim, the kind of acceptance and
        who decides, then the verdict line (with the witness of a
        falsification) and one line per change the write makes.
        Detail lines are indented two spaces under the header.
    """
    key, as_ = plan["key"], plan["as"]
    who = f", by {plan['by']}" if plan.get("by") else ""
    if as_ == "reconciled" and plan.get("from"):
        return ([f"accept {key} as reconciled from {plan['from']}{who}"]
                + [f"  {a}" for a in plan.get("actions") or []])
    if as_ == "reconciled":
        return [f"accept {key} as reconciled{who}",
                "  its integrity is re-stamped over its current contents "
                "and anchored to HEAD"]
    name = plan.get("claim_name") or (plan.get("claim") or {}).get("name")
    lines = []
    verdict = _verdict_line(plan)
    if verdict:
        lines.append(verdict)
    accepted = plan.get("accepted") or {}
    if as_ == "evidence":
        lines.append(f"the claim is accepted as evidence at n={plan.get('n')}"
                     f", bound to form {accepted.get('form')}")
    elif as_ == "risk":
        if plan.get("new_verdict"):
            lines.append(f"its verdict becomes {plan['new_verdict']}; strict "
                         "mode still refuses it, lenient mode proceeds")
        else:
            lines.append("the claim is recorded as an accepted risk")
    elif as_ == "historical":
        lines.append("the claim moves to historical, last supported at "
                     f"commit {accepted.get('commit') or 'unknown'}")
    elif as_ == "superseded":
        lines.append("the verified claim moves to superseded; the authored "
                     "version is checked on the next verify")
    elif as_ == "trusted":
        lines.append(f"the claim is trusted at its claimed level, "
                     f"{accepted.get('level')}, on the word of "
                     f"{accepted.get('source') or 'its compendium entry'}; a "
                     "local verdict replaces it when verify checks this key "
                     "again")
    elif as_ == "discovery":
        lines.extend(_discovery_lines(plan))
    return ([f"accept {key} :: {name} as {_KIND_PHRASE.get(as_, as_)}{who}"]
            + [f"  {ln}" for ln in lines])


def corrected_stub(plan: dict) -> dict | None:
    """Intent:
        The declared-layer stanza for a discovery's corrected claim:
        its name, statement and route, the route reduced to the base
        spelling a claims file takes (`probe`, `derive` or `best`), and
        its tolerance when the correction states one.
        None when the plan corrects no claim.
    """
    if not plan.get("corrected_statement"):
        return None
    route = (plan["claim"].get("route") or "best").split(":", 1)[0]
    stub = {"name": plan["corrected_name"],
            "statement": plan["corrected_statement"],
            "route": route if route in ("probe", "derive") else "best"}
    if plan.get("corrected_tolerance") is not None:
        stub["tolerance"] = plan["corrected_tolerance"]
    return stub


def _carry_trust(c: dict, accepted: dict, history: list) -> None:
    """Intent:
        Carry a trusted acceptance onto a freshly adjudicated row. A
        local verdict that contradicts the trusted level (falsified), or
        is at least as strong as it (proven over a trusted proven or
        holds, holds over a trusted holds), is evidence that replaces
        it: the acceptance is marked stale. A weaker consistent local
        verdict (holds under a trusted proven) leaves the acceptance
        standing at its level, and the row says what was seen: its note
        reads `trusted as: proven, strongest evidence seen: holds` and
        `meta["mathema.strongest_evidence"]` holds the local verdict. A
        re-adjudication that cannot settle the row (unknown, skipped)
        leaves the acceptance standing too, never `invalidated`, with
        `meta["mathema.trusted_unsettled"]` recording what the sweep got.
    """
    meta = dict(c.get("meta") or {})
    fresh = c.get("verdict") or ""
    if classify_verdict(fresh) == "invalidated":
        fresh = meta.get("mathema.regressed_to") or fresh
    level = accepted.get("level") or "holds"
    kind = classify_verdict(fresh)
    meta.pop("mathema.strongest_evidence", None)
    if kind in ("unknown", "skipped", "declared"):
        c["verdict"] = level
        meta.pop("mathema.regressed_to", None)
        if meta.get("mathema.previous_verdict") == level:
            meta.pop("mathema.previous_verdict")
        meta["mathema.trusted_unsettled"] = fresh
    elif kind == "holds" and classify_verdict(level) == "proven":
        c["verdict"] = level
        meta.pop("mathema.regressed_to", None)
        meta.pop("mathema.trusted_unsettled", None)
        if meta.get("mathema.previous_verdict") == level:
            meta.pop("mathema.previous_verdict")
        meta["mathema.strongest_evidence"] = fresh
        c["note"] = (f"trusted as: {level}, strongest evidence seen: "
                     f"{fresh}")
    else:
        meta.pop("mathema.trusted_unsettled", None)
        accepted["stale"] = True
        history.append({"at": datetime.date.today().isoformat(),
                        "event": "stale",
                        "reason": f"a local verdict ({fresh}) replaces the "
                                  f"level it was trusted at"})
    c["meta"] = meta
    c["accepted"] = accepted
    c["acceptance_history"] = history


def written_row(root: "str | None", key: str, name) -> tuple:
    """Intent:
        `(statement, versions)` of the library row `key` / `name` as the
        claims file writes it: its `statement:` string unchanged, and its
        own `versions:` range or else the file's; `(None, None)` when no
        claims file under `root` (or bundled with mathema) states it.
    """
    from .compendium import load_library_claims
    try:
        info = load_library_claims(root).get(key)
    except Exception:
        return None, None
    if not info:
        return None, None
    row = next((r for r in info["entry"].get("claims") or []
                if isinstance(r, dict) and r.get("name") == name), None)
    if row is None:
        return None, None
    return (row.get("statement") or row.get("law"),
            str(row.get("versions") or info.get("versions") or "*"))


def _range_ends(spec: str) -> tuple:
    """The `(lowest, highest)` version tuples a range admits, None for
    an open end: `>=2.2,<3` is `((2, 2), (3,))`."""
    from .compendium import _version_tuple
    low = high = None
    for part in (p.strip() for p in str(spec or "*").split(",")):
        if part.startswith(">="):
            low = _version_tuple(part[2:])
        elif part.startswith("<"):
            high = _version_tuple(part[1:])
    return low, high


def _widened(old: str, new: str) -> bool:
    """Whether the range `new` admits a version the range `old` does
    not: a lower floor, a higher ceiling, or an end left open."""
    old_low, old_high = _range_ends(old)
    new_low, new_high = _range_ends(new)
    if old_low is not None and (new_low is None or new_low < old_low):
        return True
    if old_high is not None and (new_high is None or new_high > old_high):
        return True
    return False


def trust_mismatch(accepted: dict, statement, versions) -> "str | None":
    """Intent:
        Why a trusted acceptance no longer speaks for the row as the
        claims file now writes it, or None when it still does: the
        acceptance stored no statement (it predates storing one), the
        row is no longer stated, its statement string changed, or its
        versions range admits versions the accepted range did not. A
        narrower range, and edits elsewhere in the file, keep it.
    """
    stored = accepted.get("statement")
    if stored is None:
        return ("the acceptance predates storing the row's statement, so "
                "it cannot show the row is unchanged")
    if statement is None:
        return "the row is no longer stated in a claims file"
    if statement != stored:
        return "the row's statement changed since it was accepted"
    old = accepted.get("versions")
    if old is not None and versions is not None and _widened(old, versions):
        return (f"the row's versions range widened from {old} to "
                f"{versions} since it was accepted")
    return None


def carry_acceptance(spec: dict, key: str, path: str) -> None:
    """Intent:
        At record-write time, carry each claim's acceptance state
        forward from the prior record onto the freshly adjudicated
        spec, adjudication rebuilds records from scratch, and a human
        decision must never be silently dropped by a re-run.

    Notes:
        A trusted acceptance (testimony at the level a row claims)
        stands until a local verdict contradicts it or is at least as
        strong (`_carry_trust`). Three rules
        ride along for the others. A changed form marks the acceptance
        stale (it was a decision about a different function; a new
        sign-off is required) and the stale marker is itself a history
        event. A still-valid risk acceptance re-applies the
        `skipped:unknown_but_accepted` classification to a fresh
        `unknown`. A still-valid evidence acceptance compares the
        fresh sample size against the accepted one and stamps a drift
        warning when it has materially weakened (under half). The
        `discoveries` section is retained history and carries forward
        verbatim.
    """
    if not os.path.exists(path):
        return
    try:
        import yaml
        with open(path) as fh:
            prior_doc = yaml.safe_load(fh) or {}
        prior_entry = prior_doc.get(key) or {}
    except Exception:
        return
    prior_claims = {c.get("name"): c for c in prior_entry.get("claims") or []
                    if c.get("name")}
    discovery_rows = [d for d in honoured_retirements(prior_entry,
                                                      "discoveries")
                      if d.get("name")]
    historical_names = {h.get("name")
                        for h in honoured_retirements(prior_entry,
                                                      "historical")
                        if h.get("name")}
    if discovery_rows or historical_names:
        # a claim accepted as historical is retained under its own
        # section and never re-grows as a live claim, name-wide. A
        # discovery retires a specific LAW: the same name stated with
        # a DIFFERENT law is new authorship and lives on; only the
        # retired law itself stays out. A SUPERSEDED name is different
        # again: the name lives on with its re-authored statement,
        # only the old version is retained history.
        # a discovery row that states its law retires exactly that
        # law; a statement-less row (an older record's shape) cannot
        # be compared and retires its name outright
        matchers = []
        for d in discovery_rows:
            stmt = d.get("statement") or d.get("law") or ""
            matchers.append((d["name"], _same_law_as(stmt, key) if stmt else None))

        def _retired(c) -> bool:
            name = c.get("name")
            if name in historical_names:
                return True
            stmt = c.get("statement") or c.get("law") or ""
            return any(n == name and (same is None or same(stmt))
                       for n, same in matchers)

        spec["claims"] = [c for c in spec.get("claims") or []
                          if not _retired(c)]
    fresh_form = (spec.get("identity") or {}).get("form")
    for c in spec.get("claims") or []:
        prior = prior_claims.get(c.get("name"))
        if prior is None or "accepted" not in prior:
            continue
        accepted = dict(prior["accepted"])
        history = list(prior.get("acceptance_history") or [])
        if accepted.get("as") == "trusted" and not accepted.get("stale"):
            root = os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(path))))
            written, versions = written_row(root, key, c.get("name"))
            reason = trust_mismatch(accepted, written, versions)
            if reason is not None:
                accepted["stale"] = True
                history.append({
                    "at": datetime.date.today().isoformat(),
                    "event": "stale",
                    "reason": f"{reason}; accept the row as trusted: "
                              f"mathema accept {key} {c.get('name')} "
                              f"--as trusted"})
                c["accepted"] = accepted
                c["acceptance_history"] = history
                continue
            _carry_trust(c, accepted, history)
            continue
        if not same_form(accepted.get("form"), fresh_form) \
                and not accepted.get("stale"):
            accepted["stale"] = True
            history.append({"at": datetime.date.today().isoformat(),
                            "event": "stale",
                            "reason": "form changed since acceptance, "
                                      "re-verification and a new sign-off "
                                      "are required"})
        c["accepted"] = accepted
        c["acceptance_history"] = history
        if accepted.get("stale"):
            continue
        base = classify_verdict(c.get("verdict") or "")
        if accepted.get("as") == "risk" and base in ("unknown", "skipped"):
            if c.get("verdict") != "skipped:unknown_but_accepted":
                meta = dict(c.get("meta") or {})
                meta["mathema.previous_verdict"] = c.get("verdict")
                c["meta"] = meta
                c["verdict"] = "skipped:unknown_but_accepted"
        elif accepted.get("as") == "evidence" and base == "holds":
            accepted_n = accepted.get("n") or 0
            fresh_n = c.get("n") or 0
            if accepted_n and fresh_n < accepted_n / 2:
                meta = dict(c.get("meta") or {})
                meta["mathema.acceptance_evidence_drift"] = (
                    f"accepted at n={accepted_n}, current run n={fresh_n}, "
                    "materially weaker evidence than was signed off")
                c["meta"] = meta
    if prior_entry.get("discoveries") and "discoveries" not in spec:
        spec["discoveries"] = prior_entry["discoveries"]
    if prior_entry.get("historical") and "historical" not in spec:
        spec["historical"] = prior_entry["historical"]
    if prior_entry.get("superseded") and "superseded" not in spec:
        spec["superseded"] = prior_entry["superseded"]


def _intent_binding(entry: dict) -> dict:
    """Intent:
        What an intent acceptance binds to: the signature hash, the
        raised-exception surface, and the intent text itself. A change
        to ANY of these re-opens the acceptance; a body-only refactor
        (same signature, same raises) deliberately does not, the
        claims layer guards the body through the form hash.
    """
    import hashlib
    text = (entry.get("intent") or "").strip()
    return {"sig": (entry.get("identity") or {}).get("sig"),
            "raises": sorted(entry.get("raises") or []),
            "intent_hash": hashlib.sha256(text.encode()).hexdigest()[:12]}


def plan_intent_acceptance(root: str, key: str, by: str | None = None,
                           note: str | None = None) -> dict:
    """Intent:
        The human step that moves a function's intent from `declared`
        to `documented`: reviewed the stated intent against the
        implementation and signed it off. Requires a recorded intent;
        stamps who/when and the binding above.
    """
    path, doc = _load_record(root, key)
    entry = doc[key]
    if not (entry.get("intent") or "").strip():
        raise AcceptanceError(f"{key} has no recorded intent to accept, "
                              f"state one (a docstring Intent: block or a "
                              f"declared-layer intent) and re-verify first")
    accepted = {"at": datetime.date.today().isoformat(),
                **_intent_binding(entry)}
    if by:
        accepted["by"] = by
    if note:
        accepted["note"] = note
    return {"path": path, "doc": doc, "key": key, "root": root,
            "intent_accepted": accepted,
            "actions": [f"accept the stated intent of {key} as documented "
                        f"(binds to signature + raises + the text; a "
                        f"body-only refactor keeps it, any interface or "
                        f"wording change re-opens it)"]}


def apply_intent_acceptance(plan: dict) -> str:
    from . import auth
    attestation = auth.require_human("accept --intent")
    auth.enforce_policy(attestation, plan.get("root", "."))
    if attestation:
        plan["intent_accepted"]["verified_by"] = dict(attestation)
    entry = plan["doc"][plan["key"]]
    entry["intent_accepted"] = plan["intent_accepted"]
    entry.setdefault("meta", {})["mathema.intent_provenance"] = "documented"
    _restamp_integrity(plan["doc"][plan["key"]])
    write_yaml(plan["path"], plan["doc"],
               header=f"machine record; intent accepted for {plan['key']}")
    return f"accepted intent of {plan['key']} as documented"


def carry_intent_acceptance(spec: dict, key: str, path: str) -> None:
    """Intent:
        Carry a standing intent acceptance across a record rewrite,
        re-checking its binding: if the signature, the raised-
        exception surface, or the intent text changed, the acceptance
        goes stale (an event says why) and the rung drops back to
        declared until a person re-accepts.
    """
    import os

    import yaml
    if not os.path.exists(path):
        return
    try:
        with open(path) as fh:
            prior = (yaml.safe_load(fh) or {}).get(key) or {}
    except Exception:
        return
    # concepts_accepted rides the same carry (tags are curation, not
    # evidence, no staleness; removable only by editing the record
    # through mathema accept)
    if prior.get("concepts_accepted") and "concepts_accepted" not in spec:
        spec["concepts_accepted"] = prior["concepts_accepted"]
    accepted = prior.get("intent_accepted")
    if not accepted:
        return
    accepted = dict(accepted)
    fresh = _intent_binding(spec)
    changed = [what for what in ("sig", "raises", "intent_hash")
               if accepted.get(what) != fresh[what]]
    if changed and not accepted.get("stale"):
        accepted["stale"] = True
        accepted["stale_reason"] = (
            f"{', '.join(changed)} changed since acceptance, the "
            f"documented rung needs a new sign-off")
    spec["intent_accepted"] = accepted
    if not accepted.get("stale"):
        spec.setdefault("meta", {})["mathema.intent_provenance"] = \
            "documented"


def _scope_intent_path(root: str) -> str:
    import os
    return os.path.join(root, ".mathema", "meta", "intent.yaml")


def _current_scope_intent(root: str, key: str) -> "str | None":
    """Intent:
        The live intent text for a module key (its docstring's Intent:
        block or first paragraph, README fallback) or for the project
        ("__project__": the top README's Intent). None when nothing is
        stated.
    """
    import importlib
    import os

    from .docstring import _read_module_intent, _read_readme_intent
    if key == "__project__":
        readme = os.path.join(root, "README.md")
        got = (_read_readme_intent(open(readme).read())
               if os.path.exists(readme) else None)
        return (got or {}).get("text")
    try:
        module = importlib.import_module(key)
    except Exception:
        return None
    got = _read_module_intent(module)
    if got is None:
        src = getattr(module, "__file__", None)
        if src:
            readme = os.path.join(os.path.dirname(src), "README.md")
            if os.path.exists(readme):
                got = _read_readme_intent(open(readme).read())
    return (got or {}).get("text")


def plan_scope_intent_acceptance(root: str, key: str,
                                 by: "str | None" = None,
                                 note: "str | None" = None) -> dict:
    """Intent:
        What accepting a MODULE's or the whole PROJECT's
        ("__project__") stated intent would do, decided but not
        written, the same plan/apply split every other acceptance
        has, so the prompt can never drift from the act and a caller
        can preview the change before committing to it.

    Raises:
        AcceptanceError: the scope states no intent to accept.
    """
    import hashlib
    text = _current_scope_intent(root, key)
    if not text:
        raise AcceptanceError(
            f"{key} states no intent to accept; add an Intent: block "
            f"(module docstring or README) first")
    accepted = {"at": datetime.date.today().isoformat(),
                "text_hash": hashlib.sha256(
                    text.strip().encode()).hexdigest()[:12]}
    if by:
        accepted["by"] = by
    if note:
        accepted["note"] = note
    return {"key": key, "path": _scope_intent_path(root), "text": text,
            "root": root, "accepted": accepted, "by": by, "note": note,
            "actions": [f"accept the stated intent of {key} as documented"]}


def apply_scope_intent_acceptance(plan: dict) -> str:
    """Intent:
        Write the scope-intent acceptance `plan_scope_intent_acceptance`
        decided, into .mathema/meta/intent.yaml.
    """
    import os

    import yaml
    from . import auth
    attestation = auth.require_human("accept --intent (scope)")
    auth.enforce_policy(attestation, plan.get("root", "."))
    if attestation:
        plan["accepted"]["verified_by"] = dict(attestation)
    path = plan["path"]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    doc = (yaml.safe_load(open(path)) or {}) if os.path.exists(path) else {}
    doc[plan["key"]] = {"text": plan["text"], "accepted": plan["accepted"]}
    from .spec import atomic_write_text
    atomic_write_text(
        path, "# scope-level intent acceptances (module / __project__)"
              ", committed with the store\n"
        + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True))
    return f"accepted the stated intent of {plan['key']} as documented"


def accept_scope_intent(root: str, key: str, by: "str | None" = None,
                        note: "str | None" = None) -> str:
    """Intent:
        The documented rung for a MODULE or the whole PROJECT: plan
        and apply in one call, for callers that do not need to preview
        (the plan/apply pair above is what the CLI uses).
    """
    return apply_scope_intent_acceptance(
        plan_scope_intent_acceptance(root, key, by=by, note=note))


def scope_intent_status(root: str, key: str,
                        current_text: "str | None") -> "str | None":
    """Intent:
        "documented" when a live scope acceptance matches the current
        text, "stale" when the text moved on, None when never
        accepted.
    """
    import hashlib
    import os

    import yaml
    path = _scope_intent_path(root)
    if not os.path.exists(path):
        return None
    try:
        entry = (yaml.safe_load(open(path)) or {}).get(key)
    except Exception:
        return None
    if not entry:
        return None
    if not current_text:
        return "stale"
    now = hashlib.sha256(current_text.strip().encode()).hexdigest()[:12]
    return "documented" if now == (entry.get("accepted") or {}).get(
        "text_hash") else "stale"


_CHANGED_WORDS = {"sig": "signature", "raises": "raised exceptions",
                  "intent_hash": "intent text"}
_LEVEL_ORDER = {"codebase": 0, "package": 1, "module": 2, "function": 3}


def _in_project(root_abs: str, path: "str | None") -> bool:
    """Intent:
        Whether a source file belongs to the project at `root_abs`:
        inside the root, and not inside an installed environment's
        site-packages.
    """
    import os
    if not path:
        return False
    path = os.path.abspath(path)
    inside = os.path.commonpath([root_abs, path]) == root_abs
    return inside and "site-packages" not in path.split(os.sep)


def _marker_line(lines: list, start: int = 0,
                 end: "int | None" = None) -> "int | None":
    """Intent:
        The 1-based number of the first line in `lines[start:end]`
        that opens an intent: an `Intent:` line or an `# Intent`
        style markdown heading. None when no line does.
    """
    import re
    heading = re.compile(r"^#{1,4}\s*Intent\s*$", re.IGNORECASE)
    for i in range(start, len(lines) if end is None else end):
        text = lines[i].strip()
        if text.lower() == "intent:" or heading.match(text):
            return i + 1
    return None


def _file_lines(path: str) -> list:
    """Intent:
        The lines of a text file, empty when it cannot be read.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read().splitlines()
    except OSError:
        return []


def _scope_source(root: str, key: str) -> tuple:
    """Intent:
        Where a scope's stated intent is written, as `(path, line)`:
        the top README for `__project__`; otherwise the module's own
        source when its docstring states the intent, else the README.md
        beside it. `(None, None)` when the scope does not resolve.
    """
    import importlib
    import os

    from .docstring import _read_module_intent
    if key == "__project__":
        path = os.path.join(root, "README.md")
    else:
        try:
            module = importlib.import_module(key)
        except Exception:
            return None, None
        src = getattr(module, "__file__", None)
        if not src:
            return None, None
        path = src
        if _read_module_intent(module) is None:
            path = os.path.join(os.path.dirname(src), "README.md")
    return path, _marker_line(_file_lines(path)) or 1


def _scope_item(root: str, key: str, level: str) -> "dict | None":
    """Intent:
        A module, package or codebase intent that waits on a person:
        stated and never accepted (`new`), or accepted and since
        reworded (`stale`). None when nothing is stated or the
        acceptance is current.
    """
    text = _current_scope_intent(root, key)
    if not text:
        return None
    status = scope_intent_status(root, key, text)
    if status == "documented":
        return None
    path, line = _scope_source(root, key)
    item = {"key": key, "level": level,
            "status": "stale" if status == "stale" else "new",
            "text": text, "file": path, "line": line}
    if status == "stale":
        item["changed"] = [_CHANGED_WORDS["intent_hash"]]
        accepted = (_scope_acceptances(root).get(key) or {}).get(
            "accepted") or {}
        item["accepted_at"] = accepted.get("at")
    return item


def _function_item(key: str, entry: dict, fn) -> "dict | None":
    """Intent:
        A function intent that waits on a person, read from its
        record: a recorded intent with no acceptance (`new`), or an
        acceptance whose signature, raised exceptions or text moved on
        (`stale`, with what changed). None when there is no recorded
        intent or the acceptance is current.
    """
    import inspect
    text = (entry.get("intent") or "").strip()
    if not text:
        return None
    accepted = entry.get("intent_accepted") or {}
    changed: list = []
    if accepted:
        fresh = _intent_binding(entry)
        changed = [_CHANGED_WORDS[what]
                   for what in ("sig", "raises", "intent_hash")
                   if accepted.get(what) != fresh[what]]
        if not changed and not accepted.get("stale"):
            return None
    path = line = None
    from .analysis import foreign_body
    if fn is not None and not foreign_body(fn):
        try:
            path = inspect.getsourcefile(fn)
            body, first = inspect.getsourcelines(fn)
        except (OSError, TypeError):
            path = None
        if path:
            lines = _file_lines(path)
            line = (_marker_line(lines, first - 1, first - 1 + len(body))
                    or first)
    item = {"key": key, "level": "function",
            "status": "stale" if accepted else "new", "text": text,
            "signature": entry.get("signature"),
            "raises": sorted(entry.get("raises") or []),
            "file": path, "line": line}
    if accepted:
        item["changed"] = changed
        item["accepted_at"] = accepted.get("at")
        item["accepted_raises"] = sorted(accepted.get("raises") or [])
        if accepted.get("stale_reason"):
            item["reason"] = accepted["stale_reason"]
    return item


def _scope_acceptances(root: str) -> dict:
    """Intent:
        The scope-level acceptances on file, keyed by scope; empty
        when none are recorded or the file cannot be read.
    """
    import os

    import yaml
    path = _scope_intent_path(root)
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as fh:
            return yaml.safe_load(fh) or {}
    except Exception:
        return {}


def pending_intents(root: str = ".") -> list:
    """Intent:
        Every stated intent in the project that waits on a person's
        acceptance, top down: the codebase README (`__project__`), then
        each package, then each module, then each function with a
        record whose source is in the project (a library function's
        record is not the project's to document). The packages and
        modules are the ones that hold such a function, and any
        already accepted. Each item
        says its key, level, status (`new` or `stale`), text and where
        the text is written; a function also gives its signature and
        raised exceptions, and a stale item says what changed. Reading
        only: nothing is written.
    """
    import importlib
    import inspect
    import os

    from .conjecture import _resolve_func_ref
    from .docstring import _read_module_intent
    from .spec import load_verified

    root_abs = os.path.abspath(root)
    items: list = []
    scopes: set = set()
    for key, wrap in sorted(load_verified(root).items()):
        entry = (wrap or {}).get("entry") or {}
        fn = None if ":" in key else _resolve_func_ref(key, root=root)
        if ":" not in key:
            # a dotted key counts when it names a function whose source
            # is in the project: a library function (a compendium
            # record, a builtin) is not the project's to document, and
            # a key that no longer resolves is a moved record; a
            # function another frontend read, whose record the project
            # keeps, counts, its Python file being a wrapper's
            from .analysis import foreign_body
            foreign = fn is not None and foreign_body(fn)
            try:
                src = (inspect.getsourcefile(fn)
                       if fn is not None and not foreign else None)
            except TypeError:
                src = None
            if not foreign and not _in_project(root_abs, src):
                continue
            parts = (getattr(fn, "__module__", "") or "").split(".")
            scopes.update(".".join(parts[:i])
                          for i in range(1, len(parts) + 1) if parts[0])
        item = _function_item(key, entry, fn)
        if item is not None:
            items.append(item)
    on_file = _scope_acceptances(root)
    scopes.update(k for k in on_file if k != "__project__")
    for key in sorted(scopes):
        try:
            module = importlib.import_module(key)
        except Exception:
            continue
        if not _in_project(root_abs, getattr(module, "__file__", None)):
            continue
        is_package = hasattr(module, "__path__")
        if (not is_package and key not in on_file
                and _read_module_intent(module) is None):
            # a module with no docstring of its own reads its intent
            # from the README beside it, which is its package's
            continue
        item = _scope_item(root, key, "package" if is_package else "module")
        if item is not None:
            items.append(item)
    project = _scope_item(root, "__project__", "codebase")
    if project is not None:
        items.append(project)
    items.sort(key=lambda i: (_LEVEL_ORDER[i["level"]],
                              i["key"].count(".") if i["level"] == "package"
                              else 0, i["key"]))
    return items


def reread_intent(root: str, item: dict) -> "dict | None":
    """Intent:
        The same intent read again after its source was edited: the
        module (or the function's module) is reloaded from source and
        the item rebuilt. For a function, whose acceptance binds to its
        record, the item carries `live_text` when the docstring now
        says something the record does not yet hold. None when the
        intent is no longer stated, or is now accepted and current.
    """
    import importlib
    import importlib.util
    import os
    import sys

    from .conjecture import _resolve_func_ref
    from .spec import load_verified

    def reload(name: str) -> None:
        module = sys.modules.get(name)
        src = getattr(module, "__file__", None)
        if module is None or not src:
            return
        try:
            os.remove(importlib.util.cache_from_source(src))
        except (OSError, ValueError, NotImplementedError):
            pass
        importlib.invalidate_caches()
        importlib.reload(module)

    if item["level"] != "function":
        if item["key"] != "__project__":
            reload(item["key"])
        return _scope_item(root, item["key"], item["level"])
    fn = _resolve_func_ref(item["key"], root=root)
    if fn is not None:
        reload(fn.__module__)
        fn = _resolve_func_ref(item["key"], root=root)
    wrap = load_verified(root).get(item["key"]) or {}
    fresh = _function_item(item["key"], wrap.get("entry") or {}, fn)
    if fresh is None or fn is None:
        return fresh
    from .analysis import _intent_block_text
    from .analysis import docstring_of
    from .intent import parse_doc
    doc = docstring_of(fn)
    live = (_intent_block_text(doc) or parse_doc(doc).summary or "").strip()
    if live and live != fresh["text"]:
        fresh["live_text"] = live
    return fresh
