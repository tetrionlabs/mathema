# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The empty-input line of a value claim.

A value claim over sequences is a statement about non-empty inputs: an
unbound list and one bound over a dimension (`x in R^n`, n >= 1) start
at length one. What the function does with the empty list is a separate
question, `is_empty_safe[x]`, answered under the claim: the claim's own
calls to f are evaluated as the claim evaluates them, with `x` (and
every sequence the claim ties to its length) empty, and f executed
there.

- f returns a value, or raises behind an explicit emptiness guard (`if
  not x: raise ...`, a deliberate refusal): the line holds.
- f raises with no such guard: the line is falsified, with the
  arguments of the call that raised as its witness, and the claim is
  falsified with it.
- no call to f could be evaluated there: the line is unknown.

A library function's row (a compendium key) has no such line: its body
is not read, so a raise at the empty list is not judged here.

A claim whose binding fixes the length (`x in R^3`), or whose premises
name the empty list (`assuming len(x) == 0`), has no such line: the
claim itself says what it covers there. A premise that excludes it
(`assuming len(x) >= 1`) restates the claim's domain and leaves the
line in place.
"""
from __future__ import annotations

import ast
import random
import re

#: the claim families whose statement is a comparison of f with itself
#: or an accuracy check, which ask nothing about the empty input
_NOT_VALUE_CLAIMS = frozenset({"is_deterministic", "is_reproducible",
                               "is_state_safe", "is_numerically_stable"})

_COMPARISONS = frozenset({"==", "~=", "!=", "<=", ">=", "<", ">"})


def claim_calls(fn, srcs, point: dict, bound_funcs: "dict | None" = None,
                pins: "dict | None" = None) -> list:
    """Intent:
        Every `f(...)` call in the claim text, evaluated at `point` the
        way the claim evaluates (its math functions, keywords, slices)
        and executed: `[(call text, arguments by parameter, the name of
        the exception raised or None)]`. A call whose arguments cannot
        be evaluated, or that does not bind to f's signature, is left
        out; the other calls are still made. `bound_funcs` are the
        claim's own bound functions (`let g = math.fabs`), and `pins`
        the pinned parameters (`let alpha be 2`) a call is made with
        when it leaves them out.
    """
    from ._linalg_eval import FUNCTIONS as vector_funcs
    from ._math_vocab import MATH_CONSTANTS
    from ._signatures import callable_signature
    from .conjecture import _SAFE_FUNCS
    env = {"__builtins__": {}, **_SAFE_FUNCS, **vector_funcs,
           **MATH_CONSTANTS, **(bound_funcs or {}), **point}
    try:
        sig = callable_signature(fn)
    except (TypeError, ValueError):
        return []

    def value(node):
        return eval(compile(ast.Expression(body=node), "<claim>", "eval"),
                    env)
    out = []
    for src in srcs:
        try:
            tree = ast.parse(src or "0", mode="eval")
        except SyntaxError:
            continue
        for n in ast.walk(tree):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                    and n.func.id == "f"):
                continue
            try:
                args = [value(a) for a in n.args]
                kwargs = {k.arg: value(k.value) for k in n.keywords}
                given = sig.bind_partial(*args, **kwargs).arguments
                kwargs.update({p: v for p, v in (pins or {}).items()
                               if p not in given and p in sig.parameters})
                bound = sig.bind(*args, **kwargs)
            except Exception:
                continue
            try:
                fn(*args, **kwargs)
                raised = None
            except Exception as e:
                raised = type(e).__name__
            out.append((ast.unparse(n), dict(bound.arguments), raised))
    return out


def _shown(value):
    """`value` as a witness prints it: a matrix with no rows as `[]`."""
    rows = getattr(value, "rows", None)
    return [] if rows == () else value


def _calls_f(srcs) -> bool:
    for src in srcs:
        try:
            tree = ast.parse(src or "0", mode="eval")
        except SyntaxError:
            continue
        if any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
               and n.func.id == "f" for n in ast.walk(tree)):
            return True
    return False


def _reads_length(name: str, assumption) -> bool:
    pattern = re.compile(rf"\b{re.escape(name)}\b")
    return any(pattern.search(f"{lhs} {rhs}")
               for lhs, _rel, rhs in assumption or ())


def empty_input_lines(cj, fn, facts, cj_domain: dict, assumption) -> list:
    """Intent:
        The `is_empty_safe[x]` lines of a value claim, one per sequence
        parameter whose empty list the claim does not settle itself, as
        Probes tagged `mathema.companion_of` the claim; empty when the
        claim is not a value claim over a sequence.
    """
    from . import families
    from ._shapes import dims_of, fixed_size
    from .hazards import _emptiness_guard_params
    from .probing import _synth
    from .records import Probe
    from .runtime_types import SEQUENCE_KINDS, calling, realised_parameters
    from .runtime_types._abstract import AbstractMat
    from .symbolic._prove import _premises_hold
    from .symbolic._seq_common import _length_ties, signature_shapes
    if cj.relation not in _COMPARISONS or cj.negated or cj.links \
            or families.claim_base_name(cj.name) in _NOT_VALUE_CLAIMS:
        return []
    srcs = (cj.lhs, cj.rhs)
    if not _calls_f(srcs):
        return []
    from .compendium import library_key_of
    if library_key_of(fn) is not None:
        # a library row states what the library computes; its body is
        # not read, so a raise at the empty list is not judged here
        return []
    shapes = signature_shapes(fn)
    seqs = [p for p in facts.params
            if facts.param_kinds.get(p) in SEQUENCE_KINDS]
    open_seqs = []
    realised = realised_parameters(facts)
    empty: dict = {}
    for p in seqs:
        dims = dims_of((cj_domain or {}).get(p)) or dims_of(shapes.get(p))
        # a matrix parameter's runtime type receives the 0x0 matrix
        empty[p] = AbstractMat(()) if len(dims) == 2 and p in realised else []
        if dims and fixed_size(dims[0]) is not None:
            continue
        reading = [a for a in assumption or ()
                   if _reads_length(p, [a])]
        if reading and _premises_hold(reading, {p: []}) is True:
            # the claim's own premises name the empty list (`assuming
            # len(x) == 0`): the claim itself covers it
            continue
        open_seqs.append(p)
    if not open_seqs:
        return []
    ties = _length_ties(seqs, cj_domain, assumption, shapes)
    guarded = _emptiness_guard_params(facts)
    from ._linalg_eval import as_array, from_law, law_callable
    from .conjecture import _resolve_func_ref, call_defaults
    bound_funcs = {}
    for fname, ref in (cj.funcs or {}).items():
        resolved = ref if callable(ref) else _resolve_func_ref(ref)
        if resolved is not None:
            bound_funcs[fname] = resolved
    try:
        pins = call_defaults(fn, cj)[1]
    except Exception:
        pins = {}
    # the claim reads a sequence as an array (`-xs`, `2 * xs`) and f
    # receives it back as the plain list its runtime type realises
    call = law_callable(calling(fn, facts))
    rng = random.Random(0)
    lines = []
    for target in open_seqs:
        group = {p for p in seqs if ties[p] == ties[target]}
        point = None
        for _attempt in range(8):
            drawn: "dict | None" = {}
            for p in facts.params:
                if p in group:
                    drawn[p] = empty[p]
                    continue
                try:
                    drawn[p] = _synth(facts.param_kinds.get(p, "float"), rng,
                                      (cj_domain or {}).get(p))
                except Exception:
                    drawn = None
                    break
            if drawn is None:
                break
            others = [a for a in assumption or ()
                      if not any(_reads_length(g, [a]) for g in group)]
            if _premises_hold(others, drawn) is False:
                continue
            point = drawn
            break
        name, statement = f"is_empty_safe[{target}]", f"is_empty_safe({target})"
        meta = {"mathema.companion_of": cj.name,
                "mathema.family": "is_empty_safe"}
        law_point = None if point is None else {
            p: as_array(v) if p in seqs else v for p, v in point.items()}
        made = (claim_calls(call, srcs, law_point, bound_funcs, pins)
                if law_point is not None else [])
        if not made:
            lines.append(Probe(
                name, statement, "unknown", route="probe:algorithmic", meta=meta,
                note=f"{target} = []: no call to f in {cj.name} could be "
                     f"made there"))
            continue
        raised = [(text, args, exc) for text, args, exc in made if exc]
        if not raised:
            lines.append(Probe(
                name, statement, "holds", route="probe:algorithmic", n=len(made),
                meta=meta,
                note=f"{target} = []: {made[0][0]} returns a value"))
            continue
        text, args, exc = raised[0]
        at = ", ".join(f"{p} = {_shown(from_law(v))!r}" for p, v in args.items())
        if target in guarded:
            lines.append(Probe(
                name, statement, "holds", route="probe:algorithmic", n=len(made),
                meta=meta,
                note=f"{target} = []: {text} raises {exc} behind an "
                     f"explicit emptiness guard, a deliberate refusal"))
            continue
        lines.append(Probe(
            name, statement, "falsified", route="probe:algorithmic", n=len(made),
            counterexample=at, meta=meta,
            note=f"{text} raises {exc} at {at} with no emptiness guard in "
                 f"the body: the empty input is stumbled into, not "
                 f"handled"))
    return lines
