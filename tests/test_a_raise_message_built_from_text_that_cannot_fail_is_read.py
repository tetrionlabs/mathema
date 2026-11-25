# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A raise whose message is formatted is read as raising its class when
formatting cannot fail on the values the names hold: an f-string field
with a float presentation spec of at most two digits of precision
(`{x:.3f}`, `{x:.2e}`, `{x:.1%}`) on an int, float or bool no larger
than the largest float; `"%s" % x` and `"{}".format(x)` with `%s`, `%r`,
`%a` or `{}` fields on values whose text cannot fail; `type(x).__name__`
of a value of a builtin type. The second operand of `or` runs only when
the first is false, so `x is None or math.isnan(x)` reads `math.isnan`
on a value that is not None. Anything else stays unread."""
import math
from typing import Optional

import pytest

from mathema.conjecture import check_conjectures, claim


def fixed_spec(x: float) -> float:
    if x < 0:
        raise ValueError(f"negative: {x:.3f}")
    return x


def exponent_spec(x: int) -> int:
    if x < 0:
        raise ValueError(f"negative: {x:.2e} or {x:.1%}")
    return x


def percent_format(x: float) -> float:
    if x < 0:
        raise ValueError("negative: %s (%r)" % (x, x))
    return x


def percent_one(x: float) -> float:
    if x < 0:
        raise ValueError("negative: %s" % x)
    return x


def brace_format(x: float) -> float:
    if x < 0:
        raise ValueError("negative: {} {!r}".format(x, x))
    return x


def type_name(x: float) -> float:
    if x < 0:
        raise ValueError(f"negative {type(x).__name__}")
    return x


def width_spec(x: float) -> float:
    if x < 0:
        raise ValueError(f"negative: {x:>{10}}")
    return x


def int_spec_on_unbounded_int(x: int) -> int:
    if x > 0:
        raise ValueError(f"{x:.2f}")
    return x


def percent_count_mismatch(x: float) -> float:
    if x < 0:
        raise ValueError("%s %s" % x)
    return x


def _derive(fn, exception="ValueError", domain="[-5, -1]"):
    (row,) = check_conjectures(
        fn, [claim(f"for x in {domain}, raises(f(x), {exception})", route="derive")])
    return row


_READ = [fixed_spec, exponent_spec, percent_format, percent_one, brace_format, type_name]


@pytest.mark.parametrize("fn", _READ, ids=lambda f: f.__name__)
def test_a_message_formatted_from_text_that_cannot_fail_is_proven(fn):
    with pytest.raises(ValueError):
        fn(-2)
    row = _derive(fn)
    assert row.verdict == "proven", (row.verdict, row.sketch)


def test_a_spec_with_a_nested_field_is_not_read():
    assert _derive(width_spec).verdict != "proven"


def test_a_float_spec_on_an_unbounded_int_is_not_proven():
    with pytest.raises(OverflowError):
        int_spec_on_unbounded_int(10 ** 400)
    assert _derive(int_spec_on_unbounded_int, domain="[1, oo)").verdict != "proven"


def test_a_percent_format_of_the_wrong_count_is_not_proven():
    with pytest.raises(TypeError):
        percent_count_mismatch(-2.0)
    assert _derive(percent_count_mismatch).verdict != "proven"


def policy_none_or_nan(x: Optional[float], y: float) -> float:
    if x is None or math.isnan(x):
        raise TypeError("x is required")
    return x * y


def test_the_second_operand_of_or_sees_the_value_the_first_left():
    rows = check_conjectures(policy_none_or_nan, [
        claim("for x in [0, 1], y in [-1, 1], f(x, y) == x * y"),
        claim("absent(f, x) raises(TypeError)")])
    assert rows[-1].verdict == "proven", (rows[-1].verdict, rows[-1].note)


def test_the_reader_reads_isnan_only_past_a_none_test():
    import ast
    from mathema._raise_reading import TOTAL, ValueKind, read_expression, _Namespace
    test = ast.parse("x is None or math.isnan(x)", mode="eval").body
    ns = _Namespace(policy_none_or_nan)
    either = ValueKind(frozenset({float, type(None)}), 5.0)
    assert read_expression(test, {"x": either}, ns)[0] == TOTAL
    wrong = ast.parse("x is not None or math.isnan(x)", mode="eval").body
    assert read_expression(wrong, {"x": either}, ns)[0] < TOTAL
