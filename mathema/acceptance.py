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
    from .spec import integrity_checksum, load_verified
    out = []
    for key, info in load_verified(root).items():
        entry = info.get("entry") or {}
        stored = (entry.get("identity") or {}).get("integrity")
        if stored and integrity_checksum(entry) != stored:
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
                          route: "str | None"):
    """Intent:
        Dry-run one candidate corrected claim against the live
        function: `(probe, None)` when it adjudicated, `(None,
        reason)` when it could not run (function unresolvable,
        statement rejected). Read-only; the plan stays a true preview.
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
        cj = _claim(statement, name="corrected_candidate", route=base_route)
        probes = check_conjectures(fn, [cj])
    except TimeoutError:
        raise
    except Exception as e:
        return None, f"the candidate did not adjudicate ({e})"
    if not probes:
        return None, "the candidate did not adjudicate"
    return probes[0], None


def _same_law_as(statement: str):
    """Intent:
        A canonical-law comparator over claim spellings: two texts
        match when they parse to the same fingerprint form, so the
        record's canonical rendering and an author's hand spelling of
        the same law compare equal. An unparseable side never matches.
    """
    from .spec import _declared_conjecture, fingerprint_text

    def canon(text: str):
        try:
            return fingerprint_text(_declared_conjecture({"statement": text}))
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
    same = _same_law_as(statement)
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
    with open(path, "w") as fh:
        yaml.safe_dump(data, fh, sort_keys=False, default_flow_style=False,
                       allow_unicode=True)


def _load_record(root: str, key: str):
    import yaml
    from .spec import verified_dir
    path = os.path.join(verified_dir(root), f"{key}.yaml")
    if not os.path.exists(path):
        raise AcceptanceError(f"no verified record for {key!r} at {path}, "
                              "run `mathema verify` (or `check`) first; "
                              "acceptance annotates adjudicated evidence")
    with open(path) as fh:
        doc = yaml.safe_load(fh) or {}
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
        raise AcceptanceError(f"{key} has no claim named {claim_name!r} "
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


def plan_acceptance(root: str, key: str, claim_name: str, as_: str,
                    by: str | None = None, note: str | None = None,
                    corrected: str | None = None) -> dict:
    """Intent:
        Resolve one acceptance request against the verified record and
        return everything the write WOULD do, the annotation, any
        verdict change, any generated discovery claim, without
        writing. The CLI prints this and asks; `apply_acceptance`
        executes it. Split so the prompt can never drift from the act.

    Raises:
        AcceptanceError: for every vocabulary violation, with the rule
        stated (notably: a falsified claim accepts only as a discovery;
        there is no accepting a bug, code changes until the claim
        stops falsifying).
    """
    if as_ not in ACCEPT_AS:
        raise AcceptanceError(f"--as must be one of {', '.join(ACCEPT_AS)}")
    path, doc = _load_record(root, key)
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
        raise AcceptanceError(f"{key} has no claim named {claim_name!r} "
                              f"(recorded claims: {names})")
    verdict = target.get("verdict") or ""
    base = classify_verdict(verdict)
    form = (entry.get("identity") or {}).get("form")

    plan = {"path": path, "doc": doc, "key": key, "claim": target,
            "root": root,
            "as": as_, "by": by, "note": note, "verdict": verdict,
            "actions": []}
    if as_ == "trusted":
        # external testimony (a compendium row) accepted at the
        # level its curator claims: the row's verdict becomes that
        # level, provenance meta marks it testimony, and premises
        # resting on it cap at that level, never higher
        meta = target.get("meta") or {}
        if meta.get("mathema.surface") != "compendium" or verdict != "declared":
            raise AcceptanceError(
                f"{claim_name} is {verdict!r}"
                + ("" if meta.get("mathema.surface") == "compendium"
                   else " and not compendium-sourced")
                + ": --as trusted applies to an unaccepted compendium "
                  "row (verdict 'declared'); anything else is either "
                  "already evidence or needs the ordinary flow")
        claimed = meta.get("mathema.compendium_claimed", "holds")
        plan["accepted"] = {"as": "trusted",
                            "at": datetime.date.today().isoformat(),
                            "level": claimed,
                            "source": meta.get("mathema.compendium", "")}
        if by:
            plan["accepted"]["by"] = by
        if note:
            plan["accepted"]["note"] = note
        plan["new_verdict"] = claimed
        plan["actions"].append(
            f"trust {claim_name} at its claimed level ({claimed}), on "
            f"the word of {meta.get('mathema.stub') or 'its compendium entry'}; "
            f"`mathema verify` re-adjudicating this key replaces the "
            f"testimony with a local verdict")
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
            f"new statement adjudicates on the next verify")
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
        accepted = {"as": "discovery", "at": datetime.date.today().isoformat(),
                    "form": form}
        if by:
            accepted["by"] = by
        if note:
            accepted["note"] = note
        plan["accepted"] = accepted
        # the discovery itself is always recordable, whatever the
        # claim's shape. A corrected claim exists only when it is
        # VERIFIED here and now: the author's --corrected statement, or
        # a mechanically sound inverse, each adjudicated against the
        # live function before anything may be written
        if corrected is not None:
            candidate, why_not, stated = corrected, None, True
        else:
            candidate, why_not = invert_conjecture(
                target.get("statement") or "", claim_name)
            stated = False
        c_verdict = c_n = None
        if candidate:
            probe, err = _adjudicate_candidate(root, key, candidate,
                                               target.get("route"))
            if probe is None:
                if stated:
                    raise AcceptanceError(
                        f"--corrected {candidate!r} cannot be adjudicated: "
                        f"{err}")
                candidate, why_not = None, err
            else:
                base_c = classify_verdict(probe.verdict)
                if base_c == "falsified":
                    if stated:
                        raise AcceptanceError(
                            f"--corrected {candidate!r} itself falsifies "
                            f"(counterexample: {probe.counterexample}); a "
                            "correction that is wrong too is never written")
                    candidate, why_not = None, (
                        "its mechanical inverse falsifies too "
                        f"(counterexample: {probe.counterexample})")
                elif not stated and base_c not in ("proven", "holds"):
                    candidate, why_not = None, (
                        f"its mechanical inverse adjudicates "
                        f"{probe.verdict!r}, not a holding verdict")
                else:
                    c_verdict = probe.verdict
                    c_n = getattr(probe, "n", None)
        plan["actions"].append(
            f"move {claim_name} to the record's discoveries section"
            + (f" (superseded_by: {claim_name}_corrected)" if candidate
               else "")
            + ", keeping its counterexample as the witness")
        if candidate:
            plan["corrected_statement"] = candidate
            plan["corrected_name"] = f"{claim_name}_corrected"
            plan["corrected_verdict"] = c_verdict
            if c_n:
                plan["corrected_n"] = c_n
            plan["actions"].append(
                f"declare the {'stated' if stated else 'inverted'} corrected "
                f"claim {plan['corrected_name']!r}: {candidate!r}, "
                f"adjudicated now: {c_verdict}"
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
        Execute a `plan_acceptance` result: mutate the record document
        and write it back, appending the acceptance-history event so
        every classification change stays tracked.
    """
    doc, key, target = plan["doc"], plan["key"], plan["claim"]
    entry = doc[key]
    # the human gate: when a PIN is configured, nothing below runs
    # without a person at a terminal, and the record says which
    # credential authorised it. Every acceptance path funnels through
    # an apply function, so gating here (not at the CLI prompts)
    # covers the JSON and scripted paths too.
    from . import auth
    attestation = auth.require_human(f"accept --as {plan['as']}")
    auth.enforce_policy(attestation, plan.get("root", "."))
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
                f"version adjudicates on the next verify")
    if plan["as"] == "historical":
        entry = doc[plan["key"]]
        claims = entry.get("claims") or []
        target["accepted"] = plan["accepted"]
        target.setdefault("acceptance_history", []).append(event)
        claims.remove(target)
        entry.setdefault("historical", []).append(target)
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
    if (plan.get("accepted") or {}).get("as") == "discovery":
        claims = entry.get("claims") or []
        claims.remove(target)
        if plan.get("corrected_name"):
            target["superseded_by"] = plan["corrected_name"]
        entry.setdefault("discoveries", []).append(target)
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
                        f"{target['name']!r} as a discovery; adjudicated "
                        "at acceptance",
                "meta": meta,
            }
            if plan.get("corrected_n"):
                new_claim["n"] = plan["corrected_n"]
            claims.append(new_claim)
        entry["claims"] = claims
    _restamp_integrity(entry)
    write_yaml(plan["path"], doc,
               header=f"machine record; binds to form "
                      f"{(entry.get('identity') or {}).get('form')}")
    if plan.get("declared_edits"):
        stub = corrected_stub(plan)
        for rel in plan["declared_edits"]:
            _apply_declared_edit(plan["root"], rel, plan["key"],
                                 target["name"], stub)
    return "; ".join(plan["actions"])


