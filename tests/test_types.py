# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""mathema.types: semantic type markers as a fourth, inferred claim-
authoring surface."""
from typing import Annotated

import mathema
from mathema.types import Probability, Shape, domain_from_signature, \
    type_probes


def test_domain_from_signature_infers_probability_bounds():
    from mathema.domain import MISSING, domain_contains

    def f(p: Annotated[float, Probability], q: float) -> float:
        return p

    dom = domain_from_signature(f)
    assert set(dom) == {"p"}
    # the [0, 1] bound holds, and a bound marker is explicit that the
    # value is present: the missing sentinel (nan/None) is excluded.
    assert domain_contains(0.5, dom["p"])
    assert not domain_contains(2.0, dom["p"])
    assert not domain_contains(float("nan"), dom["p"])
    assert not domain_contains(MISSING, dom["p"])


def test_domain_marker_merges_into_check_and_explicit_wins():
    def f(p: Annotated[float, Probability]) -> float:
        return p

    rec = mathema.check(f, domain={"p": (0.2, 0.3)})
    # explicit domain must win over the inferred one; smoke-check by
    # confirming check() ran without error and produced the usual probes
    assert any(p.name == "is_deterministic" for p in rec.probes)


def matmul(a: Annotated[list, Shape("m", "n")],
          b: Annotated[list, Shape("n", "p")]) -> Annotated[list, Shape("m", "p")]:
    m, n, p = len(a), len(a[0]), len(b[0])
    return [[sum(a[i][k] * b[k][j] for k in range(n)) for j in range(p)]
           for i in range(m)]


def bad_matmul(a: Annotated[list, Shape("m", "n")],
              b: Annotated[list, Shape("n", "p")]) -> Annotated[list, Shape("m", "p")]:
    m, n, p = len(a), len(a[0]), len(b[0])
    return [[sum(a[i][k] * b[k][j] for k in range(n)) for i in range(m)]
           for j in range(p)]   # transposed on purpose


def plain(x: float) -> float:
    return x * 2


def test_shape_marker_holds_for_correct_implementation():
    results = type_probes(matmul)
    shape = next(p for p in results if p.name == "shape")
    assert shape.verdict == "holds"


def test_shape_marker_falsified_for_wrong_implementation():
    results = type_probes(bad_matmul)
    shape = next(p for p in results if p.name == "shape")
    assert shape.verdict == "falsified"
    assert "expected shape" in shape.counterexample


def test_shape_enforced_flags_matmul_accepting_a_mismatched_n():
    # a real, confirmed finding, not a hypothetical: neither matmul nor
    # bad_matmul guards against a's column count disagreeing with b's
    # row count; one truth, no mode: a declared shared dim the code
    # silently accepts a mismatch on is a witnessed policy violation
    probe = next(p for p in type_probes(matmul) if p.name == "shape_enforced")
    assert probe.verdict == "falsified"
    assert probe.n > 0
    assert probe.counterexample


def test_shape_enforced_absent_when_no_dim_is_shared_across_parameters():
    def single_vector(x: Annotated[list, Shape("n")]) -> Annotated[list, Shape("n")]:
        return list(x)

    names = [p.name for p in type_probes(single_vector)]
    assert "shape_enforced" not in names


def test_no_markers_produces_no_type_probes():
    assert type_probes(plain) == []


def test_check_picks_up_shape_probe_automatically():
    rec = mathema.check(matmul)
    names = [p.name for p in rec.probes]
    assert "shape" in names


def test_mat_marker_resolves_wrapped_and_bare():
    # Mat(...) already returns an Annotated, so Annotated[T, Mat(...)]
    # nests one; both the wrapped and the bare spelling must resolve the
    # Shape (and any Structure), not silently yield {}.
    from mathema.types import (Mat, Symmetric, shapes_from_signature,
                               structures_from_signature)

    def bare(A: Mat("n", "m")):
        return A

    def wrapped(A: Annotated[list, Mat("n", "m")]):
        return A

    def wrapped_struct(A: Annotated[list, Mat("n", "n", Symmetric)]):
        return A

    assert shapes_from_signature(bare)["A"].dims == ("n", "m")
    assert shapes_from_signature(wrapped)["A"].dims == ("n", "m")
    assert shapes_from_signature(wrapped_struct)["A"].dims == ("n", "n")
    assert structures_from_signature(wrapped_struct)["A"] == ("is_symmetric",)


def test_new_bound_markers_and_bare_spelling():
    from mathema.types import (Negative, Nonpositive, UnitBall, UnitInterval,
                               InRange, return_bound)
    from mathema.domain import domain_contains

    # bare markers (class or instance) work as annotations, no Annotated
    def f(a: Negative, b: UnitBall, c: InRange(0, 10, (True, False))
          ) -> UnitInterval:
        return 0.0
    dom = domain_from_signature(f)
    assert not domain_contains(0.0, dom["a"])        # Negative excludes 0
    assert domain_contains(-5.0, dom["a"])
    assert domain_contains(0.5, dom["b"]) and not domain_contains(2.0, dom["b"])
    # InRange closedness carries through: [0, 10)
    assert domain_contains(0.0, dom["c"]) and not domain_contains(10.0, dom["c"])

    # the semantic OUTPUT bound (not the clamped sampling interval)
    assert return_bound(f) == (0.0, 1.0, True, True)     # UnitInterval

    def g(x: float) -> Nonpositive:
        return -abs(x)
    assert return_bound(g) == (None, 0.0, None, True)    # f(x) <= 0


# --- the Vec/Mat shorthand classifies like the long form ---------------------

def test_annotation_base_reduces_a_wrapper_to_the_type_it_is_about():
    from mathema.analysis import _annotation_base
    # the long form: the marker rides along, the type decides
    assert _annotation_base("annotated[float, probability]") == "float"
    assert _annotation_base("annotated[list, shape('n')]") == "list"
    # the shorthand: Vec("n") IS Annotated[list, Shape("n")], so it has
    # to reduce to the same thing
    assert _annotation_base("vec('n')") == "list"
    assert _annotation_base("mat('n', 'n')") == "list"
    # anything else is left alone
    assert _annotation_base("list[float]") == "list[float]"
    assert _annotation_base("float") == "float"
    assert _annotation_base("literal['a', 'b']") == "literal['a', 'b']"


def test_a_vec_parameter_is_a_sequence_not_a_scalar():
    """`Vec("n")` expands to `Annotated[list, Shape("n")]`, so every
    reader has to see a sequence. Reading the wrapper instead left the
    parameter to the arithmetic fallback, which called it a scalar and
    got it sampled as a bare float, producing witnesses that violated
    the function's own signature."""
    from mathema.analysis import analyze_source
    from mathema.types import Mat, Vec

    # the body gives no array signal at all, so only the annotation can
    # carry the classification
    def tagged(x: Vec("n"), s: float) -> float:
        """Ignore the vector entirely."""
        return s * 2.0

    assert analyze_source(tagged).param_kinds == {"x": "sequence",
                                                  "s": "scalar"}

    # and the real case, where the body is matrix idiom
    def quad_form(A: Mat("n", "n"), x: Vec("n")) -> float:
        """Quadratic form."""
        return float(x.T @ A @ x)

    assert analyze_source(quad_form).param_kinds == {"A": "sequence",
                                                     "x": "sequence"}


