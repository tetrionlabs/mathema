# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Each grammar word means one thing on every route.

A claim word such as `std` or `det` is read by the exact evaluator a
claim is sampled with (`_linalg_eval.FUNCTIONS`, with `len` and `dim`
from the claim namespace) and by the symbolic lowering a proof is
built in (`_seqir.Lowering` for vectors of symbolic length,
`_matrix._lift` for matrix algebra). A trusted definition row maps a
library's function onto the word, so a proof through the row is only
sound when both readings agree.

Each test here evaluates a word both ways at fixed inputs (length 1,
length 2, repeated values, negative and fractional values, each
keyword) and compares exactly: the lowering is evaluated in sympy's
rationals, and the evaluator, which computes exactly and rounds once,
must return the exact value rounded to the nearest float. Both must
also agree on where the word has no value. The table in
`mathema._grammar_words` is checked against both, and the docs page
against the table.
"""
from __future__ import annotations

import ast
import inspect
import math
import os
from fractions import Fraction

import pytest
import sympy

np = pytest.importorskip("numpy")

from mathema import _grammar_words as G  # noqa: E402
from mathema._linalg_eval import FUNCTIONS, as_array  # noqa: E402
from mathema._math_vocab import MATH_CONSTANTS  # noqa: E402
from mathema.conjecture import _SAFE_FUNCS  # noqa: E402
from mathema.symbolic import _matrix as M  # noqa: E402
from mathema.symbolic._base import NotSymbolic  # noqa: E402
from mathema.symbolic._seqir import INDEX, Lowering, Vec  # noqa: E402

_DOCS = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs")

#: vectors every sequence word is evaluated at: length 1, length 2,
#: repeated values, negative and fractional values, decimal floats
VECTORS = [
    [3],
    [1, 2],
    [2, 2, 2],
    [-1.5, 0.25, 4, -3],
    [0.1, 0.2, 0.3],
    [5, -5, 5, 1, 1],
]

#: the claim words in the namespace a claim is evaluated in
ENV = {**_SAFE_FUNCS, **FUNCTIONS, **MATH_CONSTANTS}


# --- the two readings ---------------------------------------------------

def _exact(v) -> sympy.Rational:
    """A Python number as the exact rational it holds."""
    return sympy.Rational(Fraction(v))


def evaluate(src: str, **values):
    """`src` through the exact evaluator, compiled as a claim is (its
    `@` the exact product), each value given as the array a claim
    evaluates it as. Returns the value, or the exception it raised."""
    from mathema.conjecture import _exact_products
    env = {**ENV, **{k: as_array(v) for k, v in values.items()}}
    code = compile(_exact_products(ast.parse(src, mode="eval")), "<claim>",
                   "eval")
    try:
        with np.errstate(all="ignore"):
            return eval(code, env)  # noqa: S307
    except Exception as e:
        return e


def lower_sequence(src: str, names=("x", "y")):
    """`src` through the sequence lowering, every vector name of one
    symbolic length `L`. Returns `(value, obligations, L, bases)`.

    Raises:
        NotSymbolic: the lowering does not read `src`.
    """
    L = sympy.Symbol("L", integer=True, positive=True)
    bases = {n: sympy.IndexedBase(n, real=True) for n in names}
    low = Lowering({n: (b, L) for n, b in bases.items()}, {}, {})
    value = low.lower(ast.parse(src, mode="eval"))
    return value, low.obligations, L, bases


def at(expr, L, n: int, bases: dict, values: dict):
    """A lowered number at length `n`, each sequence read at `values`."""
    e = expr.subs(L, n).doit()
    subs = {bases[name][k]: _exact(v)
            for name, vs in values.items() for k, v in enumerate(vs)}
    return sympy.simplify(e.xreplace(subs).doit())


def sequence_value(src: str, **values):
    """`src` read through the sequence lowering at concrete vectors:
    `(defined, value)`, `value` a sympy number or a list of them for a
    vector-valued word, `defined` whether every obligation the lowering
    recorded is met at this length.
    """
    value, obligations, L, bases = lower_sequence(src, tuple(values))
    n = len(next(iter(values.values())))
    defined = all(n >= least for least in obligations.min_length.values())
    if isinstance(value, Vec):
        return defined, [at(value.elem.xreplace({INDEX: i}), L, n, bases,
                            values) for i in range(n)]
    return defined, at(value, L, n, bases, values)


def matrix_value(src: str, **values):
    """`src` lifted to sympy's matrix algebra and evaluated at concrete
    values (a vector is a column, as the lift reads it): `(defined,
    value)`, `defined` False where sympy finds no value (a singular
    inverse).

    Raises:
        ValueError: the lift does not read `src`.
    """
    syms, concrete, vectors = {}, {}, set()
    for name, v in values.items():
        rows = [[_exact(e) for e in r] for r in v] \
            if isinstance(v[0], list) else [[_exact(e)] for e in v]
        sym = sympy.MatrixSymbol(name, len(rows), len(rows[0]))
        syms[name] = sym
        concrete[sym] = sympy.ImmutableMatrix(rows)
        if not isinstance(v[0], list):
            vectors.add(sym)
    term = M._lift(ast.parse(src, mode="eval"), syms, frozenset(vectors))
    try:
        out = term.xreplace(concrete).doit()
        if isinstance(out, sympy.MatrixExpr):
            out = out.as_explicit()
        if isinstance(out, sympy.MatrixBase):
            out = out.applyfunc(sympy.simplify)
        else:
            out = sympy.simplify(out.doit())
    except (ValueError, ZeroDivisionError,
            sympy.matrices.exceptions.NonInvertibleMatrixError):
        return False, None
    return True, out


# --- comparing them -----------------------------------------------------

def _no_value(v) -> bool:
    if isinstance(v, Exception):
        return True
    if isinstance(v, float):
        return math.isnan(v)
    return False


def _nearest_float(exact) -> float:
    """The exact value rounded once to the nearest float."""
    if exact.is_Rational:
        return float(Fraction(int(exact.p), int(exact.q)))
    return float(sympy.N(exact, 60))


def same(evaluated, exact) -> bool:
    """Whether the evaluator's value is the exact value rounded once:
    element by element for a vector or matrix, both without a value
    where either has none."""
    if isinstance(exact, sympy.MatrixBase):
        a = np.asarray(evaluated, dtype=object)
        if exact.shape[1] == 1 and a.ndim == 1:
            exact = list(exact)
        elif exact.shape == (1, 1) and a.ndim == 0:
            exact = exact[0, 0]
        else:
            return a.shape == exact.shape and all(
                same(a[i, j], exact[i, j])
                for i in range(exact.shape[0]) for j in range(exact.shape[1]))
    if isinstance(exact, list):
        a = list(np.asarray(evaluated, dtype=object).ravel())
        return len(a) == len(exact) and all(same(u, v)
                                            for u, v in zip(a, exact))
    if exact.has(sympy.nan, sympy.zoo) or not exact.is_finite:
        return _no_value(evaluated)
    if _no_value(evaluated) or isinstance(evaluated, Exception):
        return False
    if hasattr(evaluated, "item"):
        evaluated = evaluated.item()
    return evaluated == _nearest_float(exact)


# --- sequence words -----------------------------------------------------

#: every spelling of a sequence word the lowering reads with a closed
#: form, each keyword at more than one value
SEQUENCE_CASES = [
    "len(x)", "dim(x)", "dim(x, 0)", "count(x)",
    "sum(x)", "prod(x)", "mean(x)",
    "var(x)", "var(x, ddof=0)", "var(x, ddof=1)", "var(x, ddof=2)",
    "std(x)", "std(x, ddof=0)", "std(x, ddof=1)", "std(x, ddof=2)",
    "cumsum(x)", "cumprod(x)", "abs(x)", "Abs(x)",
    "dot(x, y)", "x @ y",
    "norm(x)", "norm(x, 2)", "norm(x, ord=2)", "norm(x, 1)",
    "norm(x, ord=1)",
]


def _partner(x):
    """A second vector of `x`'s length, with negative and fractional
    entries."""
    return [(-1) ** k * (k + Fraction(1, 2)) for k in range(len(x))]


def _cases():
    for src in SEQUENCE_CASES:
        for x in VECTORS:
            yield pytest.param(src, x, id=f"{src} at {x}")


@pytest.mark.parametrize("src, x", list(_cases()))
def test_a_sequence_word_has_one_value_on_both_routes(src, x):
    values = {"x": x}
    if "y" in src:
        values["y"] = [float(v) for v in _partner(x)]
    defined, exact = sequence_value(src, **values)
    evaluated = evaluate(src, **values)
    if not defined:
        assert _no_value(evaluated), (
            f"{src} at {values}: the lowering has no value here, the "
            f"evaluator gives {evaluated!r}")
        return
    assert same(evaluated, exact), (
        f"{src} at {values}: the lowering gives {exact}, the evaluator "
        f"{evaluated!r}")


@pytest.mark.parametrize("word", ["mean", "sum", "prod", "count", "std",
                                  "var", "len"])
def test_a_reduction_of_nothing_agrees_on_both_routes(word):
    """Length 0 lies outside every `R^n`, but where a word is read
    there, the two routes still give one answer: `mean([])` has no
    value on either, `sum([])` is 0 on both."""
    value, obligations, L, _ = lower_sequence(f"{word}(x)")
    evaluated = evaluate(f"{word}(x)", x=np.array([], dtype=float))
    if obligations.min_length:
        assert _no_value(evaluated)
        return
    exact = sympy.simplify(value.subs(L, 0).doit())
    assert same(evaluated, exact), (word, exact, evaluated)


@pytest.mark.parametrize("ddof", [0, 1, 2, 3])
@pytest.mark.parametrize("word", ["std", "var"])
def test_a_moment_has_a_value_from_the_same_length_on_both_routes(word, ddof):
    """`std(x, ddof=k)` has a value from length `k + 1`, as the table
    states: the lowering records that obligation, and the evaluator
    gives no value one element short of it and a value at it."""
    src = f"{word}(x, ddof={ddof})"
    _, obligations, L, _ = lower_sequence(src)
    least = eval(G.word(word).least_length, {"ddof": ddof})  # noqa: S307
    assert max(obligations.min_length.values(), default=1) == least
    short = [Fraction(k + 1, 3) for k in range(least - 1)]
    if short:
        assert _no_value(evaluate(src, x=[float(v) for v in short]))
    enough = [float(Fraction(k + 1, 3)) for k in range(least)]
    assert not _no_value(evaluate(src, x=enough))


@pytest.mark.parametrize("x", VECTORS, ids=str)
@pytest.mark.parametrize("word", ["min", "max", "cummax", "cummin",
                                  "norm_inf"])
def test_an_extremum_meets_every_fact_the_lowering_states(word, x):
    """The lowering knows `min`, `max`, the running extrema and
    `norm(x, inf)` only through facts (one of the elements, at most or
    at least every element, `min(x) <= mean(x)`); the evaluator's value
    meets each one exactly."""
    src = "norm(x, inf)" if word == "norm_inf" else f"{word}(x)"
    lower_sequence(src)
    exact = [Fraction(v) for v in x]
    got = evaluate(src, x=x)
    if word in ("min", "max", "norm_inf"):
        elements = [abs(v) for v in exact] if word == "norm_inf" else exact
        value = Fraction(got)
        assert value in elements
        mean = sum(exact) / len(exact)
        if word == "min":
            assert all(value <= v for v in elements) and value <= mean
        else:
            assert all(value >= v for v in elements)
            if word == "max":
                assert value >= mean
        return
    for i, value in enumerate(Fraction(v) for v in got):
        assert value in exact[:i + 1]
        if word == "cummax":
            assert all(value >= v for v in exact[:i + 1])
        else:
            assert all(value <= v for v in exact[:i + 1])


# --- matrix words -------------------------------------------------------

#: square matrices by size, with a second matrix and two vectors of the
#: same size; repeated, negative and decimal entries among them
SQUARE = {
    1: [[[2]], [[-0.5]]],
    2: [[[1, 2], [3, 4]], [[0.1, 0.2], [0.3, 0.4]], [[-3, 0.5], [7, -0.25]],
        [[2, 2], [2, 3]]],
    3: [[[2, -1, 0], [-1, 2, -1], [0, -1, 2]],
        [[1, 0.5, -2], [0, 3, 0.25], [4, -1, 1]]],
}
PARTNER = {1: [[3]], 2: [[0, 1], [-2, 0.5]],
           3: [[1, 2, 3], [0, 1, 4], [5, 6, 0]]}
VECTOR = {1: ([4], [-0.5]), 2: ([1, -2], [0.25, 3]),
          3: ([1, 0.5, -1], [2, 2, 2])}
#: singular matrices, where an inverse has no value
SINGULAR = [[[0]], [[1, 2], [2, 4]], [[1, 1], [1, 1]],
            [[1, 2, 3], [4, 5, 6], [7, 8, 9]]]

MATRIX_CASES = [
    "det(A)", "trace(A)", "inv(A)", "transpose(A)", "A.T",
    "matrix_power(A, 0)", "matrix_power(A, 1)", "matrix_power(A, 3)",
    "matrix_power(A, -1)", "matrix_power(A, -2)",
    "dot(A, B)", "dot(A, x)", "dot(x, y)", "outer(x, y)", "kron(A, B)",
    "solve(A, x)", "norm(A)", "norm(x)", "abs(det(A))",
]


def _matrix_cases():
    for src in MATRIX_CASES:
        for n, mats in SQUARE.items():
            for A in mats:
                yield pytest.param(src, n, A, id=f"{src} at {A}")


@pytest.mark.parametrize("src, n, A", list(_matrix_cases()))
def test_a_matrix_word_has_one_value_on_both_routes(src, n, A):
    x, y = VECTOR[n]
    values = {"A": A, "B": PARTNER[n], "x": x, "y": y}
    used = {k: v for k, v in values.items()
            if k in {node.id for node in ast.walk(ast.parse(src))
                     if isinstance(node, ast.Name)}}
    try:
        defined, exact = matrix_value(src, **used)
    except ValueError:
        # the lift reads a 1-by-1 matrix as the number it holds, so a
        # matrix word on one is left to sampling, never proven
        assert n == 1, f"the lift declines {src} at {used}"
        return
    evaluated = evaluate(src, **used)
    assert defined, f"{src} at {used}: the lift has no value"
    assert same(evaluated, exact), (
        f"{src} at {used}: the lift gives {exact}, the evaluator "
        f"{evaluated!r}")


def test_the_identity_is_the_same_matrix_on_both_routes():
    for n in (1, 2, 3):
        _, exact = matrix_value(f"I({n})")
        assert same(evaluate(f"I({n})"), exact)


@pytest.mark.parametrize("A", SINGULAR, ids=str)
@pytest.mark.parametrize("src", ["inv(A)", "solve(A, x)",
                                 "matrix_power(A, -1)"])
def test_an_inverse_of_a_singular_matrix_has_no_value_on_either_route(src, A):
    """The lift records that the claim inverts `A` (a proof needs
    `det(A) != 0`), sympy finds no value at a singular `A`, and the
    evaluator raises there."""
    used = {"A": A}
    if "x" in src:
        used["x"] = [1] * len(A)
    tree = ast.parse(src, mode="eval")
    sym = sympy.MatrixSymbol("A", len(A), len(A))
    assert M._inverted_symbols(tree, {"A": sym}) == {sym}
    try:
        defined, _ = matrix_value(src, **used)
        assert not defined
    except ValueError:
        # the lift reads a 1-by-1 matrix as the number it holds
        assert len(A) == 1
    assert isinstance(evaluate(src, **used), Exception)


@pytest.mark.parametrize("A", [[[1, 2, 3], [4, 5, 6]], [[1, 2], [3, 4], [5, 6]],
                               [[7, -1]]], ids=str)
@pytest.mark.parametrize("word", ["trace", "det"])
def test_a_square_word_has_no_value_on_a_non_square_matrix(word, A):
    """`trace` and `det` are defined for a square matrix only: the lift
    refuses a non-square one, and the evaluator raises there."""
    with pytest.raises(ValueError):
        matrix_value(f"{word}(A)", A=A)
    assert isinstance(evaluate(f"{word}(A)", A=A), Exception)


@pytest.mark.parametrize("word", ["sum", "prod"])
def test_the_eigenvalue_lemmas_agree_with_the_evaluator(word):
    """The lift reads `sum(eigvals(A))` as `trace(A)` and
    `prod(eigvals(A))` as `det(A)`; at a triangular matrix, whose
    eigenvalues are its diagonal entries exactly, the evaluator gives
    the same value."""
    A = [[2, 1, -1], [0, -3, 4], [0, 0, 0.5]]
    _, exact = matrix_value(f"{word}(eigvals(A))", A=A)
    assert same(evaluate(f"{word}(eigvals(A))", A=A), exact)


# --- the table ----------------------------------------------------------

def _evaluator(name):
    return FUNCTIONS.get(name) or _SAFE_FUNCS[name]


#: a spelling of each word for each lowering, to ask whether it reads it
_SEQ_PROBE = {"dot": "dot(x, y)", "quantile": "quantile(x, 0.5)"}
_MAT_PROBE = {"I": "I(2)", "matrix_power": "matrix_power(A, 2)",
              "dot": "dot(A, B)", "outer": "outer(x, y)",
              "kron": "kron(A, B)", "solve": "solve(A, x)",
              "abs": "abs(A)"}


def _reads(lowering: str, w: G.Word, keyword=None) -> bool:
    if lowering == G.SEQUENCE:
        src = _SEQ_PROBE.get(w.name, f"{w.name}(x)")
        if keyword is not None:
            src = src[:-1] + f", {keyword[0]}={keyword[1]!r})"
        try:
            lower_sequence(src)
            return True
        except NotSymbolic:
            return False
    src = _MAT_PROBE.get(w.name, f"{w.name}(A)")
    try:
        matrix_value(src, A=[[1, 2], [3, 5]], B=[[0, 1], [1, 0]],
                     x=[1, 2], y=[3, 4])
        return True
    except (ValueError, KeyError, TypeError):
        return False


def test_the_table_names_every_word_the_evaluator_reads():
    evaluator = {w for w in FUNCTIONS if not w.startswith("_")} | {"len", "dim"}
    table = {w.name for w in G.WORDS} | set(G.SYNONYMS)
    assert evaluator == table, (
        f"in the evaluator only: {sorted(evaluator - table)}; in the table "
        f"only: {sorted(table - evaluator)}")


@pytest.mark.parametrize("w", G.WORDS, ids=lambda w: w.name)
def test_the_table_states_which_lowering_reads_each_word(w):
    for lowering in (G.SEQUENCE, G.MATRIX):
        assert _reads(lowering, w) == (lowering in w.lowering), (
            f"{w.name}: the table says the {lowering} lowering "
            f"{'reads' if lowering in w.lowering else 'does not read'} it")


def test_the_words_only_the_evaluator_reads_are_the_ones_listed():
    """Words the derive route leaves to sampling: their meaning is the
    evaluator's alone, so no proof rests on them."""
    sampled_only = sorted(w.name for w in G.WORDS if not w.lowering)
    assert sampled_only == ["cond", "diag", "eigvals", "eigvalsh", "median",
                            "pinv", "quantile"]


