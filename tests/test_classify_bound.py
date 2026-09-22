# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""probing._classify_bound(): the shared domain-bound-shape classifier
_synth() and _sampling_shorthand() both dispatch off, factored out so a
new bound shape only needs teaching to one place. Before this, each
function independently re-implemented the same isinstance/equality
checks, and _sampling_shorthand's own copy was missing the Domain
branch _synth already had, a real crash the first time a claim's own
richer domain bound (not just probe()'s battery's plain tuples) reached
it."""
import random

from mathema.grammar import Domain, Interval
from mathema.probing import _classify_bound, _sampling_shorthand, _synth


def test_classifies_a_domain_object():
    dom = Domain(base_type="R", pieces=(Interval(0.0, 1.0),), excluded=frozenset())
    assert _classify_bound(dom) == "domain"


def test_classifies_a_frozenset():
    assert _classify_bound(frozenset({1, 2, 3})) == "frozenset"


def test_classifies_named_integer_sets():
    assert _classify_bound("Z") == "Z"
    assert _classify_bound("N") == "N"


def test_classifies_a_plain_interval_tuple():
    assert _classify_bound((0.0, 1.0)) == "interval"


def test_classifies_none():
    assert _classify_bound(None) == "none"


def test_classifies_anything_else_as_other():
    assert _classify_bound("not a recognized shape") == "other"


def test_sampling_shorthand_does_not_crash_on_a_domain_bound():
    # the real regression: a claim's own Domain-shaped bound (union/
    # exclusion/explicit type refinement), not just the plain tuples
    # probe()'s old battery ever passed here.
    dom = Domain(base_type="R", pieces=(Interval(0.0, 1.0),),
                excluded=frozenset({0.5}))
    text = _sampling_shorthand({"x": "scalar"}, {"x": dom}, 128)
    assert "x~" in text
    assert "seed=" in text


def test_synth_still_samples_correctly_from_a_domain_bound():
    dom = Domain(base_type="R", pieces=(Interval(0.0, 1.0),), excluded=frozenset())
    rng = random.Random(7)
    for _ in range(50):
        v = _synth("scalar", rng, dom)
        assert 0.0 <= v <= 1.0
