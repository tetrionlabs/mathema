# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Claims about functions whose parameters are numpy arrays, pandas or
polars objects are adjudicated against those objects.

The claim draws its values as always; each call of the function
realises them as the parameter's runtime type, and what the function
returns is observed as a plain value before the claim compares it. A
parameter the body uses as a vector while the signature names no
runtime type is still sampled as a list, and the record says which
runtime type to annotate; a list the function cannot use is then
`skipped:misspecified`, never `falsified`. A raise on a declared
runtime type falsifies as always.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import polars as pl
import pytest

import mathema
from mathema.claims import check_conjectures, claim
from mathema.gates import companion_descriptor
from mathema.types import Vec

_BETWEEN = "for xs in R^n, min(xs) <= f(xs) <= max(xs)"


def mean_of(xs: np.ndarray):
    return float(xs.mean())


def series_mean(xs: pd.Series):
    return float(xs.mean())


def polars_mean(xs: pl.Series):
    return float(xs.mean())


def marked_mean(xs: Vec("n", runtime="pandas.Series")):
    return float(xs.mean())


def transpose(A: np.ndarray):
    return A.T


def unannotated_mean(returns):
    return returns.mean()


def first_is_one(xs: np.ndarray):
    if xs[0] > 0:
        raise ValueError("positive first value")
    return 1.0


def _verdict(fn, law, **kw):
    (p,) = check_conjectures(fn, [claim(law, route="probe", **kw)])
    return p


@pytest.mark.parametrize("fn", [mean_of, series_mean, polars_mean,
                                marked_mean])
def test_a_mean_lies_between_the_extremes_whatever_the_runtime_type(fn):
    p = _verdict(fn, _BETWEEN)
    assert p.verdict == "holds", (p.verdict, p.note, p.counterexample)


def test_numpy_transpose_is_an_involution():
    p = _verdict(transpose, "for A in R^(n,n), f(f(A)) == A")
    assert p.verdict == "holds", (p.verdict, p.note, p.counterexample)


def test_a_raise_on_a_declared_runtime_type_falsifies():
    p = _verdict(first_is_one, "for xs in R^n, f(xs) == 1")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "ValueError" in p.counterexample


def test_the_sampling_note_names_the_runtime_type():
    p = _verdict(series_mean, _BETWEEN)
    assert "as pandas.Series" in p.meta["mathema.sampling"], p.meta


def test_the_list_sampling_note_states_the_nested_list_cap():
    def trace(A):
        return sum(A[i][i] for i in range(len(A)))
    p = _verdict(trace, "for A in R^(n,n), f(A) == f(A)")
    assert "as nested lists, at most 64 per axis" in \
        p.meta["mathema.sampling"], p.meta


def test_an_undeclared_vector_is_sampled_as_a_list_and_hinted():
    hint = ("returns is used as a vector; this module imports pandas: "
            "annotate `returns: pd.Series` to sample it as one")
    facts = mathema.analyze(unannotated_mean)
    assert facts.runtime_hints["returns"]["text"] == hint
    p = _verdict(unannotated_mean, "for returns in R^n, f(returns) == "
                                   "f(returns)")
    assert p.verdict == "skipped:misspecified", (p.verdict, p.note)
    assert hint in p.note, p.note


def test_the_hint_rides_every_claim_row_of_the_function():
    rec = mathema.check(unannotated_mean,
                        claims=["for returns in R^n, f(returns) == "
                                "f(returns)"])
    row = next(p for p in rec.probes if p.statement.endswith("f(returns)"))
    assert "annotate `returns: pd.Series`" in row.note


def test_the_record_identity_names_the_runtime_type_and_its_library():
    from mathema.spec import to_spec
    rec = mathema.check(series_mean, claims=[_BETWEEN])
    identity = to_spec(rec)["identity"]
    assert identity["runtime_types"] == {"xs": {
        "type": "pandas.Series", "evidence": "annotation: pandas.Series",
        "library": f"pandas=={pd.__version__}"}}


def test_a_list_function_record_states_no_runtime_types():
    from mathema.spec import to_spec

    def total(xs: list) -> float:
        return sum(xs)
    rec = mathema.check(total, claims=["f(xs) == f(xs)"])
    assert "runtime_types" not in to_spec(rec)["identity"]


def test_the_companion_descriptor_names_the_runtime_type():
    def scaled_sum(xs: pd.Series):
        return float((2 * xs).sum())
    rows = check_conjectures(
        scaled_sum, [claim("for xs in [-1, 1]^n, f(xs) == 2*sum(xs)",
                           route="derive")], float_companions=True)
    companions = [p for p in rows if (p.meta or {}).get(
        "mathema.companion_of")]
    for c in companions:
        assert companion_descriptor(c.name) == ("float", "pandas.Series")


def test_a_claims_file_names_a_runtime_type_for_code_it_cannot_annotate():
    from mathema.spec import ClaimsFileError, validate_claims_file

    def untyped_mean(xs):
        return float(xs.mean())
    validate_claims_file({"m.untyped_mean": {
        "runtime_types": {"xs": "pandas.Series"},
        "claims": [{"statement": _BETWEEN}]}}, "c.claims.yaml")
    with pytest.raises(ClaimsFileError, match="runtime_types"):
        validate_claims_file({"m.f": {"runtime_types": {"xs": "pandas.Serie"}}},
                             "c.claims.yaml")
    rec = mathema.check(untyped_mean, claims=[_BETWEEN],
                        declared={"runtime_types": {"xs": "pandas.Series"}})
    row = next(p for p in rec.probes if p.statement.startswith("for xs"))
    assert row.verdict in ("holds", "proven"), (row.verdict, row.note)
    assert rec.facts.runtime_types["xs"][0].evidence == \
        "claims file: pandas.Series"
