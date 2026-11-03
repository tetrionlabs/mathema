# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A container is never its element. A vector of one element against a
number is a different shape, so the claim is falsified, with the two
values as the witness, and the note offers the spellings that compare
what the user meant: the element, `f(a)["x"][0]`, or the whole,
`[sum(a.x)]`. pandas and polars read alike, since both answer a
one-row table with a vector of one element per column."""
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
    words = f"{probe.counterexample}\n{probe.note}"
    offered = remedy_statements(words)
    assert 'f(a)["x"][0] ~= sum(a.x)' in offered, words
    assert 'f(a)["x"] ~= [sum(a.x)]' in offered, words


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
    offered = remedy_statements(
        f"{probe.counterexample}\n{probe.sketch}\n{probe.note}")
    assert 'f(n)["qty"][0] == n' in offered, offered
    assert 'f(n)["qty"] == [n]' in offered, offered
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
    offered = remedy_statements(f"{probe.counterexample}\n{probe.sketch}\n{probe.note}")
    assert "f(n)[0] == n" in offered, offered
    assert "f(n) == [n]" in offered, offered


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
    offered = remedy_statements(
        f"{probe.counterexample}\n{probe.sketch}\n{probe.note}")
    assert f"f(n)[0] == {written}" in offered, offered
    assert f"f(n) == [{written}]" in offered, offered
    assert _verdict(fn, f"for n in {{1, 2}}, f(n)[0] == {written}") in (
        "holds", "proven")
    assert _verdict(fn, f"for n in {{1, 2}}, f(n) == [{written}]") in (
        "holds", "proven")
