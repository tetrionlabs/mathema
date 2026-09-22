# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The normalization pre-pass: exact AST-to-AST rewrites applied to a
function body before ANY recognizer walks it, so one rewrite benefits
lift, fold, sum, and dot at once.

Every rewrite preserves semantics exactly or does not fire:

- a tuple-unpacking assignment becomes sequential assignments with
  simultaneous semantics (temporaries when a target also appears on
  the right, so ``a, b = b, a`` stays a swap);
- a ``range(a, b)`` / ``range(a, b, s)`` loop header (s a positive
  integer literal) becomes ``range(<trip count>)`` with the index
  rewritten to ``a + s*i`` in the body, so the zero-based fold and
  sum recognizers read nonzero-start and stepped loops unchanged;
- a leading straight-line temporary inside a loop body
  (``term = expr`` then ``total += term``) folds into its use sites
  when that is provably iteration-local, a temp carried across
  iterations is a second accumulator and is deliberately left alone;
- a module-level numeric constant read from global scope is inlined
  as its exact current value. The names and values are recorded (see
  `inlined_globals`) and joined to the dependency-freshness surface
  by `inventory.function_dependencies`, so a changed constant
  INVALIDATES records instead of silently keeping stale proofs.

The ORIGINAL tree is never modified: identity hashes (`form`) and
every structural fact keep reading the code as written.
"""
from __future__ import annotations

import ast
import copy


def normalized_body(fn, facts) -> list:
    """The function's docstring-stripped body statements after the
    pre-pass, cached per Facts instance. Falls back to the plain
    stripped body if any rewrite raises (a normalization must never
    take down a lift that would have worked without it)."""
    cached = getattr(facts, "_normalized_body", None)
    if cached is not None:
        return cached
    body = _strip_docstring_stmts(facts.tree.body)
    # an in-function `import` binds a module name the math vocabulary
    # resolves by attribute anyway; dropping the statement is
    # semantics-preserving for every recognizer
    body = [st for st in body
            if not isinstance(st, (ast.Import, ast.ImportFrom))]
    try:
        tree = ast.Module(body=copy.deepcopy(body), type_ignores=[])
        _expand_tuple_unpacks(tree)
        _desugar_comprehension_sums(tree)
        _shift_range_headers(tree)
        _inline_loop_temps(tree)
        inlined = _inline_numeric_globals(tree, fn, facts)
        out = tree.body
    except Exception:
        out, inlined = body, {}
    facts._normalized_body = out
    facts._inlined_globals = inlined
    return out


def inlined_globals(facts) -> dict:
    """The module-constant names and exact values the pre-pass inlined
    for this facts instance ({} before any lift ran, or when none
    were)."""
    return getattr(facts, "_inlined_globals", {}) or {}


def _strip_docstring_stmts(body: list) -> list:
    if (body and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        return body[1:]
    return body



def _lambda_subst(lam: ast.Lambda, args: list) -> "ast.expr | None":
    """Intent:
        The lambda's body with its parameters replaced by the given
        argument expressions, inline beta-reduction for the map/
        filter desugar. None when the lambda's signature is anything
        beyond plain positional parameters.
    """
    if (lam.args.posonlyargs or lam.args.kwonlyargs or lam.args.vararg
            or lam.args.kwarg or lam.args.defaults):
        return None
    names = [a.arg for a in lam.args.args]
    if len(names) != len(args):
        return None
    mapping = dict(zip(names, args))

    class _Sub(ast.NodeTransformer):
        def visit_Name(self, node):
            if isinstance(node.ctx, ast.Load) and node.id in mapping:
                return copy.deepcopy(mapping[node.id])
            return node
    return ast.fix_missing_locations(_Sub().visit(copy.deepcopy(lam.body)))


def _as_genexp(call: ast.Call) -> "ast.GeneratorExp | None":
    """Intent:
        The generator expression a `sum(...)` argument amounts to:
        the genexp itself, a bare name (`sum(xs)` reads as
        `sum(v for v in xs)`), or a `map`/`filter` over a lambda or
        name, folded to the equivalent genexp. None for anything
        else.
    """
    if len(call.args) != 1 or call.keywords:
        return None
    (arg,) = call.args
    if isinstance(arg, ast.GeneratorExp):
        return arg
    fresh = ast.Name(id="_elt", ctx=ast.Load())
    target = ast.Name(id="_elt", ctx=ast.Store())
    if isinstance(arg, ast.Name):
        return ast.GeneratorExp(elt=fresh, generators=[
            ast.comprehension(target=target, iter=arg, ifs=[], is_async=0)])
    if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name) \
            and arg.func.id in ("map", "filter") and len(arg.args) == 2 \
            and not arg.keywords:
        fnode, seq = arg.args
        if isinstance(fnode, ast.Lambda):
            applied = _lambda_subst(fnode, [fresh])
            if applied is None:
                return None
        elif isinstance(fnode, ast.Name):
            applied = ast.Call(func=copy.deepcopy(fnode), args=[fresh],
                               keywords=[])
        else:
            return None
        if arg.func.id == "map":
            return ast.GeneratorExp(elt=applied, generators=[
                ast.comprehension(target=target, iter=seq, ifs=[],
                                  is_async=0)])
        return ast.GeneratorExp(elt=fresh, generators=[
            ast.comprehension(target=target, iter=seq, ifs=[applied],
                              is_async=0)])
    return None


def _desugar_comprehension_sums(tree: ast.Module) -> None:
    """`total = sum(x*x for x in xs)` (and `return sum(...)`,
    `acc += sum(...)`; `sum(xs)`, `sum(map(g, xs))`,
    `sum(filter(p, xs))` likewise) rewritten to the explicit
    accumulator loop every loop recognizer already reads:

        _sum0 = 0.0
        for x in xs:
            _sum0 = _sum0 + x*x
        <original statement, the call replaced by _sum0>

    Multi-generator expressions nest their loops; an `if` filter
    becomes the loop-body If (the conditional-summand shape). Only
    async-free generators over the statement's own scope rewrite;
    anything else is left exactly as written."""
    counter = [0]

    def _hoist(stmt) -> "list | None":
        hoisted: list = []

        class _Rw(ast.NodeTransformer):
            def visit_Call(self, node):
                self.generic_visit(node)
                if not (isinstance(node.func, ast.Name)
                        and node.func.id == "sum"):
                    return node
                gen = _as_genexp(node)
                if gen is None or any(g.is_async for g in gen.generators):
                    return node
                acc = f"_sum{counter[0]}"
                counter[0] += 1
                update: ast.stmt = ast.AugAssign(
                    target=ast.Name(id=acc, ctx=ast.Store()),
                    op=ast.Add(), value=gen.elt)
                for g in reversed(gen.generators):
                    inner: ast.stmt = update
                    for test in reversed(g.ifs):
                        inner = ast.If(test=test, body=[inner], orelse=[])
                    update = ast.For(target=g.target, iter=g.iter,
                                     body=[inner], orelse=[])
                hoisted.append(ast.Assign(
                    targets=[ast.Name(id=acc, ctx=ast.Store())],
                    value=ast.Constant(value=0.0)))
                hoisted.append(update)
                return ast.Name(id=acc, ctx=ast.Load())

        new_stmt = _Rw().visit(stmt)
        if not hoisted:
            return None
        return [*hoisted, new_stmt]

    out: list = []
    for stmt in tree.body:
        expanded = None
        if isinstance(stmt, (ast.Assign, ast.AugAssign, ast.Return)) \
                and getattr(stmt, "value", None) is not None:
            expanded = _hoist(stmt)
        out.extend(expanded if expanded is not None else [stmt])
    tree.body = out
    ast.fix_missing_locations(tree)


def _expand_tuple_unpacks(tree) -> None:
    """Intent:
        `ax, ay = e1, e2` -> sequential assignments, with temporaries
        first whenever a target name also appears on the right (the
        swap case) so the simultaneous semantics survive. Only
        Name-target/Tuple-value pairs of equal length are touched.
    """
    class _Expander(ast.NodeTransformer):
        def _expand(self, stmts):
            out = []
            for st in stmts:
                st = self.visit(st)
                if (isinstance(st, ast.Assign) and len(st.targets) == 1
                        and isinstance(st.targets[0], ast.Tuple)
                        and isinstance(st.value, ast.Tuple)
                        and len(st.targets[0].elts) == len(st.value.elts)
                        and all(isinstance(t, ast.Name)
                                for t in st.targets[0].elts)):
                    targets = [t.id for t in st.targets[0].elts]
                    rhs_names = {n.id for v in st.value.elts
                                 for n in ast.walk(v)
                                 if isinstance(n, ast.Name)}
                    if rhs_names & set(targets):
                        temps = []
                        for i, v in enumerate(st.value.elts):
                            tmp = f"_unpack{i}_{targets[i]}"
                            temps.append(tmp)
                            out.append(ast.Assign(
                                targets=[ast.Name(id=tmp, ctx=ast.Store())],
                                value=v))
                        for name, tmp in zip(targets, temps):
                            out.append(ast.Assign(
                                targets=[ast.Name(id=name, ctx=ast.Store())],
                                value=ast.Name(id=tmp, ctx=ast.Load())))
                    else:
                        for name, v in zip(targets, st.value.elts):
                            out.append(ast.Assign(
                                targets=[ast.Name(id=name, ctx=ast.Store())],
                                value=v))
                else:
                    out.append(st)
            return out

        def visit_Module(self, node):
            node.body = self._expand(node.body)
            return node

        def visit_For(self, node):
            node.body = self._expand(node.body)
            node.orelse = self._expand(node.orelse)
            return node

        def visit_If(self, node):
            node.body = self._expand(node.body)
            node.orelse = self._expand(node.orelse)
            return node

    _Expander().visit(tree)
    ast.fix_missing_locations(tree)


def _shift_range_headers(tree) -> None:
    """Intent:
        `for i in range(a, b[, s])` (s a positive int literal) ->
        `for i in range(<trip>)` with every read of i in the body
        rewritten to `a + s*i`. Trip count matches Python's own range
        semantics for positive step: `b - a` for s == 1, else
        `(b - a + s - 1) // s`. Skipped whenever the body itself
        assigns the loop variable.
    """
    for node in ast.walk(tree):
        if not (isinstance(node, ast.For) and isinstance(node.target, ast.Name)
                and isinstance(node.iter, ast.Call)
                and isinstance(node.iter.func, ast.Name)
                and node.iter.func.id == "range"
                and len(node.iter.args) in (2, 3)
                and not node.iter.keywords):
            continue
        args = node.iter.args
        start = args[0]
        stop = args[1]
        if isinstance(start, ast.Constant) and start.value == 0 \
                and len(args) == 2:
            node.iter.args = [stop]
            continue
        step = 1
        if len(args) == 3:
            if not (isinstance(args[2], ast.Constant)
                    and isinstance(args[2].value, int)
                    and args[2].value >= 1):
                continue
            step = args[2].value
        var = node.target.id
        assigned = {t.id for st in ast.walk(ast.Module(body=node.body,
                                                       type_ignores=[]))
                    if isinstance(st, ast.Assign)
                    for t in st.targets if isinstance(t, ast.Name)}
        assigned |= {st.target.id for st in ast.walk(
            ast.Module(body=node.body, type_ignores=[]))
            if isinstance(st, ast.AugAssign)
            and isinstance(st.target, ast.Name)}
        if var in assigned:
            continue
        span = ast.BinOp(left=stop, op=ast.Sub(), right=copy.deepcopy(start))
        if step == 1:
            trip = span
        else:
            padded = ast.BinOp(left=span, op=ast.Add(),
                               right=ast.Constant(value=step - 1))
            trip = ast.BinOp(left=padded, op=ast.FloorDiv(),
                             right=ast.Constant(value=step))
        node.iter.args = [trip]

        scaled = (ast.Name(id=var, ctx=ast.Load()) if step == 1 else
                  ast.BinOp(left=ast.Constant(value=step), op=ast.Mult(),
                            right=ast.Name(id=var, ctx=ast.Load())))
        shifted = ast.BinOp(left=copy.deepcopy(start), op=ast.Add(),
                            right=scaled)

        class _Shift(ast.NodeTransformer):
            def visit_Name(self, n):
                if n.id == var and isinstance(n.ctx, ast.Load):
                    return copy.deepcopy(shifted)
                return n

        node.body = [_Shift().visit(st) for st in node.body]
    ast.fix_missing_locations(tree)


def _inline_loop_temps(tree) -> None:
    """Intent:
        Leading `temp = expr` statements inside a loop body fold into
        their use sites when provably iteration-local: the temp is
        assigned exactly once (first), never read before it, never
        used outside the loop, and no name `expr` reads is assigned
        elsewhere in the body. A temp read across iterations is a
        second accumulator and stays.
    """
    for loop in ast.walk(tree):
        if not isinstance(loop, ast.For):
            continue
        while len(loop.body) > 1:
            first = loop.body[0]
            if not (isinstance(first, ast.Assign) and len(first.targets) == 1
                    and isinstance(first.targets[0], ast.Name)):
                break
            temp = first.targets[0].id
            rest = loop.body[1:]
            rest_mod = ast.Module(body=rest, type_ignores=[])
            assigned_in_rest = set()
            for st in ast.walk(rest_mod):
                if isinstance(st, ast.Assign):
                    assigned_in_rest |= {t.id for t in st.targets
                                         if isinstance(t, ast.Name)}
                elif isinstance(st, (ast.AugAssign, ast.AnnAssign)) \
                        and isinstance(st.target, ast.Name):
                    assigned_in_rest.add(st.target.id)
            if temp in assigned_in_rest:
                break
            expr_names = {n.id for n in ast.walk(first.value)
                          if isinstance(n, ast.Name)}
            if expr_names & assigned_in_rest:
                break
            # the temp must be local to this loop: no reference
            # anywhere else in the function
            outside = ast.Module(
                body=[st for st in tree.body], type_ignores=[])
            uses_outside = any(
                isinstance(n, ast.Name) and n.id == temp
                and not _within(loop, n)
                for n in ast.walk(outside))
            if uses_outside:
                break

            class _Sub(ast.NodeTransformer):
                def visit_Name(self, n):
                    if n.id == temp and isinstance(n.ctx, ast.Load):
                        return copy.deepcopy(first.value)
                    return n

            loop.body = [_Sub().visit(st) for st in rest]
    ast.fix_missing_locations(tree)


def _within(container: ast.AST, node: ast.AST) -> bool:
    return any(n is node for n in ast.walk(container))


def _inline_numeric_globals(tree, fn, facts) -> dict:
    """Intent:
        Replace a Name read that resolves to a plain int/float in the
        function's own module globals with its exact current value,
        returning {name: value}. Only names analysis already
        classified as global-variable reads are candidates, locals,
        params, and callables are untouched, and anything non-numeric
        stays exactly as written.
    """
    g = getattr(fn, "__globals__", {}) or {}
    candidates = {}
    for name in getattr(facts, "global_vars", []) or []:
        value = g.get(name)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            candidates[name] = value
    if not candidates:
        return {}
    inlined: dict = {}

    class _Inline(ast.NodeTransformer):
        def visit_Name(self, n):
            if n.id in candidates and isinstance(n.ctx, ast.Load):
                inlined[n.id] = candidates[n.id]
                return ast.Constant(value=candidates[n.id])
            return n

    _Inline().visit(tree)
    ast.fix_missing_locations(tree)
    return inlined
