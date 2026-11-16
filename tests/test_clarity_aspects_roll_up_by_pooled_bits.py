# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Each aspect rolls up across functions by pooled bits: 1 - sum(w * left)
/ sum(w * bits), w the function's centrality weight, over the functions
where the aspect applies. A large aspect left open outweighs a tiny one
settled, where a mean of scores would split the difference."""
import re
import sys
from datetime import date

import pytest

from mathema.badges import (CLARITY_ALGO, POOLED_REPO_CLARITY_BY, Aspect,
                            ClarityAspects, _pool_aspects, clarity_aspects,
                            repo_clarity_aspects)

_IDS = ("computes", "accepts", "shape", "safety", "failure")


def _fn(**bits_left) -> ClarityAspects:
    """A ClarityAspects with the given `(bits, left)` per aspect id; the
    function-level fields are not read by the roll-up."""
    aspects = []
    for i in _IDS:
        b, rem = bits_left.get(i, (0.0, 0.0))
        aspects.append(Aspect(i, i, b, rem, b > 0, None, 0.0))
    return ClarityAspects(tuple(aspects), 0.0, 0.0, None, CLARITY_ALGO)


def test_a_tiny_aspect_settled_does_not_lift_a_large_one_left_open():
    out = _pool_aspects([(1.0, _fn(accepts=(0.1, 0.0))),
                         (1.0, _fn(accepts=(20.0, 20.0)))])
    a = out["accepts"]
    assert a.bits == pytest.approx(20.1) and a.left == pytest.approx(20.0)
    assert 1.0 - a.left / a.bits == pytest.approx(0.1 / 20.1)   # about 0.5%
    assert a.score == 0


def test_the_roll_up_is_the_weighted_bits_mean_of_the_function_scores():
    fns = [(2.0, _fn(computes=(1.4, 0.7), safety=(0.7, 0.1),
                     shape=(1.4, 1.4))),
           (0.5, _fn(computes=(1.0, 0.0), accepts=(3.0, 2.0),
                     shape=(2.0, 0.5))),
           (1.0, _fn(computes=(2.2, 2.2), safety=(1.6, 0.4),
                     failure=(2.5, 1.0), accepts=(0.9, 0.3)))]
    out = _pool_aspects(fns)
    total = sum(w * a.bits for w, ca in fns for a in ca.aspects)
    for k, ident in enumerate(_IDS):
        on = [(w, ca.aspects[k]) for w, ca in fns if ca.aspects[k].applies]
        wb = sum(w * a.bits for w, a in on)
        mean = sum(w * a.bits * (1.0 - a.left / a.bits) for w, a in on) / wb
        assert 1.0 - out[ident].left / out[ident].bits == pytest.approx(mean)
        assert out[ident].weight == pytest.approx(wb / total)
        assert out[ident].score == round(100 * mean)


def test_an_aspect_that_applies_nowhere_has_no_score_and_no_weight():
    out = _pool_aspects([(1.0, _fn(computes=(1.0, 0.5))),
                         (3.0, _fn(computes=(2.0, 2.0)))])
    for ident in ("accepts", "shape", "safety", "failure"):
        assert out[ident].applies is False
        assert out[ident].score is None and out[ident].weight == 0
    assert out["computes"].weight == pytest.approx(1.0)
    assert list(out) == list(_IDS)


def test_a_rolled_up_aspect_reads_100_only_when_nothing_is_left():
    nearly = _pool_aspects([(1.0, _fn(shape=(1000.0, 0.001)))])
    assert nearly["shape"].score == 99
    settled = _pool_aspects([(1.0, _fn(shape=(1000.0, 0.0)))])
    assert settled["shape"].score == 100


def test_the_roll_up_reads_the_badges_population_and_its_weights(tmp_path):
    from mathema.badges import _population
    from mathema.centrality import centrality_weights
    pkg = tmp_path / "rcapkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(
        "def core(a: float, b: float) -> float:\n"
        "    '''Sum.'''\n"
        "    if a < 0:\n"
        "        raise ValueError(a)\n"
        "    return a + b\n"
        "def wrap(a: float, b: float) -> float:\n"
        "    '''Delegates.'''\n"
        "    return core(a, b) + core(b, a)\n")
    sys.path.insert(0, str(tmp_path))
    try:
        out = repo_clarity_aspects(root=str(tmp_path), targets=["rcapkg"])
        fns = _population(["rcapkg"], str(tmp_path))
        weights = centrality_weights(fns)
        by_hand = _pool_aspects(
            [(weights.get(k, 1.0), clarity_aspects(fn, root=str(tmp_path)))
             for k, fn in fns.items()])
    finally:
        sys.path.remove(str(tmp_path))
        for m in [m for m in sys.modules if m.startswith("rcapkg")]:
            del sys.modules[m]
    assert set(fns) == {"rcapkg.mod.core", "rcapkg.mod.wrap"}
    assert len(set(weights.values())) > 1          # the weights matter here
    assert list(out) == list(_IDS)
    assert out == by_hand


def test_repo_clarity_is_pooled_bits_by_its_date():
    version = tuple(int(n) for n in
                    re.search(r"@(\d+)\.(\d+)", CLARITY_ALGO).groups())
    assert version >= (1, 5) or date.today() <= POOLED_REPO_CLARITY_BY, (
        "repo clarity is still a centrality-weighted mean of function "
        "scores, so the five rolled-up aspects do not roll up into it; "
        "clarity 1.5 (card clarity-calibration) makes it pooled bits")
