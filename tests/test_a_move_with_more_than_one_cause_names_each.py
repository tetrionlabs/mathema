# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A transition's cause names every trigger that re-adjudicated the
function and could have moved the verdict: a callee that changed, and a
reading made stricter at a soundness epoch, together."""


def test_a_move_from_a_callee_change_and_the_epoch_names_both_causes():
    from mathema.transitions import cause_of
    cause = cause_of(["dependency", "soundness-epoch"])
    assert "a callee changed" in cause and "soundness epoch 1" in cause, cause
    assert cause_of(["dependency"]) == "a callee changed"
