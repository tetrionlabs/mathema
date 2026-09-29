# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A binding without a type clause is completed from the parameter's
annotation: a `float` slot may hold its NaN hole, an `int`, `bool` or
`str` holds none, an `Optional[...]` may be absent, a list element may
be `null` or `nan`, a runtime type holds what its adapter and the
definition rows say. The record states the resolved members in
`meta["mathema.missing"]["admitted"]`, and a written clause wins over
the annotation with a note saying whether it widens or narrows it."""
import datetime
from typing import Annotated, Optional

import pytest

import mathema
from mathema.types import Probability, missing_policy_from_signature

np = pytest.importorskip("numpy")
npt = pytest.importorskip("numpy.typing")
pd = pytest.importorskip("pandas")
pl = pytest.importorskip("polars")


def signature(a: float, b: int, c: bool, d: str, e: Optional[float],
              g: "float | None", h: Optional[str], i: datetime.datetime,
              j: Annotated[float, Probability], k, lst: list,
              lf: list[float], li: list[int], arr: np.ndarray,
              af: npt.NDArray[np.float64], ai: npt.NDArray[np.int64],
              s: pd.Series, df: pd.DataFrame, ps: pl.Series,
              pdf: pl.DataFrame, oa: Optional[np.ndarray]):
    return 0.0


#: parameter, whether the object may be absent, the hole members
DEFAULTS = [
    ("a", False, ("nan",)),
    ("b", False, ()),
    ("c", False, ()),
    ("d", False, ()),
    ("e", True, ("nan",)),
    ("g", True, ("nan",)),
    ("h", True, ()),
    ("i", False, ("NaT",)),
    ("j", False, ()),
    ("k", True, ("nan",)),
    ("lst", False, ("null", "nan")),
    ("lf", False, ("nan",)),
    ("li", False, ()),
    ("arr", False, ("nan",)),
    ("af", False, ("nan",)),
    ("ai", False, ()),
    ("s", False, ("nan", "null", "NA", "NaT")),
    ("df", False, ("nan", "null", "NA")),
    ("ps", False, ("null", "nan")),
    ("pdf", False, ("null", "nan")),
    ("oa", True, ("nan",)),
]


@pytest.mark.parametrize("param, absent, members", DEFAULTS)
def test_the_annotation_states_the_default(param, absent, members):
    policy = missing_policy_from_signature(signature)[param]
    assert (policy.absent, policy.members) == (absent, members)


def plain(x: float) -> float:
    return 1.0


def optional(x: Optional[float]) -> float:
    return 1.0


def bare(x):
    return 1.0


def marked(x: Annotated[float, Probability]) -> float:
    return 1.0


def summed(xs: list) -> float:
    return 1.0


def summed_floats(xs: list[float]) -> float:
    return 1.0


def summed_ints(xs: list[int]) -> float:
    return 1.0


def array_mean(xs: np.ndarray) -> float:
    return 1.0


def int_array(xs: npt.NDArray[np.int64]) -> float:
    return 1.0


def optional_array(xs: Optional[np.ndarray]) -> float:
    return 1.0


def series_mean(xs: pd.Series) -> float:
    return 1.0


def polars_mean(xs: pl.Series) -> float:
    return 1.0


def run(fn, text: str):
    report = mathema.check(fn, claims=[mathema.claim(text, name="c")])
    return next(p for p in report.probes if p.name == "c")


@pytest.mark.parametrize("fn, text, statement, holes", [
    (plain, "for x in [0, 1], f(x) >= 0",
     "for x in [0.0, 1.0] : float|missing, f(x) >= 0", ("nan",)),
    (optional, "for x in [0, 1], f(x) >= 0",
     "for x in [0.0, 1.0] : float|absent|missing, f(x) >= 0", ("nan",)),
    (bare, "for x in [0, 1], f(x) >= 0",
     "for x in [0.0, 1.0] : float|absent|missing, f(x) >= 0",
     ("nan",)),
    (marked, "for x in [0, 1], f(x) >= 0",
     "for x in [0.0, 1.0] : float, f(x) >= 0", None),
    (summed, "for xs in [0, 1]^n, f(xs) >= 0",
     "for xs in ([0.0, 1.0] | {missing})^n : float, f(xs) >= 0",
     ("null", "nan")),
    (summed_floats, "for xs in [0, 1]^n, f(xs) >= 0",
     "for xs in ([0.0, 1.0] | {missing})^n : float, f(xs) >= 0",
     ("nan",)),
    (summed_ints, "for xs in [0, 1]^n, f(xs) >= 0",
     "for xs in [0.0, 1.0]^n : float, f(xs) >= 0", None),
    (array_mean, "for xs in [0, 1]^n, f(xs) >= 0",
     "for xs in ([0.0, 1.0] | {missing})^n : float, f(xs) >= 0",
     ("nan",)),
    (int_array, "for xs in [0, 1]^n, f(xs) >= 0",
     "for xs in [0.0, 1.0]^n : float, f(xs) >= 0", None),
    (optional_array, "for xs in [0, 1]^n, f(xs) >= 0",
     "for xs in ([0.0, 1.0] | {missing})^n : float|absent, f(xs) >= 0",
     ("nan",)),
    (series_mean, "for xs in [0, 1]^n, f(xs) >= 0",
     "for xs in ([0.0, 1.0] | {missing})^n : float, f(xs) >= 0",
     ("nan", "null", "NA")),
    (polars_mean, "for xs in [0, 1]^n, f(xs) >= 0",
     "for xs in ([0.0, 1.0] | {missing})^n : float, f(xs) >= 0",
     ("null", "nan")),
    (array_mean, "for xs in R^n, f(xs) >= 0", "for xs in (R | {missing})^n, f(xs) >= 0",
     ("nan",)),
    (array_mean, "for xs in R^n \\ {missing}, f(xs) >= 0",
     "for xs in R^n \\ {missing}, f(xs) >= 0", None),
])
def test_the_record_renders_the_completed_domain(fn, text, statement, holes):
    probe = run(fn, text)
    assert probe.statement == statement
    admitted = ((probe.meta or {}).get("mathema.missing") or {}).get("admitted") or {}
    found = next(iter(admitted.values()), {}).get("holes", [])
    assert tuple(found) == (holes or ()), admitted


def test_a_stated_type_clause_with_no_suffix_excludes_and_says_so_where_it_narrows():
    assert run(bare, "for x in [0, 100] subset Z, f(x) >= 0").statement == \
        "for x in [0, 100] \\ {absent, missing} : int, f(x) >= 0"


def test_a_written_clause_that_admits_more_widens_the_type():
    probe = run(plain, "for x in [0, 1] : float|None|missing, f(x) >= 0")
    assert probe.statement == "for x in [0.0, 1.0] : float|absent|missing, f(x) >= 0"
    assert "the claim widens x beyond its type float" in probe.note


def test_a_written_clause_that_admits_less_narrows_the_type():
    probe = run(optional, "for x in [0, 1] : float, f(x) >= 0")
    assert probe.statement == "for x in [0.0, 1.0] \\ {absent, missing} : float, f(x) >= 0"
    assert "the claim narrows x within its type float" in probe.note


def test_a_listed_absence_on_a_float_widens_the_type():
    probe = run(plain, "for x in {0.25, None}, f(x) >= 0")
    assert "the claim widens x beyond its type float" in probe.note


def test_a_datetime_slot_holds_nat():
    policy = missing_policy_from_signature(signature)["i"]
    assert policy.slot_type == "datetime" and policy.members == ("NaT",)


def counted(n: int) -> int:
    return n


def flagged(b: bool) -> bool:
    return b


def named(s: str) -> str:
    return s


@pytest.mark.parametrize("fn, text, what", [
    (counted, "for n in [0, 5] subset Z|missing, f(n) >= 0", "a int has no hole"),
    (flagged, "for b in {True, missing}, f(b) == f(b)", "a bool has no hole"),
    (named, "for s in {missing}, f(s) == s", "a string has no hole"),
])
def test_the_class_on_a_type_with_no_hole_is_refused(fn, text, what):
    probe = run(fn, text)
    assert probe.verdict == "skipped:misspecified", (probe.verdict, probe.note)
    assert what in probe.note and "write `|None`" in probe.note


def test_a_datetime_member_on_a_real_series_is_refused():
    probe = run(series_mean, "for xs in ([0, 1] | {NaT})^n, f(xs) >= 0")
    assert probe.verdict == "skipped:misspecified", (probe.verdict, probe.note)
    assert "holds no NaT" in probe.note


@pytest.mark.parametrize("text", ['for s in {"a", nan}, f(s) == s',
                                  'for s in {"a", null}, f(s) == s',
                                  'for s in {"a", absent} \\ {missing}, f(s) == s'])
def test_any_hole_written_on_a_string_is_refused(text):
    probe = run(named, text)
    assert probe.verdict == "skipped:misspecified", (probe.verdict, probe.note)
    assert "s: a string has no hole; write `|None`" in probe.note


def test_a_claim_may_widen_a_float_with_absence_and_the_none_is_executed():
    probe = run(plain_raising, "for x in {0.25, absent}, f(x) >= 0")
    assert "the claim widens x beyond its type float" in probe.note
    assert probe.verdict == "proven", (probe.verdict, probe.note)
    executed = probe.meta["mathema.missing"]["executed"]
    assert executed == {"x": {"None": "raised TypeError"}}


def plain_raising(x: float) -> float:
    return x + 1.0
