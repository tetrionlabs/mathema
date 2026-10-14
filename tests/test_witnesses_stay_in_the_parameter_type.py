# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A witness lies inside each parameter's declared type. A `str`
parameter is called with strings, a `Vec` parameter with a vector and
a `Mat` parameter with a matrix, sized so shared dimension names
agree; a magnitude corner is a number, so it is only ever tried for a
number. A raise at an input outside the parameter's type says nothing
about the function, and is never a counterexample."""
import ast
import re

import numpy as np

from mathema import enforce_dimensions
from mathema.conjecture import check_conjectures, claim
from mathema.types import Mat, Vec


def ticker_exchange(symbol: str) -> str:
    return symbol.split(".")[1]


def portfolio_variance(weights: Vec("n"), cov: Mat("n", "n")) -> float:
    w = np.asarray(weights)
    return float(w @ np.asarray(cov) @ w)


def factor_exposure(weights: Vec("n"), betas: Mat("n", "k")) -> Vec("k"):
    return list(np.asarray(betas) @ np.asarray(weights))


@enforce_dimensions()
def guarded_variance(weights: Vec("n"), cov: Mat("n", "n")) -> float:
    w = np.asarray(weights)
    return float(w @ np.asarray(cov) @ w)


def _witness_values(counterexample: str) -> dict:
    """`name = value` pairs of a witness text, each value read as a
    Python literal."""
    head = counterexample.split(": f raised")[0]
    out = {}
    for name, text in re.findall(
            r"(\w+) = (.+?)(?=, \w+ = |$)", head):
        out[name] = ast.literal_eval(text)
    return out


def test_a_string_parameter_is_falsified_only_at_a_string():
    (p,) = check_conjectures(ticker_exchange, [claim("is_defined(f)")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    witness = _witness_values(p.counterexample)
    assert isinstance(witness["symbol"], str), p.counterexample
    assert "IndexError" in p.counterexample, p.counterexample


def test_a_vector_and_a_matrix_parameter_draw_a_vector_and_a_matrix():
    for fn in (portfolio_variance, guarded_variance):
        (p,) = check_conjectures(fn, [claim("is_defined(f)")])
        assert p.verdict == "holds", (fn.__name__, p.verdict,
                                      p.counterexample, p.note)


def test_a_shaped_witness_is_a_vector_and_a_matrix_sharing_n():
    # betas @ weights needs k == n: it raises at consistent shapes
    (p,) = check_conjectures(factor_exposure, [claim("is_defined(f)")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    witness = _witness_values(p.counterexample)
    weights, betas = witness["weights"], witness["betas"]
    assert all(isinstance(v, float) for v in weights), p.counterexample
    assert all(isinstance(row, list) for row in betas), p.counterexample
    assert len(betas) == len(weights), p.counterexample
