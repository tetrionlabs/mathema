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
import contextvars
import random
import re

#: the claims of the check in progress, outermost first, whose literal
#: calls at the empty input state the empty policy of the value claims
#: checked beside them (a chained claim checks its links in a nested
#: check that reads them too)
STATED: "contextvars.ContextVar[tuple]" = contextvars.ContextVar(
    "mathema_empty_policies", default=())

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
        and executed: `[(call text, arguments by parameter, the
        exception raised or None, the value returned or None)]`. A call whose arguments cannot
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
            result = None
            try:
                result = fn(*args, **kwargs)
                raised = None
            except Exception as e:
                raised = e
            out.append((ast.unparse(n), dict(bound.arguments), raised,
                        result))
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


def _passed_names(srcs) -> set:
    """Intent:
        The names the claim's `f(...)` calls pass in their arguments:
        `f(x[1:], 1.0)` passes `x`, `f([1.0])` passes none.
    """
    names: set = set()
    for src in srcs:
        try:
            tree = ast.parse(src or "0", mode="eval")
        except SyntaxError:
            continue
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) \
                    and n.func.id == "f":
                for arg in [*n.args, *(k.value for k in n.keywords)]:
                    names |= {m.id for m in ast.walk(arg)
                              if isinstance(m, ast.Name)}
    return names


def _reads_length(name: str, assumption) -> bool:
    pattern = re.compile(rf"\b{re.escape(name)}\b")
    return any(pattern.search(f"{lhs} {rhs}")
               for lhs, _rel, rhs in assumption or ())


def _no_value(value) -> bool:
    """Whether a returned value is no value: None, or a nan (a float
    nan, pandas' NA)."""
    from .domain import is_missing
    if value is None:
        return True
    try:
        return bool(is_missing(value))
    except Exception:
        return False


def _empty_call_args(node: ast.Call, sig) -> "dict | None":
    """The arguments a literal call binds, by parameter, each as source
    text; None when it does not bind."""
    try:
        bound = sig.bind(*[ast.unparse(a) for a in node.args],
                         **{k.arg: ast.unparse(k.value) for k in node.keywords
                            if k.arg is not None})
    except TypeError:
        return None
    return dict(bound.arguments)


def stated_policies(fn, siblings, target: str) -> list:
    """Intent:
        The claims beside a value claim that state what f does with an
        empty `target`: a literal call with `[]` there, `f([]) in
        {missing}`, `raises(f([]), E)`, `f([]) == v`, as
        `[(kind, operand, text)]` with kind "missing", "raises" or
        "value"; f may be spelled by its own name.
    """
    from ._signatures import callable_signature
    try:
        sig = callable_signature(fn)
    except (TypeError, ValueError):
        return []
    names = {"f", getattr(fn, "__name__", "f")}
    out = []
    for cj in siblings or ():
        try:
            node = ast.parse(cj.lhs or "", mode="eval").body
        except SyntaxError:
            continue
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in names):
            continue
        args = _empty_call_args(node, sig)
        if not args or args.get(target) != "[]":
            continue
        rhs = (cj.rhs or "").strip()
        text = f"{cj.lhs} {cj.relation} {cj.rhs}"
        if cj.relation == "in" and re.search(r"\b(missing|None|null|nan|NA)\b",
                                             rhs):
            out.append(("missing", rhs, text))
        elif cj.relation == "raises" and rhs:
            out.append(("raises", rhs, f"raises({cj.lhs}, {rhs})"))
        elif cj.relation in ("==", "~="):
            out.append(("value", rhs, text))
    return out


def _matches(policy, raised, result) -> bool:
    """Whether what f did at the empty input is what `policy` states."""
    kind, operand, _text = policy
    if kind == "raises":
        return raised is not None and any(
            cls.__name__ == operand.split(".")[-1]
            for cls in type(raised).__mro__)
    if raised is not None:
        return False
    if kind == "missing":
        return _no_value(result)
    try:
        expected = float(ast.literal_eval(operand))
        return float(result) == expected
    except (ValueError, SyntaxError, TypeError):
        return False


