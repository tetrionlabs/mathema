# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""What a witness call saw is said without the value it saw. A row
names what changed and describes each value by its type and size (`a
str of 21 characters`), so a value a call copied from the environment
appears nowhere in the row. A change is reported only when it is shown:
two values are compared by what they hold, never by which object they
are, so an object written back as it was has not changed and two equal
objects returned by two calls do not differ; a value that cannot be
compared leaves the row unknown with the reason.

A call that writes and then raises has written. A claim over the
integers is witnessed at integers, and every member of a finite set is
tried. A draw from the shared random generator, text printed to
standard output and an entry of `sys.modules` assigned are changes of
process state, witnessed in the child's own copies. The row says the
witness was observed in a fresh import of the function's module, which
each child imports once."""
import os
import random
import sys
import time

import pytest

from mathema.conjecture import check_conjectures, claim

_KEY = "MATHEMA_TEST_INVENTED_SECRET"
_SECRET = "TOPSECRETVALUE-abcdef"
_IMPORTS = "MATHEMA_TEST_INVENTED_IMPORT_LIST"

if os.environ.get(_IMPORTS):
    with open(os.environ[_IMPORTS], "a") as _made:
        _made.write("imported\n")

_cache = None
_log: list = []


class Point:
    def __init__(self, v):
        self.v = v


class Slotted:
    __slots__ = ("v",)

    def __init__(self, v):
        self.v = v


_point = Point(1)
_slotted = Slotted(1)
_nans = [float("nan")]


def copies_the_environment(x):
    global _cache
    _cache = os.environ["MATHEMA_TEST_INVENTED_SECRET"]
    return x


def returns_the_environment_and_a_draw(x):
    return os.environ["MATHEMA_TEST_INVENTED_SECRET"] + str(random.random())


def names_a_variable_from_the_environment(x):
    os.environ[os.environ["MATHEMA_TEST_INVENTED_SECRET"]] = "1"
    return x


def prints_the_environment(x):
    print(os.environ["MATHEMA_TEST_INVENTED_SECRET"])
    return x


def writes_the_point_back(x):
    _point.v = _point.v
    return x


_lock_like = object()


def rebinds_what_cannot_be_compared(x):
    global _lock_like
    _lock_like = object()
    return x


def moves_the_point(x):
    _point.v = _point.v + 1
    return x


def writes_the_slot_back(x):
    _slotted.v = _slotted.v
    return x


def moves_the_slot(x):
    _slotted.v = _slotted.v + 1
    return x


def binds_a_fresh_nan_list(x):
    global _nans
    _nans = [float("nan")]
    return x


def an_equal_point_after_reading_the_clock(x):
    time.time()
    return Point(1)


def a_later_point_after_reading_the_clock(x):
    return Point(time.perf_counter_ns())


def a_bare_object_after_reading_the_clock(x):
    time.time()
    return object()


def writes_then_raises(x):
    _log.append(x)
    raise ValueError("refused after the write")


def raises_before_the_write(x):
    raise ValueError("refused before the write")
    _log.append(x)


def appends_after_an_exec(x):
    exec("pass")
    _log.append(x)
    return x


def always_writes(x):
    _log.append(x)
    return x


def writes_past_three_tenths(x):
    if x > 0.3:
        _log.append(x)
    return x


def writes_below_a_tenth(x):
    if x < 0.1:
        _log.append(x)
    return x


def writes_below_a_half_chained(x):
    if x < 0.5 < 1.0:
        _log.append(x)
    return x


def writes_past_two(x):
    if x > 2.0:
        _log.append(x)
    return x


def draws_and_drops(x):
    random.random()
    return x * 2.0


def prints_a_line(x):
    print("a line")
    return x * 2.0


def prints_nothing(x):
    print(end="")
    return x * 2.0


def sets_a_module_entry(x):
    sys.modules["mathema_test_invented_module"] = None
    return x * 2.0


def writes_a_module_entry_back(x):
    sys.modules["math"] = sys.modules["math"]
    return x * 2.0


def _row(fn, text):
    rows = check_conjectures(fn, [claim(text)])
    return next(r for r in rows if not r.name.endswith("[float]"))


def _everything(p) -> str:
    return " | ".join(str(part) for part in (
        p.sketch, p.note, p.counterexample, p.meta, repr(p), vars(p),
        p.to_dict() if hasattr(p, "to_dict") else ""))


@pytest.mark.parametrize("fn, text, said", [
    (copies_the_environment, "for x in [0, 1], not is_state_safe(f)",
     "the module-level _cache changed (None before it, a str of 21 "
     "characters after it)"),
    (returns_the_environment_and_a_draw,
     "for x in [0, 1], not is_deterministic(f)",
     "returned two results that differ (a str of "),
    (names_a_variable_from_the_environment,
     "for x in [0, 1], not is_state_safe(f)",
     "an environment variable whose name the source does not write out"),
    (prints_the_environment, "for x in [0, 1], not is_state_safe(f)",
     "22 characters were written to standard output"),
], ids=lambda v: getattr(v, "__name__", None))
def test_a_value_from_the_environment_is_nowhere_in_the_row(
        fn, text, said, monkeypatch):
    monkeypatch.setenv(_KEY, _SECRET)
    p = _row(fn, text)
    assert p.verdict == "proven", (p.verdict, p.sketch, p.note)
    assert said in p.sketch, p.sketch
    assert _SECRET not in _everything(p)
    assert "TOPSECRET" not in _everything(p)
    assert _cache is None and _SECRET not in os.environ


@pytest.mark.parametrize("fn, said", [
    (moves_the_point,
     "_point changed (an object before it, an object after it)"),
    (moves_the_slot,
     "_slotted changed (an object before it, an object after it)"),
], ids=lambda v: getattr(v, "__name__", None))
def test_an_object_whose_state_changed_is_witnessed(fn, said):
    p = _row(fn, "for x in [0, 1], not is_state_safe(f)")
    assert p.verdict == "proven", (p.verdict, p.sketch, p.note)
    assert said in p.sketch, p.sketch
    assert " at 0x" not in p.sketch, p.sketch
    assert (_point.v, _slotted.v) == (1, 1)


@pytest.mark.parametrize("fn", [
    writes_the_point_back, writes_the_slot_back, binds_a_fresh_nan_list,
], ids=lambda fn: fn.__name__)
def test_a_value_written_back_as_it_was_is_no_witness(fn):
    p = _row(fn, "for x in [0, 1], not is_state_safe(f)")
    assert p.verdict == "unknown", (p.verdict, p.sketch, p.note)
    assert "child process" not in (p.sketch or ""), p.sketch


def test_two_equal_objects_returned_do_not_differ():
    p = _row(an_equal_point_after_reading_the_clock,
             "for x in [0, 1], not is_deterministic(f)")
    assert p.verdict == "unknown", (p.verdict, p.sketch, p.note)
    p = _row(a_later_point_after_reading_the_clock,
             "for x in [0, 1], not is_deterministic(f)")
    assert p.verdict == "proven", (p.verdict, p.sketch, p.note)
    assert ("returned two results that differ (an object, then an "
            "object)") in p.sketch, p.sketch


def test_a_result_that_cannot_be_compared_is_unknown_with_the_reason():
    p = _row(a_bare_object_after_reading_the_clock,
             "for x in [0, 1], not is_deterministic(f)")
    assert p.verdict == "unknown", (p.verdict, p.sketch, p.note)
    assert ("the two results could not be compared (an object has no "
            "state the comparison can read)") in (p.note or ""), p.note


def test_a_value_that_cannot_be_compared_is_unknown_with_the_reason():
    p = _row(rebinds_what_cannot_be_compared,
             "for x in [0, 1], not is_state_safe(f)")
    assert p.verdict == "unknown", (p.verdict, p.sketch, p.note)
    assert ("the module-level _lock_like could not be compared before and "
            "after the call (an object has no state the comparison "
            "can read)") in (p.note or ""), p.note


def test_a_function_that_cannot_be_read_whole_is_never_run():
    p = _row(appends_after_an_exec, "for x in [0, 1], not is_state_safe(f)")
    assert p.verdict == "unknown", (p.verdict, p.sketch, p.note)
    assert "child process" not in (p.note or ""), p.note
    assert _log == []


def test_a_write_before_a_raise_is_a_write():
    p = _row(writes_then_raises, "for x in [0, 1], not is_state_safe(f)")
    assert p.verdict == "proven", (p.verdict, p.sketch, p.note)
    assert "_log changed (a list of 0 items before it, a list of 1 item " \
        "after it)" in p.sketch, p.sketch
    p = _row(raises_before_the_write, "for x in [0, 1], not is_state_safe(f)")
    assert p.verdict != "proven", (p.verdict, p.sketch, p.note)
    assert _log == []


@pytest.mark.parametrize("fn, text, verdict, point", [
    (always_writes, "for x in Z, not is_state_safe(f)", "proven", "x = 0"),
    (always_writes, "for x in N, not is_state_safe(f)", "proven", "x = 0"),
    (writes_past_three_tenths, "for x in Z, not is_state_safe(f)",
     "proven", "x = 1"),
    (writes_past_three_tenths, "for x in {0, 1}, not is_state_safe(f)",
     "proven", "x = 1"),
    (writes_past_two, "for x in {0, 1, 2, 3}, not is_state_safe(f)",
     "proven", "x = 3"),
    (writes_past_two, "for x in {0, 1, 2}, not is_state_safe(f)",
     "not proven", None),
], ids=["Z", "N", "Z-conditional", "set", "last-member", "no-member"])
def test_integers_and_every_member_of_a_finite_set_are_tried(
        fn, text, verdict, point):
    p = _row(fn, text)
    if point is None:
        assert p.verdict != "proven", (p.verdict, p.sketch, p.note)
    else:
        assert p.verdict == verdict, (p.verdict, p.sketch, p.note)
        assert f"the call at {point} was run" in p.sketch, p.sketch
    assert _log == []


@pytest.mark.parametrize("domain", ["(0, 1]", "(0, 1)", "[0.5, 1]"])
def test_a_number_in_a_chained_comparison_is_a_point_to_try(domain):
    p = _row(writes_below_a_half_chained,
             f"for x in {domain}, not is_state_safe(f)")
    if domain == "[0.5, 1]":
        # no number of the domain is below a half, and nan is not
        assert p.verdict != "proven", (p.verdict, p.sketch, p.note)
    else:
        assert p.verdict == "proven", (p.verdict, p.sketch, p.note)
        assert "the call at x = 0.49999999999999994 was run" in p.sketch, \
            p.sketch
    assert _log == []


@pytest.mark.parametrize("fn, said", [
    (draws_and_drops, "the state of the shared random generator (random) "
                      "changed"),
    (prints_a_line, "7 characters were written to standard output"),
    (sets_a_module_entry,
     "sys.modules['mathema_test_invented_module'] changed (not set before "
     "it, None after it)"),
], ids=lambda v: getattr(v, "__name__", None))
def test_a_change_of_process_state_is_witnessed_in_the_child(fn, said):
    drawn, loaded = random.getstate(), set(sys.modules)
    p = _row(fn, "for x in [0, 1], not is_state_safe(f)")
    assert p.verdict == "proven", (p.verdict, p.sketch, p.note)
    assert "child process" in p.sketch and said in p.sketch, p.sketch
    assert "a line" not in p.sketch
    assert random.getstate() == drawn
    assert "mathema_test_invented_module" not in sys.modules
    assert set(sys.modules) >= loaded


@pytest.mark.parametrize("fn", [prints_nothing, writes_a_module_entry_back],
                         ids=lambda fn: fn.__name__)
def test_process_state_left_as_it_was_is_no_witness(fn):
    p = _row(fn, "for x in [0, 1], not is_state_safe(f)")
    assert p.verdict == "unknown", (p.verdict, p.sketch, p.note)


def test_the_module_is_imported_once_in_a_child_and_the_row_says_afresh(
        tmp_path, monkeypatch):
    made = tmp_path / "imports.txt"
    monkeypatch.setenv(_IMPORTS, str(made))
    p = _row(writes_below_a_tenth, "for x in [0, 1], not is_state_safe(f)")
    assert p.verdict == "proven", (p.verdict, p.sketch, p.note)
    # the upper end is tried first and shows nothing; the lower end is next
    assert "the call at x = 0 was run in a child process that imported " \
        "f's module afresh" in p.sketch, p.sketch
    assert made.read_text().splitlines() == ["imported"]
    assert str(tmp_path) not in _everything(p)
