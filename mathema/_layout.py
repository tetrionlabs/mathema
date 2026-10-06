# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim and the lines under it, as a record prints them.

A claim with lines under it prints as a block. Its first line is the
claim's name, its statement and its overall verdict: falsified, with the
witness, when any line is falsified, otherwise the verdict of its
mathematics. One line follows per aspect of what is known about it:

- `mathematics`: the claim over the numbers of its domain, as derive
  decided it; a verdict reached by running the code is a computation
  line instead;
- `computation`: the claim run in the number representation (`[float]`);
- `policy`: what f does at each value that is not a number, as the call
  `f(nan)`, `f(None)` or `f([])`.

Each line starts with its verdict word (proven, holds, falsified,
unknown); a claim mathema could not run reads unknown, with the reason. A falsified absence or missing line is followed by
its possible fixes.
"""
from __future__ import annotations

import re

#: what a `[float]` companion's family is called
_COMPUTATION = "is_numerically_stable"
_EMPTY = "is_empty_safe"

#: how strong each verdict a line can carry is, weakest first
_STRENGTH = {"skipped": 0, "unknown": 1, "holds": 2, "proven": 3}

_ADMISSIONS = re.compile(r"(?:\|(?:absent|missing|None|null|nan|NA|NaT|unset))+")
_WRITTEN = re.compile(r" \| \{(?:missing|absent|None|null|nan|NA|NaT|unset|∅)"
                      r"(?:, (?:missing|absent|None|null|nan|NA|NaT|unset|∅))*\}")
#: the clause a note gives a pass within the tolerance, with its gap
_WITHIN = re.compile(r"within the (?:default tolerance|tolerance \(|round-off)")
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


def _ran(route) -> bool:
    """Whether a verdict was reached by running the code (a probe route)
    rather than decided by derive."""
    return str(route or "").startswith("probe")


def _shown(statement: str, aspect: str) -> str:
    """The claim as the line of `aspect` restates it."""
    return over_the_reals(statement) if aspect == "mathematics" \
        else over_numbers(statement)


def _verdict(p) -> str:
    return (p.verdict or "").split(":", 1)[0]


def _admits(main, param: str, kind: str) -> bool:
    admitted = (((main.meta or {}).get("mathema.missing") or {})
                .get("admitted") or {}).get(param) or {}
    return bool(admitted.get(kind))


def _hole_word(main, param: str) -> str:
    """The hole a member-less missing row is about: the parameter's one
    admitted member (`nan` for a float), else the class, `missing`."""
    admitted = (((main.meta or {}).get("mathema.missing") or {})
                .get("admitted") or {}).get(param) or {}
    members = admitted.get("missing")
    if isinstance(members, (list, tuple)) and len(members) == 1:
        return str(members[0])
    return "missing"


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
    if _verdict(p) == "falsified" and p.counterexample:
        # what f did, beside the word it broke
        said = f"{_did(p.counterexample)}, where the word is {behaviour}"
        return f"{said} ({source})" if source else said
    return f"{behaviour}, {source}" if source else behaviour


#: the policy a row's next step says to state, as the record words it
_CORRECTED = re.compile(r'--corrected "([^"]+)"')


def _intended(stated: str, word: str) -> str:
    """What f does, as the condition of the command that states it: `the
    raise`, `dropping nan`, `giving nan back`, else `that`."""
    if " raises" in stated:
        return "the raise"
    if stated.endswith(" drops"):
        return f"dropping {word}"
    if stated.endswith(" propagates"):
        return f"giving {word} back"
    return "that"


def _fixes(p, key: str, word: str) -> str:
    """The possible fixes under a falsified absence or missing line: the
    command that records what f does as a stated policy, when the row
    names one policy to state, then excluding the value, then handling
    it at entry."""
    pol = (p.meta or {}).get("mathema.policy") or {}
    # a row with no single policy needs one claim per case, not one command
    mixed = (pol.get("sentence") or "").startswith("f has no single policy")
    from ._missing_words import remedy_statements
    corrected = _CORRECTED.findall(pol.get("next") or "")
    stated_all = set(corrected) or set(remedy_statements(pol.get("next") or ""))
    # a row whose next step states one claim per member or case has no
    # single command that settles it
    found = None if mixed or len(stated_all) != 1 else stated_all.pop()
    fixes = []
    if found:
        # the condition first, the command last, after a colon
        fixes.append(f"if {_intended(found, word)} is intended, run: mathema accept "
                     f"{key} {p.name} --as discovery --corrected \"{found}\"")
    fixes += [f"exclude {word}", f"handle {word} at entry"]
    # each fix on its own line, the command last on its line
    from ._missing_words import options
    return "possible fixes:\n" + "\n".join(f"  {line}" for line in
                                             options(fixes).splitlines())


def _split_lines(p, key: str) -> list:
    """The split a claim falsified only below some length is offered as:
    what the witnesses share, and the command that writes the claim
    narrowed to the longer inputs and the region f has a value on."""
    from ._split import split_command
    offer = (p.meta or {}).get("mathema.split")
    if not offer:
        return []
    param, at = offer["param"], offer["at"]
    written = (p.meta or {}).get("mathema.split_statement") or p.statement
    return [" " * 28 + f"every witness has len({param}) < {at}; the claim "
                       f"holds for len({param}) >= {at}, where f is defined",
            " " * 28 + "possible fixes: (i) to split at the shared cause, "
                       "run: " + split_command(key, written, offer)]


def _row(verdict: str, aspect: str, what: str, detail: str = "") -> str:
    verdict = "unknown" if verdict == "skipped" else verdict
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
            # mathematics over non-empty inputs is printed as it was found
            found = meta.get("mathema.mathematics") or {}
            verdict = (found.get("verdict") or "unknown").split(":", 1)[0]
            detail = ""
            if verdict == "holds" and found.get("n"):
                detail = count_words(found["n"], meta.get("mathema.drawn"))
            elif verdict in ("unknown", "skipped") and found.get("note"):
                detail = found["note"]
            # a verdict reached by running the code is the computation's
            aspect = "computation" if _ran(found.get("route")) else "mathematics"
            lines.append(_row(verdict, aspect, _shown(main.statement, aspect), detail))
        else:
            aspect = "computation" if _ran(main.route) else "mathematics"
            lines.append(_row(_verdict(main), aspect, _shown(main.statement, aspect),
                              _detail(main, count_words)))
            if _verdict(main) == "falsified":
                falsified.append(main.counterexample)
                lines += _split_lines(main, key)
        lines += _extras(main)
        for c in under:
            fam = (c.meta or {}).get("mathema.family")
            if fam == _EMPTY:
                param = c.name.split("[", 1)[-1].rstrip("]")
                what = _call(params, {param: "sequence"} | kinds, param, "[]")
                lines.append(_row(_verdict(c), "policy", what,
                                  c.note if _verdict(c) != "holds" else ""))
                if _verdict(c) == "falsified" and \
                        (c.meta or {}).get("mathema.empty_fixes"):
                    lines += [" " * 28 + part
                              for part in c.meta["mathema.empty_fixes"].splitlines()]
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
            word = "None" if kind == "absent" else (
                pol.get("member") or _hole_word(main, param))
            what = _call(params, kinds, param, word)
            if pol.get("premise"):
                # a row about one case of the parameter names its case
                what += f" assuming {pol['premise']}"
            lines.append(_row(_verdict(r), "policy", what, _policy_detail(r)))
            if _verdict(r) == "falsified":
                falsified.append(r.counterexample)
                lines += [" " * 28 + part for part in _fixes(r, key, word).splitlines()]
            used.add(id(r))
        if falsified:
            head = "falsified" + (f" at {falsified[0]}" if falsified[0] else "")
            head = head.split(": ", 1)[0] if ": " in head else head
        else:
            # the weakest line: proven only when every line is proven
            head = min((ln.split()[0] for ln in lines if ln.split()
                        and ln.split()[0] in _STRENGTH),
                       key=_STRENGTH.__getitem__, default=_verdict(main))
            head = "unknown" if head == "skipped" else head
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
        # a pass within the tolerance always prints its gap
        gaps = [c for c in (p.note or "").split("; ") if _WITHIN.search(c)]
        return "; ".join([count_words(p.n, (p.meta or {}).get("mathema.drawn")),
                          *gaps])
    if verdict == "falsified" and p.counterexample:
        return f"counterexample {p.counterexample}"
    if verdict in ("unknown", "skipped") and p.note:
        return p.note
    return ""
