# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A branch is read as unreachable over a claim's domain in two cases
only: its test is a constant that never takes it, or its test compares
a bare parameter name with numeric literals (`<`, `<=`, `>`, `>=`,
`==`, `!=`, joined by `and`, `or`, `not`), sits in the function's own
body, and reads a parameter nothing in the function binds again. Then
the name holds the argument at the test, each comparison means in
Python what it means over the reals, and no arithmetic is rounded. A
write under any other test falsifies `is_state_safe(f)` as in general."""
import contextlib

import pytest

from mathema.conjecture import check_conjectures, claim

_log: list = []
_count = 0
LIMIT = 0.5


def rebound_before_the_test(x):
    x = x + 100.0
    if x > 10.0:
        _log.append(x)
    return x * 2.0


def rebound_in_an_earlier_branch(x):
    if x >= 0.0:
        x = 50.0
    if x > 10.0:
        _log.append(x)
    return x


def loop_target_of_the_same_name(x):
    for x in (100.0,):
        if x > 10.0:
            _log.append(x)
    return 2.0


def inner_parameter_of_the_same_name(x):
    def g(x):
        if x > 10.0:
            _log.append(x)
    g(x + 100.0)
    return x * 2.0


def inner_test_beside_the_same_outer_test(x):
    def g(x):
        if x > 10.0:
            _log.append(x)
    if x > 10.0:
        pass
    g(x + 100.0)
    return x * 2.0


def xor_read_as_a_power(x):
    if x ^ 12 > 10:
        _log.append(x)
    return x * 2


def true_only_in_floats(x):
    if (x + 1e16) - 1e16 > 1.5:
        _log.append(x)
    return x * 2.0


def augmented(x):
    x *= 100.0
    if x > 10.0:
        _log.append(x)
    return x


def walrus(x):
    if (x := x + 100.0) > 10.0:
        _log.append(x)
    return x


def walrus_elsewhere(x):
    y = (x := x + 100.0)
    if x > 10.0:
        _log.append(y)
    return x


def with_target(x):
    with contextlib.nullcontext(100.0) as x:
        if x > 10.0:
            _log.append(x)
    return 2.0


def except_name(x):
    try:
        raise ValueError(100.0)
    except ValueError as x:
        if x.args[0] > 10.0:
            _log.append(1.0)
    return 2.0


def deleted(x):
    y = x
    del x
    x = y + 100.0
    if x > 10.0:
        _log.append(x)
    return y


def comprehension_of_the_same_name(x):
    ys = [x for x in (1.0, 2.0)]
    if x > 10.0:
        _log.append(x)
    return ys[0]


def lambda_of_the_same_name(x):
    g = lambda x: x + 1.0  # noqa: E731
    if x > 10.0:
        _log.append(x)
    return g(x)


def arithmetic_in_the_test(x):
    if x * x > 1.0:
        _log.append(x)
    return x


def negated_parameter(x):
    if -x < -10.0:
        _log.append(x)
    return x


def module_constant_in_the_test(x):
    if x > LIMIT:
        _log.append(x)
    return x


def edge_of_the_domain(x):
    if x >= 1.0:
        _log.append(x)
    return x * 2.0


def while_loop(x):
    while x > 10.0:
        _log.append(x)
        x -= 1
    return x * 2.0


def comprehension_filter(x):
    [_log.append(x) for _ in range(2) if x > 10.0]
    return x * 2.0


def conditional_expression(x):
    _log.append(x) if x > 10.0 else None
    return x * 2.0


def short_circuit(x):
    x > 10.0 and _log.append(x)
    return x * 2.0


def second_live_copy(x):
    if x > 10.0:
        _log.append(x)
    _log.append(x)
    return x * 2.0


def second_copy_in_a_live_branch(x):
    if x > 10.0:
        _log.append(x)
    if x < 10.0:
        _log.append(x)
    return x * 2.0


def guard_on_another_parameter(x, y=100.0):
    if y > 10.0:
        _log.append(x)
    return x


def else_a_nan_takes(x):
    if x < 10.0:
        pass
    else:
        _log.append(x)
    return x * 2.0


def negation_a_nan_takes(x):
    if not (x < 10.0):
        _log.append(x)
    return x * 2.0


def unequal_a_nan_takes(x):
    if x != x or x > 10.0:
        _log.append(x)
    return x * 2.0


REACHABLE = [
    (rebound_before_the_test, "for x in [0, 1], is_state_safe(f)"),
    (rebound_before_the_test, "for x in [0, 1], is_deterministic(f)"),
    (rebound_in_an_earlier_branch, "for x in [0, 1], is_state_safe(f)"),
    (loop_target_of_the_same_name, "for x in [0, 1], is_state_safe(f)"),
    (inner_parameter_of_the_same_name, "for x in [0, 1], is_state_safe(f)"),
    (inner_test_beside_the_same_outer_test,
     "for x in [0, 1], is_state_safe(f)"),
    (xor_read_as_a_power, "for x in [0, 1], is_state_safe(f)"),
    (true_only_in_floats, "for x in [0, 1.2], is_state_safe(f)"),
    (augmented, "for x in [0, 1], is_state_safe(f)"),
    (walrus, "for x in [0, 1], is_state_safe(f)"),
    (walrus_elsewhere, "for x in [0, 1], is_state_safe(f)"),
    (with_target, "for x in [0, 1], is_state_safe(f)"),
    (except_name, "for x in [0, 1], is_state_safe(f)"),
    (deleted, "for x in [0, 1], is_state_safe(f)"),
    (comprehension_of_the_same_name, "for x in [0, 1], is_state_safe(f)"),
    (lambda_of_the_same_name, "for x in [0, 1], is_state_safe(f)"),
    (arithmetic_in_the_test, "for x in [0, 2], is_state_safe(f)"),
    (arithmetic_in_the_test, "for x in [0, 1], is_state_safe(f)"),
    (negated_parameter, "for x in [0, 1], is_state_safe(f)"),
    (module_constant_in_the_test, "for x in [0, 1], is_state_safe(f)"),
    (edge_of_the_domain, "for x in [0, 1], is_state_safe(f)"),
    (while_loop, "for x in [0, 1], is_state_safe(f)"),
    (comprehension_filter, "for x in [0, 1], is_state_safe(f)"),
    (conditional_expression, "for x in [0, 1], is_state_safe(f)"),
    (short_circuit, "for x in [0, 1], is_state_safe(f)"),
    (second_live_copy, "for x in [0, 1], is_state_safe(f)"),
    (second_copy_in_a_live_branch, "for x in [0, 1], is_state_safe(f)"),
    (guard_on_another_parameter, "for x in [0, 1], is_state_safe(f)"),
    (else_a_nan_takes, "for x in [0, 1], is_state_safe(f)"),
    (negation_a_nan_takes, "for x in [0, 1], is_state_safe(f)"),
    (unequal_a_nan_takes, "for x in [0, 1], is_state_safe(f)"),
]


def _row(fn, text):
    rows = check_conjectures(fn, [claim(text)])
    return next(r for r in rows if not r.name.endswith("[float]"))


@pytest.mark.parametrize(
    "fn, text", REACHABLE, ids=[f"{fn.__name__}:{text.split(', ')[-1]}"
                                for fn, text in REACHABLE])
def test_a_write_under_any_other_test_falsifies(fn, text):
    p = _row(fn, text)
    assert p.verdict == "falsified", (p.verdict, p.sketch)
    assert "unreachable" not in (p.counterexample or ""), p.counterexample


def test_a_false_proof_of_state_safety_does_not_falsify_its_negation():
    p = _row(rebound_before_the_test, "for x in [0, 1], not is_state_safe(f)")
    assert p.verdict != "falsified", (p.verdict, p.sketch)


# --- what is still read as unreachable ---------------------------------------

def never_writes(x):
    if False:
        _log.append(x)
    return x * 2.0


def never_writes_in_an_inner_function(x):
    def g(y):
        if False:
            _log.append(y)
    g(x)
    return x * 2.0


def past_ten(x):
    if x > 10.0:
        _log.append(x)
    return x * 2.0


def literal_on_the_left(x):
    if 10 < x:
        _log.append(x)
    return x * 2.0


def below_a_negative_literal(x):
    if x <= -1.5:
        _log.append(x)
    return x * 2.0


def joined_by_and(x):
    if x > 0.25 and x < 0.2:
        _log.append(x)
    return x * 2.0


def joined_by_or(x):
    if x < -1 or x > 10 or x == 7:
        _log.append(x)
    return x * 2.0


def negated(x):
    if not (x != 3.0):
        _log.append(x)
    return x * 2.0


def after_a_live_branch(x):
    if x < 0.5:
        return 1.0
    elif x > 10.0:
        _log.append(x)
    return x


def two_copies_under_the_same_test(x):
    if x > 10.0:
        _log.append(x)
    y = x * 2.0
    if x > 10.0:
        _log.append(x)
    return y


UNREACHABLE = [
    (never_writes, "for x in [0, 1], is_state_safe(f)", "constant"),
    (never_writes, "is_state_safe(f)", "constant"),
    (never_writes, "for x in [0, 1], is_deterministic(f)", "constant"),
    (never_writes_in_an_inner_function,
     "for x in [0, 1], is_state_safe(f)", "constant"),
    (past_ten, "for x in [0, 5], is_state_safe(f)", "x > 10"),
    (past_ten, "for x in [0, 5], is_deterministic(f)", "x > 10"),
    (literal_on_the_left, "for x in [0, 5], is_state_safe(f)", "10 < x"),
    (below_a_negative_literal, "for x in [0, 5], is_state_safe(f)",
     "x <= -1.5"),
    (joined_by_and, "for x in [0, 1], is_state_safe(f)", "x > 0.25 and"),
    (joined_by_or, "for x in [0, 5], is_state_safe(f)", "x < -1 or"),
    (negated, "for x in [0, 1], is_state_safe(f)", "not x != 3.0"),
    (after_a_live_branch, "for x in [0, 1], is_state_safe(f)", "x > 10"),
    (two_copies_under_the_same_test, "for x in [0, 1], is_state_safe(f)",
     "holds nowhere"),
]


@pytest.mark.parametrize(
    "fn, text, shown", UNREACHABLE,
    ids=[f"{fn.__name__}:{text.split(', ')[-1]}:{i}"
         for i, (fn, text, _shown) in enumerate(UNREACHABLE)])
def test_a_write_in_unreachable_code_is_proven(fn, text, shown):
    p = _row(fn, text)
    assert p.verdict == "proven", (p.verdict, p.sketch)
    assert "unreachable code" in p.sketch and shown in p.sketch, p.sketch


# --- a negated safety claim is proven by a witness ---------------------------
# `not is_state_safe(f)` and `not is_deterministic(f)` say a call exists
# that writes, or that two calls with one input differ. A call that was
# run and showed it proves the claim; a line read from the source does
# not, and a wrong reading of unreachable code never falsifies it.

def always_writes(x):
    _log.append(x)
    return x * 2.0


def draws(x):
    import random
    return x + random.random()


def writes_and_returns_the_same(x):
    _log.append(x)
    return x * 2.0


def sets_the_environment(x):
    import os
    os.environ["MATHEMA_TEST_WITNESS_NOT_RUN"] = "1"
    return x * 2.0


def test_an_executed_write_proves_the_function_is_not_state_safe():
    p = _row(always_writes, "for x in [0, 1], not is_state_safe(f)")
    assert p.verdict == "proven", (p.verdict, p.sketch, p.note)
    assert "_log" in p.sketch and "x = " in p.sketch, p.sketch


def test_an_executed_write_in_a_branch_the_domain_reaches_proves_it():
    p = _row(past_ten, "for x in [0, 20], not is_state_safe(f)")
    assert p.verdict == "proven", (p.verdict, p.sketch, p.note)
    assert "x = 20" in p.sketch, p.sketch


def test_a_write_past_a_number_the_test_names_is_witnessed_beside_it():
    p = _row(past_ten, "not is_state_safe(f)")
    assert p.verdict == "proven", (p.verdict, p.sketch, p.note)
    assert "x = 10.0000" in p.sketch, p.sketch


def test_two_calls_that_differ_prove_the_function_is_not_deterministic():
    p = _row(draws, "for x in [0, 1], not is_deterministic(f)")
    assert p.verdict == "proven", (p.verdict, p.sketch, p.note)
    assert "two calls" in p.sketch and "x = " in p.sketch, p.sketch


def test_a_write_after_a_rebinding_is_witnessed_not_read_as_unreachable():
    p = _row(rebound_before_the_test, "for x in [0, 1], not is_state_safe(f)")
    assert p.verdict == "proven", (p.verdict, p.sketch, p.note)


@pytest.mark.parametrize("fn, text", [
    (never_writes, "for x in [0, 1], not is_state_safe(f)"),
    (never_writes, "for x in [0, 1], not is_deterministic(f)"),
    (past_ten, "for x in [0, 5], not is_state_safe(f)"),
], ids=["constant", "constant-deterministic", "past-ten"])
def test_a_proven_safety_claim_falsifies_its_negation(fn, text):
    p = _row(fn, text)
    assert p.verdict == "falsified", (p.verdict, p.sketch, p.note)


def test_a_write_only_a_nan_reaches_is_witnessed_at_nan():
    # no number in [0, 5] takes the else; nan, which the domain admits, does
    p = _row(else_a_nan_takes, "for x in [0, 5], not is_state_safe(f)")
    assert p.verdict == "proven", (p.verdict, p.sketch, p.note)
    assert "x = nan" in p.sketch, p.sketch


def test_no_witness_leaves_the_negation_undecided():
    # the result never reads what the call wrote: two calls agree
    p = _row(writes_and_returns_the_same,
             "for x in [0, 1], not is_deterministic(f)")
    assert p.verdict == "unknown", (p.verdict, p.sketch, p.note)


def test_a_function_that_writes_outside_its_module_is_not_run_for_a_witness():
    import os
    p = _row(sets_the_environment, "for x in [0, 1], not is_state_safe(f)")
    assert p.verdict == "proven", (p.verdict, p.sketch, p.note)
    assert "child process" in p.sketch, p.sketch
    assert "MATHEMA_TEST_WITNESS_NOT_RUN" not in os.environ
