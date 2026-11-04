# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A container is never its element. A vector of one element against a
number is a different shape, so the claim is falsified, with the two
values as the witness, and the note offers the spellings that compare
what the user meant: the element, `f(a)["x"][0]`, or the whole,
`[sum(a.x)]`. A spelling is offered, with the claim's own domain, only
when it holds there; otherwise the note states the mismatch and offers
nothing. pandas and polars read alike, since both answer a one-row table
with a vector of one element per column."""
import numpy as np
import pytest

pd = pytest.importorskip("pandas")
pl = pytest.importorskip("polars")

from mathema.conjecture import check_conjectures, claim  # noqa: E402
from mathema._missing_words import remedy_statements  # noqa: E402

_OVER = "for a in [1, 100]^n \\ {missing}, "


def polars_sums(a: pl.DataFrame):
    return a.select("x").sum()


def pandas_one_row(a: pd.DataFrame):
    return pd.DataFrame({"x": [float(a["x"].sum())]})


def pandas_series_sums(a: pd.DataFrame):
    return a.sum()


def no_table_pandas(n: int) -> pd.DataFrame:
    return pd.DataFrame({"qty": [float(n)]})


def no_table_polars(n: int) -> pl.DataFrame:
    return pl.DataFrame({"qty": [float(n)]})


def series_pandas(n: int) -> pd.Series:
    return pd.Series([float(n)])


def series_polars(n: int) -> pl.Series:
    return pl.Series([float(n)])


def one_element_list(n: int) -> list:
    return [float(n)]


def _plain_miss(x: float) -> float:
    return x


def _probe(fn, law):
    (probe,) = check_conjectures(fn, [claim(law, name="c")])
    return probe


def _verdict(fn, law):
    return _probe(fn, law).verdict


@pytest.mark.parametrize("fn", [polars_sums, pandas_one_row])
def test_a_one_row_reduction_against_the_sum_is_a_mismatch(fn):
    probe = _probe(fn, _OVER + 'f(a)["x"] ~= sum(a.x)')
    assert probe.verdict == "falsified", (probe.verdict, probe.note)
    witness = str(probe.counterexample)
    assert "] vs " in witness, witness


@pytest.mark.parametrize("fn", [polars_sums, pandas_one_row])
def test_the_witness_offers_the_spellings_that_hold(fn):
    probe = _probe(fn, _OVER + 'f(a)["x"] ~= sum(a.x)')
    offered = remedy_statements(probe.note)
    assert _OVER + 'f(a)["x"][0] ~= sum(a.x)' in offered, probe.note
    assert _OVER + 'f(a)["x"] ~= [sum(a.x)]' in offered, probe.note


@pytest.mark.parametrize("fn", [polars_sums, pandas_one_row])
@pytest.mark.parametrize("law", ['f(a)["x"][0] ~= sum(a.x)',
                                 'f(a)["x"] ~= [sum(a.x)]'])
def test_the_offered_spellings_hold(fn, law):
    assert _verdict(fn, _OVER + law) in ("holds", "proven")


def test_a_pandas_series_reduction_is_a_number_per_column():
    assert _verdict(pandas_series_sums, _OVER + 'f(a)["x"] ~= sum(a.x)') in (
        "holds", "proven")


@pytest.mark.parametrize("fn", [no_table_pandas, no_table_polars])
def test_a_one_row_frame_from_any_function_reads_alike(fn):
    probe = _probe(fn, 'for n in {1, 2, 3}, f(n)["qty"] == n')
    assert probe.verdict == "falsified", (probe.verdict, probe.note)
    assert "] vs " in str(probe.counterexample), probe.counterexample
    offered = remedy_statements(probe.note)
    assert 'for n in {1, 2, 3}, f(n)["qty"][0] == n' in offered, probe.note
    assert 'for n in {1, 2, 3}, f(n)["qty"] == [n]' in offered, probe.note
    assert _verdict(fn, 'for n in {1, 2, 3}, f(n)["qty"] == [n]') in ("holds", "proven")
    assert _verdict(fn, 'for n in {1, 2, 3}, f(n)["qty"][0] == n') in ("holds", "proven")


@pytest.mark.parametrize("fn", [series_pandas, series_polars, one_element_list])
def test_a_vector_of_one_element_is_not_the_element_on_any_library(fn):
    assert _verdict(fn, "for n in {1, 2, 3}, f(n) == n") == "falsified"
    assert _verdict(fn, "for n in {1, 2, 3}, f(n) == [n]") in ("holds", "proven")
    assert _verdict(fn, "for n in {1, 2, 3}, f(n)[0] == n") in ("holds", "proven")


def test_the_finite_sweep_offers_the_spellings_too():
    probe = _probe(one_element_list, "for n in {1, 2, 3}, f(n) == n")
    assert probe.route.startswith("derive"), probe.route
    offered = remedy_statements(probe.note)
    assert "for n in {1, 2, 3}, f(n)[0] == n" in offered, probe.note
    assert "for n in {1, 2, 3}, f(n) == [n]" in offered, probe.note


def test_no_one_row_reading_remains():
    from mathema import probing
    from mathema.runtime_types import _abstract
    assert not hasattr(_abstract, "OneRowColumn")
    assert not hasattr(probing, "_one_element_series")
    assert probing.plain_value(pl.Series([3.0])) == [3.0]
    assert probing.plain_value(pd.Series([3.0])) == [3.0]


def one_true(n: int) -> list:
    return [True]


def one_word(n: int) -> list:
    return ["a"]


@pytest.mark.parametrize("fn,written", [(one_true, "True"), (one_word, "'a'")])
def test_a_bool_or_a_word_is_offered_the_same_spellings(fn, written):
    law = f"for n in {{1, 2}}, f(n) == {written}"
    probe = _probe(fn, law)
    assert probe.verdict == "falsified", (probe.verdict, probe.note)
    offered = remedy_statements(probe.note)
    assert f"for n in {{1, 2}}, f(n)[0] == {written}" in offered, probe.note
    assert f"for n in {{1, 2}}, f(n) == [{written}]" in offered, probe.note
    assert _verdict(fn, f"for n in {{1, 2}}, f(n)[0] == {written}") in (
        "holds", "proven")
    assert _verdict(fn, f"for n in {{1, 2}}, f(n) == [{written}]") in (
        "holds", "proven")


def zeros(x: list):
    return [0.0 for _ in x]


def nested(x: float):
    return np.array([[378.0]])


def labelled(x: float) -> pd.Series:
    return pd.Series([378.0], index=["a"])


def one(x: float):
    return [378.0]


def test_a_spelling_that_does_not_hold_is_not_offered():
    probe = _probe(zeros, "for x in [0,1]^n, f(x) == 0")
    assert probe.verdict == "falsified"
    offered = remedy_statements(probe.note)
    assert offered == ["for x in [0,1]^n, f(x)[0] == 0"], probe.note


@pytest.mark.parametrize("fn,law", [
    (nested, "for x in [0,1], f(x) == 378.0"),
    (nested, "for x in [0,1], f(x) == 379.0"),
])
def test_with_no_spelling_that_holds_the_note_offers_nothing(fn, law):
    probe = _probe(fn, law)
    assert probe.verdict == "falsified"
    assert remedy_statements(probe.note or "") == [], probe.note


def test_a_labelled_series_is_offered_only_what_holds():
    probe = _probe(labelled, "for x in [0,1], f(x) == 378.0")
    assert probe.verdict == "falsified"
    for text in remedy_statements(probe.note or ""):
        assert _verdict(labelled, text) in ("holds", "proven"), text


def test_a_ground_claim_is_offered_the_spellings():
    probe = _probe(one, "f(1.0) == 378.0")
    assert probe.verdict == "falsified"
    offered = remedy_statements(probe.note)
    assert "f(1.0)[0] == 378.0" in offered, probe.note
    assert "f(1.0) == [378.0]" in offered, probe.note


def test_the_offers_show_where_a_record_is_read():
    import mathema
    record = mathema.check(one, claims=[mathema.claim(
        "f(1.0) == 378.0", name="c")])
    assert "write: f(1.0)[0] == 378.0" in str(record), str(record)


def test_every_offer_holds_when_written():
    for fn, law in [(polars_sums, _OVER + 'f(a)["x"] ~= sum(a.x)'),
                    (one_element_list, "for n in {1, 2, 3}, f(n) == n"),
                    (one, "f(1.0) == 378.0")]:
        offered = remedy_statements(_probe(fn, law).note)
        assert offered
        for text in offered:
            assert _verdict(fn, text) in ("holds", "proven"), text


def test_a_claim_with_no_offer_runs_no_second_check(monkeypatch):
    from mathema import conjecture
    runs = []
    run = conjecture._check_conjectures

    def counted(*args, **kwargs):
        runs.append(args[1][0].raw)
        return run(*args, **kwargs)

    monkeypatch.setattr(conjecture, "_check_conjectures", counted)
    check_conjectures(_plain_miss, [claim("for x in {1, 2}, f(x) == 5", name="c")])
    assert len(runs) == 1, runs
    runs.clear()
    check_conjectures(one, [claim("f(1.0) == 378.0", name="c")])
    assert len(runs) == 3, runs
