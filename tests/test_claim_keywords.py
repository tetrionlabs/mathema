# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The battery keywords: defined / excluding / stable / stateless
(and their long spellings) inside check()'s claims list expand to the
relevant hazard claims, the members' own structural gates decide
relevance, keyword claims carry no route (examine by construction),
and a near-miss string errors with the whole vocabulary."""
import math

import pytest

import mathema
from mathema.conjecture import InvalidConjecture


def guarded_log(x: float) -> float:
    if x != x or x is None:
        raise ValueError("missing")
    return math.log(x) if x > 0 else 0.0


def line(x: float) -> float:
    return 3.0 * x + 2.0


def test_defined_expands_to_the_gated_hazard_members():
    r = mathema.check(guarded_log, claims=["defined"],
                      domain={"x": (0.5, 10.0)})
    names = {p.name for p in r.probes}
    # gated in: the missing guard exists, log is a restricted builtin
    assert "is_missing_safe[x]" in names
    assert "is_builtin_safe[x]" in names
    # gated out: no pole, no overflow-prone call, nothing suggested
    # that isn't structurally relevant
    assert not any(n.startswith("is_pole_safe") for n in names)
    assert not any(n.startswith("is_extremity_safe") for n in names)
    # and no mathematical suggestions ride along with a keyword
    assert not any(n.startswith("monotonic") for n in names)


def test_excluding_generates_the_exclusion_per_declared_parameter():
    r = mathema.check(line, claims=["excluding"],
                      domain={"x": (0.0, 1.0)})
    (probe,) = [p for p in r.probes
                if p.name == "excluded_outside_domain[x]"]
    assert probe.verdict == "falsified"   # line accepts everything
    assert "asserted, not enforced" in probe.counterexample


def test_stable_and_stateless_name_their_members():
    r = mathema.check(line, claims=["stable", "stateless"])
    names = {p.name for p in r.probes}
    assert "is_numerically_stable" in names
    assert "is_state_safe" in names
    assert "is_deterministic" in names
    # reproducibility stays gated on structural randomness
    assert "is_reproducible" not in names


def test_keywords_mix_with_law_strings():
    r = mathema.check(line, claims=["stateless", "f(x) >= 2"])
    names = {p.name for p in r.probes}
    assert "is_deterministic" in names
    assert any(p.verdict == "falsified" for p in r.probes
               if p.name == "f_x_ge_2")


def test_long_spellings_are_accepted():
    r = mathema.check(guarded_log, claims=["defined_within_domain"],
                      domain={"x": (0.5, 10.0)})
    assert any(p.name == "is_missing_safe[x]" for p in r.probes)


def test_near_miss_errors_with_the_whole_vocabulary():
    with pytest.raises(InvalidConjecture) as err:
        mathema.check(line, claims=["exclduing"])
    message = str(err.value)
    assert "did you mean" in message and "excluding" in message
    for keyword in ("defined", "stable", "stateless"):
        assert keyword in message
