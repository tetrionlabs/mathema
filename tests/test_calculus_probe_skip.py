# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A calculus claim on the probe route skips cleanly, with the reason
in the sketch, never the old misleading 'could not resolve bound
function d, bind one explicitly with funcs=' message."""
from mathema.conjecture import claim, check_conjectures


def sq(x):
    return x * x


def _p(law, route):
    return check_conjectures(sq, [claim(law, route=route)])[0]


def test_derivative_on_probe_skips_with_reason_in_sketch():
    p = _p("for x in [1,5], d(f(x),x) >= 0", "probe")
    assert p.verdict == "skipped"
    assert "not implemented on the probe route" in p.sketch
    assert "probe route: d" in p.sketch
    assert "bind one explicitly" not in (p.note or "") + (p.sketch or "")


def test_integrate_and_lim_and_sum_on_probe_skip_cleanly():
    for law in ("integrate(f(x), x, 0, 1) >= 0",
                "lim(f(x), x, 0) == 0",
                "Sum(f(i), i, 1, n) >= 0"):
        p = _p(law, "probe")
        assert p.verdict == "skipped"
        assert "not implemented on the probe route" in p.sketch


def test_derivative_on_derive_still_proves():
    assert _p("d(f(x), x) == 2*x", "derive").verdict == "proven"
