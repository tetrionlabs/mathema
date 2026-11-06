# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The readings the linear algebra sweep is to give. An equality premise that
pins a whole vector or matrix is not read yet, and a size-one result in the
matrix algebra is not always told from a number. Each case states the reading
wanted, and fails strictly until the sweep lands, so it flips loudly then."""
from typing import Optional

import numpy as np
import pytest

from mathema.conjecture import check_conjectures, claim
from mathema.types import Mat

SWEEP = "held to the linear algebra sweep"


def echo(x: np.ndarray):
    return np.asarray(x, dtype=float)


def scal(x: float) -> float:
    return x + 1.0


def idl(x: list[float]):
    return x


def idot(x: list[float]) -> float:
    return sum(x)


def opt(x: Optional[list[float]]):
    return x


def opt_array(x: Optional[np.ndarray]):
    return x


def anyx(x):
    return x


def dot(xs: list[float], ys: list[float]) -> float:
    return sum(a * b for a, b in zip(xs, ys))


def det_of(A: np.ndarray) -> float:
    return float(np.linalg.det(np.asarray(A, dtype=float)))


def det_marked(A: Mat("n", "n")) -> float:
    return float(np.linalg.det(np.asarray(A, dtype=float)))


def m(A: Mat("n", "n")):
    return A


def rc(A: Mat("n", "m")):
    return A


def _probe(fn, law):
    (probe,) = check_conjectures(fn, [claim(law, name="c")])
    return probe


_HOLD = [
    # S1
    (idl, "assuming x == 0, for x in [0,5]^2 subset Z, f(x) == [0, 0]"),
    (idl, "assuming x == 0, for x in Z^2, f(x) == [0, 0]"),
    (idl, "assuming x == 0, for x in N^2, f(x) == [0, 0]"),
    (idl, "assuming x == 0, for x in [-5,5]^n subset Z, f(x)[0] == 0"),
    (idl, "assuming x == [1, 2], for x in [0,5]^2 subset Z, f(x) == [1, 2]"),
    # S2
    (opt, "assuming x == 0, for x in [0,1]^3 | {None}, f(x) == [0,0,0]"),
    (idl, "assuming x == 0, for x in [0,1]^3, f(x) == [0,0,0]"),
    (opt_array, "assuming x == 0, for x in [0,1]^3 | {None}, f(x) == [0,0,0]"),
    (anyx, "assuming x == 0, for x in [0,1]^2, f(x) == [0,0]"),
    (anyx, "assuming x == 0, for x in [0,1]^(2,2), f(x) == [[0,0],[0,0]]"),
    # F1 and R2
    (echo, "assuming x == 0, for x in [0,1]^3, f(x) == [0,0,0]"),
    (det_of, "assuming A == 0, for A in [0,1]^(n,n), f(A) == 0"),
    (det_marked, "assuming A == 0, f(A) == 0"),
    (m, "assuming A == 0, A @ A == A"),
    (m, "assuming A == 0, trace(A) == 0"),
    (m, "assuming A == 0, for A in R^(n,n), A @ A == A"),
    (dot, "assuming xs == [1,1,1], for xs in [-1,1]^n, ys in [-1,1]^n, "
          "f(xs, ys) == ys[0]+ys[1]+ys[2]"),
    # the zero and the literal the domain admits
    (echo, "assuming x == [1,1,1], for x in [0,1]^3, f(x) == [1,1,1]"),
]


@pytest.mark.xfail(strict=True, reason=SWEEP)
@pytest.mark.parametrize("fn,law", _HOLD, ids=lambda v: getattr(v, "__name__", v))
def test_a_pinned_container_holds_where_the_claim_does(fn, law):
    assert _probe(fn, law).verdict in ("holds", "proven")


@pytest.mark.xfail(strict=True, reason=SWEEP)
def test_a_false_claim_at_a_pinned_container_is_falsified():
    probe = _probe(idot, "assuming x == 0, for x in [0,1]^2 subset Z, f(x) == 1")
    assert probe.verdict == "falsified"


_NO_VALID_DOMAIN = [
    # S3
    (idl, "assuming x == ['a','b'], for x in [0,1]^2, f(x) == x"),
    (idl, "assuming x == [None, 1], for x in [0,1]^2, f(x) == x"),
    # R1
    (echo, "assuming x == 0, for x in [1,2]^3, f(x) == [0,0,0]"),
    (echo, "assuming x == [5,5,5], for x in [0,1]^3, f(x) == [5,5,5]"),
    (echo, "assuming x == [1,1], for x in [0,1]^3, f(x) == [1,1]"),
    (idl, "assuming x == 0, for x in {1,2}^2, f(x) == [5,5]"),
    (echo, "assuming x == 5, for x in [0,1]^3, f(x) == [5,5,5]"),
    (scal, "assuming x == [1,2], for x in [0,5], f(x) == 3"),
]


@pytest.mark.xfail(strict=True, reason=SWEEP)
@pytest.mark.parametrize("fn,law", _NO_VALID_DOMAIN,
                         ids=lambda v: getattr(v, "__name__", v))
def test_a_pin_the_domain_excludes_has_no_valid_domain(fn, law):
    probe = _probe(fn, law)
    assert probe.verdict == "unknown"
    assert "no valid domain" in probe.note, probe.note


@pytest.mark.xfail(strict=True, reason=SWEEP)
@pytest.mark.parametrize("fn,law", [
    (rc, "for A in R^(1,2), A @ A.T - A @ A.T == 0"),
    (rc, "for A in [0,1]^(2,1), A.T @ A - A.T @ A == 0"),
    (m, "for A in R^(1,1), I(1) - I(1) == 0"),
], ids=lambda v: getattr(v, "__name__", v))
def test_a_one_by_one_result_is_not_a_number(fn, law):
    assert _probe(fn, law).verdict == "falsified"


@pytest.mark.xfail(strict=True, reason=SWEEP)
def test_an_inverse_at_size_one_is_proven():
    probe = _probe(m, "assuming det(A) != 0, for A in R^(1,1), A @ inv(A) == I(1)")
    assert probe.verdict == "proven"
