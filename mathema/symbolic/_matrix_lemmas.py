# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Lemmas of real matrix algebra that sympy does not apply on its own.

sympy's matrix expressions know that a transpose reverses a product
and that a determinant is multiplicative, but not that a trace is
invariant under a cyclic permutation of its product, that `@`
distributes over `+`, or that `A @ A.T` is positive semidefinite. Each
fact here holds for real matrices of every size, so a claim closed
through one is proven for a symbolic `n`, not sampled.

Three kinds of fact live here, each used by `symbolic/_matrix.py`:

- **Words the lift reads through a lemma**: `sum(eigvals(X))` is
  `trace(X)`, `prod(eigvals(X))` is `det(X)` (the eigenvalues counted
  with algebraic multiplicity), and `rank(X)` is a number.
- **Rewrites before the sides are compared**: `@` distributed over
  `+`, a trace spelled by the least cyclic rotation of its product
  (and of its transpose), the rank of a Gram product `X @ X.T` read as
  the rank of `X`, and, for an ordering, a trace, determinant or
  quadratic form of a positive semidefinite matrix read as a
  nonnegative number.
- **Structure**: which of the registry's structure properties
  (symmetric, triangular, diagonal, orthogonal, positive
  (semi)definite, skew-symmetric) an expression has, from the
  properties its operands are given. The rules are this module's own:
  sympy's `ask(Q.symmetric(A*B), Q.symmetric(A) & Q.symmetric(B))`
  answers True, which is false for matrices that do not commute.

Every rewrite is an equality or a weakening (a quantity replaced by a
symbol that keeps only its sign), so a relation closed after them
holds of the original claim. A relation they do not close is left to
the caller, which never reads that as a disproof.
"""
from __future__ import annotations

import ast

import sympy

__all__ = ["LemmaTable", "lift_lemma_call", "normalise", "prove_structure",
           "structure_of", "structure_properties"]

#: the internal property of an invertible matrix, beside the registry's
_INVERTIBLE = "invertible"

#: every structure property the inference below can establish
_STRUCTURE_PROPERTIES = frozenset({
    "is_symmetric", "is_skew_symmetric", "is_diagonal",
    "is_upper_triangular", "is_lower_triangular", "is_identity",
    "is_orthogonal", "is_positive_definite", "is_positive_semidefinite",
})


class LemmaTable:
    """The shared state of one comparison: the scalar symbol chosen for
    each quantity the lemmas make opaque (a rank, a nonnegative trace),
    keyed by the quantity's canonical form so both sides share it, and
    the names of the lemmas used, for the proof's sketch."""

    def __init__(self, known: dict, invertible: frozenset):
        self.known = known
        self.invertible = invertible
        self.symbols: dict = {}
        self.used: list = []

    def transpose(self, term):
        """`term.T`, with the transpose of a symmetric matrix symbol
        read as the symbol itself."""
        out = sympy.Transpose(term).doit()
        fixed = {sympy.Transpose(m): m for m, props in self.known.items()
                 if "is_symmetric" in props}
        return out.xreplace(fixed) if fixed else out

    def use(self, lemma: str) -> None:
        if lemma not in self.used:
            self.used.append(lemma)

    def symbol(self, kind: str, quantity, **assumptions):
        key = (kind, sympy.srepr(quantity))
        if key not in self.symbols:
            self.symbols[key] = sympy.Symbol(f"<{kind} {quantity}>",
                                             real=True, **assumptions)
        return self.symbols[key]


# --- words read through a lemma ---------------------------------------

class Rank(sympy.Function):
    """The rank of a matrix expression, a number the lemmas below
    rewrite and finally make opaque."""

    is_integer = True
    is_nonnegative = True


