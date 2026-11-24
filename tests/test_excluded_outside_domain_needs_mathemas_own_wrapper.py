# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`excluded_outside_domain(x)` is proven by construction only when f
really is the wrapper `enforce_domain` built, which checks every call
before the body runs. An `__mathema_enforced_domain__` attribute set by
hand on a plain function checks nothing, so it proves nothing: the
calls outside the domain decide."""
from mathema import enforce_domain
from mathema.conjecture import check_conjectures, claim


def doubled(x):
    return x * 2.0


doubled.__mathema_enforced_domain__ = {"x": "[0, 1]"}


@enforce_domain({"x": "[0, 1]"})
def guarded_doubled(x):
    return x * 2.0


def _row(fn, text="for x in [0, 1], excluded_outside_domain(x)"):
    rows = check_conjectures(fn, [claim(text)])
    return next(r for r in rows if not r.name.endswith("[float]"))


def test_a_hand_set_attribute_does_not_prove_exclusion():
    p = _row(doubled)
    assert p.verdict != "proven", (p.verdict, p.route, p.sketch)


def test_a_hand_set_attribute_is_falsified_by_a_call_outside_the_domain():
    p = _row(doubled)
    assert p.verdict == "falsified", (p.verdict, p.route, p.sketch)


def test_the_enforce_domain_wrapper_still_proves_exclusion():
    p = _row(guarded_doubled)
    assert p.verdict == "proven", (p.verdict, p.route, p.sketch)
