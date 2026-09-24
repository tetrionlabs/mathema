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
`det`/`inv`/`trace`/`I(n)`) plus scalar arithmetic joining scalar
results (a determinant or trace is a scalar). A construct outside it
returns `None`, and the caller falls back exactly as any other
undecided derive claim does.
"""
from __future__ import annotations

import ast

import sympy

from .._timeout import FAST_TIMEOUT_SECONDS, _with_timeout
from ..linalg import MATRIX_TOKENS, mentions_matrix_ops
from ._proof_support import ProofResult

__all__ = ["MATRIX_TOKENS", "matrix_param_dims", "mentions_matrix_ops",
           "try_prove_matrix"]

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


def _matrix_params(facts, domain: dict, shapes: dict) -> tuple[dict, dict]:
    """`({param: (rows, cols)}, {dim_name: sympy.Symbol})` for every
    matrix parameter, the dimensions turned into shared sympy symbols so
    a name appearing on two parameters ties them together and `I(n)` in
    the claim reuses the same `n`."""
    symbols: dict = {}

    def dim_symbol(d):
        if isinstance(d, int):
            return d
        return symbols.setdefault(d, sympy.Symbol(d, positive=True,
                                                  integer=True))
    params = {p: tuple(dim_symbol(d) for d in dims)
              for p, dims in matrix_param_dims(domain, shapes).items()}
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


def _lift(node, env: dict):
    """One claim-expression node to a sympy (matrix or scalar) term, or
    raise ValueError for a construct outside the matrix vocabulary. A
    name the claim uses as a matrix but that was never declared
    two-dimensional reaches here as a bare `Symbol` and is refused by
    `_shaped` at the operator that needs it."""
    if isinstance(node, ast.Expression):
        return _lift(node.body, env)
    if isinstance(node, ast.Name):
        return env[node.id] if node.id in env else sympy.Symbol(node.id)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return sympy.sympify(node.value)
    if isinstance(node, ast.Attribute) and node.attr == "T":
        return sympy.Transpose(_shaped(_lift(node.value, env), node.value))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_lift(node.operand, env)
    if isinstance(node, ast.BinOp):
        left = _lift(node.left, env)
        right = _lift(node.right, env)
        if isinstance(node.op, ast.MatMult):
            return (_shaped(left, node.left) * _shaped(right, node.right))
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Pow):
            return left ** right
        if isinstance(node.op, ast.Div):
            # a scalar reciprocal in a matrix claim (`det(inv(A)) ==
            # 1/det(A)`): sympy reads the division on Determinant/Trace
            # scalars directly. Without this the whole claim declined
            # as an unsupported operator, which read as a proof gap
            # rather than a missing case.
            return left / right
        raise ValueError(f"unsupported matrix operator {ast.dump(node.op)}")
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        name = node.func.id
        args = [_lift(a, env) for a in node.args]
        if name == "det":
            return sympy.Determinant(args[0])
        if name == "trace":
            return sympy.Trace(args[0])
        if name == "inv":
            return sympy.Inverse(args[0])
        if name == "transpose":
            return sympy.Transpose(args[0])
        if name == "I" and len(args) == 1:
            return sympy.Identity(args[0])
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
    call, or a power with a negative exponent), read off the source:
    sympy cancels `Inverse(A) * A` to the identity as the product is
    built, so the lifted expression no longer shows the inverse."""
    out: set = set()
    for node in ast.walk(tree):
        inverted = None
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == "inv" and node.args:
            inverted = node.args[0]
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
            try:
                exponent = ast.literal_eval(node.right)
            except (ValueError, SyntaxError):
                exponent = None
            if not isinstance(exponent, (int, float)) or exponent < 0:
                inverted = node.left
        if inverted is None:
            continue
        try:
            term = _lift(inverted, env)
        except (ValueError, KeyError):
            continue
        out |= getattr(term, "atoms", lambda *_: set())(sympy.MatrixSymbol)
    return out


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


def try_prove_matrix(lhs_src: str, rhs_src: str, relation: str, facts,
                     domain: dict, shapes: dict,
                     structures: dict,
                     premises=None) -> "ProofResult | None":
    """Prove `lhs <relation> rhs` over matrix parameters, or return None
    when it is not a matrix claim or the lift cannot model it (the
    caller then falls back). An equality (`==`/`~=`) is decided by
    zeroing the refined difference; a scalar comparison of
    determinants/traces (`det(A) > 0`) is decided by sympy's assumption
    engine under the structure premises. A matrix ordering is not
    defined and is declined.

    An inverse needs an invertible operand: every matrix inside one
    must carry a structure that makes it invertible or an `assuming
    det(A) != 0` premise (`premises`, the clause's (lhs, relation,
    rhs) conjuncts), or the claim stays undecided. sympy reads an
    orthogonal matrix's determinant as 1, which only rotations have,
    so a claim involving one is decided for both signs, +1 and -1."""
    if relation not in ("==", "~=") and relation not in _ASK_FOR_RELATION:
        return None
    params, dim_syms = _matrix_params(facts, domain, shapes)
    mat_syms = {p: sympy.MatrixSymbol(p, r, c) for p, (r, c) in params.items()}
    if not mat_syms:
        return None
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
    try:
        lhs_tree = ast.parse(lhs_src, mode="eval")
        rhs_tree = ast.parse(rhs_src, mode="eval")
        lhs = _lift(lhs_tree, env)
        rhs = _lift(rhs_tree, env)
    except (ValueError, SyntaxError):
        return None
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
    context = _assumptions(mat_syms, structures)
    extra = [sympy.Q.invertible(mat_syms[p]) for p in sorted(nonsingular)
             if p in mat_syms]
    if extra:
        context = sympy.And(context, *extra) if context is not None \
            else sympy.And(*extra)
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
        return sympy.ask(_ASK_FOR_RELATION[relation](diff), context)

    def _decide():
        lhs_d, rhs_d = lhs.doit(), rhs.doit()
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
        rel_text = "=" if is_equality else relation
        return ProofResult(
            "proven",
            sketch=f"matrix relation: {_humanize(lhs)} {rel_text} "
                   f"{_humanize(rhs)} holds in sympy's matrix algebra{prem}")
    # a definite non-relation (a false identity or inequality): a matrix
    # disproof needs a witness (a concrete counterexample matrix), which
    # the empirical route supplies; stay undecided here
    return ProofResult("undecided",
                       sketch="matrix relation did not hold symbolically; "
                              "left to empirical checking")


def _humanize(expr) -> str:
    return str(expr).replace("**", "^")
