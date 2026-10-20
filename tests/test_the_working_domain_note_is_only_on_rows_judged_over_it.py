# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The record states the working domain (the note and the
`mathema.working_domain` meta) on a row judged over it, and only there.
A claim that binds its own domain is judged over that domain, and a
witness at an input f's own guard refuses is stated with no working
domain beside it. `excluded_outside_domain` asks about the whole
domain, and the state and repeatability families are read from the
source, so neither states a working domain."""
import math

from mathema.conjecture import check_conjectures, claim


def volatility(variance: float) -> float:
    if variance < 0:
        raise ValueError("variance is negative")
    return math.sqrt(variance)


def _one(text):
    (p,) = check_conjectures(volatility, [claim(text)])
    return p


def _states_no_working_domain(p):
    assert "working domain" not in (p.note or ""), (p.statement, p.note)
    assert "mathema.working_domain" not in (p.meta or {}), \
        (p.statement, p.meta)


def test_a_claim_binding_its_own_domain_states_no_working_domain():
    p = _one("for variance in [-1, 1], is_finite(f(variance))")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert p.counterexample.startswith("variance = -"), p.counterexample
    _states_no_working_domain(p)


def test_is_defined_binding_its_own_domain_states_no_working_domain():
    p = _one("for variance in [-1, 1], is_defined(f)")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert p.counterexample.startswith("variance = -"), p.counterexample
    _states_no_working_domain(p)


def test_excluded_outside_domain_states_no_working_domain():
    _states_no_working_domain(_one("excluded_outside_domain(variance)"))


def test_a_family_read_from_the_source_states_no_working_domain():
    p = _one("for variance in [-1, 1], is_deterministic(f)")
    assert p.verdict == "proven", (p.verdict, p.note)
    _states_no_working_domain(p)


def test_a_row_judged_over_the_working_domain_states_it():
    p = _one("is_finite(f(variance))")
    assert p.verdict in ("proven", "holds"), (p.verdict, p.counterexample,
                                              p.note)
    assert "the working domain is variance in [0, oo)" in (p.note or ""), \
        p.note
    p = _one("is_defined(f)")
    assert p.verdict == "proven", (p.verdict, p.note)
    assert "the working domain is variance in [0, oo)" in (p.note or ""), \
        p.note
