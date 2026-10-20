# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`is_finite(f(x))` and `is_real(f(x))` on a function that returns a
number are decided the same way whether numpy is installed or not: a
real number is finite when it is neither an infinity nor a NaN, a
complex number when both its parts are, and a bool is a finite real
number. `is_real` reads the value, not its type: a complex number is
real when its imaginary part is zero, and a vector or matrix is real
when every entry is. A Fraction or a Decimal is a number too, an empty
vector or matrix is finite and real, and a result that is not a number
(None, a string, a ragged list) is undecided, never finite or not."""

import json
import math
from decimal import Decimal
from fractions import Fraction
import os
import subprocess
import sys
from pathlib import Path

import pytest

import mathema.matrices as M

ROOT = Path(__file__).resolve().parent.parent

_CLAIMS = r'''
import json, math, sys
from decimal import Decimal
from fractions import Fraction
if BLOCK:
    sys.modules["numpy"] = None
from mathema.conjecture import check_conjectures, claim
from mathema.types import Mat, Vec


def guarded_sqrt(variance: float) -> float:
    if variance < 0:
        raise ValueError("variance is negative")
    return math.sqrt(variance)


def doubled(x: float) -> float:
    return x * 2.0


def unbounded(x: float) -> float:
    return math.inf


def as_complex(x: float) -> complex:
    return complex(x, 1.0)


def complex_infinite(x: float) -> complex:
    return complex(x, math.inf)


def complex_on_the_axis(x: float) -> complex:
    return complex(x, 0.0)


def positive(x: float) -> bool:
    return x > 0


def vector_on_the_axis(xs: Vec("n")) -> list:
    return [complex(v, 0.0) for v in xs]


def vector_off_the_axis(xs: Vec("n")) -> list:
    return [complex(v, 1.0) for v in xs]


def matrix_on_the_axis(a: Mat("n", "n")) -> list:
    return [[complex(v, 0.0) for v in row] for row in a]


def a_third(x: int) -> Fraction:
    return Fraction(x, 3)


def a_decimal_third(x: int) -> Decimal:
    return Decimal(x) / 3


def a_decimal_infinity(x: int) -> Decimal:
    return Decimal("Infinity")


def a_decimal_nan(x: int) -> Decimal:
    return Decimal("NaN")


def text(x: int) -> str:
    return "abc" * (x % 2 + 1)


def nothing(x: int):
    return None


def empty(x: int) -> list:
    return []


def nothing_for_positives(x: float):
    return None if x > 0 else x


def nothing_or_infinity(x: float):
    return None if x > 0 else math.inf


rows = [
    (guarded_sqrt, "is_finite(f(variance))"),
    (doubled, "is_finite(f(x))"),
    (unbounded, "is_finite(f(x))"),
    (as_complex, "is_finite(f(x))"),
    (complex_infinite, "is_finite(f(x))"),
    (doubled, "is_real(f(x))"),
    (as_complex, "is_real(f(x))"),
    (complex_on_the_axis, "is_real(f(x))"),
    (complex_on_the_axis, "is_finite(f(x))"),
    (positive, "is_finite(f(x))"),
    (positive, "is_real(f(x))"),
    (vector_on_the_axis, "is_real(f(xs))"),
    (vector_off_the_axis, "is_real(f(xs))"),
    (matrix_on_the_axis, "is_real(f(a))"),
    (a_third, "for x in [1, 5], is_finite(f(x))"),
    (a_third, "for x in [1, 5], is_real(f(x))"),
    (a_decimal_third, "for x in [1, 5], is_finite(f(x))"),
    (a_decimal_third, "for x in [1, 5], is_real(f(x))"),
    (a_decimal_infinity, "for x in [1, 5], is_finite(f(x))"),
    (a_decimal_nan, "for x in [1, 5], is_finite(f(x))"),
    (text, "for x in [1, 5], is_finite(f(x))"),
    (text, "for x in [1, 5], is_real(f(x))"),
    (nothing, "for x in [1, 5], is_finite(f(x))"),
    (nothing, "for x in [1, 5], is_real(f(x))"),
    (empty, "for x in [1, 5], is_finite(f(x))"),
    (empty, "for x in [1, 5], is_real(f(x))"),
    (nothing_for_positives, "is_finite(f(x))"),
    (nothing_or_infinity, "is_finite(f(x))"),
]
out = {}
for fn, text in rows:
    (p,) = check_conjectures(fn, [claim(text)])
    out[f"{fn.__name__}: {text}"] = [p.verdict, p.route, p.note or "",
                                     p.counterexample or ""]
print(json.dumps({"numpy": "numpy" in sys.modules
                  and sys.modules["numpy"] is not None, "rows": out}))
'''


def _run(block: bool, folder: Path) -> dict:
    script = folder / "claims.py"
    script.write_text(f"BLOCK = {block}\n" + _CLAIMS)
    done = subprocess.run([sys.executable, str(script)], cwd=ROOT,
                          env={**os.environ, "PYTHONPATH": str(ROOT)},
                          capture_output=True, text=True, timeout=600)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module", params=[True, False],
                ids=["numpy blocked", "numpy as installed"])
def rows(request, tmp_path_factory):
    got = _run(request.param, tmp_path_factory.mktemp("claims"))
    if request.param:
        assert got["numpy"] is False
    return got["rows"]


def test_a_finite_scalar_result_holds(rows):
    for key in ("doubled: is_finite(f(x))",
                "guarded_sqrt: is_finite(f(variance))"):
        verdict, route, note, _ = rows[key]
        assert (verdict, route) == ("holds", "probe:algorithmic"), (key, note)
        assert "no evaluable inputs" not in note, (key, note)


def test_the_guarded_row_still_states_its_working_domain(rows):
    note = rows["guarded_sqrt: is_finite(f(variance))"][2]
    assert "the working domain is variance in [0, oo)" in note, note


def test_an_infinite_scalar_result_is_falsified(rows):
    verdict, _, note, witness = rows["unbounded: is_finite(f(x))"]
    assert verdict == "falsified", note
    assert "result is not finite" in witness, witness


def test_a_complex_result_is_finite_when_both_parts_are(rows):
    verdict, _, note, _ = rows["as_complex: is_finite(f(x))"]
    assert verdict == "holds", note
    verdict, _, note, witness = rows["complex_infinite: is_finite(f(x))"]
    assert verdict == "falsified", note
    assert "result is not finite" in witness, witness


def test_a_real_scalar_result_is_real_and_a_complex_one_is_not(rows):
    verdict, _, note, _ = rows["doubled: is_real(f(x))"]
    assert verdict == "holds", note
    verdict, _, note, witness = rows["as_complex: is_real(f(x))"]
    assert verdict == "falsified", note
    assert "result is not real" in witness, witness


def test_a_complex_result_on_the_real_axis_is_real(rows):
    for key in ("complex_on_the_axis: is_real(f(x))",
                "complex_on_the_axis: is_finite(f(x))"):
        verdict, route, note, _ = rows[key]
        assert (verdict, route) == ("holds", "probe:algorithmic"), (key, note)


@pytest.fixture(scope="module")
def numpy_free_rows(tmp_path_factory):
    got = _run(True, tmp_path_factory.mktemp("claims"))
    assert got["numpy"] is False
    return got["rows"]


def test_without_numpy_a_complex_vector_or_matrix_is_real_on_the_axis(
        numpy_free_rows):
    for key in ("vector_on_the_axis: is_real(f(xs))",
                "matrix_on_the_axis: is_real(f(a))"):
        verdict, route, note, _ = numpy_free_rows[key]
        assert (verdict, route) == ("holds", "probe:algorithmic"), (key, note)
    verdict, _, note, witness = \
        numpy_free_rows["vector_off_the_axis: is_real(f(xs))"]
    assert verdict == "falsified", note
    assert "result is not real" in witness, witness


def test_a_bool_result_is_finite_and_real(rows):
    for key in ("positive: is_finite(f(x))", "positive: is_real(f(x))"):
        verdict, route, note, _ = rows[key]
        assert (verdict, route) == ("holds", "probe:algorithmic"), (key, note)


def test_a_fraction_or_decimal_result_is_read_by_its_value(rows):
    for name in ("a_third", "a_decimal_third"):
        for prop in ("is_finite", "is_real"):
            key = f"{name}: for x in [1, 5], {prop}(f(x))"
            verdict, route, note, _ = rows[key]
            assert (verdict, route) == ("holds", "probe:algorithmic"), \
                (key, note)
    for name in ("a_decimal_infinity", "a_decimal_nan"):
        verdict, _, note, witness = \
            rows[f"{name}: for x in [1, 5], is_finite(f(x))"]
        assert verdict == "falsified", (name, note)
        assert "result is not finite" in witness, witness


def test_a_result_that_is_not_a_number_is_undecided(rows):
    for name in ("text", "nothing"):
        for prop in ("is_finite", "is_real"):
            key = f"{name}: for x in [1, 5], {prop}(f(x))"
            verdict, _, note, _ = rows[key]
            assert verdict == "unknown", (key, note)
            assert "x = 1: the result is not a number" in note, (key, note)


def test_a_result_that_is_not_a_number_at_some_points_is_undecided(rows):
    verdict, _, note, _ = rows["nothing_for_positives: is_finite(f(x))"]
    assert verdict == "unknown", note
    assert "the result is not a number" in note, note


def test_a_point_that_falsifies_outweighs_a_result_that_is_not_a_number(rows):
    verdict, _, note, witness = rows["nothing_or_infinity: is_finite(f(x))"]
    assert verdict == "falsified", note
    assert "result is not finite" in witness, witness


def test_an_empty_result_is_finite_and_real(rows):
    for prop in ("is_finite", "is_real"):
        key = f"empty: for x in [1, 5], {prop}(f(x))"
        verdict, route, note, _ = rows[key]
        assert (verdict, route) == ("holds", "probe:algorithmic"), (key, note)


_SCALARS = [
    (3, True, True), (2.5, True, True), (-0.0, True, True),
    (True, True, True), (False, True, True),
    (math.nan, False, True), (math.inf, False, True),
    (-math.inf, False, True),
    (1 + 2j, True, False), (1 + 0j, True, True),
    (complex(math.inf, 0.0), False, True),
    (complex(math.nan, 0.0), False, True),
    (complex(0.0, math.nan), False, False),
    (complex(0.0, math.inf), False, False), (10 ** 400, True, True),
    (Fraction(1, 3), True, True), (Decimal("1.5"), True, True),
    (Decimal("NaN"), False, True), (Decimal("Infinity"), False, True),
    (Decimal("-Infinity"), False, True),
]


@pytest.mark.parametrize("value,finite,real", _SCALARS,
                         ids=[repr(v[0]) for v in _SCALARS])
def test_the_pure_python_checks_decide_a_number(monkeypatch, value,
                                                finite, real):
    monkeypatch.setattr(M, "_numpy", lambda: None)
    assert M.PROPERTIES["is_finite"].check(value) is finite
    assert M.PROPERTIES["is_real"].check(value) is real


_VECTORS = [
    ([1.0, 2.0], True, True), ([1, 2.5], True, True),
    ([True, 2.0], True, True), ([[True, False], [0.0, 1.0]], True, True),
    ([1.0, math.inf], False, True), ([[False, math.nan], [0.0, 1.0]], False, True),
    ([1.0, 2j], True, False), ([1.0, 0j], True, True),
    ([[1.0, 0.0], [0.0, 1.0]], True, True),
    ([[1.0, 1j], [0.0, 1.0]], True, False),
    ([[1.0, 0j], [0.0, 1.0]], True, True),
    ([[1, 2j], [0, 1]], True, False),
    ([1.0, complex(0.0, math.inf)], False, False),
    ([], True, True), ([[]], True, True), ((1.0, 2.0), True, True),
    ([Fraction(1, 2)], True, True), ([Decimal("NaN"), 1.0], False, True),
    ([[True]], True, True), ([[[1.0], [2.0]], [[3.0], [math.inf]]], False, True),
    ([[1, 2], [3]], None, None), ([[1, 2], [[3], 4]], None, None),
    ([None], None, None), ([1.0, None], None, None),
    (None, None, None), ("abc", None, None), ({"a": 1.0}, None, None),
]


@pytest.mark.parametrize("value,finite,real", _VECTORS,
                         ids=[repr(v[0]) for v in _VECTORS])
def test_the_pure_python_checks_read_a_vector_or_matrix(monkeypatch, value,
                                                        finite, real):
    monkeypatch.setattr(M, "_numpy", lambda: None)
    assert M.PROPERTIES["is_finite"].check(value) is finite
    assert M.PROPERTIES["is_real"].check(value) is real


@pytest.mark.parametrize("value", [v for v, _, _ in _SCALARS + _VECTORS],
                         ids=[repr(v) for v, _, _ in _SCALARS + _VECTORS])
def test_numpy_and_pure_python_agree_on_numbers(monkeypatch, value):
    pytest.importorskip("numpy")
    with_numpy = {n: M.PROPERTIES[n].check(value)
                  for n in ("is_finite", "is_real")}
    monkeypatch.setattr(M, "_numpy", lambda: None)
    without = {n: M.PROPERTIES[n].check(value)
               for n in ("is_finite", "is_real")}
    assert with_numpy == without


def test_a_numpy_array_or_scalar_reads_as_the_values_it_holds():
    np = pytest.importorskip("numpy")
    for value in ([1.0, 2.0], [1.0, math.nan], [[1, 0j], [0, 1]],
                  [[1, 2j], [0, 1]], [[[1.0], [math.inf]]], [], [[]]):
        for name in ("is_finite", "is_real"):
            assert M.PROPERTIES[name].check(np.asarray(value)) is \
                M.PROPERTIES[name].check(value), (name, value)
    for scalar, finite, real in ((np.int64(3), True, True),
                                 (np.float32("nan"), False, True),
                                 (np.complex64(1 + 0j), True, True),
                                 (np.complex128(complex(0, 1)), True, False),
                                 (np.bool_(True), True, True)):
        assert M.PROPERTIES["is_finite"].check(scalar) is finite, scalar
        assert M.PROPERTIES["is_real"].check(scalar) is real, scalar
    assert M.PROPERTIES["is_finite"].check(np.asarray(["a"])) is None
