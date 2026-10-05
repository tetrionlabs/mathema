# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The grammar's own words: what each one computes.

A claim's vector and matrix words (`sum`, `mean`, `std`, `dot`, `norm`,
`det`, `cumsum`, `quantile`, ...) are read in two places: the exact
evaluator that samples a claim (`_linalg_eval.FUNCTIONS`, with `len`
and `dim` from the claim namespace) and the symbolic lowering that
proves one (`symbolic/_seqir.py` for vectors of symbolic length,
`symbolic/_matrix.py` for matrix algebra). A trusted definition row
maps a library's function onto one of these words, so a proof through
the row rests on the word's meaning here.

`WORDS` states each word once: its formula, where it has a value, its
keyword arguments with their defaults, what it does with a hole (a
missing slot), and which lowering reads it. `markdown_table()` renders
the table the grammar-words docs page shows. The vocabulary of the
table: `x` and `y` are vectors of length `n`, `A` and `B` matrices, a
value slot is a position that holds a value rather than a hole.
"""
from __future__ import annotations

from dataclasses import dataclass

__all__ = ["HOLES", "MATRIX", "SEQUENCE", "SYNONYMS", "WORDS", "Word",
           "markdown_table", "word"]


#: what a word does with a hole, by rule name
HOLES = {
    "slots": "reads the value slots; a hole when every slot is one",
    "identity": "reads the value slots; {identity} when every slot is a "
                "hole",
    "count": "counts the value slots; 0 when every slot is a hole",
    "every slot": "counts every slot, holes included",
    "running": "a hole stays at its position; entry `i` reads the "
               "value slots among `0..i`",
    "elementwise": "a hole stays a hole",
    "dot": "reads the positions where both vectors hold a value; 0 when "
           "there is none",
    "norm": "reads the value slots at every order; 0 when every slot is "
            "a hole; a matrix's `ord=2` norm with a hole entry is a hole",
    "entries": "not read over holes: a hole entry is nan",
}

#: the lowerings that read a word
SEQUENCE = "sequence"
MATRIX = "matrix"


@dataclass(frozen=True)
class Word:
    """Intent:
        One grammar word: `call` its spelling with its keywords at
        their defaults, `formula` what it computes, `has_value` where it
        has a value (beyond its arguments having the shapes `call`
        names), `keywords` each keyword argument and its default, `holes`
        a rule name in `HOLES`, `least_length` the fewest elements a
        vector argument needs for a value as an expression in the
        keywords (None when the word takes no vector or needs only the
        one element every vector has), and `lowering` the symbolic
        lowerings that read it (`"sequence"`, `"matrix"`), with
        `lowered_keywords` the keywords they read (any other keyword
        leaves the claim to sampling). `identity` is the value a
        reduction with an identity gives over no value slot.
    """
    name: str
    call: str
    formula: str
    has_value: str
    keywords: tuple = ()
    holes: str = "entries"
    least_length: "str | None" = None
    lowering: frozenset = frozenset()
    lowered_keywords: tuple = ()
    identity: "str | None" = None


def _w(name, call, formula, has_value="always", keywords=(), holes="entries",
       least_length=None, lowering=(), lowered_keywords=(), identity=None):
    return Word(name, call, formula, has_value, tuple(keywords), holes,
                least_length, frozenset(lowering), tuple(lowered_keywords),
                identity)


_AXIS = (("axis", None),)
_SEQ = (SEQUENCE,)
_MAT = (MATRIX,)

#: every grammar word, in the order the docs page lists them
WORDS: tuple = (
    # counting
    _w("len", "len(x)", "the number of slots of `x`", holes="every slot",
       lowering=_SEQ),
    _w("dim", "dim(x, axis=0)", "the size of axis `axis` of `x`: a "
       "vector's length, a matrix's rows; `dim(A, 1)` its columns",
       keywords=(("axis", 0),), holes="every slot", lowering=_SEQ),
    _w("count", "count(x, axis=None)", "the number of value slots of `x`",
       keywords=_AXIS, holes="count", lowering=_SEQ),
    # reductions
    _w("sum", "sum(x, axis=None)", "`x[0] + x[1] + ... + x[n-1]`",
       keywords=_AXIS, holes="identity", identity="0", lowering=_SEQ),
    _w("prod", "prod(x, axis=None)", "`x[0] * x[1] * ... * x[n-1]`",
       keywords=_AXIS, holes="identity", identity="1", lowering=_SEQ),
    _w("mean", "mean(x, axis=None)", "`sum(x) / n`", keywords=_AXIS,
       holes="slots", lowering=_SEQ),
    _w("var", "var(x, ddof=0, axis=None)",
       "`sum((x[i] - mean(x))^2) / (n - ddof)`, the population variance "
       "at `ddof=0` and the sample variance at `ddof=1`",
       has_value="`n >= ddof + 1`", keywords=(("ddof", 0), ("axis", None)),
       holes="slots", least_length="ddof + 1", lowering=_SEQ,
       lowered_keywords=("ddof",)),
    _w("std", "std(x, ddof=0, axis=None)", "`sqrt(var(x, ddof))`",
       has_value="`n >= ddof + 1`", keywords=(("ddof", 0), ("axis", None)),
       holes="slots", least_length="ddof + 1", lowering=_SEQ,
       lowered_keywords=("ddof",)),
    _w("min", "min(x, axis=None)", "the least element of `x`; `min(a, b, "
       "...)` the least of several numbers", keywords=_AXIS, holes="slots",
       lowering=_SEQ),
    _w("max", "max(x, axis=None)", "the greatest element of `x`; `max(a, "
       "b, ...)` the greatest of several numbers", keywords=_AXIS,
       holes="slots", lowering=_SEQ),
    _w("median", "median(x, axis=None)", "the middle element of `x` "
       "sorted, or the mean of the middle two when `n` is even",
       keywords=_AXIS, holes="slots"),
    _w("quantile", "quantile(x, q)", "with `s` the sorted `x` and `h = (n "
       "- 1) * q`: `s[floor(h)] + (h - floor(h)) * (s[floor(h) + 1] - "
       "s[floor(h)])`, linear interpolation; a list of levels gives one "
       "quantile each", has_value="`0 <= q <= 1`", holes="slots"),
    # running reductions
    _w("cumsum", "cumsum(x, axis=None)", "entry `i` is `sum(x[0..i])`",
       keywords=_AXIS, holes="running", lowering=_SEQ),
    _w("cumprod", "cumprod(x, axis=None)", "entry `i` is `prod(x[0..i])`",
       keywords=_AXIS, holes="running", lowering=_SEQ),
    _w("cummax", "cummax(x, axis=None)", "entry `i` is `max(x[0..i])`",
       keywords=_AXIS, holes="running", lowering=_SEQ),
    _w("cummin", "cummin(x, axis=None)", "entry `i` is `min(x[0..i])`",
       keywords=_AXIS, holes="running", lowering=_SEQ),
    # elementwise
    _w("abs", "abs(x)", "`abs(x[i])` at every position; the absolute "
       "value of a number", holes="elementwise", lowering=_SEQ),
    # products and norms
    _w("dot", "dot(x, y)", "`sum(x[i] * y[i])` for two vectors of one "
       "length; the matrix product when either argument is a matrix",
       has_value="the inner dimensions agree", holes="dot",
       lowering=(SEQUENCE, MATRIX)),
    _w("norm", "norm(x, ord=None)", "`sqrt(sum(x[i]^2))`, the Euclidean "
       "norm of a vector and the Frobenius norm of a matrix; `ord=1` is "
       "`sum(abs(x[i]))` (a matrix's largest column sum), `ord=inf` "
       "`max(abs(x[i]))` (a matrix's largest row sum), `ord=2` on a "
       "matrix the largest singular value", keywords=(("ord", None),),
       holes="norm", lowering=(SEQUENCE, MATRIX),
       lowered_keywords=("ord",)),
    _w("outer", "outer(x, y)", "the matrix with entry `(i, j)` equal to "
       "`x[i] * y[j]`", lowering=_MAT),
    _w("kron", "kron(A, B)", "the Kronecker product: block `(i, j)` is "
       "`A[i, j] * B`", lowering=_MAT),
    # matrices
    _w("det", "det(A)", "the determinant of `A`", has_value="`A` square",
       lowering=_MAT),
    _w("trace", "trace(A)", "`A[0, 0] + A[1, 1] + ... + A[n-1, n-1]`",
       has_value="`A` square", lowering=_MAT),
    _w("transpose", "transpose(A)", "`A` with rows and columns exchanged, "
       "also written `A.T`; a vector is its own transpose", lowering=_MAT),
    _w("inv", "inv(A)", "the matrix `B` with `A @ B == I(n)`",
       has_value="`det(A) != 0`", lowering=_MAT),
    _w("solve", "solve(A, b)", "the `x` with `A @ x == b`, which is "
       "`inv(A) @ b`", has_value="`det(A) != 0`", lowering=_MAT),
    _w("I", "I(n)", "the `n` by `n` identity matrix",
       has_value="`n` a whole number, `n >= 0`", lowering=_MAT),
    _w("matrix_power", "matrix_power(A, k)", "`A @ A @ ... @ A`, `k` "
       "factors; `I(n)` at `k = 0`; `matrix_power(inv(A), -k)` for a "
       "negative `k`", has_value="`A` square, `k` whole; `det(A) != 0` "
       "for `k < 0`", lowering=_MAT),
    _w("diag", "diag(x)", "the square matrix with `x` on its diagonal and "
       "0 elsewhere; of a matrix, the vector of its diagonal entries"),
    _w("rank", "rank(A)", "the number of linearly independent rows of "
       "`A`", lowering=_MAT),
    _w("eigvals", "eigvals(A)", "the eigenvalues of `A`, each as often as "
       "its algebraic multiplicity, sorted by real then imaginary part",
       has_value="`A` square"),
    _w("eigvalsh", "eigvalsh(A)", "the eigenvalues of a symmetric `A`, "
       "real and ascending", has_value="`A` square and symmetric"),
    _w("cond", "cond(A)", "the largest singular value of `A` over its "
       "smallest", has_value="`A` of full rank"),
    _w("pinv", "pinv(A)", "the Moore-Penrose pseudoinverse of `A`"),
)

#: the grammar's spellings that read as another word
SYNONYMS = {"Abs": "abs"}


def word(name: str) -> Word:
    """The `Word` named `name`, a synonym read as the word it spells.

    Raises:
        KeyError: no grammar word has that name.
    """
    name = SYNONYMS.get(name, name)
    for w in WORDS:
        if w.name == name:
            return w
    raise KeyError(name)


def _keywords_text(w: Word) -> str:
    if not w.keywords:
        return "none"
    text = ", ".join(f"`{k}={v!r}`" for k, v in w.keywords)
    if w.lowering and w.lowered_keywords:
        text += " (derive reads " + ", ".join(
            f"`{k}`" for k in w.lowered_keywords) + ")"
    return text


#: how the docs table names each lowering
_LOWERING_TEXT = {SEQUENCE: "over vectors of any length",
                  MATRIX: "in matrix algebra"}


def _lowering_text(w: Word) -> str:
    return ", ".join(_LOWERING_TEXT[k] for k in (SEQUENCE, MATRIX)
                     if k in w.lowering) or "no, sampled only"


def markdown_table() -> str:
    """The grammar-words table as the docs page shows it: one row per
    word, its call, formula, where it has a value, keywords, holes and
    lowering."""
    rows = ["| Word | Computes | Has a value | Keywords | A hole | "
            "Derive reads it |",
            "|---|---|---|---|---|---|"]
    for w in WORDS:
        rows.append(f"| `{w.call}` | {w.formula} | {w.has_value} | "
                    f"{_keywords_text(w)} | "
                    f"{HOLES[w.holes].format(identity=w.identity)} | "
                    f"{_lowering_text(w)} |")
    return "\n".join(rows) + "\n"
