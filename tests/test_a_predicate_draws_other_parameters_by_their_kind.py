# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A predicate claim (`is_symmetric(f(X))`, `is_symmetric(A)`,
`is_finite(f(x))`, `is_overflow_safe(x)`) calls f with every other
parameter drawn as its own kind: an `int` as an int, never a float. A
parameter with no annotation whose default is `None` is held at that
default (it is absent) unless the claim binds it; an annotated one is
drawn inside its type. A witness names only the arguments the claim
passes, at the values f received."""
import re
from typing import Optional

import pytest

from mathema.conjecture import check_conjectures, claim

np = pytest.importorskip("numpy")

pytestmark = pytest.mark.filterwarnings(
    "ignore::mathema.analysis.StateDependenceWarning")

_SEEN: list = []


def scaled_matrix(X, k: int = 5, discrete=None):
    _SEEN.append({"k": k, "discrete": discrete})
    return np.asarray(X, dtype=float) * k


def scaled_guard(A, k: int = 5, discrete=None):
    _SEEN.append({"k": k, "discrete": discrete})
    return np.asarray(A, dtype=float) * k


def scaled_value(x: float, k: int = 5, discrete=None,
                 scale: Optional[float] = None) -> float:
    _SEEN.append({"k": k, "discrete": discrete, "scale": scale})
    return x * k


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


@pytest.mark.parametrize("fn, law", [
    (scaled_matrix, "is_symmetric(f(X))"),
    (scaled_matrix, "is_symmetric(f(X, k))"),
    (scaled_guard, "is_symmetric(A)"),
    (scaled_value, "is_finite(f(x))"),
    (scaled_value, "is_overflow_safe(x)"),
], ids=["output", "output-k", "guard", "output-value", "region"])
def test_an_int_is_an_int_and_a_none_default_stays_absent(fn, law):
    _SEEN.clear()
    check_conjectures(fn, [claim(law)])
    assert _SEEN, law
    assert all(_is_int(s["k"]) for s in _SEEN), \
        [s["k"] for s in _SEEN if not _is_int(s["k"])][:3]
    assert all(s["discrete"] is None for s in _SEEN), \
        [s["discrete"] for s in _SEEN if s["discrete"] is not None][:3]


def test_an_annotated_none_default_is_drawn_inside_its_type():
    _SEEN.clear()
    check_conjectures(scaled_value, [claim("is_overflow_safe(x)")])
    drawn = [s["scale"] for s in _SEEN if s["scale"] is not None]
    assert drawn, "scale was never drawn"
    assert all(isinstance(v, (int, float)) for v in drawn), drawn[:3]


def test_a_none_default_the_claim_binds_is_drawn():
    _SEEN.clear()
    check_conjectures(scaled_value, [
        claim("for discrete in [1, 2], is_overflow_safe(x)")])
    drawn = [s["discrete"] for s in _SEEN if s["discrete"] is not None]
    assert drawn and all(1 <= v <= 2 for v in drawn), drawn[:3]


def test_the_witness_names_what_f_was_called_with():
    (p,) = check_conjectures(scaled_matrix, [claim("is_symmetric(f(X))")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    head = p.counterexample.split(":")[0]
    # k and discrete are not passed by `f(X)`: they take their defaults
    assert "discrete" not in head, p.counterexample
    assert "k =" not in head, p.counterexample

    (p,) = check_conjectures(scaled_matrix, [claim("is_symmetric(f(X, k))")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    head = p.counterexample.split(":")[0]
    assert re.search(r"\bk = -?\d+(,|$)", head), p.counterexample
    assert "discrete" not in head, p.counterexample
