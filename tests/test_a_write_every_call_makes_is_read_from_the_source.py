# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Where no call is run to witness it, `not is_state_safe(f)` is proven
by reading only when the source shows a statement that changes state on
every call that reaches it: an append to a module-level list, a
module-level integer incremented, an item of `os.environ` deleted that
is set. As the first statement of the body it runs on every call; as
the first statement under a test that compares a parameter nothing
binds again with numeric literals it runs at every point where the test
holds, and the row names one such point of the claim's domain. Nothing
is called. A write after a statement that can raise or return, or under
a test of any other form, is not read.

A file opened for writing is no proof of a write: `r+` changes nothing
until something is written, `x` fails on a file that exists, and any
mode fails on a path that cannot be written. A function that opens a
file for writing is never run, so its row is unknown and says so.
`os.environ["K"] = "V"` changes nothing when K already holds V, so it
is a write only where a call was run and the value differed: a
module-level function whose only writes outside itself are to
`os.environ` is run in a child process, which has its own copy of the
environment. The row names the variable and the length of its value,
never the value, and the checking process's environment is as it
was."""
import os

import pytest

from mathema.conjecture import check_conjectures, claim

_log: list = []
_KEY = "MATHEMA_TEST_WRITE_READ_NOT_RUN"
_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "_a_read_write_must_not_make_this.txt")


def sets_the_environment(x):
    os.environ["MATHEMA_TEST_WRITE_READ_NOT_RUN"] = "1"
    return x * 2.0


def imports_then_sets_the_environment(x):
    import os
    os.environ["MATHEMA_TEST_WRITE_READ_NOT_RUN"] = "1"
    return x * 2.0


def deletes_from_the_environment(x):
    del os.environ["MATHEMA_TEST_WRITE_READ_DELETED"]
    return x * 2.0


def opens_to_write(x):
    with open(_PATH, "w") as out:
        out.write("written")
    return x * 2.0


def opens_to_append(x):
    out = open(_PATH, mode="a")
    out.close()
    return x * 2.0


def opens_to_update(x):
    handle = open(__file__, "r+")
    handle.close()
    return x * 2.0


def opens_what_exists_exclusively(x):
    with open(__file__, "x") as out:
        out.write("never reached")
    return x * 2.0


def opens_in_a_missing_directory(x):
    with open("/mathema-test-no-such-directory/out.txt", "w") as out:
        out.write("never reached")
    return x * 2.0


def opens_to_read(x):
    with open(_PATH) as source:
        source.read()
    return x * 2.0


def sets_a_long_value(x):
    os.environ["MATHEMA_TEST_WRITE_READ_NOT_RUN"] = "kept-out-of-the-row-0123"
    return x * 2.0


def opens_past_a_half(x):
    if x > 0.5:
        open(_PATH, "a")
    return x * 2.0


def opens_in_the_else(x):
    if x < 0.5:
        pass
    else:
        open(_PATH, "a")
    return x * 2.0


def opens_in_a_band(x):
    if x > 0.25 and x < 0.75:
        if not x == 0.5:
            open(_PATH, "a")
    return x * 2.0


def opens_under_arithmetic(x):
    if x * x > 100.0:
        open(_PATH, "a")
    return x * 2.0


def opens_after_a_division(x):
    y = 1.0 / x
    open(_PATH, "a")
    return y


def opens_after_an_early_return(x):
    if x >= 0.0:
        return x
    open(_PATH, "a")
    return x


def sets_past_a_half(x):
    if x > 0.5:
        os.environ["MATHEMA_TEST_WRITE_READ_NOT_RUN"] = "1"
    return x * 2.0


def sets_in_the_else(x):
    if x < 0.5:
        pass
    else:
        os.environ["MATHEMA_TEST_WRITE_READ_NOT_RUN"] = "1"
    return x * 2.0


def sets_in_a_band(x):
    if x > 0.25 and x < 0.75:
        if not x == 0.5:
            os.environ["MATHEMA_TEST_WRITE_READ_NOT_RUN"] = "1"
    return x * 2.0


def sets_under_arithmetic(x):
    if x * x > 100.0:
        os.environ["MATHEMA_TEST_WRITE_READ_NOT_RUN"] = "1"
    return x * 2.0


def sets_after_a_division(x):
    y = 1.0 / x
    os.environ["MATHEMA_TEST_WRITE_READ_NOT_RUN"] = "1"
    return y


def sets_after_an_early_return(x):
    if x >= 0.0:
        return x
    os.environ["MATHEMA_TEST_WRITE_READ_NOT_RUN"] = "1"
    return x


def sets_after_a_rebinding(x):
    x = x - 10.0
    if x > 0.5:
        os.environ["MATHEMA_TEST_WRITE_READ_NOT_RUN"] = "1"
    return x


def _row(fn, text="for x in [0, 1], not is_state_safe(f)"):
    rows = check_conjectures(fn, [claim(text)])
    return next(r for r in rows if not r.name.endswith("[float]"))


@pytest.mark.parametrize("fn, text, point", [
    (sets_the_environment, "for x in [0, 1], not is_state_safe(f)", "x = 1"),
    (imports_then_sets_the_environment,
     "for x in [0, 1], not is_state_safe(f)", "x = 1"),
    (sets_past_a_half, "for x in [0, 1], not is_state_safe(f)", "x = 1"),
    (sets_past_a_half, "not is_state_safe(f)", "x = 0.5000000000000001"),
    (sets_in_the_else, "for x in [0, 1], not is_state_safe(f)", "x = 1"),
    (sets_in_a_band, "for x in [0, 1], not is_state_safe(f)", "x = 0."),
    (sets_after_a_division, "for x in [0, 1], not is_state_safe(f)", "x = 1"),
    (sets_after_an_early_return,
     "for x in [0, 1], not is_state_safe(f)", "x = nan"),
], ids=["first", "import", "body", "no-domain", "else", "band", "division",
        "return"])
def test_an_environment_write_is_witnessed_in_a_child_process(fn, text, point):
    p = _row(fn, text)
    assert p.verdict == "proven", (p.verdict, p.sketch, p.note)
    assert "proven by a witness: the call at " + point in p.sketch, p.sketch
    assert "child process" in p.sketch, p.sketch
    assert ("the environment variable MATHEMA_TEST_WRITE_READ_NOT_RUN was "
            "not set before it and 1 character long after it") in p.sketch, \
        p.sketch
    assert _KEY not in os.environ


def test_the_row_shows_the_length_of_the_value_and_never_the_value():
    p = _row(sets_a_long_value)
    assert p.verdict == "proven", (p.verdict, p.sketch, p.note)
    assert "24 characters long after it" in p.sketch, p.sketch
    assert "kept-out" not in p.sketch + (p.note or ""), (p.sketch, p.note)
    assert _KEY not in os.environ


_FILE_REASON = ("a file is opened for writing; whether it is changed is not "
                "decided without running, and file writers are not run")


@pytest.mark.parametrize("fn", [
    # each of these would write: true claims, not decided
    opens_to_write, opens_to_append,
    # none of these changes anything: false claims, not proven
    opens_to_update, opens_what_exists_exclusively,
    opens_in_a_missing_directory,
], ids=lambda fn: fn.__name__)
def test_a_file_opened_for_writing_is_unknown_and_says_why(fn):
    source = open(__file__).read()
    p = _row(fn)
    assert p.verdict == "unknown", (p.verdict, p.sketch, p.note)
    assert _FILE_REASON in (p.note or ""), p.note
    assert _KEY not in os.environ and not os.path.exists(_PATH)
    assert open(__file__).read() == source


def test_an_environment_item_assigned_is_a_write_only_where_the_value_differed(
        monkeypatch):
    def sets_locally(x):
        os.environ["MATHEMA_TEST_WRITE_READ_NOT_RUN"] = "1"
        return x * 2.0

    # no child can import it, and reading alone does not show a change
    p = _row(sets_locally)
    assert p.verdict == "unknown", (p.verdict, p.sketch, p.note)
    assert "cannot be run contained" in (p.note or ""), p.note
    assert _KEY not in os.environ
    # the variable already holds the value: no call changes it
    monkeypatch.setenv(_KEY, "1")
    for fn in (sets_locally, sets_the_environment):
        p = _row(fn)
        assert p.verdict == "unknown", (p.verdict, p.sketch, p.note)
    assert os.environ[_KEY] == "1"


def test_a_deletion_is_read_only_for_a_key_that_is_set(monkeypatch):
    p = _row(deletes_from_the_environment)
    assert p.verdict == "unknown", (p.verdict, p.sketch, p.note)
    monkeypatch.setenv("MATHEMA_TEST_WRITE_READ_DELETED", "1")
    p = _row(deletes_from_the_environment)
    assert p.verdict == "proven", (p.verdict, p.sketch, p.note)
    assert os.environ["MATHEMA_TEST_WRITE_READ_DELETED"] == "1"


@pytest.mark.parametrize("fn, text, point", [
    (opens_past_a_half, "for x in [0, 1], not is_state_safe(f)", "x = 1"),
    (opens_past_a_half, "not is_state_safe(f)", "x = 0.5000000000000001"),
    (opens_in_the_else, "for x in [0, 1], not is_state_safe(f)", "x = 1"),
    (opens_in_a_band, "for x in [0, 1], not is_state_safe(f)", "x = 0."),
], ids=["body", "no-domain", "else", "band"])
def test_a_file_opened_under_a_literal_test_is_unknown_and_says_why(
        fn, text, point):
    p = _row(fn, text)
    assert p.verdict == "unknown", (p.verdict, p.sketch, p.note)
    assert _FILE_REASON in (p.note or ""), p.note
    assert not os.path.exists(_PATH)


def test_a_literal_test_that_holds_nowhere_in_the_domain_falsifies():
    p = _row(sets_past_a_half, "for x in [0, 0.25], not is_state_safe(f)")
    assert p.verdict == "falsified", (p.verdict, p.sketch, p.note)
    p = _row(opens_past_a_half, "for x in [0, 0.25], not is_state_safe(f)")
    assert p.verdict == "falsified", (p.verdict, p.sketch, p.note)


def test_an_else_no_number_of_the_domain_takes_is_read_at_nan():
    # nan < 0.5 is False, and the domain admits nan
    p = _row(sets_in_the_else, "for x in [0, 0.25], not is_state_safe(f)")
    assert p.verdict == "proven", (p.verdict, p.sketch, p.note)
    assert "x = nan" in p.sketch, p.sketch
    p = _row(opens_in_the_else, "for x in [0, 0.25], not is_state_safe(f)")
    assert p.verdict == "unknown", (p.verdict, p.sketch, p.note)
    assert _FILE_REASON in (p.note or ""), p.note
    assert _KEY not in os.environ and not os.path.exists(_PATH)


@pytest.mark.parametrize("fn", [
    sets_under_arithmetic, sets_after_a_rebinding, opens_to_read,
    opens_under_arithmetic, opens_after_a_division,
    opens_after_an_early_return,
], ids=lambda fn: fn.__name__)
def test_a_write_neither_witnessed_nor_read_as_run_is_not_proven(fn):
    p = _row(fn)
    assert p.verdict != "proven", (p.verdict, p.sketch, p.note)
    assert _KEY not in os.environ and not os.path.exists(_PATH)


def test_a_function_defined_inside_another_is_read_the_same_way():
    def appends_past_a_half(x):
        if x > 0.5:
            _log.append(x)
        return x * 2.0

    def appends_under_arithmetic(x):
        if x * x > 100.0:
            _log.append(x)
        return x * 2.0

    def appends_past_ten(x):
        if x > 10.0:
            _log.append(x)
        return x * 2.0

    p = _row(appends_past_a_half)
    assert p.verdict == "proven", (p.verdict, p.sketch, p.note)
    assert "not run" in p.sketch and "x = 1" in p.sketch, p.sketch
    p = _row(appends_under_arithmetic)
    assert p.verdict == "unknown", (p.verdict, p.sketch, p.note)
    assert "cannot be run contained" in (p.note or ""), p.note
    p = _row(appends_past_ten)
    assert p.verdict == "falsified", (p.verdict, p.sketch, p.note)
    assert _log == []
