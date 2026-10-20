# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A falsified chained comparison's headline names the comparison that
failed and where, not the link's number; the record keeps the link's
number in the witness and the note as before."""
import mathema


def scaled(x: float) -> float:
    return x / 30


def test_the_headline_is_the_failing_comparison():
    rec = mathema.check(scaled, claims=[mathema.claim(
        "for x in [-30, 20], 0 < f(x) < 1", name="unit")])
    main = next(p for p in rec.probes if p.name == "unit")
    assert main.verdict == "falsified", main
    assert main.counterexample.startswith("link 1: "), main.counterexample
    head = next(ln for ln in str(rec).splitlines()
                if ln.strip().startswith("unit "))
    assert "at link" not in head, head
    assert " falsified: 0 < f(x) fails at x = " in head, head


def test_a_later_link_is_named_the_same_way():
    rec = mathema.check(scaled, claims=[mathema.claim(
        "for x in [0.5, 60], 0 < f(x) < 1", name="unit", route="probe")])
    main = next(p for p in rec.probes if p.name == "unit")
    assert main.counterexample.startswith("link 2: "), main.counterexample
    head = next(ln for ln in str(rec).splitlines()
                if ln.strip().startswith("unit "))
    assert " falsified: f(x) < 1 fails at x = " in head, head