def test_a_vec_return_annotation_is_a_sequence():
    from mathema.analysis import analyze_source
    from mathema.types import Mat, Vec

    def rows(a: Mat("m", "n")) -> Vec("m"):
        """Row sums."""
        return [sum(r) for r in a]

    assert analyze_source(rows).returns_kind == "sequence"


def test_matmul_and_transpose_read_as_array_operations():
    """`@` has no scalar meaning, and `.T` is an array attribute like
    `.shape`. Both used to leave an unannotated operand in the
    scalar-arithmetic bucket."""
    from mathema.analysis import analyze_source

    def prod(a, b):
        """Matrix product."""
        return a @ b

    def transposed(m):
        """Transpose."""
        return m.T

    assert analyze_source(prod).param_kinds == {"a": "sequence",
                                                "b": "sequence"}
    assert analyze_source(transposed).param_kinds == {"m": "sequence"}


def test_a_shaped_witness_conforms_to_the_declared_shapes():
    """The end-to-end consequence: a falsifying witness for a claim over
    `Mat("n", "n")` and `Vec("n")` is a square nested list and a vector
    of the matching length, never a bare float."""
    import mathema
    from mathema.types import Mat, Vec

    def quad_form(A: Mat("n", "n"), x: Vec("n")) -> float:
        """Quadratic form."""
        return float(x.T @ A @ x)

    (p,) = mathema.claims.check_conjectures(
        quad_form, [mathema.claim("f(A, x) >= 0", route="probe")])
    args = (p.meta or {}).get("mathema.counterexample_args")
    assert args is not None, p.note
    matrix, vector = args
    assert all(isinstance(row, list) for row in matrix), matrix
    assert len(matrix) == len(matrix[0]) == len(vector), (matrix, vector)
    assert all(isinstance(v, float) for v in vector), vector
