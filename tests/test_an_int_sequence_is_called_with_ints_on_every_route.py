# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A sequence annotated with int elements (`list[int]`, `tuple[int,
...]`, `NDArray[np.int64]`) is called with ints on every route that
draws it: the value probe, the `is_defined` region probe, the
empty-input and outside-the-domain families, the premise draws, the
smoke call and the exact reading of the claim. A hole the claim admits
is the one entry that is not an int. A vector the claim evaluates as an
array goes back to the function with the ints it was drawn with, holes
included, and a hole inside mathema's own array is still seen as one."""
import pytest

import mathema

np = pytest.importorskip("numpy")
npt = pytest.importorskip("numpy.typing")

pytestmark = pytest.mark.filterwarnings(
    "ignore::mathema.analysis.StateDependenceWarning")

_RECEIVED: list = []


def _record(xs):
    values = xs.tolist() if hasattr(xs, "tolist") else list(xs)
    _RECEIVED.extend(values)


def as_list(xs: list[int]) -> float:
    _record(xs)
    return float(len(xs))


def as_tuple(xs: tuple[int, ...]) -> float:
    _record(xs)
    return float(len(xs))


def as_array(xs: npt.NDArray[np.int64]) -> float:
    _record(xs)
    return float(len(xs))


CLAIMS = ["for xs in [0, 1]^n, f(xs) >= 0", "f(xs) >= 0", "is_defined(f)",
          "is_finite(f(xs))", "is_empty_safe(xs)", "is_missing_safe(f)",
          "is_overflow_safe(f)", "excluded_outside_domain(xs)",
          "for xs in [0, 3]^n, assuming max(xs) == min(xs), f(xs) >= 0",
          "for xs in [0, 5]^n, assuming dim(xs) >= 3, f(xs) >= 3",
          "f(xs) == f(xs)"]


def _not_ints(values) -> list:
    import math
    return [v for v in values
            if not (isinstance(v, int) and not isinstance(v, bool))
            and not (isinstance(v, float) and math.isnan(v)) and v is not None]


@pytest.mark.parametrize("fn", [as_list, as_tuple, as_array],
                         ids=lambda fn: fn.__name__)
@pytest.mark.parametrize("law", CLAIMS)
def test_every_route_calls_an_int_sequence_with_ints(fn, law):
    _RECEIVED.clear()
    mathema.check(fn, claims=[mathema.claim(law, name="c")])
    assert _RECEIVED, law
    assert not _not_ints(_RECEIVED), (law, _not_ints(_RECEIVED)[:5])


def test_an_array_keeps_its_ints_beside_a_hole():
    from mathema._linalg_eval import as_array as read, to_plain
    back = to_plain(read([None, 9, 3]))
    assert back == [None, 9, 3]
    assert [type(v) for v in back[1:]] == [int, int]


def test_a_hole_inside_mathemas_own_array_is_seen():
    from mathema._linalg_eval import as_array as read
    from mathema.probing import inputs_missing
    assert inputs_missing([read([None, 9, 3])])
    assert inputs_missing([read([None, 9.0, 3.0])])
    assert not inputs_missing([read([1, 2])])
