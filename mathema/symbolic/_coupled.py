# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Two linearly coupled accumulators, closed by the matrix power.

The iterative twin of `_recurrence`'s rsolve lift: a loop over
``range(<trip>)`` updating exactly two accumulators, each new value a
LINEAR combination of both old values plus a constant, with numeric
literal coefficients, the Fibonacci pair, a running sum feeding a
running sum-of-sums. Writing the state as a vector, one iteration is
``s' = M s + c``, so after n iterations

    s_n = M^n s_0 + (M^n - I)(M - I)^{-1} c

exactly. ``M^n`` at symbolic n comes from diagonalization (eigenvalues
raised elementwise), so the closed form is exact algebra, never an
approximation; a non-diagonalizable matrix, a singular ``M - I``
alongside a nonzero constant, or any non-literal coefficient declines
rather than guessing. Nonlinear coupling (the Putnam telescoping
shape) never matches the linear extraction and stays honestly out.
"""
from __future__ import annotations

import ast

import sympy

from .._timeout import FAST_TIMEOUT_SECONDS, _with_timeout
from ._base import Lifted, NotSymbolic, _bind_params, _expr_to_sympy
from ._normalize import normalized_body


def lift_coupled(fn, facts) -> "Lifted | None":
    """Recognize and close the two-accumulator linear loop, or None.
    Shape: [a init; b init; for _ in range(trip): <linear simultaneous
    update of a, b>; return <expr over a, b, params>], every update
    coefficient a numeric literal."""
    if facts.tree is None or facts.recursion or facts.branch_count:
        return None
    if len(facts.loops) != 1:
        return None
    body = normalized_body(fn, facts)
    if len(body) != 4:
        return None
    init_a, init_b, loop, ret = body
    if not (isinstance(init_a, ast.Assign) and isinstance(init_b, ast.Assign)
            and isinstance(loop, ast.For) and isinstance(ret, ast.Return)
            and ret.value is not None):
        return None
    if not all(len(st.targets) == 1 and isinstance(st.targets[0], ast.Name)
               for st in (init_a, init_b)):
        return None
    a_name, b_name = init_a.targets[0].id, init_b.targets[0].id
    if a_name == b_name:
        return None
    if not (isinstance(loop.iter, ast.Call)
            and isinstance(loop.iter.func, ast.Name)
            and loop.iter.func.id == "range" and len(loop.iter.args) == 1
            and not loop.iter.keywords):
        return None
    if not isinstance(loop.target, ast.Name):
        return None
    idx_name = loop.target.id
    # the loop variable must not feed the updates: a k-dependent update
    # is not a constant-coefficient recurrence
    if any(isinstance(n, ast.Name) and n.id == idx_name
           for st in loop.body for n in ast.walk(st)):
        return None

    params, aggregate = _bind_params(fn, facts)
    a_sym = sympy.Symbol(f"_acc_{a_name}", real=True)
    b_sym = sympy.Symbol(f"_acc_{b_name}", real=True)

    try:
        trip = _expr_to_sympy(loop.iter.args[0], dict(params))
        env = dict(params)
        a0 = _expr_to_sympy(init_a.value, env)
        env[a_name] = a0
        b0 = _expr_to_sympy(init_b.value, env)
    except NotSymbolic:
        return None
    if any(isinstance(v, tuple) for v in (trip, a0, b0)):
        return None

    # simulate one iteration symbolically over the state symbols: the
    # (normalized) body is straight-line assignments, so sequential
    # substitution yields each accumulator's new value in terms of the
    # old state
    env = {**params, a_name: a_sym, b_name: b_sym}
    for st in loop.body:
        if not (isinstance(st, ast.Assign) and len(st.targets) == 1
                and isinstance(st.targets[0], ast.Name)) and not (
                isinstance(st, ast.AugAssign)
                and isinstance(st.target, ast.Name)):
            return None
        try:
            if isinstance(st, ast.AugAssign):
                delta = _expr_to_sympy(st.value, env)
                current = env.get(st.target.id)
                if current is None or isinstance(delta, tuple):
                    return None
                op = type(st.op)
                if op is ast.Add:
                    value = current + delta
                elif op is ast.Sub:
                    value = current - delta
                elif op is ast.Mult:
                    value = current * delta
                else:
                    return None
                env[st.target.id] = value
            else:
                value = _expr_to_sympy(st.value, env)
                if isinstance(value, tuple):
                    return None
                env[st.targets[0].id] = value
        except NotSymbolic:
            return None
    new_a, new_b = env.get(a_name), env.get(b_name)
    if new_a is None or new_b is None:
        return None

    def _linear_coeffs(expr):
        # expr must be exactly alpha*a + beta*b + gamma with NUMERIC
        # alpha/beta/gamma
        try:
            poly = sympy.Poly(sympy.expand(expr), a_sym, b_sym)
        except sympy.PolynomialError:
            return None
        if poly.total_degree() > 1:
            return None
        alpha = poly.coeff_monomial(a_sym)
        beta = poly.coeff_monomial(b_sym)
        gamma = poly.coeff_monomial(1)
        if not all(getattr(v, "is_number", False)
                   for v in (alpha, beta)):
            return None
        if not getattr(gamma, "is_number", False):
            return None
        return alpha, beta, gamma

    row_a = _linear_coeffs(new_a)
    row_b = _linear_coeffs(new_b)
    if row_a is None or row_b is None:
        return None
    # genuinely COUPLED only: a decoupled pair is lift_sum's territory
    if row_a[1] == 0 and row_b[0] == 0:
        return None

    m = sympy.Matrix([[row_a[0], row_a[1]], [row_b[0], row_b[1]]])
    c = sympy.Matrix([row_a[2], row_b[2]])
    n = sympy.Symbol("_trip", integer=True, nonnegative=True)
    try:
        closed = _with_timeout(lambda: _matrix_power_closed(m, c, a0, b0, n),
                               FAST_TIMEOUT_SECONDS)
    except Exception:
        return None
    if closed is None:
        return None
    a_n, b_n = closed

    try:
        ret_expr = _expr_to_sympy(ret.value, {**params, a_name: a_sym,
                                              b_name: b_sym})
    except NotSymbolic:
        return None
    if isinstance(ret_expr, tuple):
        return None
    # range(trip) runs max(trip, 0) times
    final = ret_expr.subs({a_sym: a_n, b_sym: b_n}).subs(n, sympy.Max(trip, 0))
    try:
        final = _with_timeout(lambda: sympy.simplify(final),
                              FAST_TIMEOUT_SECONDS)
    except Exception:
        pass

    from ..grammar import render_canonical
    return Lifted(expr=final, params=params, sig_params=list(facts.params),
                  aggregate=aggregate, unicode=render_canonical(final)[0],
                  latex=sympy.latex(final))


def _matrix_power_closed(m, c, a0, b0, n):
    """Intent:
        The exact state after n iterations of `s' = M s + c` from
        `s_0 = (a0, b0)`: diagonalize for `M^n`, geometric-series the
        affine part when `M - I` is invertible; None whenever either
        piece has no clean closed form.
    """
    try:
        p, d = m.diagonalize()
    except sympy.matrices.exceptions.NonSquareMatrixError:
        return None
    except Exception:
        return None
    d_n = sympy.diag(*[val ** n for val in d.diagonal()])
    m_n = p * d_n * p.inv()
    s0 = sympy.Matrix([a0, b0])
    s_n = m_n * s0
    if c != sympy.zeros(2, 1):
        shifted = m - sympy.eye(2)
        if shifted.det() == 0:
            return None
        s_n = s_n + (m_n - sympy.eye(2)) * shifted.inv() * c
    s_n = sympy.simplify(s_n)
    return s_n[0], s_n[1]
