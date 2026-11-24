# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Where no call is run to witness it, `not is_state_safe(f)` is proven
by reading when the source shows a call that writes. A recognised write
(an item of `os.environ` assigned or deleted, a file opened for writing
or appending, an append to a module-level list, a module-level integer
incremented) that is the first statement of the body runs on every
call. The same write as the first statement under a test that compares
a parameter nothing binds again with numeric literals runs at every
point where the test holds, and the row names one such point of the
claim's domain. Nothing is called. A write after a statement that can
raise or return, or under a test of any other form, is not read."""
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


def opens_to_read(x):
    with open(_PATH) as source:
        source.read()
    return x * 2.0


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


@pytest.mark.parametrize("fn", [
    sets_the_environment, imports_then_sets_the_environment,
    opens_to_write, opens_to_append,
], ids=lambda fn: fn.__name__)
def test_a_write_that_is_the_first_statement_proves_the_negation(fn):
    p = _row(fn)
    assert p.verdict == "proven", (p.verdict, p.sketch, p.note)
    assert "proves the negation" in p.sketch, p.sketch
    assert "not run" in p.sketch and "every call" in p.sketch, p.sketch
    assert _KEY not in os.environ and not os.path.exists(_PATH)


def test_a_deletion_is_read_only_for_a_key_that_is_set(monkeypatch):
    p = _row(deletes_from_the_environment)
    assert p.verdict == "unknown", (p.verdict, p.sketch, p.note)
    monkeypatch.setenv("MATHEMA_TEST_WRITE_READ_DELETED", "1")
    p = _row(deletes_from_the_environment)
    assert p.verdict == "proven", (p.verdict, p.sketch, p.note)
    assert os.environ["MATHEMA_TEST_WRITE_READ_DELETED"] == "1"


@pytest.mark.parametrize("fn, text, point", [
    (sets_past_a_half, "for x in [0, 1], not is_state_safe(f)", "x = 1"),
    (sets_past_a_half, "not is_state_safe(f)", "x = 0.5000000000000001"),
    (sets_in_the_else, "for x in [0, 1], not is_state_safe(f)", "x = 1"),
    (sets_in_a_band, "for x in [0, 1], not is_state_safe(f)", "x = 0."),
], ids=["body", "no-domain", "else", "band"])
def test_a_write_under_a_literal_test_is_proven_at_a_point_that_takes_it(
        fn, text, point):
    p = _row(fn, text)
    assert p.verdict == "proven", (p.verdict, p.sketch, p.note)
    assert "not run" in p.sketch and point in p.sketch, p.sketch
    assert _KEY not in os.environ


def test_a_literal_test_that_holds_nowhere_in_the_domain_falsifies():
    p = _row(sets_past_a_half, "for x in [0, 0.25], not is_state_safe(f)")
    assert p.verdict == "falsified", (p.verdict, p.sketch, p.note)


def test_an_else_no_number_of_the_domain_takes_is_read_at_nan():
    # nan < 0.5 is False, and the domain admits nan
    p = _row(sets_in_the_else, "for x in [0, 0.25], not is_state_safe(f)")
    assert p.verdict == "proven", (p.verdict, p.sketch, p.note)
    assert "x = nan" in p.sketch, p.sketch
    assert _KEY not in os.environ


@pytest.mark.parametrize("fn", [
    sets_under_arithmetic, sets_after_a_division, sets_after_an_early_return,
    sets_after_a_rebinding, opens_to_read,
], ids=lambda fn: fn.__name__)
def test_a_write_not_read_as_run_is_not_proven(fn):
    p = _row(fn)
    assert p.verdict != "proven", (p.verdict, p.sketch, p.note)
    assert _KEY not in os.environ


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
