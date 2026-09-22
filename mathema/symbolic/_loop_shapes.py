# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Loop-header shape recognizers shared by `.fold` and `.sum`: what does
this `for` loop's target/iterable actually look like? One-directional
dependency on `._base` only (for `_literal_int_index`); `._base` has
no dependency back on this module, so this is an ordinary top-level
import, not a cycle-breaking lazy one. `.dot` doesn't use this module at
all; it isn't loop-shaped (it pattern-matches a bare `np.dot(...)` call
directly).
"""
from __future__ import annotations

import ast

from ._base import _literal_int_index


def bare_seq_name(node: ast.AST, seq_param: str) -> bool:
    return isinstance(node, ast.Name) and node.id == seq_param


def seq_one_colon(node: ast.AST, seq_param: str) -> bool:
    """Is `node` exactly `<seq_param>[1:]`, a plain slice from index 1 to
    the end, no step, nothing computed?"""
    return (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name)
            and node.value.id == seq_param and isinstance(node.slice, ast.Slice)
            and node.slice.lower is not None and _literal_int_index(node.slice.lower) == 1
            and node.slice.upper is None and node.slice.step is None)


def _references_name(node: ast.AST, name: str) -> bool:
    return any(isinstance(n, ast.Name) and n.id == name for n in ast.walk(node))


def _update_rhs(stmt: ast.AST, acc_name: str) -> ast.AST | None:
    """The loop body's one statement, as a single expression node giving
    the accumulator's new value, `acc = <expr>` yields `<expr>`
    directly; `acc <op>= <expr>` (`total += v`) yields the equivalent
    `acc <op> <expr>` BinOp, since analysis.py's own fold detection
    already treats the two as the same shape (`op_source` normalizes an
    AugAssign the same way). `None` if `stmt` doesn't update `acc_name`
    at all, or updates something else."""
    if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 \
            and isinstance(stmt.targets[0], ast.Name) and stmt.targets[0].id == acc_name:
        return stmt.value
    if isinstance(stmt, ast.AugAssign) and isinstance(stmt.target, ast.Name) \
            and stmt.target.id == acc_name:
        return ast.BinOp(left=ast.Name(id=acc_name, ctx=ast.Load()),
                         op=stmt.op, right=stmt.value)
    return None


def classify_loop_header(for_stmt: ast.For, seq_params: set) -> tuple | None:
    """Classify a single `for` statement's target/iterable shape for
    the general sum recognizer; one of four forms, or `None` if it's
    none of them (a loop over a computed/local iterable, a
    sequence not among the function's own parameters, an unpacking
    shape other than plain `i, item`, ...). Returns `(kind, seq_name,
    item_name, idx_name)`; `seq_name` is a plain string for every
    kind except `"scalar_index"`, where it's the raw AST node for the
    loop's own trip-count expression instead (see below):

    - `"item"`: `for item in seq:`, binds `item` to `seq[k]` for a
      fresh index `k`.
    - `"index"`: `for i in range(len(seq)):`, binds `i` directly to
      the fresh index itself, so the loop body can subscript *any* of
      the function's sequence parameters by it (`a[i]`, `b[i]`); this
      is what makes a hand-written dot product (`total += a[i]*b[i]`)
      recognizable directly from loop structure, not only via a literal
      `np.dot(...)` call (see lift_dot()).
    - `"enumerate"`: `for i, item in enumerate(seq):`, both bindings
      at once.
    - `"scalar_index"`: `for i in range(<expr>):` / `for _ in
      range(<expr>):`, where `<expr>` ISN'T the `len(seq)` shape
      `"index"` above already covers, no sequence involved at all,
      `i` bound directly to the fresh index (same as `"index"`, minus a
      sequence to subscript). The trip count can be any expression, not
      just a bare name (`range(n)`, `range(n + 1)`, `range(2 * n)`,
      ...): this function has no parameter list to check it against
      (only `seq_params`), so it's returned as the raw AST node in
      `seq_name`'s slot rather than pre-validated here; the caller lifts
      it via `_expr_to_sympy` against its own `env`, which naturally
      declines whatever isn't actually liftable, no separate
      affine/shape restriction needed at classification time, since
      `Sum`'s own upper bound (or `lift_fold()`'s telescoping `length`)
      places no degree restriction on the trip count itself, unlike a
      branch condition's corner-evaluation."""
    it = for_stmt.iter
    if isinstance(for_stmt.target, ast.Name) and isinstance(it, ast.Name) \
            and it.id in seq_params:
        return ("item", it.id, for_stmt.target.id, None)
    if isinstance(for_stmt.target, ast.Name) and isinstance(it, ast.Call) \
            and isinstance(it.func, ast.Name) and it.func.id == "range" \
            and len(it.args) == 1 and not it.keywords:
        arg = it.args[0]
        if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name) \
                and arg.func.id == "len" and len(arg.args) == 1 and not arg.keywords \
                and isinstance(arg.args[0], ast.Name) and arg.args[0].id in seq_params:
            return ("index", arg.args[0].id, None, for_stmt.target.id)
        return ("scalar_index", arg, None, for_stmt.target.id)
    if isinstance(for_stmt.target, ast.Tuple) and len(for_stmt.target.elts) == 2 \
            and all(isinstance(e, ast.Name) for e in for_stmt.target.elts) \
            and isinstance(it, ast.Call) and isinstance(it.func, ast.Name) \
            and it.func.id == "enumerate" and len(it.args) == 1 and not it.keywords \
            and isinstance(it.args[0], ast.Name) and it.args[0].id in seq_params:
        idx_name, item_name = (e.id for e in for_stmt.target.elts)
        return ("enumerate", it.args[0].id, item_name, idx_name)
    return None
