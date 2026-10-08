# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Symbolic proof of a linear-algebra identity.

A claim over matrix parameters, `det(A @ B) == det(A) * det(B)`,
`(A @ B).T == B.T @ A.T`, `trace(A + B) == trace(A) + trace(B)`, is an
identity of matrix algebra, not a fact about a function's body. sympy
already carries that algebra: this module lifts the claim's own
expressions to `sympy.MatrixSymbol` terms (dimensions from a `Shape`
marker or an `R^(n,n)` space form), turns structure premises into
sympy matrix assumptions (`Q.symmetric`, `Q.positive_definite`,
`Q.orthogonal`, ...), and decides the relation by refining both sides
under those assumptions and simplifying their difference.

The lift is deliberately narrow: the matrix vocabulary (`@`/`.T`/
`det`/`inv`/`trace`/`I(n)`/`matrix_power`/`dot`/`outer`/`kron`/
`solve`), elementwise `+`, `-`, `*` (the Hadamard product of two
matrices) and `**` (the elementwise power), scaling by a number, and
scalar arithmetic joining scalar results (a determinant or trace is a
scalar). A vector is a column, read by `@` the way numpy reads a 1-D
array, and a 1-by-1 result (`x.T @ A @ x`) is the number it holds. A
construct outside it returns `None`, and the caller falls back exactly
as any other undecided derive claim does.
"""
from __future__ import annotations

import ast

import sympy

from .._timeout import FAST_TIMEOUT_SECONDS, _with_timeout
from ..linalg import MATRIX_TOKENS, mentions_matrix_ops
from ._matrix_lemmas import (LemmaTable, lift_lemma_call, normalise,
                             prove_structure, structure_properties)
from ._proof_support import ProofResult

__all__ = ["MATRIX_TOKENS", "matrix_param_dims", "mentions_matrix_ops",
           "try_prove_matrix", "vector_param_dims"]

# registry property -> the sympy assumption predicate it maps to, for a
# structure premise or marker fed into refine(). A property with no
# sympy matrix predicate (triangular, finite) simply contributes no
# assumption, the proof proceeds without it.
_Q_FOR_PROPERTY = {
    "is_symmetric": lambda A: sympy.Q.symmetric(A),
    "is_positive_definite": lambda A: sympy.Q.positive_definite(A),
    "is_orthogonal": lambda A: sympy.Q.orthogonal(A),
    "is_diagonal": lambda A: sympy.Q.diagonal(A),
    "is_lower_triangular": lambda A: sympy.Q.lower_triangular(A),
    "is_upper_triangular": lambda A: sympy.Q.upper_triangular(A),
}

# a scalar-comparison relation -> the sympy assumption predicate that
# decides it on the refined difference (`det(A) > 0` becomes
# `ask(Q.positive(Determinant(A)), <context>)`). A matrix-valued
# difference has no ordering and is declined; only a scalar result
# (a determinant, a trace, or scalar arithmetic of them) is decided.
_ASK_FOR_RELATION = {
    ">": sympy.Q.positive, ">=": sympy.Q.nonnegative,
    "<": sympy.Q.negative, "<=": sympy.Q.nonpositive,
    "!=": sympy.Q.nonzero,
}

def matrix_param_dims(domain: dict, shapes: dict) -> dict:
    """`{param: (rows, cols)}` in the claim author's own dimension
    tokens (an `int`, or a `str` name), for every parameter that is a
    matrix: one sized from a 2-D `Shape` marker or an `R^(m,n)`
    space-form domain. The raw tokens are what both the symbolic lift
    and the matrix-value probe need, the lift turning a name into a
    shared `sympy.Symbol`, the probe into a shared concrete size."""
    dims_by_param: dict = {}
    for p, shape in (shapes or {}).items():
        if p != "return" and len(getattr(shape, "dims", ())) == 2:
            dims_by_param[p] = tuple(shape.dims)
    for p, bound in (domain or {}).items():
        d = getattr(bound, "dims", ())
        if len(d) == 2:
            dims_by_param[p] = tuple(d)
    return dims_by_param


def vector_param_dims(domain: dict, shapes: dict) -> dict:
    """`{param: (n,)}` for every parameter that is a vector: one sized
    from a 1-D `Shape` marker (`Vec("n")`) or an `R^n` domain."""
    dims_by_param: dict = {}
    for p, shape in (shapes or {}).items():
        if p != "return" and len(getattr(shape, "dims", ())) == 1:
            dims_by_param[p] = tuple(shape.dims)
    for p, bound in (domain or {}).items():
        d = getattr(bound, "dims", ())
        if len(d) == 1:
            dims_by_param[p] = tuple(d)
        elif d:
            dims_by_param.pop(p, None)
    return dims_by_param


def _matrix_params(facts, domain: dict, shapes: dict) -> tuple[dict, dict]:
    """`({param: (rows, cols)}, {dim_name: sympy.Symbol})` for every
    matrix and vector parameter, the dimensions turned into shared
    sympy symbols so a name appearing on two parameters ties them
    together and `I(n)` in the claim reuses the same `n`. A vector is
    a column, `(n, 1)`."""
    symbols: dict = {}

    def dim_symbol(d):
        if isinstance(d, int):
            return d
        if isinstance(d, str) and d.isdigit():
            return int(d)
        return symbols.setdefault(d, sympy.Symbol(d, positive=True,
                                                  integer=True))
    params = {p: tuple(dim_symbol(d) for d in dims)
              for p, dims in matrix_param_dims(domain, shapes).items()}
    for p, (n,) in vector_param_dims(domain, shapes).items():
        params.setdefault(p, (dim_symbol(n), 1))
    return params, symbols


def _shaped(term, node):
    """`term` unchanged when it is a matrix expression, else ValueError
    naming the offending source. A matrix operator needs an operand that
    has a shape: a bare `Symbol` reaching `MatMul`/`Transpose` crashes
    inside sympy the moment it is asked for `.shape`, and that
    AttributeError used to escape the whole adjudication."""
    if not isinstance(term, sympy.MatrixExpr):
        raise ValueError(f"{ast.unparse(node)!r} is not a matrix, so it "
                         f"cannot be an operand of `@`/`.T`")
    return term


def _scalar(term):
    """A 1-by-1 matrix expression as the number it holds (a quadratic
    form `x.T @ A @ x`), anything else unchanged."""
    if isinstance(term, sympy.MatrixExpr) and term.shape == (1, 1):
        from sympy.matrices.expressions.matexpr import MatrixElement
        return MatrixElement(term, 0, 0)
    return term


def _is_matrix(term) -> bool:
    return isinstance(term, sympy.MatrixExpr) and term.shape != (1, 1)


def _vector_like(term, vectors: frozenset) -> bool:
    """Whether a column expression stands for a 1-D vector (it is built
    from a vector parameter), so `@` reads it the way numpy reads a
    1-D array."""
    return (isinstance(term, sympy.MatrixExpr) and term.shape[1] == 1
            and bool(term.atoms(sympy.MatrixSymbol) & vectors))


def _transpose(term, vectors: frozenset):
    """`term.T` with numpy's reading of a 1-D vector: an expression
    built from a vector parameter that has one axis of length 1 (a
    column `x`, `A @ x`, or the row `x @ A`) is a 1-D array, whose
    transpose is itself, so `x @ x.T` is the inner product, not
    `outer(x, x)`."""
    if isinstance(term, sympy.MatrixExpr) and 1 in term.shape \
            and term.shape != (1, 1) \
            and term.atoms(sympy.MatrixSymbol) & vectors:
        return term
    return sympy.Transpose(term)


def _matmul(left, right, vectors: frozenset):
    """`left @ right` with numpy's reading of a 1-D vector: two
    vectors give their dot product, a vector on the left of a matrix
    is a row."""
    if left.shape[1] != right.shape[0] and _vector_like(left, vectors):
        left = sympy.Transpose(left)
    if left.shape[1] != right.shape[0] and right.shape[0] == 1 \
            and right.atoms(sympy.MatrixSymbol) & vectors:
        right = sympy.Transpose(right)
    return left * right


def _elementwise(op, left, right):
    """`+`, `-`, `*` and `**` between lifted terms, elementwise on
    matrices: `*` of two matrices is the Hadamard product and a
    matrix power `A ** k` is the elementwise power. A number and a
    matrix combine only by scaling (`c * A`, `A / c`); adding a number
    to a matrix, or a matrix exponent, is outside the lift."""
    from sympy.matrices.expressions.hadamard import (HadamardPower,
                                                     HadamardProduct)
    lm, rm = _is_matrix(left), _is_matrix(right)
    if not (lm or rm):
        left, right = _scalar(left), _scalar(right)
        return {ast.Add: lambda: left + right, ast.Sub: lambda: left - right,
                ast.Mult: lambda: left * right,
                ast.Div: lambda: left / right,
                ast.Pow: lambda: left ** right}[type(op)]()
    if isinstance(op, (ast.Add, ast.Sub)):
        if not (lm and rm):
            raise ValueError("derive cannot read a number added to a "
                             "matrix")
        return left + right if isinstance(op, ast.Add) else left - right
    if isinstance(op, ast.Mult):
        if lm and rm:
            return HadamardProduct(left, right)
        return _scalar(left) * right if rm else left * _scalar(right)
    if isinstance(op, ast.Div):
        if rm:
            raise ValueError("derive cannot read division by a matrix")
        return left / _scalar(right)
    if isinstance(op, ast.Pow):
        if rm:
            raise ValueError("derive cannot read a matrix exponent")
        return HadamardPower(left, _scalar(right))
    raise ValueError(f"unsupported matrix operator {ast.dump(op)}")


def _lift(node, env: dict, vectors: frozenset = frozenset()):
    """One claim-expression node to a sympy (matrix or scalar) term, or
    raise ValueError for a construct outside the matrix vocabulary. A
    name the claim uses as a matrix but that was never declared
    two-dimensional reaches here as a bare `Symbol` and is refused by
    `_shaped` at the operator that needs it. `vectors` are the matrix
    symbols that stand for 1-D vectors."""
    def lift(n):
        return _lift(n, env, vectors)
    if isinstance(node, ast.Expression):
        return lift(node.body)
    if isinstance(node, ast.Name):
        return env[node.id] if node.id in env else sympy.Symbol(node.id)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) \
            and not isinstance(node.value, bool):
        return sympy.sympify(node.value)
    if isinstance(node, ast.Attribute) and node.attr == "T":
        return _transpose(_shaped(lift(node.value), node.value), vectors)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -lift(node.operand)
    if isinstance(node, ast.BinOp):
        left = lift(node.left)
        right = lift(node.right)
        if isinstance(node.op, ast.MatMult):
            return _matmul(_shaped(left, node.left),
                           _shaped(right, node.right), vectors)
        if isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div,
                                ast.Pow)):
            try:
                return _elementwise(node.op, left, right)
            except (TypeError, sympy.ShapeError) as e:
                raise ValueError(str(e)) from e
        raise ValueError(f"unsupported matrix operator {ast.dump(node.op)}")
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
            and not node.keywords:
        name = node.func.id
        read = lift_lemma_call(node, lift)
        if read is not None:
            return read
        args = [lift(a) for a in node.args]
        one = len(args) == 1
        if name == "det" and one:
            return sympy.Determinant(args[0])
        if name == "trace" and one:
            return sympy.Trace(args[0])
        if name == "inv" and one:
            return sympy.Inverse(args[0])
        if name == "transpose" and one:
            return _transpose(_shaped(args[0], node.args[0]), vectors)
        if name == "I" and one:
            return sympy.Identity(args[0])
        if name == "matrix_power" and len(args) == 2 \
                and _is_matrix(args[0]) and args[1].is_integer:
            return sympy.MatPow(args[0], args[1])
        if name == "dot" and len(args) == 2:
            left = _shaped(args[0], node.args[0])
            right = _shaped(args[1], node.args[1])
            if _vector_like(left, vectors) and _vector_like(right, vectors):
                return _scalar(sympy.Transpose(left) * right)
            return _matmul(left, right, vectors)
        if name == "outer" and len(args) == 2:
            return (_shaped(args[0], node.args[0])
                    * sympy.Transpose(_shaped(args[1], node.args[1])))
        if name == "kron" and len(args) == 2:
            return sympy.KroneckerProduct(_shaped(args[0], node.args[0]),
                                          _shaped(args[1], node.args[1]))
        if name == "solve" and len(args) == 2:
            return sympy.Inverse(_shaped(args[0], node.args[0])) \
                * _shaped(args[1], node.args[1])
        if name in ("abs", "Abs") and one and not _is_matrix(args[0]):
            return sympy.Abs(_scalar(args[0]))
        if name == "sqrt" and one and not _is_matrix(args[0]):
            return sympy.sqrt(_scalar(args[0]))
        if name == "norm" and one and _is_matrix(args[0]):
            # a vector's Euclidean norm is the root of its inner
            # product; a matrix's Frobenius norm the root of the trace
            # of its Gram matrix. An order (`norm(A, 2)`, `norm(A,
            # inf)`) has no matrix lemma and stays with the probe
            term = args[0]
            if _vector_like(term, vectors):
                return sympy.sqrt(_scalar(sympy.Transpose(term) * term))
            return sympy.sqrt(sympy.Trace(term * sympy.Transpose(term)))
    raise ValueError(f"unsupported matrix expression {ast.unparse(node)!r}")


def _assumptions(mat_syms: dict, structures: dict):
    """The sympy assumption context from structure premises/markers:
    every property with a sympy predicate, over the matrix symbol it
    applies to. `structures` is {param: (prop, ...)}."""
    facts = []
    for param, props in (structures or {}).items():
        A = mat_syms.get(param)
        if A is None:
            continue
        for prop in props:
            builder = _Q_FOR_PROPERTY.get(prop)
            if builder is not None:
                facts.append(builder(A))
    if not facts:
        return None
    return sympy.And(*facts) if len(facts) > 1 else facts[0]


#: structure properties that make a square matrix invertible
_INVERTIBLE_PROPERTIES = frozenset({"is_orthogonal", "is_positive_definite",
                                    "is_identity"})


def _nonsingular_premises(premises) -> set:
    """The matrix names an `assuming` clause states a nonzero
    determinant for: `det(A) != 0`, `det(A) > 0` or `det(A) < 0`."""
    import re
    names: set = set()
    for lhs, rel, rhs in premises or ():
        lhs, rhs = str(lhs).strip(), str(rhs).strip()
        if rhs.startswith("det(") and lhs in ("0", "0.0"):
            lhs, rhs = rhs, lhs
            rel = {">": "<", "<": ">"}.get(rel, rel)
        m = re.fullmatch(r"det\(\s*([A-Za-z_]\w*)\s*\)", lhs)
        if m and rhs in ("0", "0.0") and rel in ("!=", ">", "<"):
            names.add(m.group(1))
    return names


def _inverted_symbols(tree, env: dict) -> set:
    """Every matrix symbol the claim text inverts (inside an `inv(...)`
    call, the matrix of a `solve(A, b)`, or a matrix power with a
    negative exponent), read off the source:
    sympy cancels `Inverse(A) * A` to the identity as the product is
    built, so the lifted expression no longer shows the inverse."""
    out: set = set()
    for node in ast.walk(tree):
        inverted = None
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id in ("inv", "solve") and node.args:
            inverted = node.args[0]
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == "matrix_power" and len(node.args) == 2:
            try:
                exponent = ast.literal_eval(node.args[1])
            except (ValueError, SyntaxError):
                exponent = None
            if not isinstance(exponent, (int, float)) or exponent < 0:
                inverted = node.args[0]
        if inverted is None:
            continue
        try:
            term = _lift(inverted, env)
        except (ValueError, KeyError):
            continue
        out |= getattr(term, "atoms", lambda *_: set())(sympy.MatrixSymbol)
    return out


def _divisors(tree, env: dict, vectors: frozenset) -> list:
    """`[(term, text)]` for every quantity the claim text divides by,
    lifted, with its source spelling."""
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            try:
                term = _scalar(_lift(node.right, env, vectors))
            except (ValueError, KeyError, TypeError, sympy.ShapeError):
                term = None
            out.append((term, ast.unparse(node.right)))
    return out


def _stated_nonzero(premises, env: dict, vectors: frozenset) -> list:
    """The lifted quantities an `assuming` clause keeps away from zero:
    `q != 0`, `q > 0`, `q < 0`, or `q` above a positive number or below
    a negative one."""
    out = []
    for lhs, rel, rhs in premises or ():
        try:
            a = _scalar(_lift(ast.parse(str(lhs), mode="eval"), env, vectors))
            b = _scalar(_lift(ast.parse(str(rhs), mode="eval"), env, vectors))
        except (ValueError, KeyError, TypeError, SyntaxError,
                sympy.ShapeError):
            continue
        for q, bound, r in ((a, b, rel),
                            (b, a, {">": "<", "<": ">", ">=": "<=",
                                    "<=": ">="}.get(rel, rel))):
            if not getattr(bound, "is_number", False) or q.is_number:
                continue
            if (r == "!=" and bound.is_zero) \
                    or (r == ">" and bound.is_nonnegative) \
                    or (r == ">=" and bound.is_positive) \
                    or (r == "<" and bound.is_nonpositive) \
                    or (r == "<=" and bound.is_negative):
                out.append(q)
    return out


def _nonzero_divisor(term, invertible, stated: list, context,
                     domain: dict) -> bool:
    """Whether the divisor `term` is nonzero wherever the claim is
    judged: a nonzero number; a quantity a premise keeps away from
    zero; or a product whose every factor is nonzero, a determinant of
    an invertible matrix, a scalar parameter whose domain excludes
    zero, or a quantity sympy's assumptions call nonzero under the
    claim's structure."""
    from ..domain import bound_assumptions
    if term is None:
        return False
    if term.is_number:
        return bool(term.is_nonzero)
    if any(_is_zero(term - q) for q in stated):
        return True

    def factor_nonzero(f) -> bool:
        base, exp = f.as_base_exp()
        if base.is_number:
            return bool(base.is_nonzero)
        if any(_is_zero(base - q) for q in stated):
            return True
        if isinstance(base, sympy.Determinant):
            return base.arg in invertible
        if isinstance(base, sympy.Symbol) and str(base) in (domain or {}):
            kinds = bound_assumptions(domain[str(base)]) or {}
            if kinds.get("positive") or kinds.get("negative"):
                return True
        for q in (sympy.Q.positive, sympy.Q.negative):
            try:
                if sympy.ask(q(base), context if context is not None
                             else True) is True:
                    return True
            except Exception:
                continue
        return False
    expanded = _expand_determinants(term)
    return all(factor_nonzero(f) for f in sympy.Mul.make_args(expanded))