@pytest.mark.parametrize("w", G.WORDS, ids=lambda w: w.name)
def test_the_table_states_each_keyword_and_its_default(w):
    params = inspect.signature(_evaluator(w.name)).parameters.values()
    defaults = tuple((p.name, p.default) for p in params
                     if p.default is not inspect.Parameter.empty)
    assert defaults == w.keywords
    assert f"{w.name}(" in w.call
    for name, default in w.keywords:
        assert f"{name}={default!r}" in w.call


@pytest.mark.parametrize("w", [w for w in G.WORDS if G.SEQUENCE in w.lowering
                               and w.keywords], ids=lambda w: w.name)
def test_the_sequence_lowering_reads_only_the_keywords_the_table_lists(w):
    for keyword in w.keywords:
        value = 1 if keyword[0] in ("ddof", "ord") else 0
        assert _reads(G.SEQUENCE, w, (keyword[0], value)) == (
            keyword[0] in w.lowered_keywords), (w.name, keyword)


# --- holes --------------------------------------------------------------

HOLED = [[1, None, 3], [None, 2.5], [-4, None, None, 0.5, 2]]


def _slots(v):
    return [e for e in v if e is not None]


@pytest.mark.parametrize("v", HOLED, ids=str)
@pytest.mark.parametrize("w", [w for w in G.WORDS if w.holes != "entries"],
                         ids=lambda w: w.name)
