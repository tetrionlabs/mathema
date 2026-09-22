# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The linear-algebra grammar layer: the matrix sugar (`A^T`, `|A|`,
`A^-1`) reads as transpose / determinant / inverse only for a matrix
operand, and as power / absolute value / reciprocal for a scalar one.
The reading is decided by the parameter's declared type (a signature
marker, an `R^(m*n)` domain, or a `let ... be` declaration), never
guessed, and the record's grammar is stamped `mathema/linalg` as an
informative marker that never gates round-tripping."""
import textwrap

import pytest

from mathema.conjecture import GRAMMAR, check_conjectures, claim
from mathema.linalg import apply_matrix_sugar
from mathema.records import statement_text


def _stmt(cj):
    return statement_text(cj.relation, cj.lhs, cj.rhs)


# --- the sugar primitive ---------------------------------------------------

def test_apply_matrix_sugar_on_matrix_operands():
    m = frozenset({"A", "B"})
    assert apply_matrix_sugar("A ** T", m) == "A.T"
    assert apply_matrix_sugar("A ** -1", m) == "inv(A)"
    assert apply_matrix_sugar("abs(A)", m) == "det(A)"
    assert apply_matrix_sugar("abs(A @ B)", m) == "det(A @ B)"


def test_apply_matrix_sugar_leaves_scalars_alone():
    # no name is a matrix: power, reciprocal and absolute value stand.
    assert apply_matrix_sugar("x ** T", frozenset()) == "x ** T"
    assert apply_matrix_sugar("x ** -1", frozenset({"A"})) == "x ** -1"
    assert apply_matrix_sugar("abs(x)", frozenset({"A"})) == "abs(x)"


# --- type-aware resolution in claim() -------------------------------------

def test_inline_domain_makes_the_sugar_matrix():
    for law in ("for A in R^(n*n), A^T == A",
                "let A be R^(n*n), A^T == A"):
        cj = claim(law)
        assert cj.lhs == "A.T"
        assert cj.grammar == f"{GRAMMAR}/linalg"


def test_single_bar_determinant_and_inverse():
    cj = claim("for A in R^(n*n), |A| >= 0")
    assert cj.lhs == "det(A)"
    cj = claim("for A in R^(n*n), A^-1 @ A == I(n)")
    assert cj.lhs == "inv(A) @ A"


def test_passed_matrix_names_resolve_the_sugar():
    cj = claim("A^T == A", matrix_names=frozenset({"A"}))
    assert cj.lhs == "A.T"
    assert cj.raw == "A^T == A"


def test_scalar_claim_is_untouched_and_stays_base_grammar():
    cj = claim("x^-1 == 1/x")
    assert cj.lhs == "x**-1"
    assert cj.grammar == GRAMMAR
    cj = claim("|x| >= 0")
    assert cj.lhs == "abs(x)"
    assert cj.grammar == GRAMMAR


def test_mixed_scalar_and_matrix_power_minus_one():
    # one expression, both spellings of `^-1`: the matrix operand
    # resolves to an inverse, the scalar operand stays a reciprocal.
    assert apply_matrix_sugar("c ** -1 * A ** -1",
                              frozenset({"A"})) == "c ** (-1) * inv(A)"
    # and the same through a claim whose own domain types each name
    cj = claim("for A in R^(n*n), c in (0, 10), inv(c * A) == c^-1 * A^-1")
    assert cj.rhs == "c ** (-1) * inv(A)"      # scalar reciprocal, matrix inverse
    assert "inv(A)" in cj.rhs and "inv(c)" not in cj.rhs
    assert cj.grammar == f"{GRAMMAR}/linalg"


def test_sugar_and_canonical_share_one_statement():
    # the whole point: A^T and A.T are the same claim once A is a matrix.
    a = claim("for A in R^(n*n), A^T == A")
    b = claim("for A in R^(n*n), A.T == A")
    assert _stmt(a) == _stmt(b)
    c = claim("for A in R^(n*n), A^-1 @ A == I(n)")
    d = claim("for A in R^(n*n), inv(A) @ A == I(n)")
    assert _stmt(c) == _stmt(d)


def test_the_linalg_grammar_tag_is_not_required_to_round_trip():
    # the canonical statement re-parses under base mathema on its own;
    # the mathema/linalg tag is informative, never load-bearing.
    cj = claim("for A in R^(n*n), A^T == A")
    again = claim(f"for A in R^(n*n), {_stmt(cj)}")
    assert again.lhs == cj.lhs == "A.T"
    assert again.relation == cj.relation
    assert again.rhs == cj.rhs


# --- resolution from the function signature (no inline domain) ------------

@pytest.fixture(scope="module")
def mats(tmp_path_factory):
    p = tmp_path_factory.mktemp("la") / "m.py"
    p.write_text(textwrap.dedent('''
        from typing import Annotated
        from mathema.types import Mat, Shape, Symmetric

        def f(A: Mat("n", "n"), B: Mat("n", "n")):
            return A

        def sym(A: Annotated[list, Shape("n", "n"), Symmetric]):
            return A
    '''))
    import importlib.util

    spec = importlib.util.spec_from_file_location("la", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _one(fn, law, route="derive"):
    (pr,) = check_conjectures(fn, [claim(law, route=route)])
    return pr


def test_determinant_sugar_resolved_from_signature_and_proves(mats):
    # |A|, |B| are single-atom determinant sugar; A, B are matrices only
    # by their Mat markers, resolved at check time, and the identity
    # proves through the derive backend.
    pr = _one(mats.f, "det(A @ B) == |A| * |B|")
    assert pr.verdict == "proven"
    assert pr.route == "derive"
    assert pr.grammar == f"{GRAMMAR}/linalg"
    assert pr.statement == "det(A @ B) = det(A)*det(B)"


def test_transpose_sugar_from_marker_proves(mats):
    pr = _one(mats.sym, "A^T == A")
    assert pr.verdict == "proven"
    assert pr.statement == "A.T = A"


def test_scalar_parameter_keeps_the_scalar_reading(mats):
    # a bare `claim(...)` object handed to check against a function whose
    # A is NOT a matrix: the sugar stays scalar, the reciprocal reading.
    src = textwrap.dedent('''
        def g(A: float) -> float:
            """A scalar reciprocal."""
            return 1.0 / A
    ''')
    import importlib.util
    import os
    import tempfile

    d = tempfile.mkdtemp()
    p = os.path.join(d, "g.py")
    with open(p, "w") as fh:
        fh.write(src)
    spec = importlib.util.spec_from_file_location("g", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    (pr,) = check_conjectures(mod.g, [claim("f(A) == A^-1", route="best")])
    # A^-1 read as a reciprocal, not a matrix inverse
    assert "inv(" not in pr.statement
    assert pr.grammar == GRAMMAR


# --- which names are genuinely undeclared matrix operands -------------------

def test_undeclared_operands_are_only_bare_names_under_matmul_or_transpose():
    """`operand_matrix_names` collects every name nested under a matrix
    operator, which a renderer wants but this question does not: it
    counts the callee of `I(n)` and the scalar `c` of `det(c * A)`, so
    subtracting the declared names from it reports perfectly well-formed
    claims as undeclared."""
    from mathema.linalg import undeclared_matrix_operands
    declared = {"A", "n"}

    # every one of these is well formed and must flag nothing
    for law in ("I(n) @ A", "A @ I(n)", "inv(I(n))", "I(n).T",
                "det(c * A)", "trace(c * A)", "inv(A) @ A", "A @ A.T",
                "det(A) * det(inv(A))"):
        assert undeclared_matrix_operands((law, ""), declared) == (), law

    # a bare name under `@` or `.T` that was never given dimensions is
    # the case neither route can model
    assert undeclared_matrix_operands(("x.T @ A @ x", ""), declared) == ("x",)
    assert undeclared_matrix_operands(("A @ x", "b"), declared) == ("x",)
    assert undeclared_matrix_operands(("A @ x", "y.T"), declared) == ("x", "y")

    # an unparseable side contributes nothing rather than raising
    assert undeclared_matrix_operands(("A @ (", ""), declared) == ()