def _expand_determinants(expr):
    """`expr` with each determinant of a product, power, transpose or
    inverse split into determinants of its factors, so that every
    determinant left is of a single matrix symbol where it can be."""
    def split(det):
        arg = det.arg
        if isinstance(arg, sympy.Transpose):
            return sympy.Determinant(arg.arg)
        if isinstance(arg, sympy.Inverse):
            return 1 / sympy.Determinant(arg.arg)
        if isinstance(arg, sympy.MatPow):
            return sympy.Determinant(arg.base) ** arg.exp
        if isinstance(arg, sympy.MatMul):
            coeff, factors = arg.as_coeff_matrices()
            if coeff == 1 and len(factors) > 1:
                return sympy.Mul(*(sympy.Determinant(f) for f in factors))
        return det
    for _ in range(8):
        new = expr.replace(lambda e: isinstance(e, sympy.Determinant), split)
        if new == expr:
            break
        expr = new
    return expr


def _opaque_scalars(expr, names: dict):
    """`expr` with every 1-by-1 matrix product (a quadratic form or an
    inner product) replaced by one scalar symbol per quantity. A
    number equals its own transpose, so `x.T*y` and `y.T*x` are the
    same quantity and share a symbol; `names` maps each quantity's
    chosen spelling to its symbol, shared across both sides."""
    from sympy.matrices.expressions.matexpr import MatrixElement

    def pick(e):
        one = e.parent.doit()
        other = sympy.Transpose(one).doit()
        key = min(one, other, key=sympy.default_sort_key)
        return names.setdefault(key, sympy.Symbol(f"<{key}>", real=True))
    return expr.replace(
        lambda e: isinstance(e, MatrixElement) and e.parent.shape == (1, 1),
        pick)


