# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A read that can raise keeps `is_defined(f)` from being proven by
examining the body.

A subscript raises KeyError where a mapping lacks the key and
IndexError where a sequence or a string is too short; an attribute read
raises AttributeError where the object lacks the attribute. None of
these is a raise statement or a partial math call, so a body made of
them has no raise region the walk can state, and the bare `is_defined(f)`
is decided by executing the function instead. The execution draws the
input the read fails on (the empty mapping, a mapping without the key,
the empty sequence or string), so the claim is falsified with a witness
that raises.

The same holds for any operation that can fail inside a loop body
where it is not an assignment (a branch condition, a returned value):
the walk does not condition it on the trip, so it is decided by
execution.

A read the parameter's declared type guarantees (a declared dataclass
or NamedTuple field, a required TypedDict key, an index inside a
fixed-length tuple annotation, an attribute every instance gets in
`__init__`) cannot raise, and such a body is still proven.
"""
from dataclasses import dataclass
from typing import NamedTuple, TypedDict

import mathema


def count_flags(flags: dict) -> int:
    return len(flags) + flags["a"]


def first_plus_one(xs: list) -> float:
    return xs[0] + 1


def first_of_tuple(xs: tuple) -> float:
    return xs[0] + 1


def initial(s: str) -> str:
    return s[0]


def rate_doubled(p) -> float:
    return p.rate * 2


def rate_from_module_dict(x: float) -> float:
    return x + RATES["missing"]


RATES = {"present": 1.0}


@dataclass
class Settings:
    rate: float


def field_doubled(c: Settings) -> float:
    return c.rate * 2


class Point(NamedTuple):
    x: float
    y: float


def point_sum(p: Point) -> float:
    return p.x + p.y


class Limits(TypedDict):
    low: float
    high: float


def limits_width(lim: Limits) -> float:
    return lim["high"] - lim["low"]


def pair_first(pair: tuple[float, float]) -> float:
    return pair[0] + pair[1]


def divides_in_a_loop_test(x: float, n: int) -> float:
    for _ in range(n):
        if 1 / (x - 1) > 0:
            return 1.0
    return 0.0


def divides_in_a_loop_return(x: float, n: int) -> float:
    for _ in range(n):
        return 1 / (x - 1)
    return 0.0


class Account:
    def __init__(self, balance: float):
        self.balance = balance

    def doubled(self) -> float:
        return self.balance * 2


def _defined_row(fn):
    record = mathema.check(fn, claims=["is_defined(f)"])
    (probe,) = [p for p in record.probes
                if p.meta.get("mathema.surface") == "declared"]
    return probe


def _assert_falsified_by_a_raising_witness(fn, expected_exception: str):
    probe = _defined_row(fn)
    assert probe.verdict == "falsified", (probe.verdict, probe.route,
                                          probe.sketch, probe.note)
    assert probe.route != "examine"
    assert probe.counterexample, probe
    assert expected_exception in (probe.counterexample + (probe.note or "")), \
        probe.counterexample


def test_a_missing_dict_key_falsifies_is_defined():
    _assert_falsified_by_a_raising_witness(count_flags, "KeyError")


def test_an_index_past_an_empty_list_falsifies_is_defined():
    _assert_falsified_by_a_raising_witness(first_plus_one, "IndexError")


def test_an_index_past_an_empty_tuple_falsifies_is_defined():
    _assert_falsified_by_a_raising_witness(first_of_tuple, "IndexError")


def test_an_index_past_an_empty_string_falsifies_is_defined():
    _assert_falsified_by_a_raising_witness(initial, "IndexError")


def test_a_missing_attribute_is_not_proven_by_examination():
    probe = _defined_row(rate_doubled)
    assert probe.verdict != "proven", (probe.route, probe.sketch)


def test_a_key_absent_from_a_module_mapping_is_not_proven():
    probe = _defined_row(rate_from_module_dict)
    assert probe.verdict == "falsified", (probe.verdict, probe.sketch)


def test_the_examination_names_the_read_that_can_raise():
    probe = _defined_row(count_flags)
    text = " ".join(filter(None, [probe.sketch, probe.note,
                                  str(probe.meta)]))
    assert "flags['a']" in text, text


def test_a_declared_dataclass_field_is_still_proven():
    assert _defined_row(field_doubled).verdict == "proven"


def test_a_named_tuple_field_is_still_proven():
    assert _defined_row(point_sum).verdict == "proven"


def test_a_required_typed_dict_key_is_still_proven():
    assert _defined_row(limits_width).verdict == "proven"


def test_an_index_inside_a_fixed_length_tuple_is_still_proven():
    assert _defined_row(pair_first).verdict == "proven"


def test_an_attribute_every_instance_sets_in_init_is_still_proven():
    assert _defined_row(Account.doubled).verdict == "proven"


def test_a_division_in_a_loop_condition_is_not_proven_by_examination():
    probe = _defined_row(divides_in_a_loop_test)
    assert probe.verdict == "falsified", (probe.verdict, probe.sketch)


def test_a_division_returned_from_a_loop_is_not_proven_by_examination():
    probe = _defined_row(divides_in_a_loop_return)
    assert probe.verdict == "falsified", (probe.verdict, probe.sketch)
