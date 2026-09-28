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
`apply_matrix_sugar`, and `grammar.bars_over_matrices` for the bars); a
scalar operand keeps the ordinary reading, and an explicit `abs(A)` is
always elementwise.
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
    whose bound carries two dimensions (an `R^(m,n)` space or a 2-D
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
    over an `x` with no shape, so neither route can give it one; a
    `Vec("n")` marker or an `R^n` domain states it as a vector, and
    `Mat("n", 1)` as a column matrix."""
    listed = ", ".join(repr(n) for n in names)
    subject = "is" if len(names) == 1 else "are"
    return (f"{listed} {subject} used as a matrix operand but declared "
            f"neither a vector nor a matrix (declare it with Vec(\"n\") "
            f"or an R^n domain as a vector, or Mat(\"n\", 1) as a column "
            f"matrix)")


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
    """Rewrite the matrix spelling of the sugars whose reading depends
    on whether their operand is a matrix: `A^T` (`A ** T`, a bare `T`
    exponent) to `A.T` and `A^-1` to `inv(A)`. A scalar operand is left
    untouched, so `x^-1` stays a reciprocal. The bars `|A|` read as the
    determinant while the claim text is folded
    (`grammar.bars_over_matrices`); an explicit `abs(A)` is
    elementwise and never rewritten."""
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


def apply_matrix_sugar(src: str, matrix_names: frozenset) -> str:
    """Resolve the type-dependent matrix sugar in one already-parsed
    expression string, given the names known to be matrices: `A^T` to
    `A.T`, `A^-1` to `inv(A)`. Returns `src` unchanged when there are
    no matrix names, when it does not parse, or when nothing matched,
    so a scalar claim is never touched."""
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


# --- vectors and matrices as claim values -----------------------------

#: calls whose result is a number whatever the rank of their argument
SCALAR_CALLS = frozenset({"det", "trace", "norm", "dot", "rank", "cond",
                          "len", "dim"})
#: calls whose result is a matrix
MATRIX_CALLS = frozenset({"inv", "transpose", "matrix_power", "pinv",
                          "kron", "outer", "I"})
#: reductions: a number without `axis=`, one rank lower with it
REDUCTION_CALLS = frozenset({"sum", "mean", "prod", "min", "max", "std",
                             "var", "count"})
#: running reductions: a vector without `axis=` (a matrix is read in
#: row order, as numpy does), the argument's own rank with it
CUMULATIVE_CALLS = frozenset({"cumsum", "cumprod"})
#: calls that act element by element, keeping their argument's rank
ELEMENTWISE_CALLS = frozenset({"abs", "Abs"})
#: the keywords each call of the vocabulary accepts; every other call
#: takes its arguments by position
CALL_KEYWORDS = {
    **{name: ("axis",) for name in REDUCTION_CALLS | CUMULATIVE_CALLS},
    "std": ("axis", "ddof"), "var": ("axis", "ddof"),
}
#: the calls of the linear-algebra vocabulary the probe evaluates
VOCABULARY = (SCALAR_CALLS | MATRIX_CALLS | REDUCTION_CALLS
              | CUMULATIVE_CALLS
              | frozenset({"eigvals", "eigvalsh", "solve", "diag"})) \
    - frozenset({"len", "dim", "min", "max", "sum"})


def array_ranks(domain: "dict | None", shapes: "dict | None" = None,
                param_kinds: "dict | None" = None,
                structures: "dict | None" = None) -> dict:
    """Intent:
        The names a claim quantifies over as vectors, matrices or
        tables, `{name: rank}`: 1 for a vector, 2 for a matrix, and
        the string `"table"` for a table. Read from the claim's own
        domain (`R^n`, `R^(m,n)`), the signature's `Shape` markers and
        structure markers, and the parameter kinds a runtime type
        gives (`vec`, `mat`, `table`).

    Notes:
        A domain's rank wins over a runtime kind, so an `np.ndarray`
        parameter quantified over `R^(n,n)` is a matrix. A column
        `Mat("n", 1)` reads as a vector. A plain list parameter with no
        space form is not in the result: it is a sequence, not a
        vector.
    """
    out: dict = {}
    for p, kind in (param_kinds or {}).items():
        if kind == "vec":
            out[p] = 1
        elif kind == "mat":
            out[p] = 2
        elif kind == "table":
            out[p] = "table"
    for p in (structures or {}):
        if p != "return":
            out[p] = 2
    for p, shape in (shapes or {}).items():
        dims = getattr(shape, "dims", ())
        if p != "return" and dims:
            out[p] = _rank_of(dims)
    for p, bound in (domain or {}).items():
        dims = getattr(bound, "dims", ())
        if dims:
            out[p] = _rank_of(dims)
    return out


def _rank_of(dims) -> int:
    """The rank a shape reads with: a column `(n, 1)` is a vector, so
    `x.T @ A @ x` over it is a number."""
    if len(dims) == 2 and str(dims[1]) == "1":
        return 1
    return len(dims)


def _is_pass_through(node, parent, callables: frozenset) -> bool:
    """Whether a name at `node` is handed on rather than read as a
    number: an argument of `f` or a bound function, the subject of a
    subscript, the argument of `dim`/`len`, or the iterable of a
    comprehension."""
    if isinstance(parent, ast.Call):
        func = parent.func
        name = func.id if isinstance(func, ast.Name) else None
        if node in parent.args or any(k.value is node
                                      for k in parent.keywords):
            return name in callables or name in ("dim", "len")
        return False
    if isinstance(parent, ast.Subscript):
        return parent.value is node
    if isinstance(parent, ast.comprehension):
        return parent.iter is node
    return False


def array_value_uses(srcs, names, callables=frozenset({"f"})) -> list:
    """Intent:
        The names in `names` (vectors, matrices, tables) that the
        claim's expressions use as values, in the order first met: in
        arithmetic, a comparison, a vocabulary call, or on their own.
        A name only handed to `f` (or a bound function), subscripted,
        measured with `dim`/`len`, or iterated in a comprehension is
        not a value use; a table's column read (`df["returns"]`, when
        `names` maps the name to `"table"`) is one, since the column
        is a vector.
    """
    names_ranks = names if isinstance(names, dict) else {}
    names = set(names)
    found: list = []
    for src in srcs:
        if not src:
            continue
        try:
            tree = ast.parse(str(src), mode="eval")
        except SyntaxError:
            continue
        parents = {id(c): p for p in ast.walk(tree)
                   for c in ast.iter_child_nodes(p)}
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Name) and node.id in names):
                continue
            parent = parents.get(id(node))
            if isinstance(parent, ast.keyword):
                parent = parents.get(id(parent))
            column = (isinstance(parent, ast.Subscript)
                      and names_ranks.get(node.id) == "table")
            if parent is not None and not column \
                    and _is_pass_through(node, parent, callables):
                continue
            if node.id not in found:
                found.append(node.id)
    return found


def static_rank(node, ranks: dict):
    """Intent:
        The rank of the value an expression denotes, read off its
        syntax: 0 for a number, 1 for a vector, 2 for a matrix, or
        None when it cannot be told without evaluating (a call of
        `f`, a bound function, an unknown call).

    Notes:
        A name absent from `ranks` is a number. `@` follows numpy:
        two vectors give a number, a matrix and a vector a vector.
        Arithmetic broadcasts, so it takes the larger rank.
    """
    if isinstance(node, ast.Expression):
        return static_rank(node.body, ranks)
    if isinstance(node, ast.Name):
        r = ranks.get(node.id, 0)
        return None if r == "table" else r
    if isinstance(node, ast.Constant):
        return 0
    if isinstance(node, ast.UnaryOp):
        return static_rank(node.operand, ranks)
    if isinstance(node, ast.BinOp):
        left = static_rank(node.left, ranks)
        right = static_rank(node.right, ranks)
        if left is None or right is None:
            return None
        if isinstance(node.op, ast.MatMult):
            if left == 0 or right == 0:
                return None
            return max(0, left + right - 2)
        return max(left, right)
    if isinstance(node, ast.Attribute):
        if node.attr == "T":
            return static_rank(node.value, ranks)
        if isinstance(node.value, ast.Name) \
                and ranks.get(node.value.id) == "table":
            return 1
        return None
    if isinstance(node, ast.Subscript):
        base = node.value
        if isinstance(base, ast.Name) and ranks.get(base.id) == "table" \
                and isinstance(node.slice, ast.Constant) \
                and isinstance(node.slice.value, str):
            return 1
        inner = static_rank(base, ranks)
        if not inner:
            return None
        index = node.slice
        parts = index.elts if isinstance(index, ast.Tuple) else [index]
        kept = sum(isinstance(p, ast.Slice) for p in parts)
        return inner - len(parts) + kept
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        name = node.func.id
        args = [static_rank(a, ranks) for a in node.args]
        axis = any(k.arg == "axis" for k in node.keywords)
        if name in SCALAR_CALLS:
            return 0
        if name in MATRIX_CALLS:
            return 2
        if name in REDUCTION_CALLS:
            if len(node.args) != 1:
                return 0 if all(a == 0 for a in args) else None
            if args[0] is None:
                return None
            return max(0, args[0] - 1) if axis else 0
        if name in CUMULATIVE_CALLS and len(node.args) == 1:
            if args[0] is None:
                return None
            return args[0] if axis else 1
        if name in ELEMENTWISE_CALLS and args:
            return args[0]
        if name in ("eigvals", "eigvalsh"):
            return 1
        if name == "diag" and args and args[0] is not None:
            return 1 if args[0] == 2 else 2
        if name == "solve" and len(args) == 2:
            return args[1]
        return None
    return None


def matrix_ordering_reason(relation: str, sides, ranks: dict) -> "str | None":
    """Intent:
        Why an ordering claim over a vector or matrix side is refused,
        or None when the relation is not an ordering or every side is
        a number (or cannot be told without evaluating).
    """
    if relation not in ("<", "<=", ">", ">="):
        return None
    for src in sides:
        try:
            rank = static_rank(ast.parse(str(src or "0"), mode="eval"),
                               ranks)
        except SyntaxError:
            continue
        if rank:
            what = "a vector" if rank == 1 else "a matrix"
            return (f"{src.strip()!r} is {what}, and an ordering "
                    f"({relation}) between {what} and anything is not "
                    f"defined; compare a number drawn from it (det, "
                    f"trace, norm, an element), or an elementwise reading "
                    f"spelled all(...), which the grammar does not have "
                    f"yet")
    return None