def _is_zero(expr) -> bool:
    """Whether a refined difference is the zero of its kind: a
    ZeroMatrix, or a scalar/collapsed 0 (the matrix difference of two
    equal expressions simplifies to the integer 0, not a ZeroMatrix,
    so both forms count)."""
    try:
        simplified = sympy.simplify(expr)
    except Exception:
        return False
    if isinstance(simplified, sympy.ZeroMatrix):
        return True
    if getattr(simplified, "is_zero_matrix", None) is True:
        return True
    try:
        return simplified == 0 or bool(simplified.is_zero)
    except Exception:
        return False


def _structure_substitutions(mat_syms: dict, structures: dict) -> dict:
    """Exact rewrites a structure implies that sympy has no predicate
    for: an identity matrix is `I(n)` itself, and the transpose of a
    skew-symmetric matrix is its negation (so its trace is 0)."""
    subs: dict = {}
    for param, props in (structures or {}).items():
        A = mat_syms.get(param)
        if A is None or A.shape[0] != A.shape[1]:
            continue
        if "is_identity" in props:
            subs[A] = sympy.Identity(A.shape[0])
        elif "is_skew_symmetric" in props:
            # A.T = -A, so the trace, equal to its own negation, is 0
            subs[sympy.Transpose(A)] = -A
            subs[sympy.Trace(A)] = sympy.Integer(0)
    return subs