def lift_lemma_call(node: ast.Call, lift):
    """The lifted term for a call the lemma layer reads, or None.

    Intent:
        `sum(eigvals(X))` is `trace(X)` and `prod(eigvals(X))` is
        `det(X)`: the eigenvalues of a square matrix, counted with
        algebraic multiplicity, sum to its trace and multiply to its
        determinant. `rank(X)` is the rank of `X`. `lift` lifts an
        argument node the way the caller does.

    Raises:
        ValueError: an argument that is not a square matrix.
    """
    if not isinstance(node.func, ast.Name) or node.keywords \
            or len(node.args) != 1:
        return None
    name = node.func.id
    arg = node.args[0]
    if name in ("sum", "prod") and isinstance(arg, ast.Call) \
            and isinstance(arg.func, ast.Name) and arg.func.id == "eigvals" \
            and len(arg.args) == 1 and not arg.keywords:
        inner = _square(lift(arg.args[0]), arg.args[0])
        return sympy.Trace(inner) if name == "sum" else \
            sympy.Determinant(inner)
    if name == "rank":
        term = lift(arg)
        if not isinstance(term, sympy.MatrixExpr):
            raise ValueError(f"{ast.unparse(arg)!r} is not a matrix")
        return Rank(term)
    return None


def _square(term, node):
    if not isinstance(term, sympy.MatrixExpr) \
            or term.shape[0] != term.shape[1]:
        raise ValueError(f"{ast.unparse(node)!r} is not a square matrix")
    return term


# --- rewrites before the sides are compared ---------------------------

def _factors(term) -> tuple:
    """`(coefficient, [matrix factors])` of a product, or of a single
    matrix read as a product of one."""
    if isinstance(term, sympy.MatMul):
        coeff, factors = term.as_coeff_matrices()
        return coeff, list(factors)
    return sympy.Integer(1), [term]


def _transposed(term):
    return sympy.Transpose(term).doit()


def _product(factors: list):
    return factors[0] if len(factors) == 1 else \
        sympy.MatMul(*factors).doit()


def _is_form(e) -> bool:
    from sympy.matrices.expressions.matexpr import MatrixElement
    return isinstance(e, MatrixElement) and e.parent.shape == (1, 1)


def _distribute(term, table: LemmaTable):
    """A matrix expression with every product of sums multiplied out,
    factor order kept: `(A + B) @ C` is `A @ C + B @ C`, and a small
    integer power of a sum is the product of its copies."""
    if isinstance(term, sympy.MatPow) and isinstance(term.base, sympy.MatAdd) \
            and term.exp.is_Integer and 2 <= term.exp <= 8:
        term = sympy.MatMul(*([term.base] * int(term.exp)), evaluate=False)
    if isinstance(term, sympy.MatAdd):
        return sympy.MatAdd(*(_distribute(t, table) for t in term.args)).doit()
    if isinstance(term, sympy.MatMul):
        coeff, factors = _factors(term)
        parts = [_distribute(f, table) for f in factors]
        choices = [p.args if isinstance(p, sympy.MatAdd) else (p,)
                   for p in parts]
        if all(len(c) == 1 for c in choices):
            return coeff * _product([c[0] for c in choices])
        table.use("distributivity of @ over +")
        import itertools
        return sympy.MatAdd(*(coeff * _product(list(pick))
                              for pick in itertools.product(*choices))).doit()
    if isinstance(term, sympy.Transpose):
        inner = _distribute(term.arg, table)
        return _transposed(inner)
    return term


def _expand(term, table: LemmaTable):
    """`term` with every matrix product distributed over the sums
    inside it: `A @ (B + C)` is `A @ B + A @ C`. A quadratic form (a
    1-by-1 product read as its number) is held apart, since evaluating
    one spells it as an explicit sum over its entries."""
    if not isinstance(term, sympy.Basic):
        return term
    held: dict = {}

    def hold(e):
        return held.setdefault(e, sympy.Dummy("form", real=True))
    evaluated = term.replace(_is_form, hold).doit()
    if isinstance(evaluated, sympy.MatrixExpr):
        evaluated = _distribute(evaluated, table)
    else:
        evaluated = evaluated.replace(
            lambda e: isinstance(e, (sympy.Trace, sympy.Determinant, Rank)),
            lambda e: (sympy.Trace(_distribute(e.arg, table)).doit()
                       if isinstance(e, sympy.Trace)
                       else e.func(_distribute(e.args[0], table))))
    return evaluated.xreplace({d: e for e, d in held.items()})


def _psd(term, table: LemmaTable) -> bool:
    return bool({"is_positive_semidefinite", "is_positive_definite"}
                & structure_of(term, table))


