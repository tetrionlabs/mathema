# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A witness call compares values by what they hold, and names a type
only when it is one of a fixed list of built-in and standard-library
types: any other object is "an object", whatever its class is called,
so a class named at run time from an observed value carries nothing of
it into the row.

The common standard-library values are read by their contents: a deque
and an array as sequences, an OrderedDict as an ordered mapping, a
Decimal and a date by their text, a compiled pattern by its pattern and
flags. A value that contains itself is read with a marker where it
refers back, and a large container by its length and a digest of what
it holds; a value larger than the comparison's budget leaves the row
unknown, saying the budget was reached. An object whose class decides
how its attributes are read is not compared, so nothing of the called
code runs while it is read.

Over a large finite set the points come first from the numbers the
function's own tests compare the parameter with, then from the set's
members up to the budget of points; a row whose budget ran out before
the set did says so, and how many members were tried. A row whose calls
ran and changed nothing says that, not that a line was not executed."""
import array
import collections
import datetime
import decimal
import os
import random
import re
import sys

import numpy
import pytest

from mathema.conjecture import check_conjectures, claim

_KEY = "MATHEMA_TEST_INVENTED_TYPE_MARK"
os.environ.setdefault(_KEY, "".join(["B1PL", "ANTED-", "q7z9w"]))
_MARK = os.environ[_KEY]


def _normal(text: str) -> str:
    return "".join(c for c in str(text).lower() if c.isalnum())


_Named = type(_MARK, (), {})


class _ByQualname:
    pass


_ByQualname.__qualname__ = _MARK


class _ByName:
    pass


_ByName.__name__ = _MARK


class _ByModule:
    pass


_ByModule.__module__ = _MARK


class _Stateless:
    __slots__ = ()


_Stateless.__qualname__ = _MARK


class _ReadsItself:
    def __init__(self):
        self.v = 0

    def __getattribute__(self, name):
        return object.__getattribute__(self, name)


_ReadsItself.__qualname__ = _MARK

_held = None
_held_list: list = []


def rebinds_to_a_type_named_at_run_time(x):
    global _held
    _held = _Named()
    return x


def rebinds_to_a_qualname_set_at_run_time(x):
    global _held
    _held = _ByQualname()
    return x


def rebinds_to_a_name_set_at_run_time(x):
    global _held
    _held = _ByName()
    return x


def rebinds_to_a_module_set_at_run_time(x):
    global _held
    _held = _ByModule()
    return x


def rebinds_to_a_stateless_named_object(x):
    global _held
    _held = _Stateless()
    return x


def appends_a_named_object(x):
    _held_list.append(_ByQualname())
    return x


def enters_a_named_object(x):
    sys.modules["mathema_test_invented_entry"] = _ByQualname()
    return x


def returns_a_named_object_with_a_draw(x):
    made = _ByModule()
    made.v = random.random()
    return made


def rebinds_to_an_object_that_reads_itself(x):
    global _held
    _held = _ReadsItself()
    return x


def returns_an_object_that_reads_itself(x):
    random.random()
    return _ReadsItself()


_STATE = "for x in [0, 1], not is_state_safe(f)"
_RESULTS = "for x in [0, 1], not is_deterministic(f)"

#: function, claim, whether it is proven by a witness
_MARKED = [
    (rebinds_to_a_type_named_at_run_time, _STATE, True),
    (rebinds_to_a_qualname_set_at_run_time, _STATE, True),
    (rebinds_to_a_name_set_at_run_time, _STATE, True),
    (rebinds_to_a_module_set_at_run_time, _STATE, True),
    (rebinds_to_a_stateless_named_object, _STATE, True),
    (appends_a_named_object, _STATE, True),
    (enters_a_named_object, _STATE, True),
    (returns_a_named_object_with_a_draw, _RESULTS, True),
    (rebinds_to_an_object_that_reads_itself, _STATE, False),
    (returns_an_object_that_reads_itself, _RESULTS, False),
]


def _row(fn, text):
    rows = check_conjectures(fn, [claim(text)])
    return next(r for r in rows if not r.name.endswith("[float]"))


def _everything(p) -> str:
    meta = getattr(p, "meta", None) or {}
    return " ".join(str(v) for v in (
        p.sketch, p.note, getattr(p, "counterexample", None), repr(p),
        repr(getattr(p, "__dict__", {})), *meta.keys(), *meta.values()))


@pytest.mark.parametrize("fn, text, proven", _MARKED,
                         ids=[fn.__name__ for fn, _t, _p in _MARKED])
def test_a_type_named_from_an_observed_value_appears_nowhere(fn, text,
                                                             proven):
    p = _row(fn, text)
    assert _normal(_MARK) not in _normal(_everything(p)), _everything(p)
    if proven:
        assert p.verdict == "proven", (p.verdict, p.sketch, p.note)
        assert "proven by a witness" in p.sketch, p.sketch
    else:
        assert p.verdict == "unknown", (p.verdict, p.sketch, p.note)
        assert "could not be compared" in (p.note or ""), p.note


def test_an_object_of_a_type_not_listed_is_said_as_an_object():
    p = _row(rebinds_to_a_qualname_set_at_run_time, _STATE)
    assert "(None before it, an object after it)" in p.sketch, p.sketch
    p = _row(appends_a_named_object, _STATE)
    assert "a list of 1 item after it" in p.sketch, p.sketch


# standard-library values read by their contents
_deque: collections.deque = collections.deque()
_ordered: collections.OrderedDict = collections.OrderedDict(a=1, b=2)
_number = None
_day = None
_doubles = array.array("d")
_pattern = None
_large = list(range(300_000))
_huge = [None] * 1_100_000
_cycle: list = [1]
_cycle.append(_cycle)
_selfish: list = []


def appends_to_a_deque(x):
    _deque.append(x)
    return x


def extends_a_deque_by_nothing(x):
    _deque.extend([])
    return x


def sets_an_ordered_entry(x):
    _ordered["c"] = x
    return x


def moves_an_ordered_entry_to_the_end(x):
    _ordered.move_to_end("a")
    return x


def moves_both_ordered_entries_back(x):
    _ordered.move_to_end("a")
    _ordered.move_to_end("b")
    return x


def binds_a_decimal(x):
    global _number
    _number = decimal.Decimal(1)
    return x


def binds_a_date(x):
    global _day
    _day = datetime.date(2020, 1, 1)
    return x


def appends_to_an_array(x):
    _doubles.append(x)
    return x


def binds_a_pattern(x):
    global _pattern
    _pattern = re.compile("a")
    return x


def appends_to_a_large_list(x):
    _large.append(x)
    return x


def appends_to_a_list_over_the_budget(x):
    _huge.append(x)
    return x


def appends_to_a_list_that_holds_itself(x):
    _cycle.append(x)
    return x


def writes_a_list_that_holds_itself_back(x):
    _cycle[0] = _cycle[0]
    return x


def makes_a_list_hold_itself(x):
    _selfish.append(_selfish)
    return x


def returns_a_deque_of_a_draw(x):
    return collections.deque([random.random()])


def returns_a_list_of_a_draw_that_holds_itself(x):
    made: list = [random.random()]
    made.append(made)
    return made


_WON = [
    (appends_to_a_deque, _STATE),
    (sets_an_ordered_entry, _STATE),
    (binds_a_decimal, _STATE),
    (binds_a_date, _STATE),
    (appends_to_an_array, _STATE),
    (binds_a_pattern, _STATE),
    (appends_to_a_large_list, _STATE),
    (appends_to_a_list_that_holds_itself, _STATE),
    (makes_a_list_hold_itself, _STATE),
    (rebinds_to_a_stateless_named_object, _STATE),
    (returns_a_deque_of_a_draw, _RESULTS),
    (returns_a_list_of_a_draw_that_holds_itself, _RESULTS),
]


@pytest.mark.parametrize("fn, text", _WON,
                         ids=[fn.__name__ for fn, _t in _WON])
def test_a_standard_library_value_is_compared_by_its_contents(fn, text):
    p = _row(fn, text)
    assert p.verdict == "proven", (p.verdict, p.sketch, p.note)
    assert "proven by a witness" in p.sketch, p.sketch


@pytest.mark.parametrize("fn", [
    extends_a_deque_by_nothing, moves_both_ordered_entries_back,
    writes_a_list_that_holds_itself_back,
], ids=lambda fn: fn.__name__)
def test_a_standard_library_value_left_as_it_was_is_no_witness(fn):
    p = _row(fn, _STATE)
    assert p.verdict == "unknown", (p.verdict, p.sketch, p.note)


def test_a_value_over_the_budget_is_unknown_saying_the_budget_was_reached():
    p = _row(appends_to_a_list_over_the_budget, _STATE)
    assert p.verdict == "unknown", (p.verdict, p.sketch, p.note)
    assert "budget" in (p.note or "") and "was reached" in (p.note or ""), \
        p.note


# values kept as state the comparison cannot read
_steps = None
_objects = numpy.array([1, "a"], dtype=object)


def rebinds_to_a_generator(x):
    global _steps
    _steps = (k for k in range(3))
    return x


def writes_into_an_array_of_objects(x):
    _objects[0] = x + 5.0
    return x


@pytest.mark.parametrize("fn, why", [
    (rebinds_to_a_generator,
     "a generator object keeps state the comparison cannot read"),
    (writes_into_an_array_of_objects, "it is a numpy array of objects"),
], ids=lambda v: getattr(v, "__name__", None))
def test_a_value_kept_as_state_the_comparison_cannot_read_is_unknown(fn,
                                                                     why):
    p = _row(fn, _STATE)
    assert p.verdict == "unknown", (p.verdict, p.sketch, p.note)
    assert why in (p.note or ""), p.note


# objects whose class decides how they are read: never read, never run
class _DictByProperty:
    def __init__(self):
        self.w = 1

    @property
    def __dict__(self):
        return {"n": random.random()}


class _SlotBase:
    __slots__ = ("v",)


class _SlotByProperty(_SlotBase):
    __slots__ = ()

    @property
    def v(self):
        return random.random()

    @v.setter
    def v(self, value):
        _SlotBase.v.__set__(self, value)


_by_property = _DictByProperty()
_slot_by_property = _SlotByProperty()
_slot_by_property.v = 1


def writes_an_attribute_back_beside_a_dict_property(x):
    _by_property.w = _by_property.w
    return x


def writes_a_slot_beside_a_property_shadowing_it(x):
    _slot_by_property.v = 1
    return x


@pytest.mark.parametrize("fn", [
    writes_an_attribute_back_beside_a_dict_property,
    writes_a_slot_beside_a_property_shadowing_it,
], ids=lambda fn: fn.__name__)
def test_an_object_whose_class_decides_how_it_is_read_is_not_compared(fn):
    p = _row(fn, _STATE)
    assert p.verdict == "unknown", (p.verdict, p.sketch, p.note)
    assert "could not be compared" in (p.note or ""), p.note


# points over a large finite set
_late: list = []
_MEMBERS = "{" + ", ".join(str(k) for k in range(5000)) + "}"


def writes_at_the_last_member(x):
    if x == 4999:
        _late.append(x)
    return x


def writes_past_a_late_member(x):
    if x > 4990:
        _late.append(x)
    return x


def writes_at_a_middle_member(x):
    if x == 2500:
        _late.append(x)
    return x


def writes_at_no_member(x):
    if x == 5000:
        _late.append(x)
    return x


def writes_where_arithmetic_picks_a_member(x):
    if x * 2 == 9000:
        _late.append(x)
    return x


@pytest.mark.parametrize("fn", [
    writes_at_the_last_member, writes_past_a_late_member,
    writes_at_a_middle_member,
], ids=lambda fn: fn.__name__)
def test_a_write_at_a_member_the_guard_names_is_witnessed(fn):
    p = _row(fn, f"for x in {_MEMBERS}, not is_state_safe(f)")
    assert p.verdict == "proven", (p.verdict, p.sketch, p.note)
    assert "proven by a witness" in p.sketch, p.sketch
    assert _late == []


def test_a_write_at_no_member_is_not_proven():
    p = _row(writes_at_no_member, f"for x in {_MEMBERS}, not is_state_safe(f)")
    assert p.verdict != "proven", (p.verdict, p.sketch, p.note)


def test_a_budget_reached_before_the_set_is_said_with_the_count_tried():
    from mathema.conjecture import WITNESS_POINTS
    p = _row(writes_where_arithmetic_picks_a_member,
             f"for x in {_MEMBERS}, not is_state_safe(f)")
    assert p.verdict == "unknown", (p.verdict, p.sketch, p.note)
    assert "budget" in p.note and "was reached" in p.note, p.note
    assert "of the 5000 members" in p.note, p.note
    assert "second" not in p.note, p.note
    assert str(WITNESS_POINTS) in p.note, p.note


# what a row says when the calls ran and nothing changed
class _Box:
    def __init__(self):
        self.v = 1


_box = _Box()


def writes_the_box_back(x):
    _box.v = _box.v
    return x


def test_a_call_that_ran_and_changed_nothing_says_so():
    p = _row(writes_the_box_back, _STATE)
    assert p.verdict == "unknown", (p.verdict, p.sketch, p.note)
    assert "not executed" not in (p.note or ""), p.note
    assert "nothing it holds changed" in (p.note or ""), p.note


def change_the_directory(x):
    os.chdir(".")
    return x


def test_a_function_that_is_not_run_still_says_its_line_was_not_executed():
    p = _row(change_the_directory, _STATE)
    assert p.verdict == "unknown", (p.verdict, p.sketch, p.note)
    assert "not executed" in (p.note or ""), p.note
