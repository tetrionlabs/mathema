# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Functions that write module-level values of this module: always,
never, under tests a domain may or may not reach, through rebound
names, and functions whose results repeat or do not.

`_MARK` is built from pieces, so no line of this file holds it; the
functions that copy it somewhere let a row be searched for it."""
import collections
import decimal
import random

_log: list = []
_count = 0
_box = {"v": 1.0}
_rng = random.Random(7)
_MARK = "-".join(("ZQX", "MK", "7f3a"))
_held = None
_items: list = []
_table: dict = {}
_queue: collections.deque = collections.deque()
_ordered: collections.OrderedDict = collections.OrderedDict()
_amount = None
_cycle: list = [1]
_cycle.append(_cycle)
_nested = [[0.0]]


class _Holder:
    def __init__(self):
        self.v = None


_holder = _Holder()
_Named = type(_MARK.replace("-", ""), (), {})


def appends(x):
    _log.append(x)
    return x * 2.0


def counts(x):
    global _count
    _count += 1
    return x


def pure(x):
    return x * 2.0


def appends_above_ten(x):
    if x > 10.0:
        _log.append(x)
    return x * 2.0


def appends_never(x):
    if False:
        _log.append(x)
    return x * 2.0


def appends_above_half(x):
    if x > 0.5:
        _log.append(x)
    return x * 2.0


def appends_after_rebinding(x):
    x = x + 100.0
    if x > 10.0:
        _log.append(x)
    return x * 2.0


def appends_in_loop_target(x):
    for x in (100.0,):
        if x > 10.0:
            _log.append(x)
    return 2.0


def appends_in_inner_function(x):
    def g(x):
        if x > 10.0:
            _log.append(x)
    g(x + 100.0)
    return x * 2.0


def appends_under_xor(x):
    if x ^ 12 > 10:
        _log.append(x)
    return x * 2


def appends_under_float_rounding(x):
    if (x + 1e16) - 1e16 > 1.5:
        _log.append(x)
    return x * 2.0


def appends_then_raises(x):
    _log.append(x)
    raise ValueError("n")


def appends_at_last_member(x):
    if x == 99:
        _log.append(x)
    return x


def writes_value_back(x):
    _box["v"] = _box["v"]
    return x


def draws(x):
    return x + _rng.random()


def copies_mark_to_name(x):
    global _held
    _held = _MARK
    return x


def copies_mark_to_list(x):
    _items.append(_MARK)
    return x


def copies_mark_to_dict(x):
    _table["k"] = _MARK
    return x


def copies_mark_to_attribute(x):
    _holder.v = _MARK
    return x


def makes_mark_named_object(x):
    global _held
    _held = _Named()
    return x


def returns_mark_with_draw(x):
    return [_MARK, _rng.random()]


def returns_mark_named_object(x):
    obj = _Named()
    obj.v = _rng.random()
    return obj


def appends_to_deque(x):
    _queue.append(x)
    return x


def sets_ordered_item(x):
    _ordered["k"] = x
    return x


def binds_decimal(x):
    global _amount
    _amount = decimal.Decimal(1)
    return x


def appends_to_cycle(x):
    _cycle.append(x)
    return x


def writes_nested(x):
    _nested[0][0] = x + 5.0
    return x
