# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A refusing validator may raise an exception class of its own
package: one whose only base is a builtin exception, whose type is
`type`, and which adds nothing beyond the plain class attributes (its
module, a docstring). Building it is building that builtin exception.
A class with an attribute of its own, its own `__init__`, two bases, a
metaclass, a base that is not builtin, or defined in another module is
not read."""
import pytest

import _text_validators as T
from mathema._validators import read_validator

pytest.importorskip("z3")


@pytest.fixture(autouse=True)
def served():
    T.serve()
    try:
        yield
    finally:
        T.unserve()


def test_a_plain_exception_class_of_the_package_is_read():
    read = read_validator(T.check_slug_own_error)
    assert not isinstance(read, str), read
    assert read.raises is T.SlugError


def test_a_validator_raising_it_is_decided():
    row = T.row(T.check_slug_own_error,
                'for text in L[anytext], raises(f(text + "\\n"), ValueError)')
    assert row.verdict == "proven", (row.verdict, row.note, row.sketch)
    assert T.on_smt(row)
    wrong = T.row(T.check_slug_own_error, "for text in L[anytext], f(text) == text")
    assert wrong.verdict == "falsified", (wrong.verdict, wrong.note)
    assert T.on_smt(wrong)


@pytest.mark.parametrize("fn", [
    T.check_slug_error_with_code, T.check_slug_error_with_init,
    T.check_slug_error_two_bases, T.check_slug_error_with_meta,
    T.check_slug_error_of_an_error, T.check_slug_error_elsewhere,
])
def test_any_other_exception_class_is_not_read(fn):
    read = read_validator(fn)
    assert isinstance(read, str), read
