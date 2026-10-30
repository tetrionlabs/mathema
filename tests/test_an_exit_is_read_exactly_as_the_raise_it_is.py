# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The exact reading of a body (`mathema._exact_body`) reads a statement
`sys.exit(c)` as the `raise SystemExit(c)` it is, as every other reader
of the body does: an exit the body catches reads the exit code exactly,
an exit both runs reach is a raise recorded like any other (a
`SystemExit` that is also an `Exception`), and an exit only one of the
two runs reaches makes the point undecided rather than ending the
reading."""
import sys
from fractions import Fraction

import pytest

from mathema._exact_body import NotExact, exact_callee, exact_twin, unfaithful


def caught(x: float) -> float:
    try:
        sys.exit(x * 0.1)
    except SystemExit as e:
        return e.code * 3


def caught_explicitly(x: float) -> float:
    try:
        raise SystemExit(x * 0.1)
    except SystemExit as e:
        return e.code * 3


def leave(x: int) -> int:
    if x * 0.1 > 0.3:
        sys.exit(1)
    return x


def leave_explicitly(x: int) -> int:
    if x * 0.1 > 0.3:
        raise SystemExit(1)
    return x


@pytest.mark.parametrize("fn", [caught, caught_explicitly])
def test_an_exit_the_body_catches_reads_its_code_exactly(fn):
    assert unfaithful(fn) == []
    assert exact_twin(fn) is not None
    # 9/2 * 1/10 * 3, with the literal 0.1 read as written
    assert exact_callee(fn)(Fraction(9, 2)) == Fraction(27, 20)


@pytest.mark.parametrize("fn", [leave, leave_explicitly])
def test_an_exit_only_the_float_run_reaches_is_an_undecided_point(fn):
    # 3 * 0.1 is 0.30000000000000004 in float64, above 0.3, while
    # exactly 3 * 1/10 is 3/10, not above it
    with pytest.raises(NotExact):
        exact_callee(fn)(3)


@pytest.mark.parametrize("fn", [leave, leave_explicitly])
def test_an_exit_both_runs_reach_is_a_raise_like_any_other(fn):
    with pytest.raises(Exception) as raised:
        exact_callee(fn)(5)
    assert isinstance(raised.value, SystemExit)
    assert raised.value.code == 1