def corrected_stub(plan: dict) -> dict | None:
    """Intent:
        The declared-layer stanza for a discovery's corrected claim:
        its name, statement and route, the route reduced to the base
        spelling a claims file takes (`probe`, `derive` or `best`).
        None when the plan corrects no claim.
    """
    if not plan.get("corrected_statement"):
        return None
    route = (plan["claim"].get("route") or "best").split(":", 1)[0]
    return {"name": plan["corrected_name"],
            "statement": plan["corrected_statement"],
            "route": route if route in ("probe", "derive") else "best"}


def carry_acceptance(spec: dict, key: str, path: str) -> None:
    """Intent:
        At record-write time, carry each claim's acceptance state
        forward from the prior record onto the freshly adjudicated
        spec, adjudication rebuilds records from scratch, and a human
        decision must never be silently dropped by a re-run.

    Notes:
        Three rules ride along. A changed form marks the acceptance
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
    discovery_rows = [d for d in prior_entry.get("discoveries") or []
                      if d.get("name")]
    historical_names = {h.get("name")
                        for h in prior_entry.get("historical") or []
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
            matchers.append((d["name"], _same_law_as(stmt) if stmt else None))

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
        if accepted.get("form") != fresh_form and not accepted.get("stale"):
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
    with open(path, "w") as fh:
        fh.write("# scope-level intent acceptances (module / __project__)"
                 ", committed with the store\n")
        yaml.safe_dump(doc, fh, sort_keys=False, allow_unicode=True)
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
