# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`is_defined` on a target with no Python source (a builtin, a numpy
ufunc) is adjudicated by execution, since there is no body to compute a
definedness region from. The bare `is_defined(f)` asks that every
sampled point of the domain return a finite value; the restriction
form (a claim named `is_defined` stating a region) asks that f return a
finite value inside the region and no value outside it, where a raise
and a non-finite result (nan, inf) are both no value. Either failure is
a falsification at an executed point."""
import math
import re

import pytest

import mathema

np = pytest.importorskip("numpy")


def _declared(fn, statement):
    (p,) = [p for p in mathema.check(fn, claims=[statement]).probes
            if p.meta.get("mathema.surface") == "declared"]
    return p


def _restriction(region):
    return mathema.claim(region, name="is_defined")


def _witness_x(probe) -> float:
    m = re.search(r"\bx = ([-+0-9.e]+)", probe.counterexample or "")
    assert m, probe.counterexample
    return float(m.group(1))


def _returns_a_value(fn, x) -> bool:
    try:
        with np.errstate(all="ignore"):
            out = fn(x)
    except Exception:
        return False
    return bool(np.isfinite(out))


@pytest.mark.parametrize("fn", [math.sqrt, np.sqrt], ids=["math", "numpy"])
def test_bare_is_defined_on_a_square_root_is_falsified_at_an_executed_point(fn):
    p = _declared(fn, "for x in [-4, 4], is_defined(f)")
    assert p.verdict == "falsified", (p.verdict, p.note, p.sketch)
    assert p.counterexample
    assert not _returns_a_value(fn, _witness_x(p))
    assert p.meta.get("mathema.witness_executed") is True


@pytest.mark.parametrize("fn", [math.sqrt, np.sqrt], ids=["math", "numpy"])
def test_the_square_roots_region_holds(fn):
    p = _declared(fn, _restriction("x >= 0"))
    assert p.verdict == "holds", (p.verdict, p.note, p.sketch)


def test_a_region_too_narrow_is_falsified_where_f_returns():
    p = _declared(math.sqrt, _restriction("x >= 1"))
    assert p.verdict == "falsified", (p.verdict, p.note, p.sketch)
    x = _witness_x(p)
    assert 0 <= x < 1 and _returns_a_value(math.sqrt, x)
    assert "outside the stated region" in p.counterexample
    assert p.meta.get("mathema.witness_executed") is True


def test_a_region_too_wide_is_falsified_where_f_has_no_value():
    p = _declared(np.sqrt, _restriction("x >= -1"))
    assert p.verdict == "falsified", (p.verdict, p.note, p.sketch)
    x = _witness_x(p)
    assert -1 <= x < 0 and not _returns_a_value(np.sqrt, x)


def test_a_chained_region_holds_on_arcsin():
    p = _declared(np.arcsin, _restriction("-1 <= x <= 1"))
    assert p.verdict == "holds", (p.verdict, p.note, p.sketch)


def test_an_open_region_holds_on_log1p():
    p = _declared(np.log1p, _restriction("x > -1"))
    assert p.verdict == "holds", (p.verdict, p.note, p.sketch)


def test_the_note_says_where_the_region_was_sampled():
    p = _declared(math.sqrt, _restriction("x >= 0"))
    assert "inside the stated region" in p.note
    assert "outside" in p.note
