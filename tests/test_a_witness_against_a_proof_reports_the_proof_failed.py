# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""When the `[float]` companion of a proof executes a point where the
claim fails, the point is checked in exact arithmetic. False there too,
the proof failed: the claim is falsified with that witness, and nothing
calls it a loss of precision. True there, the computation lost the
value, which is the normal shape of a proven claim whose float code
breaks it."""
import pytest

import mathema.conjecture as conjecture
from mathema.conjecture import check_conjectures, claim
from mathema.symbolic import ProofResult


def parabola(x: float) -> float:
    return x - x * x


def cancels(x: float) -> float:
    return (x + 1e16) - 1e16


@pytest.mark.needs_full_proof_budget
def test_a_false_proof_caught_by_execution_is_reported_as_a_failed_proof(
        monkeypatch):
    def wrong(*args, **kwargs):
        return ProofResult("proven", sketch="an unsound step")
    monkeypatch.setattr(conjecture, "try_prove", wrong)
    probes = check_conjectures(parabola, [
        claim("for x in [0.2, 0.8], f(x) > 0.3", route="derive")],
        float_companions=True)
    parent, companion = probes[0], probes[1]
    assert parent.verdict == "falsified", (parent.verdict, parent.sketch)
    assert "the proof failed" in parent.sketch
    assert parent.counterexample
    head, _, reason = parent.counterexample.partition(":")
    assert parabola(float(head.split("=")[1])) <= 0.3
    assert "the relation fails" in reason
    assert companion.verdict == "falsified"
    assert "the proof of" in companion.sketch
    for probe in probes:
        assert "precision loss" not in (probe.sketch or "")


@pytest.mark.needs_full_proof_budget
def test_a_float_cancellation_against_a_true_proof_is_precision_loss():
    probes = check_conjectures(cancels, [
        claim("for x in [0.1, 0.9], f(x) == x", route="derive")],
        float_companions=True)
    parent, companion = probes[0], probes[1]
    assert parent.verdict == "proven", (parent.verdict, parent.sketch)
    assert companion.verdict == "falsified", companion.sketch
    assert "precision loss" in companion.sketch
    assert companion.stratum["mathematics"] == "sound"
