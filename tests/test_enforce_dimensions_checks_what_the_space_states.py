# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`@enforce_dimensions` declares `excluded_outside_domain` proven by
construction, so its guard checks everything the claim's space states:
the rank, every fixed size and every element. `R^(30,15)` is thirty by
fifteen real numbers, so an imaginary entry, an infinite entry and a
text entry are outside it however the shape reads, and `[0, 1]^(3,2)`
holds no entry above one. A table of the stated rows and numeric
columns is the matrix it holds."""
import pytest

import mathema
from mathema.authoring import DimensionError, enforce_dimensions
from mathema import claims_decorator

np = pytest.importorskip("numpy")
pd = pytest.importorskip("pandas")


@enforce_dimensions()
@claims_decorator("for A in R^(30,15), f(A) >= 0")
def frob(A: np.ndarray) -> float:
    return float(np.square(np.asarray(A, dtype=float)).sum())


@enforce_dimensions()
@claims_decorator("for P in [0, 1]^(3,2), f(P) >= 0")
def mass(P: np.ndarray) -> float:
    return float(np.asarray(P, dtype=float).sum())


@pytest.mark.parametrize("value", [
    1j * np.ones((30, 15)),
    np.full((30, 15), np.inf),
    np.full((30, 15), -np.inf),
    np.array([["a"] * 15] * 30),
    np.full((30, 15), "x", dtype=object),
    [[True] * 15] * 30,
    [["1.0"] * 15] * 30,
], ids=["imaginary", "inf", "-inf", "text", "object-text", "bool", "str-list"])
def test_an_entry_outside_the_reals_is_rejected(value):
    with pytest.raises(DimensionError):
        frob(value)


def test_one_bad_entry_among_good_ones_is_rejected():
    a = np.ones((30, 15), dtype=complex)
    a[7, 3] = 2 + 1j
    with pytest.raises(DimensionError):
        frob(a)
    b = np.ones((30, 15))
    b[29, 14] = np.inf
    with pytest.raises(DimensionError):
        frob(b)


@pytest.mark.parametrize("value", [
    np.ones((30, 15)),
    np.ones((30, 15), dtype=np.float32),
    np.ones((30, 15), dtype=complex),
    np.ones((30, 15)).astype(object),
    np.ones((30, 15), dtype=int),
    [[1.0] * 15] * 30,
    pd.DataFrame(np.ones((30, 15))),
], ids=["float", "float32", "real-complex", "object-real", "int", "list",
        "dataframe"])
def test_a_value_inside_the_space_passes(value):
    assert frob(value) == 450.0


def test_a_wrong_shape_is_still_rejected():
    for bad in (np.ones((31, 15)), np.ones((15, 30)), np.ones(450),
                pd.DataFrame(np.ones((31, 15)))):
        with pytest.raises(DimensionError):
            frob(bad)


def test_an_entry_outside_the_element_interval_is_rejected():
    with pytest.raises(DimensionError):
        mass([[0.5, 0.5], [0.5, 2.0], [0.0, 1.0]])
    assert mass([[0.5, 0.5], [0.5, 1.0], [0.0, 1.0]]) == 3.5


def test_the_exclusion_stays_proven():
    rec = mathema.check(frob)
    row = next(p for p in rec.probes
               if p.name.startswith("excluded_outside_domain"))
    assert row.verdict == "proven", (row.verdict, row.note)
