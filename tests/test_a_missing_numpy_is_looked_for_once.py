# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""On an install without numpy, the exact reading of a claim's sides
looks for numpy once per process. A failed import is not cached by the
interpreter, so a lookup on every value read would cost a module search
per point of a sweep, and a finite domain small enough to sweep whole
would be demoted to a sample."""
import builtins

import pytest

from mathema import _exact_side


@pytest.fixture
def numpy_absent(monkeypatch):
    attempts = []
    real_import = builtins.__import__

    def refusing(name, *args, **kwargs):
        if name == "numpy" or name.startswith("numpy."):
            attempts.append(name)
            raise ImportError("no numpy on this install")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", refusing)
    monkeypatch.setattr(_exact_side, "_NUMPY", _exact_side._UNLOOKED)
    return attempts


def test_the_import_is_attempted_once_across_many_values(numpy_absent):
    for value in (1.5, 2.0, [0.5, 0.25], 3, True) * 20:
        _exact_side.to_exact(value)
        _exact_side.to_float(_exact_side.to_exact(value))
    assert _exact_side._np() is None
    assert len(numpy_absent) == 1, numpy_absent


def test_the_values_still_read_exactly_without_numpy(numpy_absent):
    from fractions import Fraction
    assert _exact_side.to_exact(0.1) == Fraction(0.1)
    assert _exact_side.to_exact([0.5, 0.75]) == [Fraction(1, 2), Fraction(3, 4)]
    assert _exact_side.to_float(Fraction(1, 2)) == 0.5
