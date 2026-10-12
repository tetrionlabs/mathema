# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A callee whose record proves what it computes over its whole domain
gives a value at every input, so the call into it is settled as a
proven `is_defined` row would settle it. An identity over part of the
domain, or a bound, does not settle the call."""
import pytest

from mathema.badges import _callee_evidence


def _entry(statement, verdict="proven", name="halves"):
    return {"claims": [{"name": name, "statement": statement,
                        "verdict": verdict, "route": "derive"}]}


def test_a_proven_identity_over_the_whole_domain_settles_the_call():
    assert _callee_evidence(_entry("f(x) == x/2")) == 1.0


def test_a_holding_identity_settles_it_as_a_holds_does():
    assert _callee_evidence(_entry("f(x) == x/2", verdict="holds")) == \
        pytest.approx(0.90)


@pytest.mark.parametrize("statement", [
    "for x in [0, 1], f(x) == x/2", "f(x) <= x"])
def test_a_narrower_identity_or_a_bound_does_not(statement):
    assert _callee_evidence(_entry(statement)) == 0.0


def test_a_falsified_identity_does_not():
    assert _callee_evidence(_entry("f(x) == x/2", verdict="falsified")) == 0.0