def _fixes(fn_name: str, call_text: str, target: str, raised,
           result) -> str:
    """The possible fixes of a falsified empty-input line: state what f
    does as its empty policy, the condition first and the claim last,
    or guard the empty input at entry."""
    called = re.sub(r"^f\(", f"{fn_name}(", call_text)
    called = re.sub(rf"(?<![\w.]){re.escape(target)}(?![\w.])", "[]",
                    called, count=1)
    if raised is not None:
        first = (f"if the {type(raised).__name__} is the intended refusal, "
                 f"state: raises({called}, {type(raised).__name__})")
    else:
        word = "None" if result is None else "nan"
        first = (f"if {word} for no data is intended, state: "
                 f"{called} in {{missing}}")
    return (f"possible fixes: (i) {first}  (ii) guard the empty input "
            f"at entry")


def empty_input_lines(cj, fn, facts, cj_domain: dict, assumption,
                      siblings=()) -> list:
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
    passed = _passed_names(srcs)
    open_seqs = []
    realised = realised_parameters(facts)
    empty: dict = {}
    for p in seqs:
        if p not in passed:
            # no call passes this parameter an open value (only
            # literals): the claim never asks f about its empty list
            continue
        dims = dims_of((cj_domain or {}).get(p)) or dims_of(shapes.get(p))
        # a matrix parameter's runtime type receives the 0x0 matrix
        empty[p] = AbstractMat(()) if len(dims) == 2 and p in realised else []
        if dims and fixed_size(dims[0]) is not None:
            continue
        # the premises over this sequence or its length's name (`n` in
        # `xs in R^n`), read at the empty list
        at_empty: dict = {p: []}
        names = [p]
        if dims and isinstance(dims[0], str) and dims[0].isidentifier():
            at_empty[dims[0]] = 0
            names.append(dims[0])
        reading = [a for a in assumption or ()
                   if any(_reads_length(name, [a]) for name in names)]
        if reading and _premises_hold(reading, at_empty) is not None:
            # the claim's own premises settle the empty list: they name
            # it (`assuming len(x) == 0`), and the claim covers it, or
            # they exclude it (`assuming len(x) >= 2`), and the claim
            # says nothing about it; either way no line is owed
            continue
        open_seqs.append(p)
    if not open_seqs:
        return []
    ties = _length_ties(seqs, cj_domain, assumption, shapes)
    guarded = _emptiness_guard_params(facts)
    # an enforce_dimensions or enforce_domain wrapper refuses a shape or
    # a value outside the declared one, an empty input among them
    enforced = set(getattr(fn, "__mathema_enforced_dimensions__", None)
                   or ()) | set(getattr(fn, "__mathema_enforced_domain__",
                                        None) or ())
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
        policies = stated_policies(fn, siblings, target)
        fn_name = getattr(fn, "__name__", "f")
        verdict, note, witness = "holds", "", None
        for text, args, raised, result in made:
            at = ", ".join(f"{p} = {_shown(from_law(v))!r}"
                           for p, v in args.items())
            did = (f"raises {type(raised).__name__}" if raised is not None
                   else f"returns {from_law(result)!r}")
            if policies:
                broken = [pol for pol in policies
                          if not _matches(pol, raised, result)]
                if broken:
                    verdict, witness = "falsified", (text, at, raised, result)
                    note = (f"{text} {did} at {at}, where the stated policy "
                            f"is {broken[0][2]}")
                    break
                note = f"{target} = []: {text} {did}, as {policies[0][2]} states"
                continue
            if raised is not None:
                if target in guarded or target in enforced:
                    note = (f"{target} = []: {text} {did} behind an explicit "
                            f"emptiness guard, a deliberate refusal")
                    continue
                verdict, witness = "falsified", (text, at, raised, result)
                note = (f"{text} {did} at {at} with no emptiness guard in "
                        f"the body: the empty input is stumbled into, not "
                        f"handled")
                break
            if _no_value(result):
                verdict, witness = "falsified", (text, at, raised, result)
                note = (f"{text} {did} at {at}: no value for no data, and "
                        f"no empty policy is stated")
                break
            note = f"{target} = []: {text} {did}"
        if verdict == "holds":
            lines.append(Probe(
                name, statement, "holds", route="probe:algorithmic",
                n=len(made), meta=meta, note=note))
            continue
        text, at, raised, result = witness
        lines.append(Probe(
            name, statement, "falsified", route="probe:algorithmic",
            n=len(made), counterexample=at,
            meta={**meta, "mathema.empty_fixes": _fixes(
                fn_name, text, target, raised, result)},
            note=note))
    return lines
