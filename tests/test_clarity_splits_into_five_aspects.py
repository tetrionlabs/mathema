# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A function's clarity read per aspect: what it computes, what it accepts,
its bounds and shape, how safely it runs and where it can go wrong. Each
aspect's bits are the a-priori bits of its sources, and the function's
score is the mean of the aspect scores weighted by those bits."""
import importlib.util
import sys

import pytest

from mathema.badges import (CLARITY_ALGO, Aspect, ClarityAspects,
                            clarity_aspects, clarity_bits, clarity_score)

_IDS = ("computes", "accepts", "shape", "safety", "failure")
_LABELS = ("what it computes", "what it accepts", "bounds and shape",
           "how safely it runs", "where it can go wrong")

_SRC = '''
import math

def double(x: float) -> float:
    """Twice."""
    return 2.0 * x

def root_of(x: float) -> float:
    if x < 0:
        raise ValueError("negative")
    return math.sqrt(x)

def total(xs: list) -> float:
    s = 0.0
    for v in xs:
        s += v
    return s

def pick(name: str, table: dict):
    return table.get(name, double(1.0))
'''

_FULL = [{"name": "doubles", "statement": "f(x) == 2*x",
          "verdict": "proven", "route": "derive"},
         {"name": "is_state_safe", "statement": "f(x) = f(x)",
          "verdict": "proven", "route": "examine"},
         {"name": "is_deterministic", "statement": "f(x) = f(x)",
          "verdict": "proven", "route": "examine"},
         {"name": "is_numerically_stable", "statement": "g(f, x) = 1",
          "verdict": "proven", "route": "probe"},
         {"name": "is_representation_safe", "statement": "no overflow",
          "verdict": "proven", "route": "derive"}]


@pytest.fixture
def mod(tmp_path):
    p = tmp_path / "aspects_fixture.py"
    p.write_text(_SRC)
    spec = importlib.util.spec_from_file_location("aspects_fixture", p)
    m = importlib.util.module_from_spec(spec)
    sys.modules["aspects_fixture"] = m
    spec.loader.exec_module(m)
    yield m
    sys.modules.pop("aspects_fixture", None)


def _cases(mod):
    nearly = [dict(c) for c in _FULL]
    nearly[1] = dict(nearly[1], verdict="holds", route="derive:brute_force")
    return [(mod.double, []), (mod.double, _FULL), (mod.double, nearly),
            (mod.double, _FULL[:1]), (mod.root_of, []), (mod.total, []),
            (mod.pick, [])]


def _read(fn, rows):
    kw = dict(verified_claims=rows, store={}, library_keys=frozenset())
    return clarity_aspects(fn, **kw), clarity_score(fn, **kw), \
        clarity_bits(fn, **kw)


def test_the_five_aspects_come_in_a_fixed_order_with_their_labels(mod):
    ca, _score, _bits = _read(mod.double, [])
    assert isinstance(ca, ClarityAspects)
    assert all(isinstance(a, Aspect) for a in ca.aspects)
    assert tuple(a.id for a in ca.aspects) == _IDS
    assert tuple(a.label for a in ca.aspects) == _LABELS
    assert ca.algo == CLARITY_ALGO


def test_the_score_and_bits_are_clarity_score_and_clarity_bits(mod):
    for fn, rows in _cases(mod):
        ca, score, (h0, left) = _read(fn, rows)
        assert ca.score == score
        assert ca.h0 == pytest.approx(h0) and ca.left == pytest.approx(left)
        assert sum(a.bits for a in ca.aspects) == pytest.approx(h0)
        assert sum(a.left for a in ca.aspects) == pytest.approx(left)


def test_the_score_is_the_bits_weighted_mean_of_the_aspect_scores(mod):
    for fn, rows in _cases(mod):
        ca, _score, _bits = _read(fn, rows)
        on = [a for a in ca.aspects if a.applies]
        assert sum(a.weight for a in on) == pytest.approx(1.0)
        for a in on:
            assert a.weight == pytest.approx(a.bits / ca.h0)
        mean = sum(a.weight * (1.0 - a.left / a.bits) for a in on)
        assert mean == pytest.approx(1.0 - ca.left / ca.h0)


def test_an_aspect_that_cannot_apply_has_no_score_and_no_weight(mod):
    ca, _score, _bits = _read(mod.double, [])
    failure = ca.aspects[_IDS.index("failure")]
    assert failure.applies is False
    assert failure.score is None and failure.weight == 0
    assert failure.bits == 0 and failure.left == 0
    # a raise site gives the same function shape a failure aspect
    raising, _s, _b = _read(mod.root_of, [])
    assert raising.aspects[_IDS.index("failure")].applies is True
    assert raising.aspects[_IDS.index("failure")].score is not None


def test_an_aspect_reads_100_only_when_nothing_is_left(mod):
    full, score, _bits = _read(mod.double, _FULL)
    assert score == 100
    assert all(a.score == 100 and a.left == 0
               for a in full.aspects if a.applies)
    nearly = [dict(c) for c in _FULL]
    nearly[1] = dict(nearly[1], verdict="holds", route="derive:brute_force")
    ca, score, (_h0, left) = _read(mod.double, nearly)
    assert left > 0 and score == 99 and ca.score == 99
    safety = ca.aspects[_IDS.index("safety")]
    assert safety.left > 0 and safety.score < 100
    assert all(a.score == 100 for a in ca.aspects
               if a.applies and a.id != "safety")


def test_an_unreadable_function_has_no_aspects():
    assert clarity_aspects(len) is None
