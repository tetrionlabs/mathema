# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Annotation-to-domain inference: an `int` annotation is domain
information the author already wrote, so a parameter with no stated
bound resolves to the integer type (a `bool` one to the two-point
set), gap-filling only and always rendered in the note, the same
terse-input/explicit-output shape as literal-argument inference."""
import math

from mathema.analysis import analyze_source
from mathema.conjecture import check_conjectures, claim


def double_int(n: int) -> int:
    return n * 2


def fact(n: int) -> int:
    return math.factorial(n)


def negate_flag(b: bool) -> bool:
    return not b


def scale(x: float) -> float:
    return x * 3.0


def _one(fn, law, **kw):
    (probe,) = check_conjectures(fn, [claim(law, **kw)],
                                 facts=analyze_source(fn))
    return probe


def test_int_annotation_infers_the_integer_type_and_says_so():
    probe = _one(double_int, "f(n) == 2*n", route="derive")
    assert probe.verdict == "proven"
    assert "inferred n in Z from its own int annotation" in probe.note


def test_stated_domain_wins_over_the_annotation():
    probe = _one(double_int, "for n in [0, 10], f(n) == 2*n",
                 route="derive")
    assert "inferred n in Z" not in probe.note


def test_bool_annotation_infers_the_two_point_set():
    # the two-point set arrives through the same stated-values channel
    # a Literal[...]/Enum annotation uses, carrying the real
    # False/True objects (never the numerically-equal 0/1, code
    # comparing with `is True` behaves differently under the two)
    facts = analyze_source(negate_flag)
    assert facts.param_kinds["b"] == "bool"
    assert facts.finite_domains["b"] == [False, True]
    probe = _one(negate_flag, "f(b) == 1 - b", route="probe")
    assert probe.verdict == "holds"
    assert ("inferred b in {False, True} from its own annotation's "
            "stated values") in probe.note


def test_float_annotation_infers_nothing():
    probe = _one(scale, "f(x) == 3*x", route="derive")
    assert "inferred x" not in probe.note


def test_inferred_integer_type_reaches_the_builtin_safety_verdict():
    # bare Z still contains a negative integer, so factorial's builtin
    # safety is honestly falsified even under the inference, and the
    # note shows exactly where the Z came from
    probe = _one(fact, "is_builtin_safe(n)", route="best")
    assert probe.verdict == "falsified"
    assert "inferred n in Z from its own int annotation" in probe.note
