# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim and the lines under it, as a record prints them.

A claim with lines under it prints as a block. Its first line is the
claim's name, its statement and its overall verdict: falsified, with the
witness, when any line is falsified, otherwise the verdict of its
mathematics. One line follows per aspect of what is known about it:

- `mathematics`: the claim over the numbers of its domain;
- `computation`: the claim run in the number representation (`[float]`);
- `policy`: what f does at each value that is not a number, as the call
  `f(nan)`, `f(None)` or `f([])`.

Each line starts with its verdict word (proven, holds, falsified,
unknown, skipped). A falsified absence or missing line is followed by
its possible fixes.
"""
from __future__ import annotations

import re

#: what a `[float]` companion's family is called
_COMPUTATION = "is_numerically_stable"
_EMPTY = "is_empty_safe"

_ADMISSIONS = re.compile(r"(?:\|(?:absent|missing|None|null|nan|NA|NaT|unset))+")
_WRITTEN = re.compile(r" \| \{(?:missing|absent|None|null|nan|NA|NaT|unset|∅)"
                      r"(?:, (?:missing|absent|None|null|nan|NA|NaT|unset|∅))*\}")
_REALS = {" : float": " ⊂ ℝ", " : int": " ⊂ ℤ", " : complex": " ⊂ ℂ"}


def over_numbers(statement: str) -> str:
    """A claim's statement over the numbers of its domain: every hole or
    absence its bindings admit left out."""
    return _ADMISSIONS.sub("", _WRITTEN.sub("", statement or ""))


def over_the_reals(statement: str) -> str:
    """`over_numbers`, with each number type written as its set."""
    text = over_numbers(statement)
    for typed, spelled in _REALS.items():
        text = re.sub(re.escape(typed) + r"\b", spelled, text)
    return text


def _verdict(p) -> str:
    return (p.verdict or "").split(":", 1)[0]


def _admits(main, param: str, kind: str) -> bool:
    admitted = (((main.meta or {}).get("mathema.missing") or {})
                .get("admitted") or {}).get(param) or {}
    return bool(admitted.get(kind))


def _call(params: list, kinds: dict, param: str, word: str) -> str:
    """`f(nan)`, `f(xs=[..., nan, ...])`: the call a policy line names."""
    from .runtime_types import SEQUENCE_KINDS
    value = word
    if kinds.get(param) in SEQUENCE_KINDS and word not in ("None", "[]"):
        value = f"[..., {word}, ...]"
    return f"f({value})" if len(params) == 1 else f"f({param}={value})"


def _did(counterexample: str) -> str:
    """`raises TypeError` from `x = None: f raised TypeError`."""
    said = (counterexample or "").split(": ", 1)[-1]
    said = re.sub(r"^f raised ", "raises ", said)
    return re.sub(r"^f returned ", "returns ", said)


def _policy_detail(p) -> str:
    pol = (p.meta or {}).get("mathema.policy") or {}
    if pol.get("sentence"):
        if pol.get("source") != "stated" and p.counterexample \
                and not pol["sentence"].startswith("f has no single policy"):
            return f"no {pol.get('kind')} policy stated; {_did(p.counterexample)}"
        return pol["sentence"]
    behaviour = pol.get("behaviour") or ""
    if pol.get("exception"):
        behaviour += f"({pol['exception']})"
    if pol.get("source") == "default":
        if _verdict(p) in ("holds", "proven"):
            return f"no {pol.get('kind')} policy stated; assumed {behaviour}"
        return f"no {pol.get('kind')} policy stated; {_did(p.counterexample)}"
    source = (pol.get("reason") or "").split("; ", 1)[0]
    return f"{behaviour}, {source}" if source else behaviour


def _fixes(p, key: str, word: str) -> str:
    return (f"possible fixes: (i) mathema claims {key} --adopt '{p.name}'  "
            f"(ii) exclude {word}  (iii) handle {word} at entry")


def _row(verdict: str, aspect: str, what: str, detail: str = "") -> str:
    line = f"    {verdict:<9}  {aspect:<11}  {what}"
    return f"{line}   {detail}" if detail else line


def blocks(probes: list, params: list, kinds: dict, key: str,
           count_words) -> dict:
    """Intent:
        `{id(main probe): [lines]}` for every claim with lines under it,
        and under the key `"used"` the ids of the probes those blocks
        print. A policy row is printed under every claim whose bindings
        admit its kind at its parameter; a stated policy row is a claim
        of its own and stays where it is.
    """
    companions: dict = {}
    for p in probes:
        parent = (p.meta or {}).get("mathema.companion_of")
        if parent:
            companions.setdefault(parent, []).append(p)
    policy = [p for p in probes
              if (p.meta or {}).get("mathema.policy")
              and ((p.meta or {}).get("mathema.policy") or {}).get("source") != "stated"]
    out: dict = {}
    used: set = set()
    for main in probes:
        meta = main.meta or {}
        if meta.get("mathema.companion_of") or meta.get("mathema.policy") \
                or meta.get("mathema.gate"):
            continue
        under = companions.get(main.name, [])
        rows = [r for r in policy
                if _admits(main, (r.meta["mathema.policy"].get("parameter") or ""),
                           r.meta["mathema.policy"].get("kind") or "")]
        if not under and not rows:
            continue
        lines = []
        falsified = []
        if meta.get("mathema.empty_input"):
            # the claim was falsified by its empty-input line; the
            # mathematics over non-empty inputs stands as it was found
            lines.append(_row("proven" if main.sketch else "holds", "mathematics",
                              over_the_reals(main.statement)))
        else:
            lines.append(_row(_verdict(main), "mathematics",
                              over_the_reals(main.statement), _detail(main, count_words)))
            if _verdict(main) == "falsified":
                falsified.append(main.counterexample)
        lines += _extras(main)
        for c in under:
            fam = (c.meta or {}).get("mathema.family")
            if fam == _EMPTY:
                param = c.name.split("[", 1)[-1].rstrip("]")
                what = _call(params, {param: "sequence"} | kinds, param, "[]")
                lines.append(_row(_verdict(c), "policy", what,
                                  c.note if _verdict(c) != "holds" else ""))
            else:
                shown = over_numbers(c.statement)
                if (c.condition or "").startswith("let |inf| be ") and "|inf|" not in shown:
                    # the pseudo-infinity that bounded the computation
                    shown = f"{c.condition.split(', ', 1)[0]}, {shown}"
                lines.append(_row(_verdict(c), "computation", shown,
                                  _detail(c, count_words)))
                lines += _extras(c)
            if _verdict(c) == "falsified":
                falsified.append(c.counterexample)
            used.add(id(c))
        for r in rows:
            pol = r.meta["mathema.policy"]
            param, kind = pol.get("parameter") or "", pol.get("kind") or ""
            word = "None" if kind == "absent" else (pol.get("member") or "nan")
            lines.append(_row(_verdict(r), "policy", _call(params, kinds, param, word),
                              _policy_detail(r)))
            if _verdict(r) == "falsified":
                falsified.append(r.counterexample)
                lines.append(" " * 28 + _fixes(r, key, word))
            used.add(id(r))
        if falsified:
            head = "falsified" + (f" at {falsified[0]}" if falsified[0] else "")
            head = head.split(": ", 1)[0] if ": " in head else head
        else:
            head = _verdict(main)
        out[id(main)] = [f"  {main.name}  {main.statement}   {head}", *lines]
    out["used"] = used
    return out


def _extras(p) -> list:
    """The warnings a claim's `let` bindings carry, and the stratum a
    falsification indicts, each on its own line under the claim's line."""
    out = [" " * 28 + f"warning: {said}"
           for said in (p.meta or {}).get("mathema.let_warning") or ()]
    stratum = getattr(p, "stratum", None) or {}
    parts = []
    if stratum.get("mathematics"):
        parts.append(f"mathematics {stratum['mathematics']}")
    if stratum.get("cause"):
        parts.append(stratum["cause"])
    elif stratum.get("blame"):
        parts.append(f"blame {stratum['blame']}")
    if parts:
        out.append(" " * 28 + f"[{', '.join(parts)}]")
    return out


def _detail(p, count_words) -> str:
    verdict = _verdict(p)
    if verdict == "holds" and p.n:
        return count_words(p.n, (p.meta or {}).get("mathema.drawn"))
    if verdict == "falsified" and p.counterexample:
        return f"counterexample {p.counterexample}"
    if verdict in ("unknown", "skipped") and p.note:
        return p.note
    return ""
