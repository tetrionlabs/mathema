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

Deliberately absent from the built-in rows: `x ** 0.5` (Python returns
a complex number, no raise, the ordering machinery already refuses
complex values) and numpy's vectorized forms (they return nan, which
is the missing-policy axis, adjudicated by is_missing_safe, never a
raise). A bare `sqrt` call in a body matches only through the caller's
own scope resolving it to a registered function, the spelling alone
never decides, since guessing the origin wrong would falsify with a
lemma about the wrong function.
"""
import ast
import contextvars
import copy

import sympy

from ._base import NotSymbolic, _bind_params, _expr_to_sympy, strip_docstring

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
    "math.log": [(lambda u: sympy.Le(u, 0), "ValueError")],
    "math.log2": [(lambda u: sympy.Le(u, 0), "ValueError")],
    "math.log10": [(lambda u: sympy.Le(u, 0), "ValueError")],
    "math.asin": [(lambda u: sympy.Gt(sympy.Abs(u), 1), "ValueError")],
    "math.acos": [(lambda u: sympy.Gt(sympy.Abs(u), 1), "ValueError")],
    # exp overflows past log of the largest double, 709.782712893384
    # (the exact binary value, so the region boundary is the real one)
    "math.exp": [(lambda u: sympy.Gt(u, sympy.Rational(709.782712893384)),
                  "OverflowError")],
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


def _lemmas_for_call(node: ast.Call, scope: dict) -> list:
    """The registered partiality lemmas matching one call node.
    Resolution goes through the enclosing function's own scope first,
    `import math as _math; _math.sqrt(u)` reaches math.sqrt's lemma by
    resolving the actual object, however the caller spelled the import,
    with the literal dotted text as the fallback for a module the
    scope can't see."""
    if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
        holder = scope.get(node.func.value.id)
        target = getattr(holder, node.func.attr, None) if holder is not None \
            else None
        key = qualified_name(target) if callable(target) else None
        if key and key in _PARTIALITY_LEMMAS:
            return _PARTIALITY_LEMMAS[key]
        return _PARTIALITY_LEMMAS.get(f"{node.func.value.id}.{node.func.attr}", [])
    if isinstance(node.func, ast.Name):
        target = scope.get(node.func.id)
        key = qualified_name(target) if callable(target) else None
        if key:
            return _PARTIALITY_LEMMAS.get(key, [])
    return []


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


_DBL_MAX = 1.7976931348623157e308

# where the walk records the regions a fractional power of a negative
# base returns a complex number, when a caller asked for them
_COMPLEX_OUT: contextvars.ContextVar = contextvars.ContextVar(
    "mathema_complex_regions", default=None)


def _float_pow_region(base, exponent: float, int_syms: frozenset):
    """The regions where `base ** exponent` raises OverflowError, a float
    power whose result would exceed the largest double: the base above
    the limit, and below its negation. An integer base (every symbol
    integer-typed, no float constant) never overflows, so it has none."""
    if base.free_symbols and base.free_symbols <= int_syms \
            and not base.atoms(sympy.Float):
        return []
    limit = sympy.Float(_DBL_MAX ** (1.0 / exponent), 17)
    return [sympy.Gt(base, limit), sympy.Lt(base, -limit)]


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
                   and isinstance(n.op, (ast.Div, ast.FloorDiv, ast.Mod))
                   or isinstance(n, ast.Call) and _lemmas_for_call(n, scope)
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
        for condition, exc_name in _lemmas_for_call(node, scope):
            if node.keywords:
                miss("keyword call")
                break
            try:
                args = [_expr_to_sympy(a, dict(env)) for a in node.args]
                region = condition(*args)
            except TimeoutError:
                raise
            except Exception:
                miss("call argument")
                continue
            out.append((sympy.And(path_cond, region), exc_name))
    complex_out = _COMPLEX_OUT.get()
    if complex_out is not None and isinstance(node, ast.BinOp) \
            and isinstance(node.op, ast.Pow):
        # a constant non-integer exponent (0.5, 1/3): Python returns a
        # complex number for a negative float base, no raise
        try:
            exponent = _expr_to_sympy(node.right, {})
        except NotSymbolic:
            exponent = None
        if exponent is not None and not isinstance(exponent, tuple) \
                and exponent.is_number and exponent.is_integer is False:
            try:
                base = _expr_to_sympy(node.left, dict(env))
            except NotSymbolic:
                base = None
            if base is None or isinstance(base, tuple):
                complex_out.append(path_cond)
            elif base.free_symbols:
                complex_out.append(sympy.And(path_cond, base < 0))
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow) \
            and isinstance(node.right, ast.Constant) \
            and isinstance(node.right.value, (int, float)) \
            and not isinstance(node.right.value, bool) \
            and node.right.value > 1:
        try:
            base = _expr_to_sympy(node.left, dict(env))
        except NotSymbolic:
            base = None
        if base is None or isinstance(base, tuple):
            miss("power base")
        elif base.free_symbols:
            for region in _float_pow_region(base, float(node.right.value),
                                            int_syms):
                out.append((sympy.And(path_cond, region), "OverflowError"))
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
    for child in ast.iter_child_nodes(node):
        _guards_in_expr(child, env, path_cond, out, scope, missed, int_syms)


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
                    complex_out: "list | None" = None) -> "tuple[list, str | None]":
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

    scope = dict(getattr(fn, "__globals__", None) or {})
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
                if body_cond is not None:
                    for node in ast.walk(stmt):
                        if isinstance(node, (ast.Assign, ast.AugAssign)):
                            _guards_in_expr(node.value, env, body_cond,
                                            guards, scope, missed, int_syms)
                loop_names = set()
                for node in ast.walk(stmt):
                    if isinstance(node, ast.Name) and isinstance(
                            getattr(node, "ctx", None), ast.Store):
                        loop_names.add(node.id)
                if isinstance(stmt.target, ast.Name):
                    loop_names.add(stmt.target.id)
                env = {k: v for k, v in env.items() if k not in loop_names}
            elif isinstance(stmt, ast.Pass):
                continue
            elif isinstance(stmt, ast.Expr):
                _guards_in_expr(stmt.value, env, path_cond, guards, scope, missed, int_syms)
            else:
                stop(stmt)
                return
    token = _COMPLEX_OUT.set(complex_out)
    try:
        walk(strip_docstring(facts.tree.body), sympy.true, dict(params))
    finally:
        _COMPLEX_OUT.reset(token)
    first = (unread or missed or [None])[0]
    return guards, first
