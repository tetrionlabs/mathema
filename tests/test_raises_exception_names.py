# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`raises(f(x), Exc)` names its exception by a built-in name, a dotted
path (`numpy.linalg.LinAlgError`), or a bare name found on the target's
own module or one of its parents (`LinAlgError` for a `numpy.linalg`
function). A name none of these resolve is `skipped:misspecified`, and
the note names it."""
import pytest

import mathema
from mathema.conjecture import check_conjectures, claim


class BadInput(Exception):
    pass


def picky(x: float) -> float:
    if x < 0:
        raise BadInput("negative")
    return x


def _declared(fn, statement):
    (p,) = [p for p in mathema.check(fn, claims=[statement]).probes
            if p.meta.get("mathema.surface") == "declared"]
    return p


def test_a_bare_name_on_the_targets_own_module_resolves():
    (p,) = check_conjectures(
        picky, [claim("for x in [-4, -1], raises(f(x), BadInput)",
                      route="probe")])
    assert p.verdict == "holds", (p.verdict, p.note)


def test_a_dotted_name_resolves():
    (p,) = check_conjectures(
        picky, [claim(f"for x in [-4, -1], raises(f(x), "
                      f"{__name__}.BadInput)", route="probe")])
    assert p.verdict == "holds", (p.verdict, p.note)


def test_a_resolved_name_still_falsifies_a_different_raise():
    (p,) = check_conjectures(
        picky, [claim("for x in [-4, -1], raises(f(x), ZeroDivisionError)",
                      route="probe")])
    assert p.verdict == "falsified"
    assert "raised BadInput" in p.counterexample


def test_an_unresolvable_name_is_misspecified_and_named():
    (p,) = check_conjectures(
        picky, [claim("for x in [-4, -1], raises(f(x), NoSuchError)")])
    assert p.verdict == "skipped:misspecified"
    assert "NoSuchError" in p.note


def test_linalgerror_resolves_bare_and_dotted_on_a_numpy_linalg_target():
    np = pytest.importorskip("numpy")
    for name in ("LinAlgError", "numpy.linalg.LinAlgError"):
        p = _declared(np.linalg.inv,
                      f"for a in R^n, raises(f(a), {name})")
        assert p.verdict == "holds", (name, p.verdict, p.note)
