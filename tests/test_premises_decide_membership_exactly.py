# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A premise decides membership in the claim's domain exactly.

`assuming std(xs, ddof=1) > 0` excludes every constant sequence over R.
Float arithmetic leaves a residue near 1e-17 on a constant sequence, so a
premise evaluated in float would admit the point, and the computation
companion would then execute the code on an input the claim never
covered and blame the code for what happens there.
"""
import pytest

pytest.importorskip("numpy")
pytest.importorskip("pandas")

import math  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import mathema  # noqa: E402
from mathema._exact_premises import premise_functions  # noqa: E402
from mathema._linalg_eval import FUNCTIONS  # noqa: E402

pytestmark = pytest.mark.needs_full_proof_budget


def ratio(xs: pd.Series) -> float:
    return float(xs.mean() / xs.std(ddof=1))


def ratio_loop(xs: pd.Series) -> float:
    total = 0.0
    for v in xs:
        total += v
    return float(total / len(xs) / xs.std(ddof=1))


def _probes(fn, text, empty_policy=None):
    claims = [mathema.claim(text, name="c")]
    if empty_policy:
        # what f does with the empty input, stated as its policy
        claims.append(mathema.claim(empty_policy, name="empty"))
    r = mathema.check(fn, claims=claims)
    return {p.name: p for p in r.probes if p.name.startswith("c")}


def test_a_constant_sequence_has_exactly_zero_spread():
    exact = premise_functions(FUNCTIONS)
    xs = [-0.1, -0.1, -0.1]
    assert FUNCTIONS["std"](xs, ddof=1) == 0.0
    assert exact["std"](xs, ddof=1) == 0.0
    assert exact["var"](xs, ddof=1) == 0.0
    assert exact["mean"](xs) == -0.1
    assert exact["std"](pd.Series(xs), ddof=1) == 0.0


def test_the_exact_words_agree_with_the_float_words_where_both_are_defined():
    exact = premise_functions(FUNCTIONS)
    xs = [0.5, -1.25, 3.0, 2.0]
    for name in ("sum", "prod", "mean", "var", "std"):
        assert math.isclose(exact[name](xs), FUNCTIONS[name](xs), rel_tol=1e-12)
    assert math.isclose(exact["var"](xs, ddof=1), FUNCTIONS["var"](xs, ddof=1), rel_tol=1e-12)
    assert math.isclose(exact["dot"](xs, xs), FUNCTIONS["dot"](xs, xs), rel_tol=1e-12)


def test_the_exact_words_fall_back_outside_flat_real_sequences():
    exact = premise_functions(FUNCTIONS)
    A = np.array([[1.0, 2.0], [3.0, 4.0]])
    assert exact["sum"](A) == FUNCTIONS["sum"](A)
    assert list(exact["sum"](A, axis=0)) == list(FUNCTIONS["sum"](A, axis=0))
    assert math.isnan(exact["std"]([1.0], ddof=1))
    assert math.isnan(exact["mean"]([1.0, float("nan")]))


def test_a_positive_spread_premise_keeps_constant_corners_out_of_the_companion():
    probes = _probes(ratio, "for xs in [-0.1, 0.1]^n, "
                            "assuming std(xs, ddof=1) > 0, f(2 * xs) ~= f(xs)",
                     empty_policy="f([]) in {missing}")
    assert probes["c"].verdict == "proven"
    companion = probes["c[float, pandas.Series]"]
    assert companion.verdict == "holds", companion.counterexample
    # the varying interior points were still executed
    assert companion.n > 0


def test_the_companion_reads_vector_arithmetic_as_the_proof_does():
    # `xs + xs` doubles every element, never the list; the ratio of mean
    # to spread is unchanged, so a proven law must not be blamed on the code
    probes = _probes(ratio, "for xs in [-0.1, 0.1]^n, "
                            "assuming std(xs, ddof=1) > 0, f(xs + xs) ~= f(xs)",
                     empty_policy="f([]) in {missing}")
    assert probes["c"].verdict == "proven"
    companion = probes["c[float, pandas.Series]"]
    assert companion.verdict == "holds", companion.sketch


def test_the_probe_route_reads_the_same_premise():
    # an unliftable body keeps the claim on the probe route, where the
    # premise filters each draw; a constant draw is outside the domain
    # the premise has no value at the empty list, so it excludes it and
    # the claim has no empty-input line
    rows = mathema.check(ratio_loop, claims=[mathema.claim(
        "for xs in [-0.1, 0.1]^n, assuming std(xs, ddof=1) > 0, "
        "f(-xs) ~= -f(xs)", name="c")]).probes
    (main,) = [p for p in rows if p.name == "c"]
    assert main.verdict == "holds"
    assert main.route.startswith("probe")
    assert not any(p.name.startswith("is_empty_safe") for p in rows)
