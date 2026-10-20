# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A sequence parameter whose annotation states the type of its
elements is drawn inside that type, as a scalar annotation is. A real
binding that states no type on `list[int]`, `tuple[int, ...]` or
`NDArray[np.int64]` completes to the integers and is rendered `: int`;
with no binding the elements range over the integers, the two bools or
the type of strings, stated in the note; a binding that writes the reals
widens the element type, and the note says so."""
import pytest

import mathema
from mathema.runtime_types import annotated_element, as_element_type

pytestmark = pytest.mark.filterwarnings(
    "ignore::mathema.analysis.StateDependenceWarning")


def steps(xs: list[int]) -> int:
    return sum(len(range(x)) for x in xs)


def steps_of_a_tuple(xs: tuple[int, ...]) -> int:
    return sum(len(range(x)) for x in xs)


def joined(xs: list[str]) -> int:
    return len("".join(xs))


def flags(xs: list[bool]) -> int:
    if not all(isinstance(b, bool) for b in xs):
        raise TypeError("a flag is a bool")
    return len(xs)


def _row(fn, law):
    rec = mathema.check(fn, claims=[mathema.claim(law, name="c")])
    return next(p for p in rec.probes if p.name == "c")


@pytest.mark.parametrize("fn", [steps, steps_of_a_tuple],
                         ids=lambda fn: fn.__name__)
def test_an_untyped_interval_on_int_elements_is_rendered_int(fn):
    p = _row(fn, "for xs in [0, 3]^n, f(xs) >= 0")
    assert p.statement == "for xs in [0, 3]^n : int, f(xs) >= 0", p.statement
    assert p.verdict == "holds", (p.verdict, p.counterexample)


@pytest.mark.parametrize("fn, words", [
    (steps, "inferred xs in Z^n from its own list[int] annotation"),
    (steps_of_a_tuple, "inferred xs in Z^n from its own tuple[int] annotation"),
    (joined, "inferred xs in S^n from its own list[str] annotation"),
    (flags, "inferred xs in {False, True}^n from its own list[bool] annotation"),
], ids=lambda v: getattr(v, "__name__", ""))
def test_an_unbound_sequence_is_drawn_in_its_element_type(fn, words):
    p = _row(fn, "f(xs) >= 0")
    assert p.verdict == "holds", (p.verdict, p.counterexample)
    assert words in p.note, p.note


def test_a_binding_over_the_reals_widens_the_element_type():
    p = _row(steps, "for xs in R^n, f(xs) >= 0")
    assert "the claim widens the type of xs's elements from int to the reals" \
        in p.note, p.note
    assert p.verdict == "falsified", (p.verdict, p.note)


def test_a_suggested_claim_is_not_falsified_by_a_float_element():
    rows = mathema.check(steps).probes
    by_name = {p.name: p for p in rows}
    for name in ("bounded_lower", "permutation_invariant"):
        assert by_name[name].verdict in ("holds", "proven"), \
            (name, by_name[name].verdict, by_name[name].counterexample)


def test_an_int_array_annotation_is_drawn_as_integers():
    np = pytest.importorskip("numpy")
    npt = pytest.importorskip("numpy.typing")

    def steps_of_an_array(xs: npt.NDArray[np.int64]) -> int:
        return sum(len(range(x)) for x in xs)

    p = _row(steps_of_an_array, "for xs in [0, 3]^n, f(xs) >= 0")
    assert p.statement == "for xs in [0, 3]^n : int, f(xs) >= 0", p.statement
    assert p.verdict == "holds", (p.verdict, p.counterexample)
    p = _row(steps_of_an_array, "f(xs) >= 0")
    assert p.verdict == "holds", (p.verdict, p.counterexample)


@pytest.mark.parametrize("fn, element", [
    (steps, "int"), (steps_of_a_tuple, "int"), (joined, "str"), (flags, "bool"),
], ids=lambda v: getattr(v, "__name__", str(v)))
def test_the_annotation_states_the_element_type(fn, element):
    assert annotated_element(fn, "xs") == element


def test_a_whole_float_is_held_as_the_member_of_the_element_type():
    assert as_element_type([0.0, 2.0, 3], "int") == [0, 2, 3]
    assert all(type(v) is int for v in as_element_type((0.0, 2.0), "int"))
    assert as_element_type([0.5], "int") == [0.5]
    assert as_element_type([0.0, 1.0], "bool") == [False, True]
    assert as_element_type([0.0], None) == [0.0]