def test_each_word_treats_a_hole_as_the_table_says(w, v):
    name = w.name
    holed = as_array(v)
    if w.holes == "every slot":
        assert evaluate(f"{name}(x)", x=v) == len(v)
        return
    if w.holes == "count":
        assert evaluate("count(x)", x=v) == len(_slots(v))
        assert evaluate("count(x)", x=[None, None]) == 0
        return
    if w.holes == "dot":
        other = [2, -1, 0.5, 3, 1][:len(v)]
        both = [(a, b) for a, b in zip(v, other) if a is not None]
        expected = sum(Fraction(a) * Fraction(b) for a, b in both)
        assert evaluate("dot(x, y)", x=v, y=other) == float(expected)
        apart = [None if e is not None else 1.5 for e in v]
        assert evaluate("dot(x, y)", x=v, y=apart) == 0
        return
    if w.holes == "elementwise":
        got = evaluate(f"{name}(x)", x=v)
        for e, g in zip(v, got):
            assert math.isnan(g) if e is None else g == abs(e)
        return
    if w.holes == "running":
        got = evaluate(f"{name}(x)", x=v)
        for i, (e, g) in enumerate(zip(v, got)):
            if e is None:
                assert math.isnan(g)
            else:
                assert g == evaluate(f"{name}(x)", x=_slots(v[:i + 1]))[-1]
        return
    spellings = {"quantile": ["quantile(x, 0.25)"],
                 "norm": ["norm(x)", "norm(x, 1)", "norm(x, 2)",
                          "norm(x, inf)", "norm(x, ord=1)"]}.get(
        name, [f"{name}(x)"])
    for src in spellings:
        assert evaluate(src, x=holed) == evaluate(src, x=_slots(v)), src
        over_none = evaluate(src, x=[None, None])
        if w.holes == "slots":
            assert _no_value(over_none), src
        else:
            identity = 0 if w.holes == "norm" else int(w.identity)
            assert over_none == identity, src
    if w.holes == "norm":
        matrix = [[1, None], [2, 3]]
        assert _no_value(evaluate("norm(A, 2)", A=matrix))
        assert evaluate("norm(A)", A=matrix) == evaluate(
            "norm(A)", A=[[1, 0], [2, 3]])


