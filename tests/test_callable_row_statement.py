# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The built-in `callable` row states what it checked.

When the battery cannot synthesise a call that returns, the row is
skipped; it still names the call it tried, and the reason stays in the
note.
"""
import mathema


def pick(a, b, c):
    if a == 0:
        raise ValueError("a must be nonzero")
    return b / a + c


def label(name: str) -> str:
    return name.upper()


def test_an_unsynthesisable_call_names_the_call_it_tried():
    rec = mathema.check(pick, claims=["for a in [0, 0], raises(f(a, b, c), ValueError)"])
    assert "  skip    callable: f(a, b, c) can be called\n" in repr(rec) + "\n"
    (row,) = [p for p in rec.probes if p.name == "callable"]
    assert "could not synthesize valid inputs" in row.note


def test_an_undeclared_string_parameter_names_the_call_it_tried():
    rec = mathema.check(label)
    (row,) = [p for p in rec.probes if p.name == "callable"]
    assert row.statement == "f(name) can be called"
    assert "string with no declared domain" in row.note
