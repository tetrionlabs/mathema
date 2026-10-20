# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Every claim mathema suggests for a function whose guard cuts a
parameter's domain parses and adjudicates: a claim variable that is not
a parameter (associativity's third argument) is introduced with `let`,
as it is when no guard cuts the domain, never bound by `for` as a
domain key no parameter matches. An authored claim that does bind a
non-parameter with `for` is still skipped, its note naming the name."""
import mathema
from mathema.conjecture import check_conjectures, claim
from mathema.suggest import suggest_claims

_UNBOUND = "don't match any real parameter"


def percent_change(old: float, new: float) -> float:
    if old == 0:
        raise ValueError("old is zero")
    return (new - old) / old * 100.0


def test_no_suggestion_for_a_guarded_function_binds_a_non_parameter_with_for():
    for cj in suggest_claims(percent_change):
        unbound = set(cj.domain or {}) - {"old", "new"} - set(cj.free_vars or ())
        assert not unbound, (cj.name, cj.lhs, cj.rhs, sorted(unbound))


def test_every_suggested_row_adjudicates():
    rows = mathema.check(percent_change).probes
    unbound = [(p.name, p.note) for p in rows if _UNBOUND in (p.note or "")]
    assert not unbound, unbound
    (assoc,) = [p for p in rows if p.name == "associative"]
    assert not assoc.verdict.startswith("skipped"), (assoc.verdict, assoc.note)


def test_the_associative_suggestion_keeps_the_third_argument_in_the_second_slot_set():
    (cj,) = [c for c in suggest_claims(percent_change) if c.name == "associative"]
    assert "c" in (cj.free_vars or ()), cj.free_vars


def test_an_authored_for_over_a_non_parameter_is_skipped_naming_it():
    (row,) = check_conjectures(percent_change, [claim(
        "for old in [1, 2], k in [0, 1], f(old, old) == 0")])
    assert row.verdict == "skipped", (row.verdict, row.note)
    assert "domain key(s) ['k']" in row.note and _UNBOUND in row.note, row.note
