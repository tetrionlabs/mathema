# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A literal dimension in a parameter's own binding (`^30`, `^(30,15)`,
`^(n,15)`) fixes that axis for every draw of the parameter: the probe,
the `callable` probe of the built-in battery, and the companion a proof
spawns. A shared name keeps unifying as before, and a fixed axis and a
shared name mix in one binding."""
import importlib.util
import textwrap

import pytest

import mathema
from mathema.conjecture import check_conjectures, claim

np = pytest.importorskip("numpy")

_MODULE = '''
import numpy as np

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
    rec = mathema.check(mod.trace_sq, claims=["for A in R^(30,15), f(A) >= 0"])
    # the battery reports the call only when it could not be made
    assert not [p.note for p in rec.probes if p.name == "callable"]
    assert set(mod.SEEN) == {(30, 15)}, sorted(set(mod.SEEN))


def test_the_callable_probe_builds_the_fixed_length(mod):
    mathema.check(mod.total, claims=["for xs in [0, 1]^30, f(xs) >= 0"])
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