# --- the docs -----------------------------------------------------------

def test_the_docs_page_shows_the_table():
    page = open(os.path.join(_DOCS, "grammar-words.md"),
                encoding="utf-8").read()
    assert G.markdown_table() in page


@pytest.mark.parametrize("src, values, exact", [
    ("x @ y", {"x": [1e16, 1, -1e16], "y": [1, 1, 1]}, 1),
    ("A @ x", {"A": [[1e16, 1, -1e16], [0.1, 0.2, 0.3]], "x": [1, 1, 1]},
     [1, Fraction(0.1) + Fraction(0.2) + Fraction(0.3)]),
    ("x @ A @ x", {"A": [[1e300, 1e300], [1e300, 1e300]],
                   "x": [1e300, -1e300]}, 0),
])
def test_a_claims_matrix_product_is_exact(src, values, exact):
    """`@` in claim text is the exact inner product rounded once, as
    `dot` is, whatever the platform's float matmul would round to: the
    claim is compiled and evaluated as every route evaluates it."""
    from mathema.conjecture import _validate
    code, _ = _validate(src, set(values))
    got = eval(code, {**ENV, **{k: as_array(v) for k, v in values.items()}})  # noqa: S307
    want = exact if isinstance(exact, list) else [exact]
    assert [float(v) for v in np.ravel(got)] == [float(Fraction(v)) for v in want]
