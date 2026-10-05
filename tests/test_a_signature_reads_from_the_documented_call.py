# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A compiled callable with no readable signature (numpy's `dot` before
numpy 2.3) is read from the call its docstring opens with, numpy's own
convention (`dot(a, b, out=None)`), so its parameters carry the same
names on every numpy. A docstring that opens with no such call gives
no signature."""
import inspect

import pytest

from mathema._signatures import documented_signature


class _Compiled:
    def __init__(self, name, doc):
        self.__name__ = name
        self.__doc__ = doc


def test_the_documented_call_is_the_signature():
    sig = documented_signature(_Compiled(
        "dot", "\n    dot(a, b, out=None)\n\n    Dot product of two arrays."))
    assert list(sig.parameters) == ["a", "b", "out"]
    assert sig.parameters["out"].default is None
    assert sig.parameters["a"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD


def test_no_documented_call_is_no_signature():
    with pytest.raises(ValueError):
        documented_signature(_Compiled("dot", "Dot product of two arrays."))
    with pytest.raises(ValueError):
        documented_signature(_Compiled("dot", "\n    vdot(a, b)\n"))
