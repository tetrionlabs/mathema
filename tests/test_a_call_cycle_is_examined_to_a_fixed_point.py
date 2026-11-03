# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""What a function does includes what every function it reaches does, and in
a call cycle each member reaches all the others. The reading of a cycle is its
least fixed point: it does not depend on which member is examined first, and
nothing read while a member is still open is kept as that member's answer."""
import ast
import random

import pytest

from mathema import _examine
from mathema._examine import examine
from mathema.conjecture import check_conjectures, claim

TABLE = {}
LOG = []


def writes_then_calls(x):
    TABLE["a"] = x
    return calls_back(x)


def calls_back(x):
    return writes_then_calls(x - 1) if x > 0 else 0


def first_of_three(x):
    return second_of_three(x)


def second_of_three(x):
    return third_of_three(x) if x else first_of_three(x)


def third_of_three(x):
    LOG.append(x)
    return first_of_three(x - 1)


def entry_a(x):
    return shared_a(x) + shared_b(x)


def shared_a(x):
    return shared_b(x - 1) if x > 0 else entry_a(x)


def shared_b(x):
    TABLE["b"] = x
    return shared_a(x - 1) if x > 0 else 0


def reads_limit(x):
    return bounded_by_limit(x)


def bounded_by_limit(x):
    return reads_limit(x - 1) if x > TABLE.get("limit", 3) else x


def pure_even(n):
    return True if n == 0 else pure_odd(n - 1)


def pure_odd(n):
    return False if n == 0 else pure_even(n - 1)


def pure_self(n):
    return pure_self(n - 1) if n else 0


def outer_of_two_cycles(x):
    return inner_writer(x) + inner_reader(x)


def inner_writer(x):
    LOG.append(x)
    return inner_writer(x - 1) if x else 0


def inner_reader(x):
    return inner_reader(x - 1) if x > 3 else 0


def hands_on(xs):
    return appends(xs)


def appends(xs):
    xs.append(1)
    return hands_on(xs) if len(xs) < 3 else xs


def passes_global(flag):
    return appends_through(LOG, flag)


def appends_through(xs, flag):
    xs.append(flag)
    return passes_global(flag) if not flag else None


_CYCLES = {
    "two": ([writes_then_calls, calls_back], "changes the module-level TABLE"),
    "three": ([first_of_three, second_of_three, third_of_three],
              "changes the module-level LOG"),
    "shared": ([entry_a, shared_a, shared_b], "changes the module-level TABLE"),
}


def _clear():
    _examine._CACHE.clear()


def _write_texts(fn):
    return [s.text for s in examine(fn).writes]


@pytest.mark.parametrize("cycle", _CYCLES, ids=str)
def test_every_member_sees_the_write_whichever_is_examined_first(cycle):
    members, written = _CYCLES[cycle]
    for first in members:
        _clear()
        examine(first)
        for member in members:
            assert any(written in t for t in _write_texts(member)), member
    for shuffled in range(6):
        order = list(members)
        random.Random(shuffled).shuffle(order)
        _clear()
        for member in order:
            assert any(written in t for t in _write_texts(member)), member


def test_the_verdict_does_not_depend_on_the_order():
    state = [claim("is_state_safe(f)")]
    _clear()
    (alone,) = check_conjectures(calls_back, state)
    assert alone.verdict == "falsified"
    _clear()
    (first,) = check_conjectures(writes_then_calls, state)
    (second,) = check_conjectures(calls_back, state)
    assert first.verdict == "falsified"
    assert second.verdict == "falsified"
    assert "TABLE" in second.counterexample


def test_a_hidden_read_reaches_every_member():
    for first, second in ((reads_limit, bounded_by_limit),
                          (bounded_by_limit, reads_limit)):
        _clear()
        examine(first)
        for fn in (first, second):
            assert [s.text for s in examine(fn).unknowns] == [
                "bounded_by_limit reads the module-level TABLE, "
                "a value other code can change"]


