# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The call that witnesses `not is_state_safe(f)` or
`not is_deterministic(f)` is made in a child process: a fresh
interpreter imports f's module, calls f, and reports what it saw. The
checking process's own module values are as they were, so one row never
shows what another row's witness wrote. A child that runs past its
budget leaves the row unknown, saying so. A function no child
can import, or one that opens a file for writing, is not called at all:
a write the source shows every call making is read, and anything else
is unknown with the reason. A function that writes the environment is called in
the child, which has its own copy of it."""
import os
import re

import pytest

from mathema.conjecture import check_conjectures, claim

_log: list = []
_calls = 0


def always_writes(x):
    _log.append(x)
    return x * 2.0


def writes_past_a_half(x):
    if x > 0.5:
        _log.append(x)
    return x * 2.0


def counts(x):
    global _calls
    _calls += 1
    return x * 2.0


def draws(x):
    import random
    return x + random.random()


def writes_then_never_returns(x):
    _log.append(x)
    while True:
        pass


def sets_the_environment(x):
    os.environ["MATHEMA_TEST_CHILD_WITNESS_NOT_RUN"] = "1"
    return x * 2.0


_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "_child_witness_must_not_write_this.txt")


def writes_a_file(x):
    with open(_PATH, "w") as out:
        out.write("written")
    return x * 2.0


def _row(fn, text):
    rows = check_conjectures(fn, [claim(text)])
    return next(r for r in rows if not r.name.endswith("[float]"))


def test_a_witnessed_write_leaves_the_checking_process_as_it_was():
    p = _row(always_writes, "for x in [0, 1], not is_state_safe(f)")
    assert p.verdict == "proven", (p.verdict, p.sketch, p.note)
    assert "proven by a witness: the call at x = " in p.sketch, p.sketch
    assert "child process" in p.sketch, p.sketch
    assert _log == []
    p = _row(counts, "for x in [0, 1], not is_state_safe(f)")
    assert p.verdict == "proven", (p.verdict, p.sketch, p.note)
    assert "_calls changed (an int before it, an int after it)" in p.sketch, \
        p.sketch
    assert _calls == 0


def test_a_second_row_does_not_see_what_the_first_rows_witness_wrote():
    first = _row(always_writes, "for x in [0, 1], not is_state_safe(f)")
    second = _row(writes_past_a_half, "for x in [0, 1], not is_state_safe(f)")
    again = _row(always_writes, "for x in [0, 1], not is_state_safe(f)")
    for p in (first, second, again):
        assert p.verdict == "proven", (p.verdict, p.sketch, p.note)
        assert "_log changed (a list of 0 items before it" in p.sketch, \
            p.sketch
    assert first.sketch == again.sketch
    assert _log == []


def test_two_calls_that_differ_are_made_in_the_child():
    p = _row(draws, "for x in [0, 1], not is_deterministic(f)")
    assert p.verdict == "proven", (p.verdict, p.sketch, p.note)
    assert "two calls at x = " in p.sketch, p.sketch
    assert "child process" in p.sketch, p.sketch


def test_a_child_past_its_budget_leaves_the_row_unknown(monkeypatch):
    from mathema import _contained
    monkeypatch.setattr(_contained, "FAILSAFE_WALL_CLOCK_SECONDS", 4)
    p = _row(writes_then_never_returns, "for x in [0, 1], not is_state_safe(f)")
    assert p.verdict == "unknown", (p.verdict, p.sketch, p.note)
    assert "the run did not finish within its budget" in (p.note or ""), p.note
    assert not re.search(r"\d s\b|second", p.note or ""), p.note
    assert _log == []


def test_the_environment_is_written_only_in_the_child_and_a_file_never():
    p = _row(sets_the_environment, "for x in [0, 1], not is_state_safe(f)")
    assert p.verdict == "proven", (p.verdict, p.sketch, p.note)
    assert "child process" in p.sketch, p.sketch
    assert "MATHEMA_TEST_CHILD_WITNESS_NOT_RUN" not in os.environ
    p = _row(writes_a_file, "for x in [0, 1], not is_state_safe(f)")
    assert p.verdict == "unknown", (p.verdict, p.sketch, p.note)
    assert "file writers are not run" in (p.note or ""), p.note
    assert "child process" not in (p.note or ""), p.note
    assert not os.path.exists(_PATH)


def test_the_same_text_in_two_modules_is_examined_once_for_each(
        tmp_path, monkeypatch):
    import importlib

    from mathema._examine import examine
    source = ("_log = []\n\n\ndef appends(x):\n"
              "    _log.append(x)\n    return x * 2.0\n")
    for name in ("witness_twin_one", "witness_twin_two"):
        (tmp_path / f"{name}.py").write_text(source)
    monkeypatch.syspath_prepend(str(tmp_path))
    one = importlib.import_module("witness_twin_one")
    two = importlib.import_module("witness_twin_two")
    assert examine(one.appends).module_writes == {("witness_twin_one", "_log")}
    assert examine(two.appends).module_writes == {("witness_twin_two", "_log")}
    for module in (one, two):
        p = _row(module.appends, "for x in [0, 1], not is_state_safe(f)")
        assert p.verdict == "proven", (p.verdict, p.sketch, p.note)
        assert "child process" in p.sketch, p.sketch
        assert module._log == []


def test_a_function_no_child_can_import_is_read_never_run():
    def appends_first(x):
        _log.append(x)
        return x * 2.0

    p = _row(appends_first, "for x in [0, 1], not is_state_safe(f)")
    assert p.verdict == "proven", (p.verdict, p.sketch, p.note)
    assert "proves the negation" in p.sketch, p.sketch
    assert "not run" in p.sketch and "first statement" in p.sketch, p.sketch
    assert _log == []


@pytest.mark.parametrize("text", [
    "for x in [0, 1], not is_state_safe(f)",
    "not is_state_safe(f)",
])
def test_a_local_function_whose_write_is_under_an_unread_test_is_unknown(text):
    def appends_where_the_square_passes_a_quarter(x):
        if x * x > 0.25:
            _log.append(x)
        return x * 2.0

    p = _row(appends_where_the_square_passes_a_quarter, text)
    assert p.verdict == "unknown", (p.verdict, p.sketch, p.note)
    assert "cannot be run contained" in (p.note or ""), p.note
    assert "defined inside another function" in (p.note or ""), p.note
    assert _log == []


def test_a_local_function_is_not_called_twice_in_process_either():
    def draws_locally(x):
        import random
        return x + random.random()

    def writes_under_a_return(x):
        if x >= 0:
            return x
        _log.append(x)
        return x

    p = _row(draws_locally, "for x in [0, 1], not is_deterministic(f)")
    assert p.verdict == "unknown", (p.verdict, p.sketch, p.note)
    assert "cannot be run contained" in (p.note or ""), p.note
    p = _row(writes_under_a_return, "for x in [0, 1], not is_state_safe(f)")
    assert p.verdict == "unknown", (p.verdict, p.sketch, p.note)
    assert _log == []
