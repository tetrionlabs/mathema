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
import pytest

pytest.importorskip("numpy")
pytest.importorskip("pandas")
pytest.importorskip("polars")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import polars as pl  # noqa: E402

import mathema  # noqa: E402
from mathema.claims import check_conjectures, claim  # noqa: E402
from mathema.gates import companion_descriptor  # noqa: E402
from mathema.types import Vec  # noqa: E402

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
    p = _verdict(series_mean, "for xs in R^n, f(xs) <= max(xs)")
    assert "as pandas.Series" in p.meta["mathema.sampling"], p.meta


def test_the_list_sampling_note_states_the_nested_list_cap():
    def trace(A):
        return sum(A[i][i] for i in range(len(A)))
    p = _verdict(trace, "for A in R^(n,n), f(A) == f(A)")
    assert "as nested lists, at most 64 per axis" in \
        p.meta["mathema.sampling"], p.meta


def test_an_undeclared_vector_is_sampled_as_a_list_and_hinted():
    hint = ("returns is used as a vector; this module imports pandas: "
            "to sample it as one, annotate: returns: pd.Series")
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
    assert "annotate: returns: pd.Series" in row.note


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


def array_total(xs: np.ndarray):
    total = 0.0
    for v in xs:
        total += v * v
    return total


def test_the_companion_descriptor_names_the_runtime_type():
    rows = check_conjectures(
        array_total, [claim("for xs in [-1, 1]^n, f(xs) >= 0",
                            name="total", route="derive")],
        float_companions=True)
    companions = [p for p in rows if p.name.startswith("total[")]
    assert companions, [(p.name, p.verdict, p.note) for p in rows]
    for c in companions:
        assert companion_descriptor(c.name) == ("float", "numpy.ndarray")
        assert c.verdict == "holds", (c.verdict, c.note)


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
    # the mean of no data is no value, stated as the empty input's policy
    rec = mathema.check(untyped_mean, claims=[_BETWEEN, "f([]) in {missing}"],
                        declared={"runtime_types": {"xs": "pandas.Series"}})
    row = next(p for p in rec.probes if p.statement.startswith("for xs"))
    assert row.verdict in ("holds", "proven"), (row.verdict, row.note)
    assert rec.facts.runtime_types["xs"][0].evidence == \
        "claims file: pandas.Series"


def test_the_cli_prints_the_hint_under_the_function(tmp_path, capsys):
    from mathema.cli import main
    (tmp_path / "quant_hint.py").write_text(
        "import pandas as pd\n\n\n"
        "def mean_return(returns):\n"
        "    return returns.mean()\n")
    main(["check", str(tmp_path / "quant_hint.py"), "--root", str(tmp_path),
          "--claim", "for returns in R^n, f(returns) <= max(returns)"])
    out = capsys.readouterr().out
    assert ("hint: returns is used as a vector; this module imports "
            "pandas: to sample it as one, annotate: returns: pd.Series") \
        in out, out


@pytest.mark.parametrize("fn", [mean_of, series_mean, polars_mean])
def test_a_law_transform_acts_on_the_drawn_value_before_it_is_realised(fn):
    p = _verdict(fn, "for xs in [-1, 1]^n, let c be [0.1, 10], "
                     "f(g(xs, c)) ~= c*f(xs)",
                 funcs={"g": "mathema.f.scale_seq"})
    assert p.verdict == "holds", (p.verdict, p.note, p.counterexample)
