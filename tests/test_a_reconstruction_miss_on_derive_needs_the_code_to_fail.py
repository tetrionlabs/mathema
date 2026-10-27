# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""On route derive, a miss found by sampling derive's own reconstructed
formula (probe:lifted_numeric) falsifies the claim only when the code,
run at that point, fails the relation exactly. A point the code cannot
be run at for the claim (a derivative, which only the reconstruction
reads) is no witness, and the claim stays unknown with the reason. The
default route still reports the reconstruction's miss."""
import math

from mathema.conjecture import check_conjectures, claim


def heat_index_like(t, h):
    return (-8.78 + 1.61 * t + 2.34 * h - 0.146 * t * h
            + 0.012 * t * t * math.exp(h / 80) / (1 + 0.01 * t * h))


_LAW = "for t in [80,110], h in [40,100], d(f(t,h), h) >= -10"


def test_a_reconstruction_miss_the_code_cannot_run_is_no_witness_on_derive():
    (p,) = check_conjectures(heat_index_like, [claim(_LAW, route="derive")])
    assert (p.verdict, p.route) == ("unknown", "derive"), (p.verdict, p.route,
                                                           p.note)
    assert "derive's reconstruction" in p.note
    assert "is no witness" in p.note
    assert p.counterexample is None
