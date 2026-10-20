# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A guard's raise region, and every text made from it (the definedness
suggestions, the working-domain note), names the parameter first: `w <=
1` and `w > 1 or w < 0`, never `1 >= w` or `1 < w`, so a region recorded
before reads the same when it is computed again."""
import math

import mathema
from mathema.conjecture import _region_texts_agree, check_conjectures, claim


def blend(x: float, w: float) -> float:
    if not 0 <= w <= 1:
        raise ValueError("w outside [0, 1]")
    return w * x + (1 - w) * math.sqrt(abs(x))


def test_the_definedness_suggestions_name_the_parameter_first():
    rows = {s.name: f"{s.lhs} {s.relation} {s.rhs}"
            for s in mathema.suggest_claims(blend)
            if s.name.startswith("is_defined")}
    assert rows == {"is_defined[1]": "w <= 1", "is_defined[2]": "w >= 0"}, rows


def test_the_working_domain_note_names_the_parameter_first():
    (p,) = check_conjectures(blend, [claim("w <= 1", name="is_defined[1]",
                                           route="derive")])
    assert "raises where w > 1 or w < 0" in (p.note or ""), p.note
    assert "1 < w" not in (p.note or "") + (p.sketch or "")


def test_a_recorded_region_still_agrees():
    assert _region_texts_agree("w <= 1", "w <= 1")
