# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The linear-algebra grammar layer.

One module for the claim-grammar concerns that are specific to matrices:
recognising the matrix vocabulary in a law's text, resolving the sugar
whose reading depends on whether a name is a matrix (`A^T`, `|A|`,
`A^-1`), and the sympy matrix expressions the vocabulary renders to. The
matrix property registry lives in `matrices.py`; the symbolic proof of a
matrix identity lives in `symbolic/_matrix.py`; this module is the
parse-and-render half, imported by `grammar.py` and `conjecture.py`.

The vocabulary is Python-flavoured: `A @ B` (matmul), `A.T` (transpose),
`det(A)`, `inv(A)`, `trace(A)`, `I(n)` (identity). The three math-paper
spellings `A^T`, `|A|`, `A^-1` are ambiguous against a power, an
absolute value, and a reciprocal, and read as transpose / determinant /
inverse only when their operand is known to be a matrix (see
`apply_matrix_sugar`); a scalar operand keeps the ordinary reading.
"""
from __future__ import annotations

import ast

import sympy

# the tokens whose presence in a law's text marks it as a matrix claim,
# the cheap trigger for the matrix proof and for the informative
# `mathema/linalg` grammar tag.
MATRIX_TOKENS = ("@", ".T", "det(", "inv(", "trace(", "transpose(", "I(")

# the matrix vocabulary's single-argument calls, each to the sympy
# matrix expression it renders as (`det` -> |A|, `trace` -> tr(A), `I` ->
# the identity). `A.T` and `A @ B` are operators, handled directly by the
# renderer.
RENDER_CALLS = {
    "det": sympy.Determinant, "inv": sympy.Inverse, "trace": sympy.Trace,
    "transpose": sympy.Transpose, "I": sympy.Identity,
}
# the calls that name a matrix operation (`det`/`trace` return a scalar,
# but their argument is a matrix); used when deciding an operand's kind.
_MATRIX_CALLS = ("det", "inv", "trace", "transpose")

# the placeholder square dimension every rendered MatrixSymbol carries:
# it never appears in a transpose/determinant/product/trace rendering,
# and one shared symbol keeps every `@` chain shape-consistent for sympy.
RENDER_DIM = sympy.Symbol("n", positive=True, integer=True)


def mentions_matrix_ops(*srcs: str) -> bool:
    """Whether any source string uses a matrix-algebra token, the cheap
    trigger for attempting a matrix proof and for tagging a record's
    grammar as the linear-algebra dialect."""
    return any(tok in (s or "") for s in srcs for tok in MATRIX_TOKENS)


def operand_matrix_names(node: ast.AST) -> frozenset:
    """Names that denote matrices by their POSITION in an expression:
    every name appearing, directly or nested, as an operand of a matrix
    operator (`.T`, `@`, or a `det`/`inv`/`trace`/`transpose` call). A
    renderer lifts exactly these to `sympy.MatrixSymbol`, leaving every
    other name a scalar symbol, so `A + A.T` reads both `A`s as the one
    matrix while `2 * c` stays scalar. This is the structural reading
    used for RENDERING; the sugar resolver instead takes the names
    DECLARED as matrices, which it must know before any operator."""
    found: set = set()

    def mark(n: ast.AST) -> None:
        found.update(x.id for x in ast.walk(n) if isinstance(x, ast.Name))

    for x in ast.walk(node):
        if isinstance(x, ast.Attribute) and x.attr == "T":
            mark(x.value)
        elif isinstance(x, ast.BinOp) and isinstance(x.op, ast.MatMult):
            mark(x.left)
            mark(x.right)
        elif (isinstance(x, ast.Call) and isinstance(x.func, ast.Name)
              and x.func.id in _MATRIX_CALLS):
            for a in x.args:
                mark(a)
    return frozenset(found)


def declared_matrix_names(domain: dict | None) -> frozenset:
    """The names a claim's own domain declares to be matrices: those
    whose bound carries two dimensions (an `R^(m*n)` space or a 2-D
    `Shape`). This is what `claim()` can know from the claim text alone,
    unioned with any matrix names a caller supplies from the signature."""
    return frozenset(
        name for name, bound in (domain or {}).items()
        if len(getattr(bound, "dims", ())) == 2)


def undeclared_matrix_operands(srcs, declared) -> tuple:
    """The bare names a claim puts directly under `@` or `.T` without
    having been declared two-dimensional, sorted.

    Intent:
        `@` and `.T` are the two operators that ask their operand for a
        `.shape`, so a bare name reaching one of them without dimensions
        is the case neither matrix route can model. Both routes need the
        same answer, so they ask here.

    Notes:
        Deliberately narrower than `operand_matrix_names`, which
        collects every name nested anywhere under a matrix operator
        because a renderer wants them all. Subtracting `declared` from
        that reading is not sound: it counts the callee of `I(n)` and
        the `c` of `det(c * A)` as matrix operands, and reports a claim
        that is perfectly well formed as undeclared. Only a bare name in
        a position that will definitely be asked for a shape belongs
        here. A compound operand (`(A + x) @ B`) is left to `_shaped`,
        which guards the operator at lift time.

        An unparseable source contributes nothing; each caller reports a
        syntax error its own way. `declared` is a set of names, not a
        domain, because the symbolic route knows its matrices as lifted
        symbols and the probe route as sampled sizes.
    """
    used: set = set()
    for src in srcs:
        try:
            tree = ast.parse(src or "", mode="eval")
        except SyntaxError:
            continue
        for x in ast.walk(tree):
            if isinstance(x, ast.Attribute) and x.attr == "T":
                operands = (x.value,)
            elif isinstance(x, ast.BinOp) and isinstance(x.op, ast.MatMult):
                operands = (x.left, x.right)
            else:
                continue
            used.update(o.id for o in operands if isinstance(o, ast.Name))
    return tuple(sorted(used - set(declared)))


def undeclared_operand_reason(names) -> str:
    """The one wording both matrix routes give for those names: what is
    wrong, and the spelling that fixes it. A claim writes `x.T @ A @ x`
    over a `Vec("n")`, which is one-dimensional, so neither route can
    give it a shape; `Mat("n", 1)` states the same vector as a column
    matrix, which both can."""
    listed = ", ".join(repr(n) for n in names)
    subject = "is" if len(names) == 1 else "are"
    return (f"{listed} {subject} used as a matrix operand but not "
            f"declared two-dimensional: a 1-D vector parameter is not "
            f"yet integrated with `@`/`.T` (declare it as Mat(\"n\", 1) "
            f"to reason about it as a column matrix)")


def is_matrix_expr(node: ast.AST, matrix_names: frozenset) -> bool:
    """Whether an expression denotes a matrix (not a scalar), so the
    ambiguous sugar on it (`^T`, `^-1`, `|.|`) reads as transpose /
    inverse / determinant rather than power / reciprocal / absolute
    value. A name is a matrix iff declared one; `@` and `.T` and
    `inv`/`transpose` are matrix-valued; `+`/`-` and a scalar power stay
    matrices if an operand is; `det`/`trace`/`abs` are scalar."""
    if isinstance(node, ast.Name):
        return node.id in matrix_names
    if isinstance(node, ast.Attribute):
        return node.attr == "T" or is_matrix_expr(node.value, matrix_names)
    if isinstance(node, ast.BinOp):
        if isinstance(node.op, ast.MatMult):
            return True
        if isinstance(node.op, (ast.Add, ast.Sub, ast.Pow)):
            return (is_matrix_expr(node.left, matrix_names)
                    or is_matrix_expr(node.right, matrix_names))
        return False
    if isinstance(node, ast.UnaryOp):
        return is_matrix_expr(node.operand, matrix_names)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        return node.func.id in ("inv", "transpose")
    return False


class _MatrixSugar(ast.NodeTransformer):
    """Rewrite the matrix spelling of the three sugars whose reading
    depends on whether their operand is a matrix: `A^T` (`A ** T`, a bare
    `T` exponent) to `A.T`, `A^-1` to `inv(A)`, and `|A|` (`abs(A)`) to
    `det(A)`. A scalar operand is left untouched, so `x^-1` stays a
    reciprocal and `|x|` an absolute value."""
    def __init__(self, matrix_names: frozenset):
        self._mats = matrix_names
        self.changed = False

    def visit_BinOp(self, node: ast.BinOp) -> ast.AST:
        self.generic_visit(node)
        if isinstance(node.op, ast.Pow) and is_matrix_expr(node.left,
                                                           self._mats):
            exp = node.right
            if isinstance(exp, ast.Name) and exp.id == "T":
                self.changed = True
                return ast.Attribute(value=node.left, attr="T",
                                     ctx=ast.Load())
            neg_one = (isinstance(exp, ast.UnaryOp)
                       and isinstance(exp.op, ast.USub)
                       and isinstance(exp.operand, ast.Constant)
                       and exp.operand.value == 1)
            if neg_one or (isinstance(exp, ast.Constant) and exp.value == -1):
                self.changed = True
                return ast.Call(func=ast.Name(id="inv", ctx=ast.Load()),
                                args=[node.left], keywords=[])
        return node

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        if (isinstance(node.func, ast.Name) and node.func.id == "abs"
                and len(node.args) == 1
                and is_matrix_expr(node.args[0], self._mats)):
            self.changed = True
            return ast.Call(func=ast.Name(id="det", ctx=ast.Load()),
                            args=node.args, keywords=[])
        return node


def apply_matrix_sugar(src: str, matrix_names: frozenset) -> str:
    """Resolve the type-dependent matrix sugar in one already-parsed
    expression string, given the names known to be matrices: `A^T` to
    `A.T`, `A^-1` to `inv(A)`, `|A|` (which the base grammar has already
    rendered `abs(A)`) to `det(A)`. Returns `src` unchanged when there
    are no matrix names, when it does not parse, or when nothing
    matched, so a scalar claim is never touched."""
    if not matrix_names or not src:
        return src
    try:
        tree = ast.parse(src, mode="eval")
    except SyntaxError:
        return src
    sugar = _MatrixSugar(matrix_names)
    rewritten = sugar.visit(tree)
    if not sugar.changed:
        return src
    ast.fix_missing_locations(rewritten)
    return ast.unparse(rewritten.body)
