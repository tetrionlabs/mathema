# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The matrix lemma layer: facts of real square matrices of every size
that sympy's matrix algebra does not apply on its own.

Each lemma is checked twice: a true identity it proves on the strict
derive route for a symbolic size `n`, and a false sibling it must not
prove, which the best route then falsifies with a witnessing draw.
"""
import textwrap

import pytest

pytest.importorskip("numpy")


@pytest.fixture(scope="module")
def mats(tmp_path_factory):
    p = tmp_path_factory.mktemp("lemmas") / "lemma_fns.py"
    p.write_text(textwrap.dedent('''
        from mathema.types import Mat, Vec

        def two(A: Mat("n", "n"), B: Mat("n", "n")):
            return A

        def three(A: Mat("n", "n"), B: Mat("n", "n"), C: Mat("n", "n")):
            return A

        def scaled(A: Mat("n", "n"), B: Mat("n", "n"), c: float):
            return A

        def form(A: Mat("n", "n"), x: Vec("n")):
            return A
    '''))
    import importlib.util

    spec = importlib.util.spec_from_file_location("lemma_fns", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _one(fn, law, route):
    from mathema.conjecture import check_conjectures, claim

    (pr,) = check_conjectures(fn, [claim(law, route=route)])
    return pr


#: (lemma, function, a true identity, its false sibling)
LEMMAS = [
    ("trace cyclicity", "two",
     "trace(A @ B) == trace(B @ A)",
     "trace(A @ B) == trace(A) * trace(B)"),
    ("trace cyclicity, three factors", "three",
     "trace(A @ B @ C) == trace(C @ A @ B)",
     "trace(A @ B @ C) == trace(B @ A @ C)"),
    ("trace of a transpose", "two",
     "trace(A @ B.T) == trace(B @ A.T)",
     "trace(A @ B.T) == trace(A @ B)"),
    ("linearity of trace", "scaled",
     "trace(c*A + B) == c*trace(A) + trace(B)",
     "trace(c*A + B) == trace(A) + c*trace(B)"),
    ("left distributivity", "three",
     "A @ (B + C) == A @ B + A @ C",
     "A @ (B + C) == A @ B + C @ A"),
    ("right distributivity", "three",
     "(A + B) @ C == A @ C + B @ C",
     "(A + B) @ C == C @ A + C @ B"),
    ("bilinear square", "two",
     "(A + B) @ (A + B) == A @ A + A @ B + B @ A + B @ B",
     "(A + B) @ (A + B) == A @ A + 2*(A @ B) + B @ B"),
    ("the product does not commute", "two",
     "(A @ B).T == B.T @ A.T",
     "A @ B == B @ A"),
    ("scaling through a product", "scaled",
     "(c*A) @ B == c*(A @ B)",
     "(c*A) @ B == c*(B @ A)"),
    ("elementwise is not the matrix product", "two",
     "A * B == B * A",
     "A * B == A @ B"),
    ("transpose of a sum and a product", "two",
     "(A + B).T @ B == A.T @ B + B.T @ B",
     "(A @ B).T == A.T @ B.T"),
    ("a Gram trace is nonnegative", "two",
     "trace(A @ A.T) >= 0",
     "trace(A @ B) >= 0"),
    ("a Gram determinant is nonnegative", "two",
     "det(A @ A.T) >= 0",
     "det(A @ A.T) > 0"),
    ("a Gram quadratic form is nonnegative", "form",
     "x.T @ (A @ A.T) @ x >= 0",
     "x.T @ A @ x >= 0"),
    ("trace is the sum of the eigenvalues", "two",
     "trace(A) == sum(eigvals(A))",
     "trace(A) == prod(eigvals(A))"),
    ("det is the product of the eigenvalues", "two",
     "det(A) == prod(eigvals(A))",
     "det(A) == sum(eigvals(A))"),
    ("det of a scaled matrix", "scaled",
     "det(c*A) == c**n * det(A)",
     "det(c*A) == c * det(A)"),
    ("det is not additive", "two",
     "det(A @ B) == det(B) * det(A)",
     "det(A + B) == det(A) + det(B)"),
    ("rank of a Gram product", "two",
     "rank(A @ A.T) == rank(A.T @ A)",
     "rank(A + B) == rank(A) + rank(B)"),
]


@pytest.mark.parametrize("lemma, fn, true, false", LEMMAS,
                         ids=[row[0] for row in LEMMAS])
def test_the_lemma_proves_its_identity_for_every_size(mats, lemma, fn,
                                                      true, false):
    pr = _one(getattr(mats, fn), true, "derive")
    assert pr.verdict == "proven", (lemma, pr.verdict, pr.sketch, pr.note)
    assert pr.route == "derive"


@pytest.mark.parametrize("lemma, fn, true, false", LEMMAS,
                         ids=[row[0] for row in LEMMAS])
def test_the_false_sibling_is_not_proven(mats, lemma, fn, true, false):
    pr = _one(getattr(mats, fn), false, "derive")
    assert pr.verdict != "proven", (lemma, pr.sketch)


@pytest.mark.parametrize("lemma, fn, true, false", LEMMAS,
                         ids=[row[0] for row in LEMMAS])
def test_the_false_sibling_is_falsified_with_a_witness(mats, lemma, fn,
                                                       true, false):
    pr = _one(getattr(mats, fn), false, "best")
    assert pr.verdict == "falsified", (lemma, pr.verdict, pr.note)
    assert pr.counterexample, lemma


def test_a_lemma_proof_names_the_lemmas_it_used(mats):
    pr = _one(mats.two, "trace(A @ B) == trace(B @ A)", "derive")
    assert "trace cyclicity" in (pr.sketch or ""), pr.sketch
    assert "trace cyclicity" in pr.meta.get("mathema.matrix_lemmas", ()), \
        pr.meta


def test_rank_of_a_gram_product_is_the_rank_of_its_factor(mats):
    pr = _one(mats.two, "rank(A @ A.T) == rank(A)", "derive")
    assert pr.verdict == "proven", pr.sketch


def test_a_proof_stands_over_a_numerical_rank_draw(mats):
    # numpy's matrix_rank can disagree at an ill-conditioned draw; the
    # identity holds of every real matrix, and the proof is the verdict
    pr = _one(mats.two, "rank(A @ A.T) == rank(A)", "best")
    assert pr.verdict == "proven"
    assert pr.route == "derive"


#: (function, a structure claim that follows, a sibling that does not)
STRUCTURES = [
    ("two", "is_symmetric(A @ A.T)", "is_symmetric(A @ B)"),
    ("two", "is_symmetric(A.T @ B @ B.T @ A)", "is_symmetric(A.T @ B @ A)"),
    ("two", "is_symmetric(A + A.T)", "is_symmetric(A - B.T)"),
    ("two", "is_positive_semidefinite(A.T @ A)",
     "is_positive_semidefinite(A @ B)"),
    ("two", "assuming A is orthogonal, is_orthogonal(A.T)",
     "is_orthogonal(A.T)"),
    ("two", "assuming A is orthogonal and B is orthogonal, "
            "is_orthogonal(A @ B)",
     "assuming A is orthogonal, is_orthogonal(A @ B)"),
    ("two", "assuming A is positive definite, is_positive_definite(inv(A))",
     "is_positive_definite(A.T @ A)"),
    ("two", "assuming det(A) != 0, is_positive_definite(A.T @ A)",
     "assuming A is positive definite and B is positive definite, "
     "is_positive_definite(A @ B)"),
    ("two", "assuming A is symmetric and B is symmetric, "
            "is_symmetric(A @ B @ A)",
     "assuming A is symmetric and B is symmetric, is_symmetric(A @ B)"),
    ("two", "assuming A is upper triangular and B is upper triangular, "
            "is_upper_triangular(A @ B)",
     "assuming A is upper triangular, is_upper_triangular(A @ B)"),
    ("two", "assuming A is upper triangular, is_lower_triangular(A.T)",
     "assuming A is upper triangular, is_lower_triangular(A.T @ A)"),
    ("two", "assuming A is diagonal and B is diagonal, "
            "is_diagonal(A @ B + B)",
     "assuming A is diagonal, is_diagonal(A @ B)"),
]


@pytest.mark.parametrize("fn, true, false", STRUCTURES,
                         ids=[row[1] for row in STRUCTURES])
def test_a_structure_that_follows_is_proven(mats, fn, true, false):
    pr = _one(getattr(mats, fn), true, "derive")
    assert pr.verdict == "proven", (pr.verdict, pr.sketch, pr.note)
    assert pr.route == "derive"


@pytest.mark.parametrize("fn, true, false", STRUCTURES,
                         ids=[row[1] for row in STRUCTURES])
def test_a_structure_that_does_not_follow_is_not_proven(mats, fn, true,
                                                        false):
    pr = _one(getattr(mats, fn), false, "derive")
    assert pr.verdict != "proven", pr.sketch


@pytest.mark.parametrize("fn, true, false", STRUCTURES,
                         ids=[row[1] for row in STRUCTURES])
def test_a_structure_that_does_not_follow_is_falsified(mats, fn, true,
                                                       false):
    pr = _one(getattr(mats, fn), false, "best")
    assert pr.verdict == "falsified", (pr.verdict, pr.note)
    assert pr.counterexample


def test_a_guard_claim_on_a_bare_parameter_is_not_a_structure_proof(mats):
    # `is_symmetric(A)` asks whether f rejects a matrix that lacks the
    # property, a question about the function, never read as a proof
    # from the premise that states it
    pr = _one(mats.two, "assuming A is symmetric, is_symmetric(A)", "derive")
    assert pr.route != "derive" or pr.verdict != "proven"
