# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The MatrixSymbol derive backend: a matrix-algebra relation claim
(`det(A @ B) == det(A) * det(B)`, `(A @ B).T == B.T @ A.T`, ...) is
proved in sympy's matrix algebra rather than by lifting f's body.
Structure markers and `assuming` premises become sympy assumptions, so
`A.T == A` proves for a symmetric A. An identity sympy cannot close
falls to the matrix-value probe: sampled concrete matrices, a witness on
disagreement, and the honest derive `unknown` when the strict `derive`
route forbids sampling."""
import textwrap

import pytest


@pytest.fixture(scope="module")
def mats(tmp_path_factory):
    p = tmp_path_factory.mktemp("md") / "m.py"
    p.write_text(textwrap.dedent('''
        from typing import Annotated

        from mathema.types import (Mat, Shape, Orthogonal, PositiveDefinite,
                                   Symmetric)

        def f(A: Mat("n", "n"), B: Mat("n", "n")):
            """Two square matrices of a shared dimension."""
            return A

        def sym(A: Annotated[list, Shape("n", "n"), Symmetric]):
            """A is declared symmetric by its type marker."""
            return A

        def orth(A: Annotated[list, Shape("n", "n"), Orthogonal]):
            """A is declared orthogonal by its type marker."""
            return A

        def one(A: Mat("n", "n")):
            """A single square matrix, no structure marker."""
            return A

        def pd(A: Annotated[list, Shape("n", "n"), PositiveDefinite]):
            """A is declared positive definite by its type marker."""
            return A
    '''))
    import importlib.util

    spec = importlib.util.spec_from_file_location("md", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _one(fn, law, route="derive"):
    from mathema.conjecture import check_conjectures, claim

    (pr,) = check_conjectures(fn, [claim(law, route=route)])
    return pr


def test_determinant_of_product_proves(mats):
    pr = _one(mats.f, "det(A @ B) == det(A) * det(B)")
    assert pr.verdict == "proven"
    assert pr.route == "derive"
    assert "matrix" in (pr.sketch or "")


def test_transpose_of_product_proves(mats):
    pr = _one(mats.f, "(A @ B).T == B.T @ A.T")
    assert pr.verdict == "proven"
    assert pr.route == "derive"


def test_trace_is_additive_proves(mats):
    pr = _one(mats.f, "trace(A + B) == trace(A) + trace(B)")
    assert pr.verdict == "proven"
    assert pr.route == "derive"


def test_symmetry_from_marker_proves(mats):
    pr = _one(mats.sym, "A.T == A")
    assert pr.verdict == "proven"
    assert pr.route == "derive"
    assert "is_symmetric" in (pr.sketch or "")


def test_symmetry_from_assuming_premise_proves(mats):
    pr = _one(mats.one, "assuming A is symmetric, A.T == A")
    assert pr.verdict == "proven"
    assert pr.route == "derive"
    assert "is_symmetric" in (pr.sketch or "")


def test_orthogonal_marker_gives_identity(mats):
    pr = _one(mats.orth, "A.T @ A == I(n)")
    assert pr.verdict == "proven"
    assert pr.route == "derive"


def test_unmarked_matrix_is_not_symmetric(mats):
    # no marker, no premise: A.T == A is not an identity, so the derive
    # route stays honest: unknown on the strict route.
    pr = _one(mats.one, "A.T == A", route="derive")
    assert pr.verdict == "unknown"
    assert pr.route == "derive"


def test_false_identity_strict_derive_is_unknown(mats):
    pr = _one(mats.f, "det(A @ B) == det(A) + det(B)", route="derive")
    assert pr.verdict == "unknown"
    assert pr.route == "derive"


def test_false_identity_best_falsifies_with_witness(mats):
    pr = _one(mats.f, "det(A @ B) == det(A) + det(B)", route="best")
    assert pr.verdict == "falsified"
    assert pr.route == "probe"
    assert pr.counterexample
    assert "A=" in pr.counterexample and "B=" in pr.counterexample


def test_true_identity_best_prefers_proof(mats):
    # on route="best" a provable identity still comes back proven via the
    # derive route, because the proof fires before any sampling.
    pr = _one(mats.f, "det(A @ B) == det(A) * det(B)", route="best")
    assert pr.verdict == "proven"
    assert pr.route == "derive"


def test_unprovable_true_identity_best_holds_by_sampling(mats):
    # the cyclic-trace law is true but sympy does not close it here; the
    # matrix-value probe samples it and reports the holds ceiling.
    pr = _one(mats.f, "trace(A @ B) == trace(B @ A)", route="best")
    assert pr.verdict == "holds"
    assert pr.route == "probe"
    assert pr.n > 0


def test_pure_algebra_proves_without_numpy(mats, monkeypatch):
    import mathema.matrices as M

    monkeypatch.setattr(M, "_numpy", lambda: None)
    # transpose / matmul lift to sympy regardless of numpy
    pr = _one(mats.f, "(A @ B).T == B.T @ A.T")
    assert pr.verdict == "proven"
    assert pr.route == "derive"


def test_determinant_probe_declines_without_numpy(mats, monkeypatch):
    import mathema.matrices as M

    monkeypatch.setattr(M, "_numpy", lambda: None)
    # det needs numpy: the matrix-value probe cannot sample it, so a
    # false det identity on route="best" degrades to the honest unknown
    # rather than a spurious verdict.
    pr = _one(mats.f, "det(A @ B) == det(A) + det(B)", route="best")
    assert pr.verdict == "unknown"
    assert pr.route == "derive"


def test_positive_definite_has_positive_determinant(mats):
    pr = _one(mats.pd, "det(A) > 0")
    assert pr.verdict == "proven"
    assert pr.route == "derive"
    assert "positive_definite" in (pr.sketch or "")


def test_positive_definite_has_positive_trace(mats):
    pr = _one(mats.pd, "trace(A) > 0")
    assert pr.verdict == "proven"
    assert pr.route == "derive"


def test_inequality_from_assuming_premise_and_sugar_proves(mats):
    # the premise supplies the structure, the sugar |A| -> det(A):
    # a positive-definite matrix has positive determinant.
    pr = _one(mats.one, "assuming A is positive definite, |A| > 0")
    assert pr.verdict == "proven"
    assert pr.route == "derive"


def test_false_matrix_inequality_falsifies_with_witness(mats):
    # a positive-definite matrix's determinant is never negative
    pr = _one(mats.one, "assuming A is positive definite, det(A) < 0",
              route="best")
    assert pr.verdict == "falsified"
    assert pr.route == "probe"
    assert pr.counterexample


def test_unconditional_determinant_sign_falsifies(mats):
    # det(A) > 0 is not true for every matrix; sampling finds a witness
    pr = _one(mats.f, "det(A) > 0", route="best")
    assert pr.verdict == "falsified"
    assert pr.route == "probe"


def test_domain_restricted_proof_records_per_branch_lines(tmp_path):
    # a proof restricted to x >= 0 prunes the `x < 0` branch, and the
    # proven probe records only the reachable lines (for the coverage
    # pass), excluding the pruned branch's line.
    import importlib.util
    import inspect
    import textwrap

    from mathema.conjecture import check_conjectures, claim as _claim

    p = tmp_path / "pb.py"
    p.write_text(textwrap.dedent("""
        def f(x: float) -> float:
            if x < 0.0:
                return -x
            return x
    """))
    spec = importlib.util.spec_from_file_location("pb", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    start = inspect.getsourcelines(mod.f)[1]

    (pr,) = check_conjectures(mod.f,
                              [_claim("for x in [0, 100], f(x) == x", route="derive")])
    assert pr.verdict == "proven"
    lines = pr.meta.get("mathema.derive_lines")
    assert lines is not None
    assert (start + 2) not in lines          # the `return -x` branch is pruned
    assert (start + 3) in lines              # the `return x` branch is covered

    # a full-domain proof prunes nothing, so no per-branch attribution
    (pr2,) = check_conjectures(mod.f, [_claim("f(x) == abs(x)")])
    assert pr2.meta.get("mathema.derive_lines") is None


# --- a 1-D parameter under a matrix operator --------------------------------

def test_a_vec_under_matmul_declines_instead_of_crashing(tmp_path, monkeypatch):
    """A `Vec("n")` is 1-D, so `_matrix_params` never promotes it to a
    MatrixSymbol. It used to fall through to a bare `Symbol` and crash
    the instant `.T`/`@` asked it for `.shape`, with the AttributeError
    escaping `check()` entirely. An unsupported construct declines with
    a reason; it never crashes."""
    import mathema
    src = tmp_path / "quadfix.py"
    src.write_text(
        "from mathema.types import Mat, Vec\n"
        "\n"
        "def quad_form(A: Mat('n', 'n'), x: Vec('n')) -> float:\n"
        '    """Quadratic form."""\n'
        "    return float(x.T @ A @ x)\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    import importlib
    import sys
    sys.modules.pop("quadfix", None)
    importlib.invalidate_caches()
    fn = __import__("quadfix").quad_form
    # the assertion is simply that this returns rather than raising
    (p,) = mathema.claims.check_conjectures(
        fn, [mathema.claim("f(A, x) >= 0", route="derive")])
    assert p.verdict


def test_the_lift_refuses_a_shapeless_matrix_operand():
    """`_shaped` guards the operator itself, so any entry into `_lift`
    is covered, not only the one that checked its operands up front."""
    import ast

    import pytest
    import sympy

    A = sympy.MatrixSymbol("A", 2, 2)
    from mathema.symbolic._matrix import _lift
    for src in ("x.T @ A @ x", "A @ x", "x.T"):
        with pytest.raises(ValueError, match="not a matrix"):
            _lift(ast.parse(src, mode="eval"), {"A": A})
    # the guard must not be satisfiable by refusing everything
    assert _lift(ast.parse("A @ A", mode="eval"), {"A": A}) == A * A


def test_the_undeclared_operand_reason_reaches_the_verdict():
    """The remedy is the useful half of the decline, so it has to
    survive to the record rather than being discarded with a bare
    None."""
    import mathema
    from mathema.types import Mat, Vec

    def quad_form(A: Mat("n", "n"), x: Vec("n")) -> float:
        """Quadratic form."""
        return float(x.T @ A @ x)

    (p,) = mathema.claims.check_conjectures(
        quad_form, [mathema.claim("x.T @ A @ x >= 0", route="derive")])
    assert p.verdict == "unknown", p.verdict
    assert "not declared two-dimensional" in (p.sketch or ""), p.sketch
    assert 'Mat("n", 1)' in (p.sketch or ""), p.sketch


def test_the_remedy_the_decline_suggests_actually_works():
    """Advice that names a specific spelling has to keep working, or it
    rots into a wrong answer. Declaring the vector as a column matrix
    makes the claim liftable and a real identity over it provable."""
    import mathema
    from mathema.types import Mat

    def quad_form(A: Mat("n", "n"), x: Mat("n", 1)) -> float:
        """Quadratic form, x as a column matrix."""
        return float(x.T @ A @ x)

    (p,) = mathema.claims.check_conjectures(
        quad_form,
        [mathema.claim("(x.T @ A @ x).T == x.T @ A.T @ x", route="derive")])
    assert p.verdict == "proven", (p.verdict, p.sketch)


def test_scalar_division_lifts_in_a_matrix_claim():
    """`_lift` had no `ast.Div` case at all, so `det(inv(A)) ==
    1/det(A)` declined as an unsupported operator, reading as a proof
    gap rather than a missing case."""
    import ast

    import sympy

    from mathema.symbolic._matrix import _lift
    A = sympy.MatrixSymbol("A", 2, 2)
    lifted = _lift(ast.parse("1/det(A)", mode="eval"), {"A": A})
    assert lifted == 1 / sympy.Determinant(A)
