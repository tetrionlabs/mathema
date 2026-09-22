# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The matrix-property registry: each property checks a value, builds
one that has it, and entails the weaker properties it implies. Checks
are numpy-fast when numpy is present and degrade honestly without it,
element-wise/structural checks in pure Python, spectral ones declining
(None) rather than guessing."""
import random

import pytest

from mathema.matrices import PROPERTIES, entailed


@pytest.mark.parametrize("name", sorted(PROPERTIES))
def test_synth_output_passes_its_own_check(name):
    p = PROPERTIES[name]
    rng = random.Random(name)     # per-property seed, deterministic
    for n in range(1, 7):
        m = p.synth(n, rng)
        assert p.check(m) is True, (name, n, m)


def test_negative_examples_reject():
    assert PROPERTIES["is_symmetric"].check([[1, 2], [3, 4]]) is False
    assert PROPERTIES["is_finite"].check([[1.0, float("nan")]]) is False
    assert PROPERTIES["is_finite"].check([[1.0, float("inf")]]) is False
    assert PROPERTIES["is_upper_triangular"].check([[1, 0], [2, 1]]) is False
    assert PROPERTIES["is_identity"].check([[1, 0], [0, 2]]) is False
    assert PROPERTIES["is_positive_definite"].check([[1, 0], [0, -1]]) is False


def test_a_non_square_value_is_undecidable_for_a_square_property():
    assert PROPERTIES["is_symmetric"].check([[1, 2, 3], [4, 5, 6]]) is None
    assert PROPERTIES["is_positive_definite"].check([[1, 2, 3]]) is None


def test_entailment_closes_transitively():
    assert entailed(["is_positive_definite"]) == {
        "is_positive_definite", "is_positive_semidefinite", "is_symmetric"}
    ident = entailed(["is_identity"])
    assert {"is_diagonal", "is_symmetric", "is_orthogonal",
            "is_positive_definite", "is_upper_triangular",
            "is_lower_triangular"} <= ident
    assert entailed(["is_symmetric"]) == {"is_symmetric"}


def test_the_hierarchy_levels_are_the_documented_taxonomy():
    levels = {p.level for p in PROPERTIES.values()}
    assert levels == {"finite", "elementwise", "structural",
                      "spectral", "quadratic-form"}


def test_checks_degrade_without_numpy(monkeypatch):
    import mathema.matrices as M

    monkeypatch.setattr(M, "_numpy", lambda: None)
    rng = random.Random(0)
    # element-wise and structural checks still work in pure Python
    for name in ("is_finite", "is_symmetric", "is_upper_triangular",
                 "is_diagonal", "is_identity", "is_lower_triangular",
                 "is_skew_symmetric"):
        p = M.PROPERTIES[name]
        assert p.check(p.synth(3, rng)) is True, name
    # spectral checks decline rather than compute an unsound answer
    for name in ("is_orthogonal", "is_positive_definite",
                 "is_positive_semidefinite"):
        p = M.PROPERTIES[name]
        assert p.check(p.synth(3, rng)) is None, name


def test_positive_definite_needs_symmetry():
    # a non-symmetric matrix is never positive-definite by mathema's
    # definition (PD is a property of symmetric matrices)
    assert PROPERTIES["is_positive_definite"].check([[1, 2], [0, 1]]) is False


def test_structure_markers_are_generated_from_the_registry():
    from mathema.types import PositiveDefinite, Structure, Symmetric
    assert Symmetric().prop == "is_symmetric"
    assert PositiveDefinite().prop == "is_positive_definite"
    assert issubclass(PositiveDefinite, Structure)


def test_synth_for_satisfies_the_whole_declared_set():
    import random

    from mathema.matrices import PROPERTIES, entailed, synth_for
    rng = random.Random(1)
    for decl in (["is_symmetric"], ["is_positive_definite"],
                 ["is_upper_triangular"], ["is_identity"], ["is_diagonal"]):
        full = sorted(entailed(decl))
        m = synth_for(full, 4, rng)
        assert all(PROPERTIES[p].check(m) is not False for p in full), (decl, m)
