# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""is_state_safe, the mutation member of the stateless cluster:
calling the function mutates no external state, no argument in
place, no global, no module attribute. WRITES only; external reads
are is_deterministic's territory. Structure proves via the
write-free certificate or a full lift; the snapshot trials falsify
with the mutated target as witness and hold otherwise (an unexecuted
branch may hide a write, so trials never establish)."""

from mathema.analysis import analyze_source
from mathema.conjecture import check_conjectures, claim
from mathema.suggest import suggest_claims

_TALLY = {"count": 0}


def line(x: float) -> float:
    return 3.0 * x + 2.0


def pusher(xs: list) -> float:
    xs.append(1.0)
    return float(len(xs))


def tallying(x: float) -> float:
    _TALLY["count"] += 1
    return x + 1.0


def local_sorter(a: float, b: float) -> float:
    vals = [a, b]
    vals.sort()
    return vals[0] + vals[1]


def _one(fn):
    (probe,) = check_conjectures(
        fn, [claim("f(" + ", ".join(analyze_source(fn).params) + ") == "
                   "f(" + ", ".join(analyze_source(fn).params) + ")",
                   name="is_state_safe", route="best")],
        facts=analyze_source(fn))
    return probe


def test_write_free_body_proves_structurally():
    probe = _one(line)
    assert probe.verdict == "proven"
    assert probe.route == "examine"
    assert "no state to mutate" in probe.sketch


def test_argument_mutation_falsifies_with_the_argument_named():
    probe = _one(pusher)
    assert probe.verdict == "falsified"
    assert probe.route == "probe:algorithmic"
    assert "mutated its own argument 'xs'" in probe.counterexample


def test_module_state_mutation_falsifies_with_the_name():
    before = _TALLY["count"]
    probe = _one(tallying)
    assert probe.verdict == "falsified"
    assert "_TALLY" in probe.counterexample
    assert _TALLY["count"] > before   # the trials really ran the body


def test_local_mutation_is_not_external_state():
    # vals.sort() mutates a LOCAL: the walk skips locals, but the
    # method call denies the write-free certificate only for
    # parameters and external roots, structure proves? No: the body
    # doesn't lift and the certificate holds (no external site), so
    # this proves structurally
    probe = _one(local_sorter)
    assert probe.verdict == "proven"
    assert probe.route == "examine"


def test_suggested_unconditionally_with_the_stateless_cluster():
    names = {c.name for c in suggest_claims(line)}
    assert "is_state_safe" in names
    assert "is_deterministic" in names
