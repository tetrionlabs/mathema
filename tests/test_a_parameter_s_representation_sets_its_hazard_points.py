# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A parameter's number representation sets where the probe looks for
the machine breaking: a KOINE body whose parameter is an `i64` has its
extreme hazard points at the `i64` range's ends and around zero, an
`f32` parameter at float32's overflow scales, and a body that names no
representation (every Python function) keeps the float64 ladder. Each
reserved representation word has exactly one profile, and how overflow
shows for a function is what its manifest says, never assumed."""
import math
import sys

import pytest

from mathema.analysis import analyze_source
from mathema.domain import Interval
from mathema.grammar import _RESERVED_REPRESENTATIONS
from mathema.hazards import _REPRESENTATION_LADDER, hazard_points
from mathema.koine import Document
from mathema.koine.facts import facts_from_koine
from mathema.representations import (PROFILES, PY_FLOAT64, PY_INT, overflow_semantics,
                                     profile)
from tests._koine_docs import at, koi

INCREMENT = f"statement::return(operator::binary::addition(x, 1), {at()})"

TRAPS = "manifest(nonvalue::machine::overflow, as::panic)"


def _document(representation: str, kind: str = "int", manifest: str = TRAPS) -> Document:
    return Document.parse(koi(INCREMENT, manifest=manifest,
                              params=f"parameter(x, kind::{kind}, "
                                     f"representation::{representation})"))


def _extremes(fn, facts, domain=None) -> list:
    return [p.value for p in hazard_points(fn, facts, domain or {}, kinds=["extreme"])]


def increment(x: float) -> float:
    return x + 1


def test_an_i64_parameter_s_extremes_are_the_i64_range_ends_and_around_zero():
    values = _extremes(None, facts_from_koine(_document("i64")))
    assert sorted(values) == [-2**63, -1, 0, 1, 2**63 - 1]
    assert all(type(v) is int for v in values)


def test_an_i64_extreme_reads_as_the_exact_integer():
    points = hazard_points(None, facts_from_koine(_document("i64")), {}, kinds=["extreme"])
    assert {p.at for p in points} == {str(-2**63), "-1", "0", "1", str(2**63 - 1)}


def test_a_128_bit_parameter_s_extremes_are_its_range_ends():
    assert sorted(_extremes(None, facts_from_koine(_document("i128")))) == [
        -2**127, -1, 0, 1, 2**127 - 1]
    assert sorted(_extremes(None, facts_from_koine(_document("u128")))) == [0, 1, 2**128 - 1]


def test_an_f16_parameter_overflows_at_half_precision_s_maximum():
    values = _extremes(None, facts_from_koine(_document("f16", kind="scalar")))
    assert 65504.0 in values and -65504.0 in values
    assert sys.float_info.max not in values


def test_an_unsigned_parameter_s_extremes_stay_in_its_range():
    assert sorted(_extremes(None, facts_from_koine(_document("u8")))) == [0, 1, 255]


def test_a_declared_bound_keeps_only_the_extremes_it_admits():
    facts = facts_from_koine(_document("i64"))
    assert sorted(_extremes(None, facts, {"x": (0, math.inf)})) == [0, 1, 2**63 - 1]


def test_an_f32_parameter_overflows_at_float32_s_maximum_not_float64_s():
    values = _extremes(None, facts_from_koine(_document("f32", kind="scalar")))
    assert 3.4028234663852886e38 in values and -3.4028234663852886e38 in values
    assert sys.float_info.max not in values


def test_an_f64_parameter_has_the_float64_ladder_a_python_function_has():
    from_document = _extremes(None, facts_from_koine(_document("f64", kind="scalar")))
    assert from_document == _extremes(increment, analyze_source(increment))


def test_a_python_function_keeps_the_float64_ladder():
    values = _extremes(increment, analyze_source(increment))
    assert values == list(_REPRESENTATION_LADDER) + [-v for v in _REPRESENTATION_LADDER]


def test_a_python_int_parameter_still_has_no_extreme_points():
    def bump(n: int) -> int:
        return n + 1
    assert _extremes(bump, analyze_source(bump)) == []


def test_every_reserved_representation_word_has_exactly_one_profile():
    assert set(PROFILES) == set(_RESERVED_REPRESENTATIONS)
    assert all(profile(tag).tag == tag for tag in PROFILES)


def test_a_profile_states_its_range_and_its_arithmetic_at_overflow():
    i64 = profile("i64")
    assert (i64.min_value, i64.max_value, i64.overflow) == (-2**63, 2**63 - 1, "wrap")
    assert (profile("u8").min_value, profile("u8").max_value) == (0, 255)
    assert profile("f32").max_value == 3.4028234663852886e38
    assert profile("f64") is PY_FLOAT64 and profile("bigint") is PY_INT
    assert profile("bigint").max_value is None


def test_the_float_profiles_state_their_unit_roundoff():
    assert profile("f64").unit_roundoff == 2.0**-53
    assert profile("f32").unit_roundoff == 2.0**-24
    assert profile("f16").unit_roundoff == 2.0**-11


def test_an_unknown_representation_word_is_refused_by_name():
    with pytest.raises(KeyError, match="i256"):
        profile("i256")


@pytest.mark.parametrize("manifest, word", [
    ("manifest(nonvalue::machine::overflow, as::panic)", "trap"),
    ("manifest(nonvalue::machine::overflow, as::trap)", "trap"),
    ('manifest(nonvalue::machine::overflow, as::raise("ArithmeticException"))', "trap"),
    ("manifest(nonvalue::machine::overflow, as::undefined)", "ub"),
    ("manifest(nonvalue::machine::overflow, as::nonfinite)", "inf"),
])
def test_how_overflow_shows_is_what_the_manifest_says(manifest, word):
    assert overflow_semantics(_document("i64", manifest=manifest), "x") == word


def test_a_manifest_that_does_not_say_how_overflow_shows_says_nothing():
    assert overflow_semantics(_document("i64", manifest=""), "x") is None


def test_an_operation_s_own_manifest_line_wins_over_the_class_line():
    manifest = ("manifest(nonvalue::machine::overflow, as::panic)\n"
                "manifest(nonvalue::machine::overflow, as::undefined, "
                "operation: operator::binary::addition)")
    d = _document("i64", manifest=manifest)
    assert overflow_semantics(d, "x", "operator::binary::addition") == "ub"
    assert overflow_semantics(d, "x", "operator::binary::multiplication") == "trap"


def test_a_bigint_parameter_cannot_overflow_whatever_the_manifest_says():
    assert overflow_semantics(_document("bigint"), "x") == "arbitrary"


@pytest.mark.parametrize("bounds, expected", [
    ((0.5, 1e30), [1, 2**63 - 1]),
    ((-1e30, 3.5), [-2**63, -1, 0, 3]),
    ((0.0, 10.0), [0, 10]),
    (Interval(0, 10, False, False), [1, 9]),
    (Interval(0.5, 0.75), []),
])
def test_an_integer_parameter_s_extremes_are_integers_inside_the_domain(bounds, expected):
    values = _extremes(None, facts_from_koine(_document("i64")), {"x": bounds})
    assert sorted(values) == expected
    assert all(type(v) is int for v in values)
