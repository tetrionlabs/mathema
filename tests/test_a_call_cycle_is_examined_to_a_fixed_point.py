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


def test_an_examination_stopped_in_a_later_round_leaves_nothing_behind():
    # the stop lands in the second round, when the first round's reading
    # of each member is held for the next
    _clear()
    run = _examine._Examiner.run
    seen = []

    def stop_second_time(self):
        if self.fn is calls_back:
            seen.append(True)
            if len(seen) == 2:
                raise TimeoutError("the cap fired")
        return run(self)

    _examine._Examiner.run = stop_second_time
    try:
        with pytest.raises(TimeoutError):
            examine(writes_then_calls)
    finally:
        _examine._Examiner.run = run
    assert len(seen) == 2
    assert _examine._CACHE == {}
    under_way = _examine._UNDER_WAY
    assert (under_way.depth, under_way.low, under_way.reading,
            under_way.finished) == ({}, [], {}, {})
    fresh = _write_texts(calls_back)
    assert any("TABLE" in t for t in fresh)
    _clear()
    assert _write_texts(writes_then_calls) == _write_texts(writes_then_calls)
    assert _write_texts(calls_back) == fresh


def test_an_examination_stopped_inside_an_inner_cycle_leaves_nothing_behind():
    _clear()
    run = _examine._Examiner.run
    seen = []

    def stop_in_the_inner_cycle(self):
        if self.fn is inner_writer:
            seen.append(True)
            if len(seen) == 2:
                raise TimeoutError("the cap fired")
        return run(self)

    _examine._Examiner.run = stop_in_the_inner_cycle
    try:
        with pytest.raises(TimeoutError):
            examine(outer_of_two_cycles)
    finally:
        _examine._Examiner.run = run
    assert _examine._CACHE == {}
    under_way = _examine._UNDER_WAY
    assert (under_way.depth, under_way.low, under_way.reading,
            under_way.finished) == ({}, [], {}, {})
    found = examine(outer_of_two_cycles)
    assert any("LOG" in s.text for s in found.writes)
    assert any("LOG" in t for t in _write_texts(inner_writer))
    assert not examine(inner_reader).writes


def two_sites_a(xs, n):
    xs.append(n)
    return two_sites_b(xs, n - 1) if n > 0 else 0


def two_sites_b(xs, n):
    return two_sites_c(xs, n)


def two_sites_c(xs, n):
    if n > 0:
        return two_sites_a(xs, n)
    xs.pop()
    return 0


def holds_its_own(n):
    return two_sites_a([0], n)


def draws_a(rng, n):
    rng.random()
    return draws_b(rng, n - 1) if n else 0


def draws_b(rng, n):
    return draws_c(rng, n)


def draws_c(rng, n):
    return draws_a(rng, n) if n else rng.randint(0, 1)


def four_a(xs, n):
    return four_b(xs, n)


def four_b(xs, n):
    xs.append(n)
    return four_c(xs, n)


def four_c(xs, n):
    return four_d(xs, n - 1) if n > 0 else 0


def four_d(xs, n):
    if n > 1:
        xs.pop()
    TABLE["d"] = n
    return four_a(xs, n)


def holds_four(n):
    return four_a([], n)


def swaps_a(xs, ys, n):
    xs.append(n)
    return swaps_b(ys, xs, n - 1) if n > 0 else 0


def swaps_b(xs, ys, n):
    return swaps_c(xs, ys, n)


def swaps_c(xs, ys, n):
    return swaps_a(xs, ys, n) if n > 0 else 0


def into(xs):
    xs.append(1)
    return 0


def hands_log(xs):
    return into(LOG)


def fresh_to_hands_log():
    return hands_log([])


def log_a(xs, n):
    return log_b(LOG, n) if n else 0


def log_b(xs, n):
    xs.append(n)
    return log_a(xs, n - 1)


def fresh_to_log_a(n):
    return log_a([], n)


def guarded_a(xs, n, flag=None):
    if flag is not None:
        guarded_b(xs, n)
    return guarded_b(xs, n)


def guarded_b(xs, n):
    return guarded_c(xs, n)


def guarded_c(xs, n):
    xs.append(n)
    return guarded_a(xs, n - 1) if n > 0 else 0


def lap_a(xs, n):
    return lap_b(xs, n)


def lap_b(xs, n):
    return lap_a(xs, n - 1) + lap_c(xs, n) if n > 0 else 0


def lap_c(xs, n):
    xs.append(n)
    return 0


def branch_a(xs, n, flag=None):
    if flag is not None:
        branch_b([], xs, n)
    return branch_b(xs, [], n)


def branch_b(p, q, n):
    q.append(n)
    return branch_c(p, n - 1) if n > 0 else 0


def branch_c(p, n):
    return branch_b([], p, n) + branch_a(p, n - 1) if n > 1 else 0


def diamond_top(xs):
    return diamond_mid(xs)


def diamond_mid(xs):
    return diamond_left(xs) + diamond_right(xs)


def diamond_left(xs):
    return diamond_sink(xs)


def diamond_right(xs):
    return diamond_sink(xs)


def diamond_sink(xs):
    xs.append(1)
    return 0


_SETTLING = {
    "two_sites": [two_sites_a, two_sites_b, two_sites_c],
    "draws": [draws_a, draws_b, draws_c],
    "four": [four_a, four_b, four_c, four_d],
    "swaps": [swaps_a, swaps_b, swaps_c],
    "guarded": [guarded_a, guarded_b, guarded_c],
    "laps": [lap_a, lap_b, lap_c],
    "branch": [branch_a, branch_b, branch_c],
}


def _orders(members):
    yield from ([m, *[o for o in members if o is not m]] for m in members)
    for seed in range(4):
        order = list(members)
        random.Random(seed).shuffle(order)
        yield order


