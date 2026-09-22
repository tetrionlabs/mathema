# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The matrix property family adjudicates structure claims through the
examine route: an output claim `is_symmetric(f(A))` samples the input,
computes the output and checks it; a bare-parameter claim
`is_symmetric(A)` checks that the function guards the precondition, the
value analogue of excluded_outside_domain."""
import textwrap

import pytest


@pytest.fixture(scope="module")
def mats(tmp_path_factory):
    p = tmp_path_factory.mktemp("mp") / "m.py"
    p.write_text(textwrap.dedent('''
        def symmetrize(a: list) -> list:
            """The symmetric part of a matrix."""
            n = len(a)
            return [[(a[i][j] + a[j][i]) / 2.0 for j in range(n)]
                    for i in range(n)]

        def keep(a: list) -> list:
            """Identity; output is not generally symmetric."""
            return a

        def strict_solve(a: list, b: list) -> list:
            """Requires a symmetric matrix; raises otherwise."""
            n = len(a)
            if any(abs(a[i][j] - a[j][i]) > 1e-9
                   for i in range(n) for j in range(n)):
                raise ValueError("a must be symmetric")
            return b

        def lax_solve(a: list, b: list) -> list:
            """Accepts any matrix; guards nothing."""
            return b
    '''))
    import importlib.util

    spec = importlib.util.spec_from_file_location("m", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _one(fn, law):
    from mathema.conjecture import check_conjectures, claim
    (p,) = check_conjectures(fn, [claim(law, route="examine")])
    return p


def test_output_symmetry_holds_and_falsifies(mats):
    good = _one(mats.symmetrize, "is_symmetric(f(a))")
    assert good.verdict == "holds"
    assert good.route in ("examine", "probe:algorithmic")

    bad = _one(mats.keep, "is_symmetric(f(a))")
    assert bad.verdict == "falsified"
    assert bad.counterexample


def test_the_guard_reading_of_a_bare_parameter(mats):
    guarded = _one(mats.strict_solve, "is_symmetric(a)")
    assert guarded.verdict == "holds"
    lax = _one(mats.lax_solve, "is_symmetric(a)")
    assert lax.verdict == "falsified"
    assert "not enforced" in (lax.counterexample or "")


def test_finiteness_of_the_output(mats):
    p = _one(mats.symmetrize, "is_finite(f(a))")
    assert p.verdict == "holds"


def test_the_postfix_spelling_adjudicates_identically(mats):
    call = _one(mats.symmetrize, "is_symmetric(f(a))")
    # a bare-param postfix; guards on strict_solve
    post = _one(mats.strict_solve, "a is symmetric")
    assert call.verdict == "holds"
    assert post.verdict == "holds"


def test_the_expression_postfix_spelling_reads_the_output(mats):
    # `f(a) is symmetric` is the postfix spelling of `is_symmetric(f(a))`:
    # the subject is a call, not a bare parameter, and it reads the
    # output exactly as the predicate form does.
    call = _one(mats.symmetrize, "is_symmetric(f(a))")
    post = _one(mats.symmetrize, "f(a) is symmetric")
    assert post.name == call.name
    assert post.verdict == call.verdict == "holds"
    bad = _one(mats.keep, "f(a) is symmetric")
    assert bad.verdict == "falsified"
    assert bad.counterexample


def test_enforce_structure_guards_a_marked_matrix():
    import random

    from mathema.authoring import declared_from_function, enforce_structure
    from mathema.matrices import PROPERTIES
    from mathema.types import Mat, PositiveDefinite, Vec

    @enforce_structure()
    def solve(a: Mat("n", "n", PositiveDefinite), b: Vec("n")) -> list:
        """Solve; needs a positive-definite."""
        return b

    pd = PROPERTIES["is_positive_definite"].synth(3, random.Random(0))
    assert solve(pd, [1, 2, 3]) == [1, 2, 3]        # PD passes
    with pytest.raises(ValueError, match="not is_positive_definite"):
        solve([[1, 2, 3], [0, 1, 0], [0, 0, 1]], [1, 2, 3])  # not symmetric

    # the guard auto-declares the predicate claim (entailment-closed)
    names = {c.get("name") for c in declared_from_function(solve)}
    assert "is_positive_definite[a]" in names
    assert "is_symmetric[a]" in names       # entailed


def test_enforce_structure_rejects_a_non_finite_matrix():
    from mathema.authoring import enforce_structure
    from mathema.types import Finite, Mat

    @enforce_structure()
    def op(a: Mat("n", "n", Finite)) -> list:
        """Needs a finite matrix."""
        return a

    assert op([[1.0, 2.0], [3.0, 4.0]]) is not None
    with pytest.raises(ValueError, match="not is_finite"):
        op([[1.0, float("nan")], [0.0, 1.0]])