@pytest.mark.parametrize("fn", [pure_even, pure_odd, pure_self])
def test_a_cycle_with_no_effect_stays_clean(fn):
    _clear()
    found = examine(fn)
    assert not (found.writes or found.hidden_reads or found.unknowns
                or found.unknown_writes or found.order_sensitive)


def test_a_write_to_an_argument_passes_round_the_cycle():
    for fn in (hands_on, appends):
        _clear()
        assert {p for p, _ in examine(fn).arg_writes} == {"xs"}


def test_a_write_to_an_argument_stops_at_one_lap():
    _clear()
    (site,) = examine(hands_on).writes
    assert site.text == ("hands_on passes its argument xs to appends, and "
                         "appends changes its argument xs (xs.append(1))")


def test_a_cycle_that_never_settles_says_so(monkeypatch):
    monkeypatch.setattr(_examine, "_ROUNDS_TO_SETTLE", 1)
    _clear()
    found = examine(writes_then_calls)
    assert [s.text for s in found.unknowns] == [
        "the examination of writes_then_calls in its call cycle did not settle"]


def test_a_write_passed_a_global_round_the_cycle_settles():
    for first in (passes_global, appends_through):
        _clear()
        examine(first)
        assert any("LOG" in t for t in _write_texts(passes_global))


def test_a_cycle_inside_another_call_is_settled_alone():
    _clear()
    found = examine(outer_of_two_cycles)
    assert any("LOG" in t for t in [s.text for s in found.writes])
    assert not examine(inner_reader).writes
    assert any("LOG" in t for t in _write_texts(inner_writer))


def test_an_interrupted_examination_leaves_nothing_behind():
    _clear()
    run = _examine._Examiner.run
    stops = []

    def stop_once(self):
        if self.fn is calls_back and not stops:
            stops.append(True)
            raise TimeoutError("the cap fired")
        return run(self)

    _examine._Examiner.run = stop_once
    try:
        with pytest.raises(TimeoutError):
            examine(writes_then_calls)
    finally:
        _examine._Examiner.run = run
    assert _examine._CACHE == {}
    assert any("TABLE" in t for t in _write_texts(writes_then_calls))
    assert any("TABLE" in t for t in _write_texts(calls_back))


def test_an_interrupted_examination_of_a_call_with_no_cycle_keeps_nothing():
    _clear()
    run = _examine._Examiner.run

    def stop(self):
        raise TimeoutError("the cap fired")

    _examine._Examiner.run = stop
    try:
        with pytest.raises(TimeoutError):
            examine(pure_self)
    finally:
        _examine._Examiner.run = run
    assert _examine._CACHE == {}


def test_the_examination_settles_in_few_rounds():
    runs = []
    run = _examine._Examiner.run

    def counted(self):
        runs.append(self.fn)
        return run(self)

    _examine._Examiner.run = counted
    try:
        _clear()
        examine(entry_a)
    finally:
        _examine._Examiner.run = run
    # each round examines each member once: the empty reading, the
    # written one, and the round that shows it no longer changes
    assert len(runs) <= 3 * 3


def test_a_dense_cycle_is_examined_once_per_round(monkeypatch):
    # nine functions that each call all the others have 8! paths through
    # them, and each round examines each function once
    scope = {"__name__": __name__}
    trees = {}
    for i in range(9):
        calls = " + ".join(f"d{j}(x)" for j in range(9) if j != i)
        source = f"def d{i}(x):\n    return {calls}"
        exec(compile(source, __file__, "exec"), scope)
        trees[scope[f"d{i}"]] = ast.parse(source).body[0]
    monkeypatch.setattr(_examine, "_project_source", trees.get)
    runs = []
    run = _examine._Examiner.run

    def counted(self):
        runs.append(self.fn.__name__)
        return run(self)

    monkeypatch.setattr(_examine._Examiner, "run", counted)
    _clear()
    found = examine(scope["d0"])
    assert not found.writes
    assert len(runs) <= 9 * 3