def _substituted(expr, subs: dict):
    if not subs:
        return expr
    for _ in range(4):
        new = expr.xreplace(subs)
        if new == expr:
            break
        expr = new
    return expr


def try_prove_matrix(lhs_src: str, rhs_src: str, relation: str, facts,
                     domain: dict, shapes: dict,
                     structures: dict,
                     premises=None) -> "ProofResult | None":
    """Prove `lhs <relation> rhs` over matrix and vector parameters, or
    return None when it is not a matrix claim or the lift cannot model
    it (the caller then falls back). An equality (`==`/`~=`) is decided
    by zeroing the refined difference; a scalar comparison of
    determinants/traces (`det(A) > 0`) is decided by sympy's assumption
    engine under the structure premises. A matrix ordering is not
    defined and is declined.

    An inverse needs an invertible operand: every matrix inside one
    must carry a structure that makes it invertible or an `assuming
    det(A) != 0` premise (`premises`, the clause's (lhs, relation,
    rhs) conjuncts), or the claim stays undecided. sympy reads an
    orthogonal matrix's determinant as 1, which only rotations have,
    so a claim involving one is decided for both signs, +1 and -1."""
    structure = relation in structure_properties()
    if relation not in ("==", "~=") and relation not in _ASK_FOR_RELATION \
            and not structure:
        return None
    params, dim_syms = _matrix_params(facts, domain, shapes)
    mat_syms = {p: sympy.MatrixSymbol(p, r, c) for p, (r, c) in params.items()}
    if not mat_syms:
        return None
    vectors = frozenset(mat_syms[p] for p in
                        vector_param_dims(domain, shapes) if p in mat_syms)
    # a bare dimension name in the claim (the `n` of `I(n)`) resolves to
    # the same symbol the matrix dimensions were built from, so an
    # identity's size matches its operands' and their difference closes.
    env = {**dim_syms, **mat_syms}
    from ..linalg import undeclared_matrix_operands, undeclared_operand_reason
    undeclared = undeclared_matrix_operands((lhs_src, rhs_src), env)
    if undeclared:
        # a decline with its reason, not a bare None: the remedy is the
        # useful half, and the caller renders this sketch on the unknown
        # it reports.
        return ProofResult("undecided",
                           sketch=undeclared_operand_reason(undeclared))
    if structure and lhs_src.strip() in mat_syms:
        # a predicate over a bare parameter asks whether the function
        # rejects a matrix that lacks the property: a question about
        # the function, adjudicated by execution
        return None
    try:
        lhs_tree = ast.parse(lhs_src, mode="eval")
        rhs_tree = ast.parse("0" if structure else rhs_src, mode="eval")
        lhs = _lift(lhs_tree, env, vectors)
        rhs = _lift(rhs_tree, env, vectors)
    except (ValueError, SyntaxError, TypeError, sympy.ShapeError):
        return None
    if structure:
        if not _is_matrix(lhs):
            return None
    elif _is_matrix(lhs) != _is_matrix(rhs):
        return None
    elif not _is_matrix(lhs):
        lhs, rhs = _scalar(lhs), _scalar(rhs)
    nonsingular = _nonsingular_premises(premises)
    invertible = {mat_syms[p] for p in mat_syms
                  if p in nonsingular
                  or set((structures or {}).get(p, ())) & _INVERTIBLE_PROPERTIES}
    singular = sorted(str(m) for m in
                      (_inverted_symbols(lhs_tree, env)
                       | _inverted_symbols(rhs_tree, env))
                      - invertible)
    if singular:
        names = ", ".join(singular)
        return ProofResult(
            "undecided",
            sketch=f"the claim inverts {names}, which may be singular (inv "
                   f"raises there); state it: assuming det({singular[0]}) "
                   f"!= 0")
    table = _lemma_table(mat_syms, structures, invertible)
    if structure:
        return _structure_verdict(relation, lhs_src, lhs, table, structures)
    subs = _structure_substitutions(mat_syms, structures)
    context = _assumptions(mat_syms, structures)
    extra = [sympy.Q.invertible(mat_syms[p]) for p in sorted(nonsingular)
             if p in mat_syms]
    if extra:
        context = sympy.And(context, *extra) if context is not None \
            else sympy.And(*extra)
    stated = _stated_nonzero(premises, env, vectors)
    for term, text in (_divisors(lhs_tree, env, vectors)
                       + _divisors(rhs_tree, env, vectors)):
        if not _nonzero_divisor(term, invertible, stated, context, domain):
            return ProofResult(
                "undecided",
                sketch=f"the claim divides by {text}, which may be zero "
                       f"(the quotient has no value there); state it: "
                       f"assuming {text} != 0")
    is_equality = relation in ("==", "~=")
    orthogonal = [mat_syms[p] for p in sorted(mat_syms)
                  if "is_orthogonal" in (structures or {}).get(p, ())]

    def _decide_one(lhs_d, rhs_d):
        lhs_r = sympy.refine(lhs_d, context) if context else lhs_d
        rhs_r = sympy.refine(rhs_d, context) if context else rhs_d
        diff = lhs_r - rhs_r
        if is_equality:
            return _is_zero(diff)
        # a scalar comparison: only a scalar difference has an ordering.
        if isinstance(diff, sympy.MatrixExpr):
            return None
        return sympy.ask(_ASK_FOR_RELATION[relation](diff),
                         context if context is not None else True)

    scalar_names: dict = {}

    def _decide():
        lhs_d = _opaque_scalars(normalise(_substituted(lhs, subs), relation,
                                          table), scalar_names).doit()
        rhs_d = _opaque_scalars(normalise(_substituted(rhs, subs), relation,
                                          table), scalar_names).doit()
        if not orthogonal:
            return _decide_one(lhs_d, rhs_d)
        import itertools
        lhs_d, rhs_d = _expand_determinants(lhs_d), _expand_determinants(rhs_d)
        for det in lhs_d.atoms(sympy.Determinant) | rhs_d.atoms(sympy.Determinant):
            if det.arg not in orthogonal and \
                    det.arg.atoms(sympy.MatrixSymbol) & set(orthogonal):
                return None
        outcomes = []
        for signs in itertools.product((1, -1), repeat=len(orthogonal)):
            fix = {sympy.Determinant(A): s for A, s in zip(orthogonal, signs)}
            outcomes.append(_decide_one(lhs_d.xreplace(fix),
                                        rhs_d.xreplace(fix)))
        if all(o is True for o in outcomes):
            return True
        if any(o is None for o in outcomes):
            return None
        return False

    # refine()/ask() can run unbounded on an expression sympy cannot
    # close; cap it and fall through to empirical checking on a timeout.
    try:
        decided = _with_timeout(_decide, FAST_TIMEOUT_SECONDS)
    except TimeoutError:
        return ProofResult("undecided",
                           sketch="matrix reasoning exceeded the wall-clock "
                                  "cap; left to empirical checking")
    except Exception:
        return None
    if decided is None:
        # a matrix-valued comparison, or ask could not decide: not our
        # verdict to give, the caller falls back
        return None
    prem = (f" under {', '.join(sorted(p for ps in structures.values() for p in ps))}"
            if structures else "")
    if decided:
        return ProofResult(
            "proven",
            sketch=f"matrix relation: {lhs_src.strip()} {relation} "
                   f"{rhs_src.strip()} holds in sympy's matrix algebra{prem}"
                   f"{_lemmas_text(table)}{_fixed_shapes_text(mat_syms, domain)}",
            meta=_lemmas_meta(table))
    # a definite non-relation (a false identity or inequality): a matrix
    # disproof needs a witness (a concrete counterexample matrix), which
    # the empirical route supplies; stay undecided here
    return ProofResult("undecided",
                       sketch="matrix relation did not hold symbolically; "
                              "left to empirical checking")


