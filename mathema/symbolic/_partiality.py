# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Partiality lemmas: where functions raise, as consumable facts.

`math.sqrt(u)` raises ValueError for u < 0 just as surely as an
explicit `if u < 0: raise ValueError` would, so a value claim
quantifying over that region is false there, pedantically, the same
reading the explicit raise guards already get. This module walks a
function body and emits those implicit raise regions as guards in the
exact shape `lift_piecewise` produces for explicit ones, so the
raise-region verdict machinery treats both identically.

The registry works for any function, not just the standard library's:
the math-module rows ship out of the box, and `register_raises_when`
(public as `mathema.partiality.register_raises_when`) declares
an arbitrary function, a third-party kernel, the user's own helper,
so claims about its CALLERS adjudicate against its raising region too.
True division contributes a ZeroDivisionError guard with no registry
entry at all.

A region where a call returns no value without raising (numpy's
`sqrt` returns nan for a negative input, `log` an infinity at zero) is
a guard of the same shape whose exception slot holds `NO_VALUE`: a
value claim over it is false just the same, and its witness is
corroborated by a call that raises or returns a non-finite value.
Those rows come from the compendium's `is_defined` rows
(`register_no_value_when`); a power with a negative base and a
non-integer exponent (`x ** 0.5` at x < 0, where Python returns a
complex number) is one too, and `math.tan` at its poles, where the
float call returns a large finite number. A bare `sqrt` call in a body matches only
through the caller's own scope resolving it to a registered function,
the spelling alone never decides, since guessing the origin wrong would
falsify with a lemma about the wrong function.

