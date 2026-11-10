# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Verdict transitions: a claim's verdict is what its latest
adjudication found, and the move from the verdict before it is a
transition recorded beside it, kept until a person acknowledges it
(`mathema accept KEY CLAIM --transition`) or a later run brings the
claim back to the level it fell from.

Kinds, by the verdicts' strength (proven > holds > unknown, skipped >
falsified):

- `regressed`: proven or holds to falsified.
- `weakened`: proven to holds, or proven or holds to unknown or skipped.
- `strengthened`: to a stronger verdict, except falsified to unknown or
  skipped, which is no transition.
- `fixed`: falsified to proven or holds when the function changed.

A claim never supported that becomes falsified is a finding, not a
transition. Each transition names its cause: `this function changed`,
`a callee changed`, or `nothing changed`, a regression with nothing
changed being a contradiction between two runs (engine, library
version, seed or timeout).

`invalidated` names a function, not a claim: a function is invalidated
when it changed since its record, by the triggers in
`OWN_TRIGGERS` or along its dependency chain (`dependency`).
"""
from __future__ import annotations

import os

from .records import classify_verdict

KINDS = ("regressed", "weakened", "strengthened", "fixed")

#: the strength order transitions are read in
_RANK = {"proven": 3, "holds": 2, "unknown": 1, "skipped": 1, "falsified": 0}

#: what changing in the function itself makes it invalidated
OWN_TRIGGERS = ("form", "provenance", "defaults", "claims", "pseudo-infinity",
                "library-version", "definition-rows", "premises")

#: what the gate does with an unacknowledged transition of each kind,
#: in strict and in lenient mode, unless the project's policy says
#: otherwise (`.mathema/meta/policy.yaml`, `transitions:`)
DEFAULT_ACTIONS = {
    "regressed": {"strict": "fail", "lenient": "fail"},
    "weakened": {"strict": "fail", "lenient": "warn"},
    "strengthened": {"strict": "pass", "lenient": "pass"},
    "fixed": {"strict": "pass", "lenient": "pass"},
}

ACTIONS = ("fail", "warn", "pass")


def kind_of(before: str, after: str, *, function_changed: bool) -> "str | None":
    """The kind of the move from verdict `before` to `after`, or None
    when there is no transition (the same strength, a verdict outside
    the strength order, or a never-supported claim found falsified)."""
    a, b = classify_verdict(before or ""), classify_verdict(after or "")
    if a not in _RANK or b not in _RANK or _RANK[a] == _RANK[b]:
        return None
    if b == "falsified":
        return "regressed" if _RANK[a] >= 2 else None
    if a == "falsified":
        if _RANK[b] < 2:
            return None
        return "fixed" if function_changed else "strengthened"
    return "weakened" if _RANK[b] < _RANK[a] else "strengthened"


def cause_of(triggers) -> str:
    """The cause of a move, from the triggers that made the function
    re-adjudicate."""
    triggers = list(triggers or [])
    if any(t in OWN_TRIGGERS for t in triggers):
        return "this function changed"
    if "dependency" in triggers:
        return "a callee changed"
    return "nothing changed"


def transition(before: str, after: str, triggers, *, commit: "str | None",
               at: str) -> "dict | None":
    """The transition record for a move, or None when there is none."""
    cause = cause_of(triggers)
    kind = kind_of(before, after, function_changed=cause == "this function changed")
    if kind is None:
        return None
    out = {"from": before, "to": after, "kind": kind, "cause": cause, "at": at}
    if commit:
        out["commit"] = commit
    return out


def open_transitions(meta: dict) -> list[dict]:
    """The transitions on a claim still waiting on a person: neither
    acknowledged nor recovered."""
    return [t for t in (meta or {}).get("mathema.transitions") or []
            if isinstance(t, dict) and not t.get("acknowledged")
            and not t.get("recovered")]


def drop_move(transitions: list, frm: str, to: str, *, at: str) -> list[dict]:
    """The transitions without the latest open move from `frm` to `to`
    recorded at `at`: what a run takes back when it settles the claim
    again before anyone has read the move."""
    out = [dict(t) for t in transitions or [] if isinstance(t, dict)]
    for i in range(len(out) - 1, -1, -1):
        t = out[i]
        if (t.get("from") == frm and t.get("to") == to and t.get("at") == at
                and not t.get("acknowledged") and not t.get("recovered")):
            del out[i]
            break
    return out


def carry(prior: list, new: "dict | None", verdict: str, *,
          commit: "str | None", at: str) -> list[dict]:
    """The transitions a claim carries after a run: the open ones from
    before, each marked recovered when the claim is back at or above
    the level it fell from, then the new one, unless it is the move
    that recovered them. Acknowledged and
    recovered transitions are dropped from the record at the next run
    after they closed."""
    out: list[dict] = []
    now = _RANK.get(classify_verdict(verdict or ""), -1)
    recovered = False
    for t in prior or []:
        if not isinstance(t, dict) or t.get("acknowledged") or t.get("recovered"):
            continue
        t = dict(t)
        if t.get("kind") in ("regressed", "weakened") \
                and now >= _RANK.get(classify_verdict(t.get("from") or ""), 99):
            t["recovered"] = {"at": at, **({"commit": commit} if commit else {})}
            recovered = True
        out.append(t)
    if new is not None and not (recovered and new.get("kind") in ("strengthened", "fixed")):
        out.append(new)
    return out


def read_invalidated_verdict(verdict: str, meta: dict) -> "tuple[str, dict]":
    """A claim as a record written before 0.6.5 stored it with the
    verdict `invalidated`: read as the verdict it regressed to, with
    the regression as an open transition of unknown cause. Any other
    claim is returned unchanged."""
    if classify_verdict(verdict or "") != "invalidated":
        return verdict, meta
    meta = dict(meta or {})
    fell_to = meta.pop("mathema.regressed_to", None) or "unknown"
    if classify_verdict(fell_to) == "invalidated":
        fell_to = "unknown"
    fell_from = meta.get("mathema.previous_verdict") or "proven"
    if classify_verdict(fell_from) == "invalidated":
        fell_from = "proven"
    if not open_transitions(meta):
        kind = kind_of(fell_from, fell_to, function_changed=False) or "weakened"
        t = {"from": fell_from, "to": fell_to, "kind": kind,
             "cause": "recorded before 0.6.5"}
        commit = meta.get("mathema.last_supported_commit")
        if commit:
            t["since"] = commit
        meta["mathema.transitions"] = [*(meta.get("mathema.transitions") or []), t]
    return fell_to, meta


def load_actions(root: str = ".") -> dict:
    """The gate's action per transition kind and mode: `DEFAULT_ACTIONS`
    with the project's `transitions:` section of
    `.mathema/meta/policy.yaml` over it. A kind maps to one action for
    both modes or to one per mode:

        transitions:
          weakened: fail
          regressed: {strict: fail, lenient: warn}

    An action is `fail`, `warn` or `pass`; anything else is refused."""
    import yaml
    actions = {k: dict(v) for k, v in DEFAULT_ACTIONS.items()}
    path = os.path.join(root, ".mathema", "meta", "policy.yaml")
    try:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except OSError:
        return actions
    section = data.get("transitions") if isinstance(data, dict) else None
    for kind, value in (section or {}).items():
        if kind not in actions:
            raise ValueError(f"policy.yaml transitions: {kind!r} is not a "
                             f"transition kind ({', '.join(KINDS)})")
        per_mode = value if isinstance(value, dict) else {"strict": value, "lenient": value}
        for mode, action in per_mode.items():
            if mode not in ("strict", "lenient") or action not in ACTIONS:
                raise ValueError(f"policy.yaml transitions.{kind}: {mode}: {action!r} "
                                 f"(a mode is strict or lenient, an action "
                                 f"{', '.join(ACTIONS)})")
            actions[kind][mode] = action
    return actions


def describe(t: dict) -> str:
    """One line for a transition: `weakened proven to unknown (a callee
    changed)`, a regression with nothing changed said as the
    contradiction it is."""
    text = f"{t.get('kind')} {t.get('from')} to {t.get('to')} ({t.get('cause')})"
    if t.get("kind") == "regressed" and t.get("cause") == "nothing changed":
        text += ("; nothing changed, so two runs disagree: the engine, a "
                 "library version, the seed or a timeout differs")
    return text
