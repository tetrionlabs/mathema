# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Point evaluation of the indexed call forms `Sum(expr, k, lo, hi)` and
`Prod(expr, k, lo, hi)`: at a concrete point both bounds are numbers,
so the form is a finite loop over the integer index, and every term is
an executed call.

A law is rewritten so each form reads `Sum(lambda k: expr, lo, hi)`,
the index bound over the summand only (shadowing a parameter of the
same name there, as the derive route reads it), and `indexed_total`
runs the loop."""
from __future__ import annotations

import ast
import math

# the call forms this module executes
INDEXED_FORMS = ("Sum", "Prod")

# the most terms one executed Sum/Prod visits
INDEXED_TERM_CAP = 10_000


def _whole(value) -> int:
    """Intent:
        `value` as an int when it is a whole real number.

    Raises:
        ValueError: a bool, a non-number, or a number with a fractional
            part or no finite value.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"an index bound must be a whole number, not {value!r}")
    if isinstance(value, float) and not (math.isfinite(value)
                                         and value.is_integer()):
        raise ValueError(f"an index bound must be a whole number, not {value!r}")
    return int(value)


def indexed_total(form: str, term, lo, hi):
    """Intent:
        The `Sum` (or `Prod`, per `form`) of `term(k)` for every integer
        k from `lo` to `hi` inclusive, in increasing k. `hi == lo - 1`
        is the empty range, 0 for a sum and 1 for a product. A sum of
        ints is exact; any other sum is `math.fsum`, the correctly
        rounded sum of the executed values.

    Raises:
        ValueError: a bound that is not a whole number, a range with
            `hi < lo - 1` (the reversed-range convention is not
            evaluated), or more than `INDEXED_TERM_CAP` terms.
    """
    lo, hi = _whole(lo), _whole(hi)
    if hi < lo - 1:
        raise ValueError(f"reversed index range {lo}..{hi}")
    if hi - lo + 1 > INDEXED_TERM_CAP:
        raise ValueError(f"{hi - lo + 1} terms exceed the executed-term cap")
    values = [term(k) for k in range(lo, hi + 1)]
    if form == "Prod":
        return math.prod(values)
    if all(isinstance(v, int) and not isinstance(v, bool) for v in values):
        return sum(values)
    return math.fsum(values)


class _Rewrite(ast.NodeTransformer):
    """`Sum(expr, k, lo, hi)` -> `Sum(lambda k: expr, lo, hi)`, innermost
    first, recording each index name in `indices`."""

    def __init__(self):
        self.indices: set[str] = set()
        self.malformed = False

    def visit_Call(self, node):
        self.generic_visit(node)
        if not (isinstance(node.func, ast.Name)
                and node.func.id in INDEXED_FORMS):
            return node
        if len(node.args) != 4 or node.keywords \
                or not isinstance(node.args[1], ast.Name):
            self.malformed = True
            return node
        body, index, lo, hi = node.args
        self.indices.add(index.id)
        term = ast.Lambda(
            args=ast.arguments(posonlyargs=[], args=[ast.arg(arg=index.id)],
                               vararg=None, kwonlyargs=[], kw_defaults=[],
                               kwarg=None, defaults=[]),
            body=body)
        return ast.Call(func=node.func, args=[term, lo, hi], keywords=[])


def _free_names(node, bound: frozenset = frozenset()) -> set[str]:
    """Every Name in `node` not bound by an enclosing lambda."""
    if isinstance(node, ast.Lambda):
        inner = bound | {a.arg for a in node.args.args}
        return _free_names(node.body, inner)
    if isinstance(node, ast.Name):
        return set() if node.id in bound else {node.id}
    out: set[str] = set()
    for child in ast.iter_child_nodes(node):
        out |= _free_names(child, bound)
    return out


def uses_indexed_form(src: str | None) -> bool:
    """Whether the law text calls `Sum` or `Prod`."""
    if not src:
        return False
    try:
        tree = ast.parse(src, mode="eval")
    except SyntaxError:
        return False
    return any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
               and n.func.id in INDEXED_FORMS for n in ast.walk(tree))


def compile_indexed(src: str, aux: set[str]):
    """Intent:
        Compile an already validated law that calls `Sum`/`Prod` for
        point evaluation: `(code, aux, bound)`, where `code` evaluates
        with `Sum`/`Prod` bound to `indexed_total` (see `indexed_env`),
        `aux` narrows the validated auxiliary names to those still free
        once each index is bound, and `bound` names every index that
        occurs nowhere free in the law.

    Raises:
        ValueError: a `Sum`/`Prod` call that is not (expr, bare index
            name, lo, hi).
    """
    tree = ast.parse(src, mode="eval")
    rewrite = _Rewrite()
    tree = ast.fix_missing_locations(rewrite.visit(tree))
    if rewrite.malformed:
        raise ValueError(f"Sum/Prod takes (expr, index, lo, hi): {src!r}")
    free = _free_names(tree)
    return (compile(tree, "<conjecture>", "eval"), set(aux) & free,
            rewrite.indices - free)


def indexed_env() -> dict:
    """The evaluation bindings for `Sum` and `Prod` in a rewritten law."""
    return {form: (lambda term, lo, hi, _form=form:
                   indexed_total(_form, term, lo, hi))
            for form in INDEXED_FORMS}
