# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`@enforce_range()` checks a function's result against its declared
range, from the return annotation (`Probability`), from a range the
function's own claims state, or from an exit assert on the returned
value, and raises `RangeError` (a ValueError, beside DomainError and
DimensionError) when the result leaves it. A caught range violation is
no value: it counts against `is_defined`."""
import textwrap
from typing import Annotated

import pytest

import mathema
from mathema import RangeError, claims_decorator, enforce_range
from mathema.conjecture import check_conjectures, claim
from mathema.types import Probability


def test_a_range_error_is_a_value_error():
    assert issubclass(RangeError, ValueError)
    assert mathema.RangeError is RangeError


def test_the_return_annotation_states_the_range():
    @enforce_range()
    def odds(x: float) -> Annotated[float, Probability]:
        return x / 2

    assert odds(1.0) == 0.5
    with pytest.raises(RangeError, match=r"odds\(\): the result 1.5"):
        odds(3.0)


def test_a_claimed_range_is_enforced():
    @enforce_range()
    @claims_decorator("for x in [0, 1], f(x) >= 0")
    def centred(x: float) -> float:
        return x - 0.5

    assert centred(0.75) == 0.25
    with pytest.raises(RangeError):
        centred(0.25)


def _module(tmp_path, name, body):
    import importlib.util
    path = tmp_path / f"{name}.py"
    path.write_text(textwrap.dedent(body))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_an_exit_assert_feeds_the_range(tmp_path):
    mod = _module(tmp_path, "range_exit", '''
        from mathema import enforce_range

        @enforce_range()
        def doubled(x: float) -> float:
            y = 2 * x
            assert 0 <= y <= 1
            return y
    ''')
    assert mod.doubled(0.25) == 0.5
    with pytest.raises(RangeError, match="range violation caught"):
        mod.doubled(0.75)


def test_a_range_violation_counts_against_is_defined():
    @enforce_range()
    def odds(x: float) -> Annotated[float, Probability]:
        return x / 2

    (p,) = check_conjectures(odds, [claim("for x in [0, 4], is_defined(f)")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "range violation caught" in p.counterexample