def _sites(found):
    return [*found.writes, *found.hidden_reads, *found.order_sensitive,
            *found.unknowns, *found.unknown_writes]


@pytest.mark.parametrize("cycle", _SETTLING, ids=str)
def test_a_cycle_passing_an_argument_settles_whichever_member_is_first(cycle):
    members = _SETTLING[cycle]
    seen = None
    for order in _orders(members):
        _clear()
        for member in order:
            examine(member)
        found = {m.__name__: examine(m) for m in members}
        for name, effects in found.items():
            assert not any("did not settle" in s.text
                           for s in _sites(effects)), name
        reading = {name: sorted(s.text for s in _sites(effects))
                   for name, effects in found.items()}
        if seen is not None:
            assert reading == seen, [m.__name__ for m in order]
        seen = reading


@pytest.mark.parametrize("cycle", _SETTLING, ids=str)
def test_a_chain_round_a_cycle_never_repeats_a_lap(cycle):
    members = _SETTLING[cycle]
    _clear()
    for member in members:
        for site in _sites(examine(member)):
            clauses = site.text.split(", and ")
            assert len(clauses) == len(set(clauses)), site.text
            assert len(clauses) <= 2 * len(members) + 1, site.text


@pytest.mark.parametrize("cycle", ["two_sites", "four", "swaps"], ids=str)
def test_the_examination_of_a_cycle_passing_an_argument_settles_in_few_rounds(
        cycle):
    members = _SETTLING[cycle]
    runs = []
    run = _examine._Examiner.run

    def counted(self):
        runs.append(self.fn)
        return run(self)

    _examine._Examiner.run = counted
    try:
        _clear()
        examine(members[0])
    finally:
        _examine._Examiner.run = run
    assert len(runs) <= 4 * len(members)


def test_a_cycle_that_passes_on_what_it_changes_is_state_unsafe():
    state = [claim("is_state_safe(f)")]
    for cycle in ("two_sites", "four", "swaps", "guarded"):
        members = _SETTLING[cycle]
        for order in _orders(members):
            _clear()
            for member in order:
                (result,) = check_conjectures(member, state)
                assert result.verdict == "falsified", (cycle, member.__name__)


def test_a_caller_that_owns_what_the_cycle_changes_is_state_safe():
    state = [claim("is_state_safe(f)")]
    for fn, members in ((holds_its_own, _SETTLING["two_sites"]),
                        (draws_a, _SETTLING["draws"]),
                        (draws_c, _SETTLING["draws"])):
        for first in (None, *members):
            _clear()
            if first is not None:
                examine(first)
            (result,) = check_conjectures(fn, state)
            assert result.verdict == "proven", (fn.__name__, first)


def test_a_caller_that_owns_one_object_of_a_cycle_still_sees_the_other():
    (site,) = (s for s in examine(holds_four).writes)
    assert "TABLE" in site.text
    for first in (four_a, four_b, four_c, four_d):
        _clear()
        examine(first)
        assert [s.text for s in examine(holds_four).writes] == [site.text]


def test_a_write_reached_through_swapped_arguments_belongs_to_both():
    for first in _SETTLING["swaps"]:
        _clear()
        examine(first)
        assert {p for p, _ in examine(swaps_a).arg_writes} == {"xs", "ys"}
        assert {p for p, _ in examine(swaps_b).arg_writes} == {"xs", "ys"}


def test_a_write_to_an_object_passed_on_is_not_the_caller_s_parameter():
    state = [claim("is_state_safe(f)")]
    for fn, middle in ((fresh_to_hands_log, hands_log),
                       (fresh_to_log_a, log_a)):
        _clear()
        assert not examine(middle).arg_writes, middle.__name__
        assert any("LOG" in t for t in _write_texts(fn)), fn.__name__
        _clear()
        (result,) = check_conjectures(fn, state)
        assert result.verdict == "falsified", fn.__name__


def test_a_cycle_member_called_outside_every_branch_writes_at_its_defaults():
    for first in _SETTLING["guarded"]:
        _clear()
        examine(first)
        found = examine(guarded_a)
        assert _examine.writes_at_defaults(guarded_a, found), first.__name__


def test_every_member_states_each_write_the_cycle_makes():
    for first in _SETTLING["two_sites"]:
        _clear()
        examine(first)
        for member in _SETTLING["two_sites"]:
            ends = {t.rsplit(", and ", 1)[-1] for t in _write_texts(member)}
            assert {"two_sites_a changes its argument xs (xs.append(n))",
                    "two_sites_c changes its argument xs (xs.pop())"} <= ends, (
                first.__name__, member.__name__)


def test_the_shorter_chain_under_a_branch_leaves_the_write_at_its_defaults():
    state = [claim("is_state_safe(f)")]
    for first in _SETTLING["branch"]:
        _clear()
        examine(first)
        found = examine(branch_a)
        assert _examine.writes_at_defaults(branch_a, found), first.__name__
        _clear()
        examine(first)
        (result,) = check_conjectures(branch_a, state)
        assert result.verdict == "falsified", first.__name__


def test_outside_a_cycle_every_path_to_a_write_is_stated():
    _clear()
    assert sorted(_write_texts(diamond_top)) == [
        "diamond_top passes its argument xs to diamond_mid, and diamond_mid "
        "passes its argument xs to diamond_left, and diamond_left passes its "
        "argument xs to diamond_sink, and diamond_sink changes its argument "
        "xs (xs.append(1))",
        "diamond_top passes its argument xs to diamond_mid, and diamond_mid "
        "passes its argument xs to diamond_right, and diamond_right passes "
        "its argument xs to diamond_sink, and diamond_sink changes its "
        "argument xs (xs.append(1))"]
