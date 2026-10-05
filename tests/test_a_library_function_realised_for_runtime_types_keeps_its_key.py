# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A library function whose parameters are realised through runtime
type adapters (the probe calls it through a realising wrapper) is still
the library key it was stated under, so its defaulted parameters stay
at their defaults: a row about `numpy.mean` never calls it with a drawn
`axis`, `dtype` or `out`."""
import inspect

import pytest

np = pytest.importorskip("numpy")


def _realising(fn):
    from mathema.runtime_types import _Realising
    return _Realising(fn, {}, inspect.signature(fn))


def test_the_realising_wrapper_of_a_library_function_is_its_key():
    from mathema.compendium import ensure_bundled, library_key_of
    ensure_bundled()
    assert library_key_of(_realising(np.mean)) == "numpy.mean"


def test_a_premise_guarded_library_function_is_its_key():
    from mathema._premises import _Guarded
    from mathema.compendium import ensure_bundled, library_key_of
    ensure_bundled()
    assert library_key_of(_Guarded(_realising(np.std), None)) == "numpy.std"


def test_a_realised_library_call_keeps_its_defaulted_parameters():
    from mathema.compendium import ensure_bundled
    from mathema.conjecture import call_defaults, claim
    ensure_bundled()
    cj = claim("dim(a) >= 1", name="is_defined")
    kept, pins, problem = call_defaults(_realising(np.mean), cj)
    assert sorted(kept) == ["axis", "dtype", "keepdims", "out", "where"]
    assert pins == {} and problem is None


def test_a_user_function_wrapping_a_library_one_is_not_its_key():
    import functools

    from mathema.compendium import ensure_bundled, library_key_of
    ensure_bundled()

    @functools.wraps(np.mean)
    def my_mean(a, *args, **kwargs):
        return np.mean(a, *args, **kwargs)

    assert library_key_of(my_mean) is None
