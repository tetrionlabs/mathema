# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""is_deterministic, the function-wide predicate and the named claim
alike, has a sampling half: two calls at the same inputs, compared by
kind. A NaN agrees with a NaN and the same exception type agrees with
itself, so a function that returns NaN, or raises, the same way every
time is deterministic. A body that reads the clock, the environment or
a file is never proven deterministic by structure, and a holds over it
says in its note what was read, since two back-to-back calls cannot see
that input change."""
import math
import os
import random
import time

import mathema
from mathema.conjecture import check_conjectures, claim


def pure(x: float) -> float:
    return 2 * x


def nan_above_zero(x: float) -> float:
    return math.nan if x > 0 else x


def raises_above_zero(x: float) -> float:
    if x > 0:
        raise ValueError("positive")
    return float(abs(x))


def noisy(x: float) -> float:
    return x + random.random()


def read_env(x: float) -> float:
    return x * float(os.environ.get("MATHEMA_SCALE", "1"))


def stamped(x: float) -> float:
    return x + 0.0 * time.time()


def _wide(fn):
    (p,) = check_conjectures(fn, [claim("is_deterministic(f)")])
    return p


def _named(fn):
    (p,) = check_conjectures(fn, [mathema.claim("f(x) == f(x)",
                                                name="is_deterministic")])
    return p


def test_a_body_that_does_not_lift_is_sampled_not_left_unknown():
    for probe in (_wide, _named):
        p = probe(noisy)
        assert p.verdict == "falsified", (p.verdict, p.note)
        assert "second" in str(p.counterexample), p.counterexample


def test_nan_agrees_with_nan():
    for probe in (_wide, _named):
        p = probe(nan_above_zero)
        assert p.verdict == "holds", (p.verdict, p.counterexample, p.note)


def test_the_same_exception_agrees_with_itself():
    for probe in (_wide, _named):
        p = probe(raises_above_zero)
        assert p.verdict in ("holds", "proven"), (p.verdict, p.counterexample,
                                                  p.note)


def test_a_hidden_read_holds_with_the_read_named():
    for fn, read in ((read_env, "os.environ"), (stamped, "time.time")):
        for probe in (_wide, _named):
            p = probe(fn)
            assert p.verdict == "holds", (fn.__name__, p.verdict, p.note)
            assert read in (p.note or ""), p.note
            assert "back-to-back" in (p.note or ""), p.note


def test_a_pure_body_is_still_proven():
    assert _wide(pure).verdict == "proven"
    assert _named(pure).verdict == "proven"