def _fixed_shapes_text(mat_syms: dict, domain: dict) -> str:
    """The clause the sketch adds for the operands whose binding fixes
    an axis: "; the binding fixes A at 30 by 15 and b at length 30";
    empty when no axis is fixed."""
    from .._shapes import dims_of, expected, fixed_size
    parts = []
    for p in sorted(mat_syms):
        dims = dims_of((domain or {}).get(p))
        if not dims or not any(fixed_size(d) is not None for d in dims):
            continue
        parts.append(f"{p} at {expected(dims)}")
    return f"; the binding fixes {' and '.join(parts)}" if parts else ""


def _lemma_table(mat_syms: dict, structures: dict, invertible) -> LemmaTable:
    """The lemma layer's view of the claim: each matrix symbol's
    structure (entailment-closed) and the symbols known invertible."""
    from ..matrices import entailed
    known = {mat_syms[p]: frozenset(entailed(props))
             for p, props in (structures or {}).items() if p in mat_syms}
    return LemmaTable(known, frozenset(invertible))


def _lemmas_text(table: LemmaTable) -> str:
    return f", using {', '.join(table.used)}" if table.used else ""


def _lemmas_meta(table: LemmaTable) -> dict:
    return {"mathema.matrix_lemmas": list(table.used)} if table.used else {}


def _structure_verdict(prop: str, lhs_src: str, term, table: LemmaTable,
                       structures: dict) -> "ProofResult | None":
    """A structure claim over a matrix expression (`is_symmetric(A @
    A.T)`): proven when the lemma layer's structure rules establish the
    property from the operands' own structure, else None (the caller
    falls back to sampling)."""
    try:
        holds = _with_timeout(lambda: prove_structure(prop, term, table),
                              FAST_TIMEOUT_SECONDS)
    except TimeoutError:
        return ProofResult("undecided",
                           sketch="matrix structure reasoning exceeded the "
                                  "wall-clock cap; left to empirical "
                                  "checking")
    except Exception:
        return None
    if not holds:
        return None
    given = sorted({p for ps in (structures or {}).values() for p in ps})
    prem = f" given {', '.join(given)}" if given else ""
    word = prop[3:].replace("_", " ")
    return ProofResult(
        "proven",
        sketch=f"matrix structure: {lhs_src.strip()} is {word} for every "
               f"size, by the structure of its operands{prem}",
        meta={"mathema.matrix_lemmas": [f"structure of {word} matrices"]})
