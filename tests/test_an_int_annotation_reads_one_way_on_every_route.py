# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""An `int`-annotated parameter bound by a plain interval (`for n in
[0, 10]`) ranges over the integers: the annotation completes the domain
to `[0, 10] : int`, rendered so, and every route reads it that way. A
type clause the claim states wins in both directions, and the record
says so: `[0, 10] ⊂ R` widens an `int` parameter to the reals (so
`math.factorial` meets 0.5), `: int` narrows a `float` one."""
import math
import re

from mathema.conjecture import check_conjectures, claim


def factorial_of(n: int) -> int:
    return math.factorial(n)


def floor_gap(n: int) -> float:
    return math.floor(n) - n


def scaled(x: float) -> float:
    return x - math.floor(x)


def _one(fn, text, route="best"):
    (p,) = check_conjectures(fn, [claim(text, route=route)])
    return p


def test_the_annotation_completes_a_plain_interval_to_the_integers():
    for text in ("for n in [0, 10], is_defined(f)",
                 "for n in [0, 10], is_number_set_safe(n)",
                 "for n in [0, 10], f(n) >= 1"):
        p = _one(factorial_of, text)
        assert ": int" in p.statement, p.statement
        assert p.verdict in ("proven", "holds"), (text, p.verdict,
                                                  p.counterexample)


def test_every_route_reads_the_integers():
    for route in ("derive", "probe", "best"):
        p = _one(floor_gap, "for n in [0, 3], f(n) == 0", route)
        assert p.verdict in ("proven", "holds"), (route, p.verdict,
                                                  p.counterexample)


def test_a_stated_real_type_widens_the_parameter():
    p = _one(factorial_of, "for n in [0, 10] ⊂ R, is_number_set_safe(n)")
    assert p.verdict == "falsified", (p.verdict, p.note)
    found = re.search(r"\bn = ([-0-9.e]+)", p.counterexample)
    assert found and not float(found.group(1)).is_integer()
    assert "the claim widens the type" in (p.note or "")
    p = _one(factorial_of, "for n in [0, 10] ⊂ R, is_defined(f)")
    assert p.verdict == "falsified", (p.verdict, p.sketch, p.note)


def test_a_stated_int_type_narrows_a_float_parameter():
    p = _one(scaled, "for x in [0, 3] : int, f(x) == 0")
    assert p.verdict in ("proven", "holds"), (p.verdict, p.counterexample)
    assert "the claim narrows the type" in (p.note or "")


def test_the_number_set_proof_declines_an_int_parameter_over_the_reals():
    from mathema.analysis import analyze_source
    from mathema.claim_families import _working_number_set_proof
    from mathema.domain import _as_domain
    real = _as_domain((0, 10))
    facts = analyze_source(factorial_of)
    assert _working_number_set_proof(factorial_of, facts, "n", ["n"],
                                     {"n": real}) is None
    p = _one(factorial_of, "for n in [0, 10] ⊂ R, is_number_set_safe(n)",
             route="derive")
    assert p.verdict != "proven", (p.verdict, p.sketch)
