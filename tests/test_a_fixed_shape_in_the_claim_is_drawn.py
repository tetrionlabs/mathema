# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A literal dimension in a parameter's own binding (`^30`, `^(30,15)`,
`^(n,15)`) fixes that axis for every draw of the parameter. The probe
route already drew a binding's fixed size before this branch; its three
tests here are regression guards. The branch's own fixes are the
others: the built-in battery's call draws the fixed shape, the
companion a proof spawns draws it, a marker-named axis (`Vec("n")`)
takes the size a binding fixes on every route, and one name fixed to
two sizes by two bindings is a conflict, not a draw outside both."""
import importlib.util
import textwrap

import pytest

import mathema
from mathema.analysis import analyze_source
from mathema.conjecture import check_conjectures, claim
from mathema.probing import probe


def _battery(fn, text):
    """The built-in battery's probes for `fn` over the claim's bindings:
    the `callable` row is present only when the call could not be
    made."""
    return probe(fn, analyze_source(fn), domain=claim(text).domain)

np = pytest.importorskip("numpy")

_MODULE = '''
import numpy as np

from mathema.types import Vec

SEEN = []


def trace_sq(A: np.ndarray) -> float:
    """Trace of A A^T; records the shape it was called with."""
    SEEN.append(tuple(np.shape(A)))
    return float(np.trace(A @ A.T))


def total(xs: list) -> float:
    """Sum; records the length it was called with."""
    SEEN.append((len(xs),))
    return sum(xs)


def entries(A: np.ndarray) -> float:
    """Sum of every entry; records the shape it was called with."""
    SEEN.append(tuple(np.shape(A)))
    return float(A.sum())


def gram_trace(A: np.ndarray) -> float:
    """Trace of A A^T, liftable to the matrix algebra."""
    return float(np.trace(A @ A.T))


def total_marked(xs: Vec("n")) -> float:
    """Sum; the marker names the axis."""
    SEEN.append((len(xs),))
    return sum(xs)


def two(a: Vec("n"), b: Vec("n")) -> float:
    """Sum of both; the marker says they agree."""
    SEEN.append((len(a), len(b)))
    return sum(a) + sum(b)
'''


@pytest.fixture()
def mod(tmp_path):
    p = tmp_path / "fixed_shapes_mod.py"
    p.write_text(textwrap.dedent(_MODULE))
    spec = importlib.util.spec_from_file_location("fixed_shapes_mod", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_a_fixed_matrix_shape_is_drawn_on_the_probe(mod):
    (p,) = check_conjectures(mod.trace_sq, [claim(
        "for A in R^(30,15), f(A) >= 0", route="probe")])
    assert p.verdict == "holds", (p.verdict, p.note)
    assert p.n > 0
    assert set(mod.SEEN) == {(30, 15)}, sorted(set(mod.SEEN))


def test_a_fixed_length_is_drawn_on_the_probe(mod):
    (p,) = check_conjectures(mod.total, [claim(
        "for xs in [0, 1]^30, f(xs) >= 0", route="probe")])
    assert p.verdict == "holds", (p.verdict, p.note)
    assert set(mod.SEEN) == {(30,)}, sorted(set(mod.SEEN))


def test_a_fixed_axis_and_a_shared_name_mix_in_one_binding(mod):
    (p,) = check_conjectures(mod.entries, [claim(
        "for A in R^(n,15), f(A) == f(A)", route="probe")])
    assert p.verdict == "holds", (p.verdict, p.note)
    shapes = set(mod.SEEN)
    assert all(len(s) == 2 and s[1] == 15 for s in shapes), sorted(shapes)
    assert len({s[0] for s in shapes}) > 1, sorted(shapes)


def test_the_callable_probe_builds_the_fixed_shape(mod):
    probes = _battery(mod.trace_sq, "for A in R^(30,15), f(A) >= 0")
    assert not [p.note for p in probes if p.name == "callable"]
    assert set(mod.SEEN) == {(30, 15)}, sorted(set(mod.SEEN))


def test_the_callable_probe_builds_the_fixed_length(mod):
    probes = _battery(mod.total, "for xs in [0, 1]^30, f(xs) >= 0")
    assert not [p.note for p in probes if p.name == "callable"]
    assert set(mod.SEEN) == {(30,)}, sorted(set(mod.SEEN))


@pytest.mark.needs_full_proof_budget
def test_the_companion_a_proof_spawns_draws_the_fixed_shape(mod):
    rec = mathema.check(mod.gram_trace,
                        claims=["for A in [-1, 1]^(30,15), f(A) >= 0"])
    by_name = {p.name: p for p in rec.probes}
    parent = by_name["f_a_ge_0"]
    assert parent.verdict == "proven", (parent.verdict, parent.note)
    (companion,) = [p for name, p in by_name.items()
                    if name.startswith("f_a_ge_0[")]
    # the corners and the sampled interior points are all 30 by 15, so
    # the trace of A A^T is a finite non-negative number at every one
    assert companion.verdict == "holds", (companion.verdict,
                                          companion.counterexample,
                                          companion.sketch)
    assert companion.n > 0


def test_a_marker_named_axis_takes_the_bindings_fixed_size(mod):
    text = "for xs in [0, 1]^30, f(xs) >= 0"
    (p,) = check_conjectures(mod.total_marked, [claim(text, route="probe")])
    assert p.verdict == "holds", (p.verdict, p.note)
    assert set(mod.SEEN) == {(30,)}, sorted(set(mod.SEEN))
    assert "len=30" in p.meta["mathema.sampling"], p.meta["mathema.sampling"]
    mod.SEEN.clear()
    probes = _battery(mod.total_marked, text)
    assert not [q.note for q in probes if q.name == "callable"]
    assert set(mod.SEEN) == {(30,)}, sorted(set(mod.SEEN))
    mod.SEEN.clear()
    rec = mathema.check(mod.total_marked, claims=[text])
    assert set(mod.SEEN) == {(30,)}, sorted(set(mod.SEEN))
    # a policy row is what `sum` does with a null slot, a question of its
    # own; every draw it made is still at the fixed length
    shape_rows = [q for q in rec.probes if "mathema.policy" not in (q.meta or {})]
    assert not [q.name for q in shape_rows if q.verdict == "falsified"], [
        (q.name, q.counterexample) for q in shape_rows if q.verdict == "falsified"]


def test_the_guard_never_rejects_the_engines_own_draws():
    from mathema import claims_decorator, enforce_dimensions
    from mathema.types import Vec

    @enforce_dimensions()
    @claims_decorator("for xs in [0, 1]^30, f(xs) >= 0")
    def total_guarded(xs: Vec("n")) -> float:
        """Sum; the marker names the axis, the binding fixes it."""
        return sum(xs)

    rec = mathema.check(total_guarded)
    # no row falls to the guard's own error, and the battery's call is
    # made; a suggested row may still be false on its own merits
    by_guard = [(q.name, q.counterexample) for q in rec.probes
                if "DimensionError" in (q.counterexample or "")]
    assert not by_guard, by_guard
    assert not [q.note for q in rec.probes if q.name == "callable"]
    (declared,) = [q for q in rec.probes if q.name == "f_xs_ge_0"]
    assert declared.verdict in ("proven", "holds"), (declared.verdict, declared.note)


def test_one_shared_name_fixed_to_two_sizes_is_a_conflict(mod):
    from mathema import claims_decorator, enforce_dimensions
    from mathema.authoring import DomainError
    from mathema.types import Vec
    text = "for a in [0, 1]^30, b in [0, 1]^15, f(a, b) >= 0"
    (p,) = check_conjectures(mod.two, [claim(text, route="probe")])
    assert p.verdict == "skipped", (p.verdict, p.note)
    assert p.meta.get("mathema.premise") == "dimension-conflict", p.meta
    for word in ("n", "30", "15"):
        assert word in (p.note or ""), p.note
    assert not mod.SEEN, mod.SEEN
    with pytest.raises(DomainError) as err:
        @enforce_dimensions()
        @claims_decorator(text)
        def two(a: Vec("n"), b: Vec("n")) -> float:
            return sum(a) + sum(b)
    for word in ("n", "30", "15"):
        assert word in str(err.value), str(err.value)
