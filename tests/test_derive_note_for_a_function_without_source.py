# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A function with no Python source (a C builtin such as `math.log`)
has no body the derive route could read, and its note says exactly
that, never that the body contains a loop, branch or recursion."""
import math

import mathema


def _note(fn, claim):
    # the claim's own row, not its companions (the empty-input line
    # sits under every value claim)
    (row,) = [p for p in mathema.check(fn, claims=[claim]).probes
              if p.name != "callable"
              and not (p.meta or {}).get("mathema.companion_of")]
    return row.note or ""


def test_a_c_builtin_says_its_body_could_not_be_read():
    note = _note(math.log, "f(1) == 0")
    assert "body could not be read" in note
    assert "loop" not in note
    assert "recursion" not in note


def test_a_python_function_with_a_loop_still_names_the_loop():
    def total(xs: list) -> float:
        s = 0.0
        for v in xs:
            s = s * 2 + v
        return s
    note = _note(total, "f([1.0]) == 1")
    assert "could not be read" not in note
