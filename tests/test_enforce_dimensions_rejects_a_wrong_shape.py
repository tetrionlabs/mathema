# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`@enforce_dimensions()` guards a function's dimensions at entry and
at exit: each shaped argument has the rank and the fixed sizes its
marker or claim binding states, a dimension name shared across
parameters agrees across the actual arguments, and the result matches
the return marker with the names this call bound. Each failure is a
`ValueError` naming the parameter (or the result), the shape found and
the shape expected. It stacks with `@enforce_domain()`, which stays
about values."""
import pytest

from mathema import claims_decorator, enforce_dimensions, enforce_domain
from mathema.types import Mat, Vec


def _matvec():
    @enforce_dimensions()
    def matvec(a: Mat("m", "n"), x: Vec("n")) -> Vec("m"):
        """Matrix times vector."""
        return [sum(a[i][j] * x[j] for j in range(len(x)))
                for i in range(len(a))]
    return matvec


def test_a_conformable_call_reaches_the_function():
    matvec = _matvec()
    assert matvec([[1, 2, 3, 4]] * 3, [1, 1, 1, 1]) == [10, 10, 10]


def test_a_shared_dimension_must_agree_across_the_arguments():
    matvec = _matvec()
    with pytest.raises(ValueError) as err:
        matvec([[1, 2, 3, 4]] * 3, [1, 1, 1, 1, 1])
    assert ("x has length 5; a is 3 by 4, so x must have length 4"
            in str(err.value)), str(err.value)


def test_a_wrong_rank_is_rejected():
    matvec = _matvec()
    with pytest.raises(ValueError) as err:
        matvec([1, 2, 3], [1, 2, 3])
    text = str(err.value)
    assert "a has length 3" in text, text
    assert 'Mat("m", "n")' in text, text


def test_a_fixed_size_from_the_marker_is_enforced():
    @enforce_dimensions()
    def diag_sum(A: Mat(30, 15)) -> float:
        """Sum of the diagonal."""
        return float(sum(A[i][i] for i in range(15)))

    assert diag_sum([[1.0] * 15 for _ in range(30)]) == 15.0
    with pytest.raises(ValueError) as err:
        diag_sum([[1.0] * 3 for _ in range(2)])
    assert ("A is 2 by 3; the shape Mat(30, 15) expects 30 by 15"
            in str(err.value)), str(err.value)


def test_a_fixed_size_from_the_claim_binding_is_enforced():
    @enforce_dimensions()
    @claims_decorator("for xs in [0, 1]^30, f(xs) >= 0")
    def total(xs: list) -> float:
        """Sum."""
        return sum(xs)

    assert total([0.5] * 30) == 15.0
    with pytest.raises(ValueError) as err:
        total([0.5] * 5)
    text = str(err.value)
    assert "xs has length 5" in text, text
    assert "expects length 30" in text, text


def test_the_result_is_checked_against_the_return_marker():
    @enforce_dimensions()
    def bad_matvec(a: Mat("m", "n"), x: Vec("n")) -> Vec("m"):
        """Returns a vector of the wrong length."""
        return [0.0] * len(x)

    with pytest.raises(ValueError) as err:
        bad_matvec([[1, 2, 3, 4]] * 3, [1, 1, 1, 1])
    assert ('bad_matvec returned length 4; the return shape Vec("m") with '
            'm = 3 expects length 3' in str(err.value)), str(err.value)


def test_a_result_of_the_declared_shape_is_returned():
    @enforce_dimensions()
    def row_sums(a: Mat("m", "n")) -> Vec("m"):
        """Sum of each row."""
        return [sum(row) for row in a]

    assert row_sums([[1, 2], [3, 4], [5, 6]]) == [3, 7, 11]


def test_a_numpy_result_is_read_through_its_adapter():
    np = pytest.importorskip("numpy")

    @enforce_dimensions()
    def first_row(A: Mat("m", "n", runtime="numpy.ndarray")) -> Vec("n"):
        """The first row, as an array."""
        return A[0]

    assert list(first_row(np.ones((3, 4)))) == [1.0] * 4

    @enforce_dimensions()
    def first_column_as_row(A: Mat("m", "n", runtime="numpy.ndarray")) -> Vec("n"):
        """Claims a row, returns a column."""
        return A[:, 0]

    with pytest.raises(ValueError) as err:
        first_column_as_row(np.ones((3, 4)))
    assert "returned length 3" in str(err.value), str(err.value)
    assert "expects length 4" in str(err.value), str(err.value)


def test_it_stacks_with_enforce_domain():
    @enforce_dimensions()
    @enforce_domain()
    @claims_decorator("for x in [0, 1]^3, f(x) >= 0")
    def total(x: Vec(3)) -> float:
        """Sum of three values in [0, 1]."""
        return sum(x)

    assert total([0.5, 0.5, 0.5]) == 1.5
    with pytest.raises(ValueError, match="x has length 2"):
        total([0.5, 0.5])
    with pytest.raises(ValueError, match="outside its declared domain"):
        total([0.5, 0.5, 1.5])


def test_the_premise_guard_still_applies():
    @enforce_dimensions()
    @claims_decorator("assuming dim(x, 0) >= 3, f(x) == f(x)")
    def head(x: list) -> float:
        """First three summed."""
        return x[0] + x[1] + x[2]

    assert head([1.0, 2.0, 3.0]) == 6.0
    with pytest.raises(ValueError, match=">= 3"):
        head([1.0, 2.0])


def test_it_auto_declares_the_exclusion_for_its_parameters():
    """The decorator that makes wrong-shape rejection true also declares
    it, as `@enforce_domain()` does: one `excluded_outside_domain(p)`
    per checked parameter, proven by construction."""
    import mathema
    matvec = _matvec()
    declared = {c["name"]: c["statement"]
                for c in getattr(matvec, "__mathema_claims__", [])}
    assert declared == {"excluded_outside_domain[a]": "excluded_outside_domain(a)",
                        "excluded_outside_domain[x]": "excluded_outside_domain(x)"}
    rec = mathema.check(matvec, claims=[])
    rows = {p.name: p for p in rec.probes if p.name.startswith("excluded_outside_domain")}
    assert set(rows) == set(declared), rows
    for p in rows.values():
        assert p.verdict == "proven", (p.name, p.verdict, p.note)
        assert "enforce_dimensions" in (p.sketch or ""), p.sketch
    with pytest.raises(ValueError):
        matvec([1, 2, 3], [1, 2, 3])


def test_stacking_in_either_order_gives_the_same_rows_and_errors():
    import mathema

    def build(outer, inner):
        @outer()
        @inner()
        @claims_decorator("for x in [0, 1]^3, f(x) >= 0")
        def total(x: Vec(3)) -> float:
            """Sum of three values in [0, 1]."""
            return sum(x)
        return total

    first = build(enforce_dimensions, enforce_domain)
    second = build(enforce_domain, enforce_dimensions)
    declared = [sorted((c["name"], c["statement"])
                       for c in getattr(fn, "__mathema_claims__", []))
                for fn in (first, second)]
    assert declared[0] == declared[1], declared
    assert ("excluded_outside_domain[x]", "excluded_outside_domain(x)") in declared[0]
    rows = [sorted((p.name, p.verdict) for p in mathema.check(fn, claims=[]).probes)
            for fn in (first, second)]
    assert rows[0] == rows[1], rows
    assert ("excluded_outside_domain[x]", "proven") in rows[0], rows[0]
    errors = []
    for fn in (first, second):
        assert fn([0.5, 0.5, 0.5]) == 1.5
        with pytest.raises(ValueError) as short:
            fn([0.5, 0.5])
        with pytest.raises(ValueError) as outside:
            fn([0.5, 0.5, 1.5])
        errors.append((str(short.value), str(outside.value)))
    assert errors[0] == errors[1], errors
    assert "x has length 2" in errors[0][0], errors[0]
    assert "outside its declared domain" in errors[0][1], errors[0]
