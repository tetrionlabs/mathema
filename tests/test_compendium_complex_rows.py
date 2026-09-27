# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""numpy computes its square root, logarithms and inverse trigonometric
and hyperbolic functions over C for complex input. A real `is_defined`
row (`x >= 0`) is a statement over real inputs: its orderings have no
complex reading, so the guard does not apply at a complex-typed
argument. Each function's complex behaviour is its own row, a bare
`is_defined(f)` over C less the points where numpy returns no value."""
import pytest

from mathema.conjecture import check_conjectures, claim

np = pytest.importorskip("numpy")

COMPLEX_ROWS = {
    "numpy.sqrt": "for x in C, is_defined(f)",
    "numpy.arcsin": "for x in C, is_defined(f)",
    "numpy.arccos": "for x in C, is_defined(f)",
    "numpy.arccosh": "for x in C, is_defined(f)",
    "numpy.log": "for x in C \\ {0}, is_defined(f)",
    "numpy.log2": "for x in C \\ {0}, is_defined(f)",
    "numpy.log10": "for x in C \\ {0}, is_defined(f)",
    "numpy.log1p": "for x in C \\ {-1}, is_defined(f)",
    "numpy.arctanh": "for x in C \\ {1, -1}, is_defined(f)",
}


def cl(z: complex) -> complex:
    return np.log(z)


def csqrt(z: complex) -> complex:
    return np.sqrt(z)


def rsqrt(x: float) -> float:
    return np.sqrt(x)


def _rows(key):
    from mathema.compendium import compendium_functions
    return compendium_functions()[key].get("claims") or []


@pytest.mark.parametrize("key, statement", sorted(COMPLEX_ROWS.items()))
def test_each_function_states_its_complex_behaviour(key, statement):
    (row,) = [r for r in _rows(key) if r["name"] == "is_defined_over_complex"]
    assert row["statement"] == statement
    assert row.get("note")
    (real,) = [r for r in _rows(key) if r["name"] == "is_defined"]
    assert "real inputs" in real["note"], real


@pytest.mark.parametrize("key, statement", sorted(COMPLEX_ROWS.items()))
def test_the_complex_rows_hold_on_numpy(key, statement):
    from mathema.compendium import ensure_bundled
    ensure_bundled()
    import mathema
    fn = getattr(np, key.split(".")[1])
    rec = mathema.check(fn, claims=[claim(statement,
                                          name="is_defined_over_complex")])
    (p,) = [p for p in rec.probes if p.name == "is_defined_over_complex"]
    assert p.verdict == "holds", (p.note, p.counterexample)


def _guards(fn, domain=None):
    from mathema import analyze
    from mathema.compendium import ensure_bundled
    from mathema.symbolic._partiality import partiality_walk
    ensure_bundled()
    guards, _unread = partiality_walk(fn, analyze(fn), domain or {})
    return [str(cond) for cond, _exc in guards]


def test_the_real_guard_does_not_apply_at_a_complex_argument():
    assert _guards(csqrt) == []
    assert _guards(rsqrt) == ["x < 0"]
    assert _guards(rsqrt, {"x": "C"}) == []


def test_the_complex_row_guards_a_complex_argument():
    assert _guards(cl) == ["Eq(z, 0)"]


def test_the_log_round_trip_over_c():
    (p,) = check_conjectures(cl, [claim("for z in C \\ {0}, exp(f(z)) ~= z")])
    assert p.verdict in ("proven", "holds"), (p.note, p.counterexample)
    (p,) = check_conjectures(cl, [claim("for z in C, exp(f(z)) ~= z")])
    assert p.verdict == "falsified", (p.note, p.counterexample)
    assert p.counterexample and "0" in p.counterexample
    (p,) = check_conjectures(cl, [claim("for z in [-4, 4], exp(f(z)) ~= z")])
    assert p.verdict == "falsified"