def _canonical_trace(trace, table: LemmaTable):
    """One spelling for every trace equal to this one by cyclicity and
    transposition: the trace of a product is unchanged by a cyclic
    rotation of its factors and by transposing the product, so the
    least of those spellings stands for all of them."""
    coeff, factors = _factors(trace.arg)
    if len(factors) < 2:
        if isinstance(trace.arg, sympy.Transpose):
            table.use("the trace of a transpose")
            return coeff * sympy.Trace(trace.arg.arg)
        return trace
    candidates = []
    for word in (factors, _factors(_transposed(_product(factors)))[1]):
        for k in range(len(word)):
            candidates.append(word[k:] + word[:k])
    best = min(candidates, key=lambda w: sympy.default_sort_key(
        sympy.MatMul(*w, evaluate=False)))
    if best != factors:
        table.use("trace cyclicity")
    return coeff * sympy.Trace(sympy.MatMul(*best, evaluate=False))


def _traces(expr, table: LemmaTable):
    return expr.replace(lambda e: isinstance(e, sympy.Trace),
                        lambda t: _canonical_trace(t, table))


def _gram_root(term):
    """`X` when `term` is `X @ X.T` or `X.T @ X` (a Gram product), for
    the rank lemma, else None."""
    coeff, factors = _factors(term)
    if coeff == 0 or len(factors) % 2:
        return None
    half = len(factors) // 2
    left, right = factors[:half], factors[half:]
    if [_transposed(f) for f in reversed(left)] == right:
        return _product(left)
    return None


def _ranks(expr, table: LemmaTable):
    """Every rank as an opaque number, after the rank of a Gram
    product is read as the rank of its factor and the rank of a
    transpose as the rank of the matrix: for a real `X`,
    `rank(X @ X.T) == rank(X.T @ X) == rank(X) == rank(X.T)`."""
    def reduce(r):
        arg = r.args[0]
        for _ in range(8):
            if isinstance(arg, sympy.Transpose):
                arg = arg.arg
                table.use("the rank of a transpose")
                continue
            root = _gram_root(arg)
            if root is None:
                break
            table.use("the rank of a Gram product")
            arg = root
        return table.symbol("rank", arg, integer=True, nonnegative=True)
    return expr.replace(lambda e: isinstance(e, Rank), reduce)


def _signed_quantities(expr, table: LemmaTable):
    """For an ordering: the trace and determinant of a positive
    semidefinite matrix, and a quadratic form `v.T @ M @ v` over one,
    as nonnegative numbers (positive, for a trace or determinant of a
    positive definite matrix)."""
    def definite(term) -> bool:
        return "is_positive_definite" in structure_of(term, table)

    def trace(t):
        coeff, factors = _factors(t.arg)
        words = [factors[k:] + factors[:k] for k in range(len(factors))]
        for word in words:
            m = _product(word)
            if _psd(m, table):
                table.use("a positive semidefinite trace is nonnegative")
                positive = definite(m)
                return coeff * table.symbol(
                    "trace", t, **({"positive": True} if positive
                                   else {"nonnegative": True}))
        return t

    def det(d):
        if _psd(d.arg, table):
            table.use("a positive semidefinite determinant is nonnegative")
            positive = definite(d.arg)
            return table.symbol("det", d, **({"positive": True} if positive
                                              else {"nonnegative": True}))
        return d

    def form(e):
        coeff, factors = _factors(e.parent)
        if len(factors) >= 2 and _transposed(factors[0]) == factors[-1]:
            middle = factors[1:-1]
            if not middle or _psd(_product(middle), table):
                table.use("a positive semidefinite quadratic form is "
                          "nonnegative")
                return coeff * table.symbol("form", e.parent,
                                            nonnegative=True)
        return e

    expr = expr.replace(lambda e: isinstance(e, sympy.Trace), trace)
    expr = expr.replace(lambda e: isinstance(e, sympy.Determinant), det)
    return expr.replace(_is_form, form)


def _forms_expanded(expr, table: LemmaTable):
    """Each 1-by-1 product (a quadratic form) distributed over the sums
    inside it, so each term is one form the sign lemmas can read."""
    from sympy.matrices.expressions.matexpr import MatrixElement

    def split(e):
        parent = _expand(e.parent, table)
        terms = parent.args if isinstance(parent, sympy.MatAdd) else (parent,)
        out = []
        for t in terms:
            coeff, factors = _factors(t)
            out.append(coeff * MatrixElement(_product(factors), 0, 0))
        return sympy.Add(*out)
    return expr.replace(_is_form, split)


