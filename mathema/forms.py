# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Other closed forms of arbitrary code: the public face of the
rewrite gallery and the substitution library.

`closed_forms(fn)` lifts a function's body to its symbolic closed form
and returns every structurally distinct equivalent the gallery can
produce (factored, expanded, trig-simplified, ...), each named by the
rewrite that made it. `substituted_forms(fn)` lists the known changes
of variable that apply to the body's shape, t = log(x) for a
logarithmic body, the Weierstrass half-angle for a trigonometric one,
with the transformed expression and the domain condition each one
needs. `register_substitution` extends that library: a registered
substitution is immediately available here and to the extensive proof
ladder, so a domain-specific change of variable contributed once can
start closing proofs.

These are the same registries `extensive=True` adjudication draws on,
exposed directly because an alternative form of one's own code is
useful beyond proving: reading it, simplifying it, or spotting that
two implementations share a closed form."""
from __future__ import annotations

from dataclasses import dataclass, field

import sympy

from .analysis import analyze_source
from .grammar import render_canonical
from .symbolic._base import lift
from .symbolic._forms import (
    Substitution, register_substitution as _register_substitution,
    rewrite_forms, substitutions as _substitutions,
)

__all__ = ["Form", "SubstitutedForm", "Substitution", "closed_forms",
           "executable_forms", "substituted_forms", "register_substitution"]

register_substitution = _register_substitution


@dataclass(frozen=True)
class Form:
    """One closed form of a function's body: `name` is the rewrite that
    produced it ("as written" for the lift itself), `expr` the sympy
    expression, `text` its canonical rendering."""
    name: str
    expr: object
    text: str


@dataclass(frozen=True)
class SubstitutedForm:
    """A function's body carried through one known change of variable:
    `name` is the substitution ("t = log(x)"), `param` the parameter it
    replaced, `expr`/`text` the transformed body in the new variable
    `var`, and `requires` the domain condition under which the
    substitution is a monotone bijection (and the transformed form
    therefore takes exactly the original's values)."""
    name: str
    param: str
    var: object
    expr: object
    text: str
    requires: str = field(default="always")


def _lifted_expr(fn, facts):
    """Intent:
        The scalar lifted body of `fn`, or a ValueError explaining why
        there is none.

    Raises:
        ValueError: when the function does not lift to a single scalar
        closed form (a loop, a branch the lift cannot resolve, a tuple
        return).
    """
    facts = facts or analyze_source(fn)
    lifted = lift(fn, facts)
    if lifted is None:
        from .inventory import unliftable_summary
        try:
            reason = unliftable_summary(fn)
        except Exception:
            reason = None
        raise ValueError(f"{fn.__name__} has no closed form to rewrite, "
                         + (reason or "the body is not derivable"))
    if isinstance(lifted.expr, tuple):
        raise ValueError(f"{fn.__name__} returns a tuple; closed forms are "
                         "only offered for a single scalar body")
    return lifted


def closed_forms(fn, facts=None) -> list[Form]:
    """Every structurally distinct closed form of `fn`'s body the
    rewrite gallery produces, the as-written lift first.

        >>> def parallel(a: float, b: float) -> float:
        ...     return 1.0 / (1.0 / a + 1.0 / b)
        >>> [f.name for f in closed_forms(parallel)]  # doctest: +SKIP
        ['as written', 'cancel', 'together', ...]

    Each `Form` carries the producing rewrite's name, the sympy
    expression, and its canonical text. Forms are deduplicated
    structurally, so two rewrites that land on the same expression
    yield one entry (the first name wins). Raises `ValueError`, with
    the blocking construct named, for a function that has no scalar
    closed form at all."""
    lifted = _lifted_expr(fn, facts)
    expr = lifted.expr
    forms = [Form("as written", expr, render_canonical(expr)[0])]
    seen = {sympy.srepr(expr)}
    for name, form_expr in rewrite_forms(expr):
        key = sympy.srepr(form_expr)
        if key in seen:
            continue
        seen.add(key)
        forms.append(Form(name, form_expr, render_canonical(form_expr)[0]))
    return forms


def substituted_forms(fn, facts=None) -> list[SubstitutedForm]:
    """The known changes of variable that apply to `fn`'s body, one
    `SubstitutedForm` per (substitution, parameter) pair whose shape
    the substitution recognizes.

        >>> import math
        >>> def loglaw(x: float) -> float:
        ...     return math.log(x) ** 2 - 2.0 * math.log(x) + 1.5
        >>> [s.name for s in substituted_forms(loglaw)]  # doctest: +SKIP
        ['t = log(x)']

    The transformed expression is simplified in the new variable, and
    `requires` states the domain condition ("x > 0") under which the
    substitution is a monotone bijection, on such a domain the
    transformed form takes exactly the values the original does, which
    is what makes it usable in a proof and not just a display. Raises
    `ValueError` for a function with no scalar closed form."""
    lifted = _lifted_expr(fn, facts)
    expr = lifted.expr
    out = []
    for pname, sym in lifted.params.items():
        if sym not in expr.free_symbols:
            continue
        for sub in _substitutions():
            try:
                if not sub.detect(expr, sym):
                    continue
            except Exception:
                continue
            t = sympy.Symbol("t", real=True)
            try:
                from ._timeout import FAST_TIMEOUT_SECONDS, _with_timeout
                transformed = _with_timeout(
                    lambda: sympy.simplify(expr.subs(sym, sub.inverse(t))),
                    FAST_TIMEOUT_SECONDS)
            except Exception:
                continue
            requires = (sub.requires if sub.requires == "always"
                        else sub.requires.replace("x", pname))
            out.append(SubstitutedForm(
                name=sub.name.replace("(x)", f"({pname})").replace("/x", f"/{pname}")
                             .replace("(x/2)", f"({pname}/2)"),
                param=pname, var=t, expr=transformed,
                text=render_canonical(transformed)[0], requires=requires))
    return out


def executable_forms(fn, facts=None, backend: str = "math") -> list:
    """Intent:
        Every closed form of `fn`'s body as a runnable CompiledForm:
        the as-written lift and each gallery rewrite, compiled through
        `mathema.compiled.compile_form`, carrying the provenance chain
        (which rewrite produced it) and, for a substituted form, the
        domain condition its equivalence needs. A compiled form is
        mathema's reconstruction, never the original code, evidence
        from running one is evidence about the symbolic form, which is
        exactly what makes it useful for cross-checking the original
        against its own mathematics.

        >>> import mathema.forms
        >>> def parallel(a: float, b: float) -> float:
        ...     return 1.0 / (1.0 / a + 1.0 / b)
        >>> cfs = mathema.forms.executable_forms(parallel)  # doctest: +SKIP
        >>> cfs[0].fn(2.0, 2.0)  # doctest: +SKIP
        1.0

    Notes:
        A form the backend cannot compile (an unevaluated calculus
        atom, an unmapped special function) is skipped, not an error;
        an unliftable function raises the same `ValueError`
        `closed_forms` does. Substituted forms carry their `requires`
        condition in `validity`; equivalence holds only where the
        change of variable is a monotone bijection.
    """
    from .compiled import compile_form
    out = []
    for form in closed_forms(fn, facts):
        cf = compile_form(form.expr, provenance=("lift",) if form.name == "as written"
                          else ("lift", form.name),
                          validity="as lifted", backend=backend)
        if cf is not None:
            out.append(cf)
    for sub in substituted_forms(fn, facts):
        cf = compile_form(sub.expr,
                          provenance=("lift", sub.name),
                          validity=sub.requires, backend=backend)
        if cf is not None:
            out.append(cf)
    return out
