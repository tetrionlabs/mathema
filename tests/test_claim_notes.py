# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A result's note is a `; `-separated list of claim-specific remarks,
and it reads from its first remark: it never opens with a separator,
whichever remark happens to come first."""
from mathema import check_conjectures, claim
from mathema.records import Probe


def scale(x: float) -> float:
    return 2 * x


def scaled(x: float, a: float) -> float:
    return a * x


def test_missing_prerequisite_note_starts_with_the_remark():
    (p,) = check_conjectures(scale, [
        claim("assuming absent holds, for x in [0,10], f(x) >= 0",
              name="orphan")])
    assert p.meta["mathema.premise"] == "missing-prerequisite"
    assert p.note == ("prerequisite 'absent' is not a claim in this batch, "
                      "nothing to rest this claim on")


def test_literal_argument_inference_note_starts_with_the_remark():
    (p,) = check_conjectures(scaled, [claim("f(x, 1.0) == x")])
    assert p.note == "inferred a=1 from the claim's own literal argument"


def test_probe_note_assigned_after_construction_drops_a_leading_separator():
    p = Probe("c", "f(x) >= 0", "holds", note="; first remark")
    assert p.note == "first remark"
    p.note = f"{''}; later remark"
    assert p.note == "later remark"


def test_probe_note_keeps_separators_between_remarks():
    p = Probe("c", "f(x) >= 0", "holds", note="one; two")
    assert p.note == "one; two"
    assert Probe("c", "s", "holds").note is None
