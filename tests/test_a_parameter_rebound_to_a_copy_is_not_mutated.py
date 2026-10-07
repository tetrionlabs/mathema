# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A function that rebinds a parameter to a copy before sorting it in
place changes nothing the caller passed: numpy's `sort` function is
pure, only the array method `sort` sorts in place. A parameter rebound
to the same object (`numpy.asarray` of an array), or to a copy on one
path only, is still the caller's object when the method runs."""

import pytest

pytest.importorskip("numpy")

import numpy as np  # noqa: E402

from mathema.analysis import analyze_source  # noqa: E402


def sorted_copy(a):
    if a is None:
        a = list(range(3))
    a = np.asanyarray(a).copy()
    a.sort()
    return a


def copy_on_both_paths(a, flat: bool):
    if flat:
        a = np.asanyarray(a).flatten()
    else:
        a = np.asanyarray(a).copy()
    a.sort()
    return a


def same_object(a):
    a = np.asarray(a)
    a.sort()
    return a


def copy_on_one_path(a, flat: bool):
    if flat:
        a = np.asanyarray(a).flatten()
    a.sort()
    return a


def test_numpy_sort_is_pure():
    facts = analyze_source(np.sort)
    assert "mutates argument 'a'" not in facts.effects, facts.effects


def test_a_copy_on_every_path_before_the_sort_is_pure():
    for fn in (sorted_copy, copy_on_both_paths):
        facts = analyze_source(fn)
        assert "mutates argument 'a'" not in facts.effects, (fn.__name__,
                                                             facts.effects)


def test_the_same_object_or_a_copy_on_one_path_is_still_mutated():
    for fn in (same_object, copy_on_one_path):
        facts = analyze_source(fn)
        assert "mutates argument 'a'" in facts.effects, (fn.__name__,
                                                         facts.effects)