Every region here is mathematics: the real domain of a primitive (`sqrt`
below zero, `log` at or below zero, `asin` outside [-1, 1], division by
zero, a fractional power of a negative base), a region a library's
`is_defined` row states, or a raise the function's own source states.
Nothing here depends on the float number representation's range or
precision, so `math.exp` has no row and `x ** 3` has no overflow region: a
proof over the reals is a proof over the reals, and where the computation
leaves the doubles is found by executing it (the `[float]` companion, the
probe route), never by this walk.
"""
from .._signatures import module_scope
import ast
import contextvars
import copy

import sympy

from ._base import NotSymbolic, _bind_params, _expr_to_sympy, strip_docstring

#: the exception-name slot of a guard whose region has no value without
#: raising: the call returns nan or an infinity there
NO_VALUE = "no value"

# the parameter symbols the current walk knows are called with an int
_INT_SYMS: contextvars.ContextVar = contextvars.ContextVar(
    "mathema_int_syms", default=frozenset())


def _integer_valued(u) -> bool:
    """Whether a lifted argument is an integer at every point, reading
    the parameters the walk knows are ints as integers."""
    u = sympy.sympify(u)
    swap = {s: sympy.Dummy(s.name, integer=True)
            for s in _INT_SYMS.get() if s in u.free_symbols}
    return bool(u.subs(swap).is_integer) if swap else bool(u.is_integer)


def _factorial_type_region(u):
    """math.factorial accepts only an int: a float argument raises
    TypeError whatever its value."""
    return sympy.false if _integer_valued(u) else sympy.true


def _factorial_value_region(u):
    """math.factorial of a negative int raises ValueError."""
    return sympy.Lt(u, 0) if _integer_valued(u) else sympy.false


def _nonpositive_integer(u):
    """Where `u` is 0, -1, -2, ...: the poles of the gamma function."""
    return sympy.And(sympy.Le(u, 0), sympy.Eq(u, sympy.floor(u)))


def _power_zero_base(base, exponent):
    """Where a power has a zero base and a negative exponent: Python
    raises there (ZeroDivisionError for `**`, ValueError for
    math.pow)."""
    return sympy.And(sympy.Eq(base, 0), sympy.Lt(exponent, 0))


def _power_negative_base(base, exponent):
    """Where a power has a negative base and an exponent not known to be
    an integer: no real value at a non-integer exponent (`**` returns a
    complex number, math.pow raises)."""
    if exponent.is_number:
        if exponent.is_real and float(exponent).is_integer():
            return sympy.false
        return sympy.Lt(base, 0)
    if _integer_valued(exponent):
        return sympy.false
    # a negative base with an exponent that may be fractional: the
    # region holds the points with an integral exponent too, where the
    # power has a value, so only an executed witness falsifies there
    return sympy.Lt(base, 0)


def _log_with_base(*args):
    """math.log(x) raises ValueError for x <= 0; math.log(x, b) also
    for b <= 0."""
    if len(args) == 1:
        return sympy.Le(args[0], 0)
    return sympy.Or(sympy.Le(args[0], 0), sympy.Le(args[1], 0))


def _divisor_zero(*args):
    """The second argument is zero (fmod, remainder, divmod)."""
    return sympy.Eq(args[1], 0)


# The partiality-lemma registry: qualified function name -> list of
# (condition builder, exception name). A condition builder takes the
# call's lifted arguments (sympy expressions) and returns the region
# where the call RAISES. The math-module rows ship out of the box;
# `register_raises_when` (public via mathema.partiality) adds rows for
# arbitrary functions, a caller's claims then falsify over a
# registered function's raising region exactly as they do over
# math.sqrt's.
_PARTIALITY_LEMMAS: dict = {
    "math.sqrt": [(lambda u: sympy.Lt(u, 0), "ValueError")],
    "math.log": [(_log_with_base, "ValueError"),
                 # log(x, 1) divides by log(1) = 0
                 (lambda *a: sympy.Eq(a[1], 1) if len(a) > 1 else sympy.false,
                  "ZeroDivisionError")],
    "math.log2": [(lambda u: sympy.Le(u, 0), "ValueError")],
    "math.log10": [(lambda u: sympy.Le(u, 0), "ValueError")],
    "math.log1p": [(lambda u: sympy.Le(u, -1), "ValueError")],
    "math.asin": [(lambda u: sympy.Gt(sympy.Abs(u), 1), "ValueError")],
    "math.acos": [(lambda u: sympy.Gt(sympy.Abs(u), 1), "ValueError")],
    "math.atanh": [(lambda u: sympy.Ge(sympy.Abs(u), 1), "ValueError")],
    "math.acosh": [(lambda u: sympy.Lt(u, 1), "ValueError")],
    # tan has a pole wherever cos is zero; in floats the call returns a
    # large finite number next to it, so this region has no value in
    # the mathematics only
    "math.tan": [(lambda u: sympy.Eq(sympy.cos(u), 0), NO_VALUE)],
    "numpy.tan": [(lambda u: sympy.Eq(sympy.cos(u), 0), NO_VALUE)],
    "math.gamma": [(_nonpositive_integer, "ValueError")],
    "math.lgamma": [(_nonpositive_integer, "ValueError")],
    "math.pow": [(_power_zero_base, "ValueError"),
                 (_power_negative_base, "ValueError")],
    "builtins.pow": [(lambda b, e, *m: _power_zero_base(b, e),
                      "ZeroDivisionError"),
                     (lambda b, e, *m: _power_negative_base(b, e),
                      NO_VALUE)],
    "math.factorial": [(_factorial_type_region, "TypeError"),
                       (_factorial_value_region, "ValueError")],
    "math.fmod": [(_divisor_zero, "ValueError")],
    "math.remainder": [(_divisor_zero, "ValueError")],
    "builtins.divmod": [(_divisor_zero, "ZeroDivisionError")],
    # numpy.linspace(start, stop, num): num must be a nonnegative integer
    "numpy.linspace": [
        (lambda *a: sympy.Ne(a[2], sympy.floor(a[2])) if len(a) > 2
         else sympy.false, "TypeError"),
        (lambda *a: sympy.Lt(a[2], 0) if len(a) > 2 else sympy.false,
         "ValueError"),
    ],
}


def qualified_name(fn) -> "str | None":
    """`module.qualname` for a plain function, `None` for anything
    without an importable identity (a lambda, a nested def's caller may
    still register it by its literal `module.qualname` string)."""
    mod = getattr(fn, "__module__", None)
    qual = getattr(fn, "__qualname__", None)
    if not mod or not qual:
        return None
    return f"{mod}.{qual}"


def register_raises_when(target, condition, exc_name: str = "ValueError") -> None:
    """Intent:
        Register a partiality lemma about any function: `condition`,
        given the call's lifted arguments as sympy expressions, returns
        the region where `target` raises `exc_name`. Claims about
        functions that CALL the target then treat that region exactly
        like an explicit raise guard.

    Notes:
        `target` is a callable or its dotted "module.qualname" string.
        Lemmas accumulate (several conditions per function are fine).
    """
    key = target if isinstance(target, str) else qualified_name(target)
    if not key:
        raise ValueError("target has no importable module.qualname; "
                         "pass the dotted name string instead")
    _PARTIALITY_LEMMAS.setdefault(key, []).append((condition, exc_name))


def register_no_value_when(target, region_builder) -> None:
    """Intent:
        Register the region where a call to `target` has no value
        without raising (it returns nan or an infinity): given the
        call's lifted arguments as sympy expressions, `region_builder`
        returns that region. Callers' claims then treat it like a
        raise region whose exception is `NO_VALUE`.

    Notes:
        `target` is a callable or its dotted "module.qualname" string.
    """
    register_raises_when(target, region_builder, NO_VALUE)


def unregister_lemmas(target, builders: list) -> None:
    """Intent:
        Remove the rows registered for `target` whose builder is one of
        `builders` (compared by identity), dropping the key when none
        remain.
    """
    key = target if isinstance(target, str) else qualified_name(target)
    have = _PARTIALITY_LEMMAS.get(key)
    if not have:
        return
    kept = [row for row in have if not any(row[0] is b for b in builders)]
    if kept:
        _PARTIALITY_LEMMAS[key] = kept
    else:
        del _PARTIALITY_LEMMAS[key]


def _call_target(node: ast.Call, scope: dict):
    """Intent:
        The object a call node names and the keys it may be registered
        under, `(target, keys)`: resolution goes through the enclosing
        function's own scope first (builtins included), so `import math
        as _math; _math.sqrt(u)` reaches math.sqrt's lemma however the
        caller spelled the import, then the library claim key of the
        resolved object, with the literal dotted text as the fallback
        for a module the scope can't see.
    """
    import builtins
    target = None
    keys: list = []
    if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
        holder = scope.get(node.func.value.id)
        target = getattr(holder, node.func.attr, None) if holder is not None \
            else None
        literal = f"{node.func.value.id}.{node.func.attr}"
    elif isinstance(node.func, ast.Name):
        target = scope.get(node.func.id, getattr(builtins, node.func.id, None))
        literal = None
    else:
        return None, []
    if callable(target):
        key = qualified_name(target)
        if key:
            keys.append(key)
        try:
            from ..compendium import library_key_of
            library_key = library_key_of(target)
        except Exception:
            library_key = None
        if library_key and library_key not in keys:
            keys.append(library_key)
    if literal:
        keys.append(literal)
    return target, keys


def _lemmas_for_call(node: ast.Call, scope: dict) -> list:
    """The registered partiality lemmas matching one call node, under
    the first key `_call_target` gives that has any."""
    _target, keys = _call_target(node, scope)
    for key in keys:
        if key in _PARTIALITY_LEMMAS:
            return _PARTIALITY_LEMMAS[key]
    return []


#: calls that return a value at every finite real argument, by
#: qualified name: a call to anything else that has no partiality
#: lemma leaves the definedness region unknown
_TOTAL_CALLS = frozenset({
    "builtins.abs", "builtins.float", "builtins.int", "builtins.round",
    "builtins.bool", "builtins.len", "builtins.isinstance",
    "builtins.callable",
    "math.exp", "math.expm1", "math.exp2", "math.sin", "math.cos",
    "math.atan", "math.atan2", "math.sinh", "math.cosh", "math.tanh",
    "math.asinh", "math.erf", "math.erfc", "math.fabs", "math.floor",
    "math.ceil", "math.trunc", "math.hypot", "math.copysign",
    "math.degrees", "math.radians", "math.cbrt", "math.isfinite",
    "math.isnan", "math.isinf", "math.isclose", "math.fsum", "math.prod",
    "numpy.sin", "numpy.cos", "numpy.arctan", "numpy.arctan2",
    "numpy.tanh", "numpy.arcsinh", "numpy.absolute", "numpy.fabs",
    "numpy.floor", "numpy.ceil", "numpy.trunc", "numpy.hypot",
    "numpy.sign", "numpy.square", "numpy.negative", "numpy.maximum",
    "numpy.minimum", "numpy.deg2rad", "numpy.rad2deg", "numpy.degrees",
    "numpy.radians", "numpy.copysign", "numpy.cbrt", "numpy.isfinite",
    "numpy.isnan", "numpy.isinf", "numpy.float64", "numpy.float32",
    "numpy.int64",
})

#: calls total when given at least two arguments (with one, they reduce
#: a sequence, and an empty one raises)
_TOTAL_WITH_TWO_ARGS = frozenset({"builtins.min", "builtins.max"})


def _states_definedness(keys: list) -> bool:
    """Whether a library claims file states an `is_defined` row for one
    of these keys (a bare row says the function is total)."""
    try:
        from ..compendium import defined_keys
    except Exception:
        return False
    stated = defined_keys()
    return any(key in stated for key in keys)


def _opaque_call(node: ast.Call, scope: dict) -> bool:
    """Intent:
        Whether a call's definedness is unknown: it has no partiality
        lemma, is not a call known to be total, and no library claims
        file states where it is defined.
    """
    _target, keys = _call_target(node, scope)
    if any(key in _PARTIALITY_LEMMAS for key in keys):
        return False
    if any(key in _TOTAL_CALLS for key in keys):
        return False
    if len(node.args) >= 2 and not node.keywords \
            and any(key in _TOTAL_WITH_TWO_ARGS for key in keys):
        return False
    return not _states_definedness(keys)


def _plain_lambda(lam: ast.Lambda) -> bool:
    """A lambda with only plain positional parameters."""
    a = lam.args
    return not (a.vararg or a.kwarg or a.kwonlyargs or a.defaults
                or a.posonlyargs)


class _LambdaInliner(ast.NodeTransformer):
    """Replace each call `g(e1, e2)` of a local `g = lambda a, b: body`
    with `body`, its parameters replaced by the argument expressions."""

    def __init__(self, lambdas: dict):
        self.lambdas = lambdas

    def visit_Call(self, node):
        self.generic_visit(node)
        lam = (self.lambdas.get(node.func.id)
               if isinstance(node.func, ast.Name) else None)
        if lam is None or node.keywords \
                or len(node.args) != len(lam.args.args):
            return node
        mapping = {a.arg: v for a, v in zip(lam.args.args, node.args)}

        class _Sub(ast.NodeTransformer):
            def visit_Name(self, n):
                return mapping.get(n.id, n) if isinstance(n.ctx, ast.Load) \
                    else n
        body = _Sub().visit(copy.deepcopy(lam.body))
        return ast.copy_location(body, node)


def _inline_lambdas(stmt: ast.stmt, lambdas: dict) -> ast.stmt:
    return _LambdaInliner(lambdas).visit(copy.deepcopy(stmt))


# where the walk records the regions a fractional power of a negative
# base returns a complex number, when a caller asked for them
_COMPLEX_OUT: contextvars.ContextVar = contextvars.ContextVar(
    "mathema_complex_regions", default=None)

# where the walk records the calls whose definedness is not known, when
# a caller asked for them
_OPAQUE_OUT: contextvars.ContextVar = contextvars.ContextVar(
    "mathema_opaque_calls", default=None)

# the names of the parameters the walk's domain binds to C
_COMPLEX_NAMES: contextvars.ContextVar = contextvars.ContextVar(
    "mathema_complex_names", default=frozenset())


def _complex_typed(expr) -> bool:
    """Intent:
        Whether a lifted call argument is complex-typed: known not to
        be real (`is_extended_real is False`), or reading a symbol
        created complex (a `complex`-annotated parameter) or a
        parameter the walk's domain binds to C.
    """
    if isinstance(expr, tuple) or not isinstance(expr, sympy.Basic):
        return False
    if expr.is_extended_real is False:
        return True
    names = _COMPLEX_NAMES.get()
    return any((sym.is_complex and sym.is_extended_real is not True)
               or str(sym) in names for sym in expr.free_symbols)


def _lemma_applies(condition, args: list) -> bool:
    """Intent:
        Whether a registered lemma speaks for a call with these
        arguments: a region stated with an ordering (`applies_to ==
        "real"`, a compendium `is_defined: x >= 0` row) is a statement
        over real inputs and does not apply at a complex-typed
        argument; a region over C (`"complex"`) applies only at one;
        any other lemma always applies.
    """
    applies_to = getattr(condition, "applies_to", "all")
    if applies_to == "all":
        return True
    complex_arg = any(_complex_typed(a) for a in args)
    return complex_arg if applies_to == "complex" else not complex_arg


def _guards_in_expr(node: ast.AST, env: dict, path_cond, out: list,
                    scope: dict, missed: "list | None" = None,
                    int_syms: frozenset = frozenset()) -> None:
    """Intent:
        Collect every implicit raise region inside one expression: a
        call with a registered partiality lemma (math.sqrt's negative
        region, a user-registered lemma about their own helper), or a
        true division, each guarded by the path condition it sits
        under.

    Notes:
        An operation whose raise region cannot be stated exactly (an
        argument or denominator that doesn't lift, a ternary or and/or
        whose condition doesn't lift) contributes no guard and is
        appended to `missed` instead, so the caller knows the region it
        reports is incomplete. The recursion is manual, never a blind ast.walk: a
        guard's condition must be EXACT about whether its operation
        executes, so a ternary's arms carry the ternary's own condition
        (`0.0 if x == 0 else 1/x` divides only where x != 0, an
        unconditional guard there falsified a true claim in dev), and
        short-circuited operands of and/or, whose execution this pass
        can't condition exactly, are reported as missed.
    """
    def miss(what: str) -> None:
        if missed is not None:
            missed.append(f"line {getattr(node, 'lineno', '?')}: {what}")

    def has_partial(sub: ast.AST) -> bool:
        return any(isinstance(n, ast.BinOp)
                   and isinstance(n.op, (ast.Div, ast.FloorDiv, ast.Mod,
                                         ast.Pow))
                   or isinstance(n, ast.Call) and (
                       _lemmas_for_call(n, scope) or _opaque_call(n, scope))
                   for n in ast.walk(sub))

    if isinstance(node, ast.IfExp):
        from ._conditioned import _condition_to_sympy
        _guards_in_expr(node.test, env, path_cond, out, scope, missed, int_syms)
        cond = _condition_to_sympy(node.test, dict(env))
        if cond is not None:
            _guards_in_expr(node.body, env, sympy.And(path_cond, cond),
                            out, scope, missed, int_syms)
            _guards_in_expr(node.orelse, env,
                            sympy.And(path_cond, sympy.Not(cond)), out,
                            scope, missed, int_syms)
        elif has_partial(node.body) or has_partial(node.orelse):
            miss("conditional expression")
        return
    if isinstance(node, ast.BoolOp):
        # only the first operand is unconditionally evaluated
        if node.values:
            _guards_in_expr(node.values[0], env, path_cond, out, scope,
                            missed, int_syms)
        if any(has_partial(v) for v in node.values[1:]):
            miss("and/or operand")
        return
    if isinstance(node, ast.Call):
        opaque = _OPAQUE_OUT.get()
        if opaque is not None and _opaque_call(node, scope):
            opaque.append(f"line {getattr(node, 'lineno', '?')}: a call to "
                          f"{ast.unparse(node.func)}, whose definedness is "
                          f"not known")
        for condition, exc_name in _lemmas_for_call(node, scope):
            if node.keywords:
                miss("keyword call")
                break
            try:
                args = [_expr_to_sympy(a, dict(env)) for a in node.args]
                if not _lemma_applies(condition, args):
                    continue
                region = condition(*args)
            except TimeoutError:
                raise
            except Exception:
                miss("call argument")
                continue
            if region is not sympy.false:
                out.append((sympy.And(path_cond, region), exc_name))
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
        _power_guards(node, env, path_cond, out, miss)
    if isinstance(node, ast.BinOp) \
            and isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)):
        try:
            denom = _expr_to_sympy(node.right, dict(env))
        except NotSymbolic:
            denom = None
        if denom is None or isinstance(denom, tuple):
            miss("divisor")
        elif denom.free_symbols:
            out.append((sympy.And(path_cond, sympy.Eq(denom, 0)),
                        "ZeroDivisionError"))
        elif denom.is_zero:
            # a divisor that is zero at every point (`x - x`)
            out.append((path_cond, "ZeroDivisionError"))
    for child in ast.iter_child_nodes(node):
        _guards_in_expr(child, env, path_cond, out, scope, missed, int_syms)


def _power_guards(node: ast.BinOp, env: dict, path_cond, out: list,
                  miss) -> None:
    """Intent:
        The regions where `base ** exponent` has no real value: a zero
        base with a negative exponent raises ZeroDivisionError, and a
        negative base with a non-integer exponent returns a complex
        number. A complex-typed base has only the first. The
        complex-number region of a constant exponent is recorded in
        `_COMPLEX_OUT` when the walk's caller asked for it, and joins
        the guards only on the definedness walk (`_OPAQUE_OUT` set); a
        symbolic exponent's always joins them.
    """
    try:
        exponent = _expr_to_sympy(node.right, dict(env))
    except NotSymbolic:
        exponent = None
    if exponent is not None and not isinstance(exponent, tuple) \
            and exponent.is_number and exponent.is_real \
            and exponent >= 0 and float(exponent).is_integer():
        return   # a nonnegative integer power is total
    try:
        base = _expr_to_sympy(node.left, dict(env))
    except NotSymbolic:
        base = None
    if exponent is None or isinstance(exponent, tuple) \
            or base is None or isinstance(base, tuple):
        miss("power")
        complex_out = _COMPLEX_OUT.get()
        if complex_out is not None and exponent is not None \
                and not isinstance(exponent, tuple) and exponent.is_number \
                and exponent.is_integer is False:
            complex_out.append(path_cond)
        return
    zero = _power_zero_base(base, exponent)
    if zero is not sympy.false:
        out.append((sympy.And(path_cond, zero), "ZeroDivisionError"))
    if _complex_typed(base):
        return
    negative = _power_negative_base(base, exponent)
    if negative is sympy.false:
        return
    complex_out = _COMPLEX_OUT.get()
    if complex_out is not None and exponent.is_number:
        complex_out.append(sympy.And(path_cond, negative))
    opaque = _OPAQUE_OUT.get()
    if opaque is not None or not exponent.is_number:
        # the definedness walk reads it as a guard; a value claim reads
        # a constant exponent's region through `complex_out`
        out.append((sympy.And(path_cond, negative), NO_VALUE))
    if opaque is not None and not exponent.is_number:
        opaque.append(f"line {getattr(node, 'lineno', '?')}: a power whose "
                      f"exponent may be an integer at a negative base")


def _range_index(stmt: ast.For, env: dict) -> dict:
    """Intent:
        `{name: symbol}` for the loop variable of `for i in range(n)` or
        `range(k, n)` with a nonnegative integer constant k: a
        nonnegative integer at every trip. Empty for any other loop.
    """
    if not (isinstance(stmt.target, ast.Name)
            and isinstance(stmt.iter, ast.Call)
            and isinstance(stmt.iter.func, ast.Name)
            and stmt.iter.func.id == "range"
            and not stmt.iter.keywords
            and len(stmt.iter.args) in (1, 2)):
        return {}
    if len(stmt.iter.args) == 2:
        try:
            start = _expr_to_sympy(stmt.iter.args[0], dict(env))
        except NotSymbolic:
            return {}
        if isinstance(start, tuple) or not (start.is_integer
                                            and start.is_nonnegative):
            return {}
    name = stmt.target.id
    return {name: sympy.Dummy(name, integer=True, nonnegative=True)}


def _integer_bound(bound) -> bool:
    """Whether a declared bound admits only integers (`subset Z`): a
    parameter there is called with an int, whatever its annotation."""
    if bound is None:
        return False
    from ..domain import bound_assumptions
    try:
        return bool((bound_assumptions(bound) or {}).get("integer"))
    except Exception:
        return False


def partiality_guards(fn, facts) -> list:
    """The implicit raise regions of `fn`'s body; see partiality_walk."""
    return partiality_walk(fn, facts)[0]


def partiality_walk(fn, facts, domain: "dict | None" = None,
                    complex_out: "list | None" = None,
                    opaque_out: "list | None" = None,
                    missed_out: "list | None" = None) -> "tuple[list, str | None]":
    """Intent:
        The implicit raise regions of a straight-line (or simply
        branched) body, as (condition, exception name) guards over the
        function's own parameter symbols, the same shape
        lift_piecewise's explicit raise guards take.

    Notes:
        Walks docstring-stripped statements with local assignments
        threaded into the environment, so `disc = b*b - 4*a*c;
        math.sqrt(disc)` guards on the full discriminant expression.
        Returns `(guards, unread)`. `unread` is `None` when every
        statement on every path was read, else a short description of
        the first statement the walk stopped at: guards past that point
        are missing, so an empty raise region is not established and a
        proof must not rely on it. A branch whose condition does not
        lift (a string comparison, say) is settled from `domain` when
        the declared domain decides it, and only the live side is walked.

        When `complex_out` is a list, the walk also appends the regions
        where a power with a constant non-integer exponent meets a
        negative base (`x ** 0.5` at `x < 0`): Python returns a complex
        number there rather than raising.

        When `opaque_out` is a list, the walk also appends a description
        of every call whose definedness is not known (no partiality
        lemma, not a known total function, no library `is_defined`
        row): the region it reports says nothing about such a call. When
        `missed_out` is a list, it receives every operation whose raise
        region the walk read but could not state (a divisor that does
        not lift), apart from the statements it stopped at.
    """
    if facts.tree is None:
        return [], "no source"
    try:
        params, aggregate = _bind_params(fn, facts)
    except Exception:
        return [], "parameters not bound"
    # bundled (dataclass/dict/self) parameters are fine now: their
    # fields are ordinary composite symbols, so a guard over
    # `self.rate` or `cfg.a` reads like any scalar guard
    from ._conditioned import (_branch_condition_truth, _condition_to_sympy,
                               _unmodified_params)
    unmodified = _unmodified_params(facts.tree, set(facts.params or ()))
    kinds = getattr(facts, "param_kinds", None) or {}
    int_syms = frozenset(sym for name, sym in params.items()
                         if (kinds.get(name) == "int"
                             or _integer_bound((domain or {}).get(name)))
                         and isinstance(sym, sympy.Symbol))

    scope = dict(module_scope(fn))
    guards: list = []
    unread: list = []
    missed: list = []
    lambdas: dict = {}

    def stop(stmt) -> None:
        if not unread:
            unread.append(f"line {getattr(stmt, 'lineno', '?')}: "
                          f"{type(stmt).__name__}")

    def bind_import(stmt) -> bool:
        import importlib
        try:
            if isinstance(stmt, ast.Import):
                for alias in stmt.names:
                    if alias.asname:
                        scope[alias.asname] = importlib.import_module(alias.name)
                    else:
                        head = alias.name.split(".")[0]
                        scope[head] = importlib.import_module(head)
                return True
            if stmt.level or not stmt.module:
                return False
            module = importlib.import_module(stmt.module)
            for alias in stmt.names:
                if alias.name == "*":
                    return False
                scope[alias.asname or alias.name] = getattr(module, alias.name)
            return True
        except Exception:
            return False

    def bind(env, name, value_node, stmt):
        # a name whose value does not lift is dropped from the
        # environment: any later raise region that reads it fails to
        # lift and is reported as missed
        _guards_in_expr(value_node, env, path_cond_box[0], guards, scope,
                        missed, int_syms)
        env = {k: v for k, v in env.items() if k != name}
        lambdas.pop(name, None)
        try:
            value = _expr_to_sympy(value_node, dict(env))
        except NotSymbolic:
            return env
        if not isinstance(value, tuple):
            env[name] = value
        return env

    path_cond_box = [sympy.true]

    def always_exits(stmts) -> bool:
        if not stmts:
            return False
        last = stmts[-1]
        if isinstance(last, (ast.Return, ast.Raise)):
            return True
        if isinstance(last, ast.If):
            return bool(last.orelse) and always_exits(last.body) \
                and always_exits(last.orelse)
        return False

    def walk(stmts, path_cond, env):
        for stmt in stmts:
            path_cond_box[0] = path_cond
            if lambdas:
                stmt = _inline_lambdas(stmt, lambdas)
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 \
                    and isinstance(stmt.targets[0], ast.Name) \
                    and isinstance(stmt.value, ast.Lambda) \
                    and _plain_lambda(stmt.value):
                name = stmt.targets[0].id
                env = {k: v for k, v in env.items() if k != name}
                lambdas[name] = stmt.value
                continue
            target = None
            value_node = None
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
                target, value_node = stmt.targets[0], stmt.value
            elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
                target, value_node = stmt.target, stmt.value
            elif isinstance(stmt, ast.AugAssign) \
                    and isinstance(stmt.target, ast.Name):
                target = stmt.target
                value_node = ast.BinOp(
                    left=ast.Name(id=stmt.target.id, ctx=ast.Load()),
                    op=stmt.op, right=stmt.value)
                ast.copy_location(value_node, stmt)
            if isinstance(target, ast.Name):
                env = bind(env, target.id, value_node, stmt)
                if env is None:
                    return
            elif isinstance(target, ast.Tuple) \
                    and isinstance(value_node, ast.Tuple) \
                    and len(target.elts) == len(value_node.elts) \
                    and all(isinstance(t, ast.Name) for t in target.elts):
                # every right-hand side is evaluated before any name binds
                new_env = dict(env)
                for t, v in zip(target.elts, value_node.elts):
                    bound = bind(env, t.id, v, stmt)
                    if bound is None:
                        return
                    new_env[t.id] = bound[t.id]
                env = new_env
            elif target is not None:
                stop(stmt)
                return
            elif isinstance(stmt, (ast.Import, ast.ImportFrom)):
                if not bind_import(stmt):
                    stop(stmt)
                    return
            elif isinstance(stmt, ast.Assert):
                cond = _condition_to_sympy(stmt.test, env)
                if cond is None:
                    stop(stmt)
                    return
                _guards_in_expr(stmt.test, env, path_cond, guards, scope, missed, int_syms)
                guards.append((sympy.And(path_cond, sympy.Not(cond)),
                               "AssertionError"))
                path_cond = sympy.And(path_cond, cond)
            elif isinstance(stmt, ast.Return):
                if stmt.value is not None:
                    _guards_in_expr(stmt.value, env, path_cond, guards, scope, missed, int_syms)
                return   # nothing after a return executes
            elif isinstance(stmt, ast.If):
                cond = _condition_to_sympy(stmt.test, env)
                if cond is None:
                    truth = None
                    if domain:
                        try:
                            truth = _branch_condition_truth(
                                stmt.test, domain, unmodified, None, params)
                        except Exception:
                            truth = None
                    if truth is None:
                        stop(stmt)
                        return
                    live = stmt.body if truth else stmt.orelse
                    walk(live, path_cond, env)
                    if always_exits(live):
                        return
                    continue
                _guards_in_expr(stmt.test, env, path_cond, guards, scope, missed, int_syms)
                walk(stmt.body, sympy.And(path_cond, cond), env)
                if stmt.orelse:
                    walk(stmt.orelse, sympy.And(path_cond, sympy.Not(cond)), env)
                # a guard's condition must be EXACT about reachability
                # (the raise-region witness is verified against the
                # condition, not by running the function, so an
                # over-approximated path would accept a false witness:
                # `if x < 0: return 0.0` followed by math.sqrt(x) never
                # raises). Statements after the If run under the
                # negation of whichever branches always exit.
                if always_exits(stmt.body):
                    path_cond = sympy.And(path_cond, sympy.Not(cond))
                if stmt.orelse and always_exits(stmt.orelse):
                    path_cond = sympy.And(path_cond, cond)
            elif isinstance(stmt, ast.Raise):
                return   # nothing after a raise executes
            elif isinstance(stmt, ast.For):
                # a loop body's guards are collected where they lift:
                # an expression depending on the loop variable or an
                # accumulator fails to lift and contributes nothing
                # (under-reporting, never a wrong guard). The walk
                # then CONTINUES past the loop with every loop-
                # assigned name evicted from the environment, a
                # later expression reading one simply stops the walk
                # there, partial coverage as everywhere else.
                # exactness across a zero-trip loop: a body guard only
                # holds where the loop actually runs, so the trip-
                # positivity condition rides on it (range(n) needs
                # n >= 1). A header this can't read collects nothing.
                body_cond = None
                if (isinstance(stmt.iter, ast.Call)
                        and isinstance(stmt.iter.func, ast.Name)
                        and stmt.iter.func.id == "range"
                        and scope.get("range", range) is range
                        and not stmt.iter.keywords):
                    # range() of a non-integer raises TypeError
                    for arg in stmt.iter.args:
                        _guards_in_expr(arg, env, path_cond, guards, scope,
                                        missed, int_syms)
                        try:
                            bound_arg = _expr_to_sympy(arg, dict(env))
                        except NotSymbolic:
                            bound_arg = None
                        if bound_arg is None or isinstance(bound_arg, tuple):
                            missed.append(f"line {stmt.lineno}: range "
                                          f"argument")
                            continue
                        if bound_arg.free_symbols \
                                and not bound_arg.free_symbols <= int_syms:
                            guards.append((sympy.And(
                                path_cond,
                                sympy.Ne(bound_arg, sympy.floor(bound_arg))),
                                "TypeError"))
                if (isinstance(stmt.iter, ast.Call)
                        and isinstance(stmt.iter.func, ast.Name)
                        and stmt.iter.func.id == "range"
                        and not stmt.iter.keywords
                        and len(stmt.iter.args) in (1, 2)):
                    try:
                        if len(stmt.iter.args) == 1:
                            trip = _expr_to_sympy(stmt.iter.args[0], dict(env))
                        else:
                            trip = (_expr_to_sympy(stmt.iter.args[1], dict(env))
                                    - _expr_to_sympy(stmt.iter.args[0], dict(env)))
                        if not isinstance(trip, tuple):
                            body_cond = sympy.And(path_cond, trip >= 1)
                    except NotSymbolic:
                        body_cond = None
                if body_cond is None:
                    stop(stmt)
                loop_names = set()
                for node in ast.walk(stmt):
                    if isinstance(node, ast.Name) and isinstance(
                            getattr(node, "ctx", None), ast.Store):
                        loop_names.add(node.id)
                if isinstance(stmt.target, ast.Name):
                    loop_names.add(stmt.target.id)
                env = {k: v for k, v in env.items() if k not in loop_names}
                if body_cond is not None:
                    # a name the body assigns changes from trip to trip,
                    # so it does not lift inside the body; a range
                    # index reads as a nonnegative integer symbol
                    body_env = {**env, **_range_index(stmt, env)}
                    for node in ast.walk(stmt):
                        if isinstance(node, (ast.Assign, ast.AugAssign)):
                            _guards_in_expr(node.value, body_env, body_cond,
                                            guards, scope, missed,
                                            int_syms)
            elif isinstance(stmt, ast.Pass):
                continue
            elif isinstance(stmt, ast.Expr):
                _guards_in_expr(stmt.value, env, path_cond, guards, scope, missed, int_syms)
            else:
                stop(stmt)
                return
    token = _COMPLEX_OUT.set(complex_out)
    opaque_token = _OPAQUE_OUT.set(opaque_out)
    int_token = _INT_SYMS.set(int_syms)
    names_token = _COMPLEX_NAMES.set(frozenset(
        name for name, bound in (domain or {}).items()
        if bound == "C" or getattr(bound, "base_type", None) == "C"))
    try:
        walk(strip_docstring(facts.tree.body), sympy.true, dict(params))
    finally:
        _COMPLEX_NAMES.reset(names_token)
        _INT_SYMS.reset(int_token)
        _OPAQUE_OUT.reset(opaque_token)
        _COMPLEX_OUT.reset(token)
    if missed_out is not None:
        missed_out.extend(missed)
    first = (unread or missed or [None])[0]
    return guards, first
