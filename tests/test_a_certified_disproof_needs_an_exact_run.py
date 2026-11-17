# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A disproof certified by interval arithmetic is reported as falsified
only when a run of the function on the witness's exact values reproduces
the failure the certificate names. Where that run does not reproduce it,
or cannot be carried out, the verdict is unknown with the uncorroborated
flag, and the certificate stays in the note."""
import math

import pytest

import mathema
from mathema import gates
from mathema.claims import check_conjectures, claim

NOT_REPRODUCED = ("not reproduced", "the function returned 0.0 on the exact values")
NOT_RUN = ("cannot run", "the function calls numpy.sqrt, which the exact reading does not follow")


def sqrt_just_above(x: float) -> float:
    return math.sqrt(x - (0.3 + 1e-20))


def sqrt_through_a_helper(x: float) -> float:
    return _root(x - (0.3 + 1e-20))


def _root(v):
    return math.sqrt(v)


def log_negative_only_exactly(x: float) -> float:
    return math.log(1 + (x - (0.3 + 1e-20)) * 1e30)


def sqrt_with_a_second_input(x: float, y: float) -> float:
    return math.sqrt(x - (0.3 + 1e-20)) + y


def reciprocal_irrational_pole(x: float) -> float:
    return 1 / (x * x - 2)


def reciprocal_rational_pole(x: float) -> float:
    return 1 / (49 * x - 1)


def pole_behind_a_branch(x: float) -> float:
    if x > 5:
        return 0.0
    return 1 / (x * x - 2)


def tangent(x: float) -> float:
    return math.tan(x)


def sqrt_through_numpy(x: float) -> float:
    import numpy as np
    return float(np.sqrt(x - (0.3 + 1e-20)))


def _row(fn, law, name="c", route="best"):
    return [p for p in mathema.check(
        fn, claims=[mathema.claim(law, name=name, route=route)]).probes
        if p.name == name][0]


def _pole_safe(fn, domain="[0, 10]"):
    (p,) = check_conjectures(
        fn, [claim(f"for x in {domain}, is_pole_safe(x)",
                   name="is_pole_safe[x]", route="derive")])
    return p


ORDERED = [
    (sqrt_just_above, "for x in [0.3, 1], f(x) >= 0"),
    (sqrt_through_a_helper, "for x in [0.3, 1], f(x) >= 0"),
    (log_negative_only_exactly, "for x in [0.3, 1], f(x) >= -1000000000"),
    (sqrt_with_a_second_input, "for x in [0.3, 1], for y in [0, 1], f(x, y) >= 0"),
]


@pytest.mark.parametrize("fn,law", ORDERED, ids=lambda v: getattr(v, "__name__", None))
def test_a_certified_raise_the_exact_run_reproduces_is_falsified(fn, law):
    p = _row(fn, law)
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "certified by interval arithmetic" in p.note
    assert p.meta.get("mathema.witness_exact_run") == "reproduced", p.meta


@pytest.mark.parametrize("fn,law", [
    (reciprocal_irrational_pole, "for x in [0, 10], is_defined(f)"),
    (reciprocal_rational_pole, "for x in [0, 1], is_defined(f)"),
    (tangent, "for x in [0, 2], is_defined(f)"),
], ids=lambda v: getattr(v, "__name__", None))
def test_a_certified_undefined_point_the_exact_run_reproduces_is_falsified(fn, law):
    p = _row(fn, law)
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert p.meta.get("mathema.witness_exact_run") == "reproduced", p.meta


@pytest.mark.parametrize("fn,domain", [
    (reciprocal_irrational_pole, "[0, 10]"),
    (reciprocal_rational_pole, "[0, 1]"),
    (pole_behind_a_branch, "[0, 10]"),
    (tangent, "[0, 2]"),
], ids=lambda v: getattr(v, "__name__", None))
def test_a_certified_pole_the_exact_run_reproduces_is_falsified(fn, domain):
    p = _pole_safe(fn, domain)
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert p.meta.get("mathema.witness_exact_run") == "reproduced", p.meta


@pytest.mark.parametrize("outcome", [NOT_REPRODUCED, NOT_RUN],
                         ids=["not_reproduced", "cannot_run"])
def test_a_certified_raise_the_exact_run_does_not_reproduce_is_unknown(
        monkeypatch, outcome):
    monkeypatch.setattr(gates, "_certified_exact_run",
                        lambda *a, **k: outcome)
    p = _row(sqrt_just_above, "for x in [0.3, 1], f(x) >= 0", route="derive")
    assert p.verdict == "unknown", (p.verdict, p.note)
    assert p.meta.get("mathema.corroboration") == "uncorroborated", p.meta
    assert p.meta.get("mathema.witness_exact_run") == outcome[0], p.meta
    assert p.counterexample is None
    assert "certified by interval arithmetic" in p.note, p.note


@pytest.mark.parametrize("outcome", [NOT_REPRODUCED, NOT_RUN],
                         ids=["not_reproduced", "cannot_run"])
@pytest.mark.parametrize("fn,law", [
    (reciprocal_irrational_pole, "for x in [0, 10], is_defined(f)"),
    (tangent, "for x in [0, 2], is_defined(f)"),
], ids=lambda v: getattr(v, "__name__", None))
def test_a_certified_undefined_point_the_exact_run_does_not_reproduce_is_unknown(
        monkeypatch, outcome, fn, law):
    monkeypatch.setattr(gates, "_certified_exact_run",
                        lambda *a, **k: outcome)
    p = _row(fn, law, route="derive")
    assert p.verdict in ("unknown", "holds"), (p.verdict, p.note)
    assert p.meta.get("mathema.corroboration") == "uncorroborated", p.meta
    assert "certified by interval arithmetic" in (p.note or ""), p.note


@pytest.mark.parametrize("outcome", [NOT_REPRODUCED, NOT_RUN],
                         ids=["not_reproduced", "cannot_run"])
def test_a_certified_pole_the_exact_run_does_not_reproduce_is_unknown(
        monkeypatch, outcome):
    monkeypatch.setattr(gates, "_certified_exact_run",
                        lambda *a, **k: outcome)
    p = _pole_safe(reciprocal_irrational_pole)
    assert p.verdict == "unknown", (p.verdict, p.note)
    assert p.meta.get("mathema.corroboration") == "uncorroborated", p.meta
    assert "certified by interval arithmetic" in (p.note or ""), p.note


def test_a_certified_raise_in_code_the_exact_run_cannot_follow_is_unknown():
    pytest.importorskip("numpy")
    p = _row(sqrt_through_numpy, "for x in [0.3, 1], f(x) >= 0",
             route="derive")
    assert p.verdict == "unknown", (p.verdict, p.note)
    assert p.meta.get("mathema.corroboration") == "uncorroborated", p.meta
    assert p.meta.get("mathema.witness_exact_run") == "cannot run", p.meta
    assert "certified by interval arithmetic" in p.note, p.note
