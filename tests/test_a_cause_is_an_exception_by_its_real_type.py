# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The cause of `raise E from c` is read as unable to fail only when the
real type of `c` is an exception class, or `c` is one. An object whose
`__class__` names an exception class (a mock built with a spec, a class
that sets the attribute) passes `isinstance` and is refused by Python
with a TypeError, so the claimed class is not what the call raises."""
from unittest import mock

import pytest

from mathema.conjecture import check_conjectures, claim

_CLAIM = "for x in [-5, -1], raises(f(x), ValueError)"
_MOCK = mock.Mock(spec=KeyError)


class _NamesKeyError:
    __class__ = KeyError


class _NamesItThroughAProperty:
    @property
    def __class__(self):
        return KeyError


class _Subclass(KeyError):
    pass


_FORGED = _NamesKeyError()
_FORGED_BY_PROPERTY = _NamesItThroughAProperty()
_INSTANCE = _Subclass("k")


def cause_is_a_mock(x):
    if x < 0:
        raise ValueError("n") from _MOCK
    return x


def cause_names_a_class(x):
    if x < 0:
        raise ValueError("n") from _FORGED
    return x


def cause_names_a_class_through_a_property(x):
    if x < 0:
        raise ValueError("n") from _FORGED_BY_PROPERTY
    return x


def cause_is_an_instance(x):
    if x < 0:
        raise ValueError("n") from _INSTANCE
    return x


def cause_is_a_subclass(x):
    if x < 0:
        raise ValueError("n") from _Subclass
    return x


def _row(fn):
    (row,) = check_conjectures(fn, [claim(_CLAIM, route="derive")])
    return row


def _raised(fn):
    try:
        fn(-2.0)
    except BaseException as error:
        return type(error).__name__
    return None


@pytest.mark.parametrize("fn", [cause_is_a_mock, cause_names_a_class,
                                cause_names_a_class_through_a_property],
                         ids=["mock with a spec", "class attribute", "property"])
def test_a_cause_that_only_names_an_exception_class_is_not_read(fn):
    assert _raised(fn) == "TypeError"
    row = _row(fn)
    assert row.verdict == "falsified", (row.verdict, row.sketch, row.note)


@pytest.mark.parametrize("fn", [cause_is_an_instance, cause_is_a_subclass],
                         ids=["instance", "class"])
def test_a_cause_whose_real_type_is_an_exception_is_read(fn):
    assert _raised(fn) == "ValueError"
    row = _row(fn)
    assert row.verdict == "proven", (row.verdict, row.sketch, row.note)
