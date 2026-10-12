# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A bool parameter with no finite set bound in the claim is drawn as
False or True, and the sampling note says so, as it does for a plain
`bool` annotation whose two points are its domain."""
from typing import Optional

from mathema.claims import check_conjectures, claim
from mathema.probing import _sampling_shorthand


def maybe_flip(x: float, on: Optional[bool]) -> float:
    return x if on else -x


def quoted_flip(x: float, on: "bool") -> float:
    return x if on else -x


def _note(fn):
    (p,) = check_conjectures(fn, [claim("abs(f(x, on)) == abs(x)", route="probe")])
    assert p.verdict == "holds", (p.verdict, p.note)
    return p.meta["mathema.sampling"]


def test_the_shorthand_describes_an_unbound_bool_as_its_two_values():
    note = _sampling_shorthand({"on": "bool"}, {}, 10)
    assert "on~U{False, True}" in note, note


def test_an_optional_bool_is_described_as_the_bool_draw():
    note = _note(maybe_flip)
    assert "on~U{False, True}" in note, note
    assert "on~U(-10,10)" not in note, note


def test_a_quoted_bool_is_described_as_the_bool_draw():
    note = _note(quoted_flip)
    assert "on~U{False, True}" in note, note
