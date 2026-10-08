# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A parameter without an annotation whose default is True or False is
a flag: it is drawn from {False, True}, never from a range of numbers,
and the sampling note says so."""
from mathema.conjecture import check_conjectures, claim


def flagged(x, compounded=True):
    return x * 2 if compounded else x


def test_an_unannotated_flag_is_drawn_from_false_and_true():
    (p,) = check_conjectures(flagged, [claim(
        "for x in [0, 1], f(x, compounded) >= 0", route="probe")])
    assert p.verdict == "holds"
    assert "compounded~U{False, True}" in p.meta["mathema.sampling"], \
        p.meta["mathema.sampling"]
    assert "compounded in {False, True} from its default" in p.note, p.note
