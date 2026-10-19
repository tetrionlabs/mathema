# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Accepting a falsified claim as a discovery may write a corrected
claim in its place, the author's `--corrected` statement or the one
mathema offers. The correction is adjudicated first, every line of it:
the mathematics row and its computation row (`NAME[float]`). It is
written only when no line falsifies; a correction whose mathematics is
proven while the computation that runs fails it is refused with the
computation line's witness."""
import pytest

from mathema.acceptance import AcceptanceError, plan_acceptance
from mathema.spec import classify_verdict
from tests.test_equivalence_discoveries import _project, _row


def test_a_correction_the_computation_fails_is_refused(tmp_path):
    # (x + 1e20) - 1e20 is x exactly, and 0.0 in float for x in [0, 1]
    entry = _project(tmp_path, "funcs.cancelling", (
        "funcs.cancelling:\n  claims:\n    - name: same\n"
        "      statement: \"let g = funcs.identity, for x in [0, 1], "
        "f =:= g\"\n"))
    assert _row(entry, "same[float]")["verdict"] == "falsified"
    with pytest.raises(AcceptanceError, match="falsifies") as caught:
        plan_acceptance(str(tmp_path), "funcs.cancelling", "same",
                        "discovery", corrected="for x in [0, 1], f(x) ~= x")
    assert "[float]" in str(caught.value), caught.value


def test_a_correction_every_line_holds_is_written(tmp_path):
    _project(tmp_path, "funcs.keep", (
        "funcs.keep:\n  claims:\n    - name: same_root\n"
        "      statement: \"let g = funcs.nudged, for x in [0, 4], "
        "f =:= g\"\n"))
    plan = plan_acceptance(
        str(tmp_path), "funcs.keep", "same_root", "discovery",
        corrected="let g = funcs.nudged, for x in [0, 4], f(x) ~= g(x)")
    assert plan["corrected_statement"].endswith("f(x) ~= g(x)")
    assert classify_verdict(plan["corrected_verdict"]) in ("proven", "holds")