def normalise(term, relation: str, table: LemmaTable):
    """`term` rewritten by the lemmas, ready for the caller to compare.

    Intent:
        Distribute `@` over `+`, spell every trace canonically, read
        each rank through the Gram and transpose lemmas, and, for an
        ordering (`>`, `>=`, `<`, `<=`), read the sign of every trace,
        determinant and quadratic form of a positive semidefinite
        matrix. Each step is an equality or keeps only a true sign, so
        a relation that closes on the result holds of `term`.
    """
    if not isinstance(term, sympy.Basic):
        return term
    ordering = relation in (">", ">=", "<", "<=")
    steps = [_expand, _forms_expanded, _traces, _ranks]
    if ordering:
        # read a sign both before the sides are evaluated (sympy
        # evaluates `det(A @ A.T)` to `det(A)*det(A.T)`, which hides the
        # Gram product) and after the products are distributed
        steps = [_signed_quantities, *steps, _signed_quantities]
    for step in steps:
        try:
            term = step(term, table)
        except (TypeError, ValueError, AttributeError, sympy.ShapeError):
            continue
    return term


# --- structure ---------------------------------------------------------

def _closure(props: set) -> set:
    """`props` with everything they entail: the registry's own
    entailments, and invertibility of an orthogonal, positive definite
    or identity matrix (a positive semidefinite invertible matrix is
    positive definite)."""
    from ..matrices import entailed
    out = set(entailed(props & _STRUCTURE_PROPERTIES)) | (props - _STRUCTURE_PROPERTIES)
    if out & {"is_orthogonal", "is_positive_definite", "is_identity"}:
        out.add(_INVERTIBLE)
    if {"is_positive_semidefinite", _INVERTIBLE} <= out:
        out |= set(entailed({"is_positive_definite"}))
    return out


def _is_sign(c, positive: bool) -> bool:
    try:
        ok = c.is_positive if positive else c.is_nonnegative
    except AttributeError:
        return False
    return ok is True


def _mirror(props: set) -> set:
    """The properties of a transpose, from those of the matrix."""
    swap = {"is_upper_triangular": "is_lower_triangular",
            "is_lower_triangular": "is_upper_triangular"}
    return {swap.get(p, p) for p in props}


def _scaled(props: set, c) -> set:
    """The properties of `c * X`, from those of `X`, for a real `c`."""
    out = props & {"is_symmetric", "is_skew_symmetric", "is_diagonal",
                   "is_upper_triangular", "is_lower_triangular"}
    if c in (1, -1) and "is_orthogonal" in props:
        out.add("is_orthogonal")
    if "is_positive_semidefinite" in props and _is_sign(c, positive=False):
        out.add("is_positive_semidefinite")
    if "is_positive_definite" in props and _is_sign(c, positive=True):
        out.add("is_positive_definite")
    if _INVERTIBLE in props and c.is_nonzero:
        out.add(_INVERTIBLE)
    return out


def _product_props(factors: list, table: LemmaTable) -> set:
    """The properties of a product of two or more matrices."""
    each = [structure_of(f, table) for f in factors]
    out: set = set()
    for prop in ("is_diagonal", "is_upper_triangular",
                 "is_lower_triangular", "is_orthogonal", _INVERTIBLE):
        if all(prop in p for p in each):
            out.add(prop)
    # a congruence `Y @ M @ Y.T`: the middle is read, the outer factors
    # mirror each other
    k = len(factors)
    half = k // 2
    left = factors[:half]
    right = factors[k - half:]
    if [table.transpose(f) for f in reversed(left)] == right:
        middle = factors[half:k - half]
        mid = structure_of(_product(middle), table) if middle else \
            _closure({"is_identity"})
        if "is_symmetric" in mid:
            out.add("is_symmetric")
        if "is_skew_symmetric" in mid:
            out.add("is_skew_symmetric")
        if "is_positive_semidefinite" in mid:
            out.add("is_positive_semidefinite")
        if "is_positive_definite" in mid and all(
                _INVERTIBLE in structure_of(f, table)
                and f.shape[0] == f.shape[1] for f in left):
            out.add("is_positive_definite")
    return out


def structure_of(term, table: LemmaTable) -> set:
    """Every structure property `term` provably has, as registry names
    (`is_symmetric`, ...) plus `invertible`.

    Intent:
        A matrix symbol has what its markers and premises give it; an
        identity has every property, a zero matrix every one an
        invertibility does not need. A transpose mirrors triangularity
        and keeps the rest. An inverse (of an invertible matrix) keeps
        symmetry, triangularity, diagonality, orthogonality and
        definiteness. A sum keeps the linear properties its terms
        share, and positive semidefiniteness (definiteness when one
        term is definite). A product keeps diagonality, triangularity,
        orthogonality and invertibility its factors share; a
        congruence `Y @ M @ Y.T` has the symmetry and semidefiniteness
        of `M`, and is definite when `M` is and every factor of `Y` is
        square and invertible. An integer power keeps what a product
        of copies keeps.
    """
    return _closure(_structure(term, table))


def _structure(term, table: LemmaTable) -> set:
    everything = set(_STRUCTURE_PROPERTIES) | {_INVERTIBLE}
    if isinstance(term, sympy.Identity):
        return everything - {"is_skew_symmetric"}
    if isinstance(term, sympy.ZeroMatrix):
        return {"is_symmetric", "is_skew_symmetric", "is_diagonal",
                "is_upper_triangular", "is_lower_triangular",
                "is_positive_semidefinite"}
    if isinstance(term, sympy.MatrixSymbol):
        props = set(table.known.get(term, ()))
        if term in table.invertible:
            props.add(_INVERTIBLE)
        return props
    if isinstance(term, sympy.Transpose):
        return _mirror(structure_of(term.arg, table))
    if isinstance(term, sympy.Inverse):
        inner = structure_of(term.arg, table)
        if _INVERTIBLE not in inner:
            return set()
        return inner & {"is_symmetric", "is_skew_symmetric", "is_diagonal",
                        "is_upper_triangular", "is_lower_triangular",
                        "is_orthogonal", "is_positive_definite",
                        "is_identity", _INVERTIBLE}
    if isinstance(term, sympy.MatAdd):
        each = [structure_of(t, table) for t in term.args]
        out = set.intersection(*each) & {
            "is_symmetric", "is_skew_symmetric", "is_diagonal",
            "is_upper_triangular", "is_lower_triangular",
            "is_positive_semidefinite"}
        if "is_positive_semidefinite" in out and any(
                "is_positive_definite" in p for p in each):
            out.add("is_positive_definite")
        # `X + X.T` is symmetric, `X - X.T` skew, for any square X
        if len(term.args) == 2:
            a, b = term.args
            if _transposed(a) == b:
                out.add("is_symmetric")
            elif _transposed(a) == -b:
                out.add("is_skew_symmetric")
        return out
    if isinstance(term, sympy.MatPow):
        k = term.exp
        if not (k.is_integer and k.is_number):
            return set()
        base = structure_of(term.base, table)
        if k < 0 and _INVERTIBLE not in base:
            return set()
        out = base & {"is_symmetric", "is_diagonal", "is_upper_triangular",
                      "is_lower_triangular", "is_orthogonal", _INVERTIBLE,
                      "is_positive_definite"}
        if k >= 0 and "is_positive_semidefinite" in base:
            out.add("is_positive_semidefinite")
        return out
    if isinstance(term, sympy.MatMul):
        coeff, factors = _factors(term)
        if coeff == 0:
            return _structure(sympy.ZeroMatrix(*term.shape), table)
        base = (structure_of(factors[0], table) if len(factors) == 1
                else _closure(_product_props(factors, table)))
        return _scaled(base, coeff)
    return set()


def prove_structure(prop: str, term, table: LemmaTable) -> bool:
    """Whether `term` provably has the structure property `prop`."""
    if prop not in _STRUCTURE_PROPERTIES:
        return False
    if not isinstance(term, sympy.MatrixExpr) \
            or term.shape[0] != term.shape[1]:
        return False
    return prop in structure_of(term.doit(), table)


def structure_properties() -> frozenset:
    """The structure predicates the derive route can establish."""
    return _STRUCTURE_PROPERTIES

