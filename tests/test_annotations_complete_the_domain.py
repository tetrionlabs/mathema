# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A binding without a type clause is completed from the parameter's
annotation: a `float` slot may hold its NaN hole, an `int`, `bool` or
`str` holds none, an `Optional[...]` may be absent, a list element may
be `null` or `nan`, a runtime type holds what its adapter and the
definition rows say. The record states the resolution ("missing for x
(float): nan"), and a written clause wins over the annotation with a
note saying whether it widens or narrows it."""
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


@pytest.mark.parametrize("fn, text, statement, note", [
    (plain, "for x in [0, 1], f(x) >= 0",
     "for x in [0.0, 1.0] : float|missing, f(x) >= 0", "missing for x (float): nan"),
    (optional, "for x in [0, 1], f(x) >= 0",
     "for x in [0.0, 1.0] : float|None|missing, f(x) >= 0", "missing for x (float): nan"),
    (bare, "for x in [0, 1], f(x) >= 0",
     "for x in [0.0, 1.0] : float|None|missing, f(x) >= 0",
     "missing for x (unannotated): nan"),
    (marked, "for x in [0, 1], f(x) >= 0",
     "for x in [0.0, 1.0] : float, f(x) >= 0", None),
    (summed, "for xs in [0, 1]^n, f(xs) >= 0",
     "for xs in ([0.0, 1.0] | {missing})^n : float, f(xs) >= 0",
     "missing for xs (list): null, nan"),
    (summed_floats, "for xs in [0, 1]^n, f(xs) >= 0",
     "for xs in ([0.0, 1.0] | {missing})^n : float, f(xs) >= 0",
     "missing for xs (list[float]): nan"),
    (summed_ints, "for xs in [0, 1]^n, f(xs) >= 0",
     "for xs in [0.0, 1.0]^n : float, f(xs) >= 0", None),
    (array_mean, "for xs in [0, 1]^n, f(xs) >= 0",
     "for xs in ([0.0, 1.0] | {missing})^n : float, f(xs) >= 0",
     "missing for xs (numpy.ndarray): nan"),
    (int_array, "for xs in [0, 1]^n, f(xs) >= 0",
     "for xs in [0.0, 1.0]^n : float, f(xs) >= 0", None),
    (optional_array, "for xs in [0, 1]^n, f(xs) >= 0",
     "for xs in ([0.0, 1.0] | {missing})^n : float|None, f(xs) >= 0",
     "missing for xs (numpy.ndarray): nan"),
    (series_mean, "for xs in [0, 1]^n, f(xs) >= 0",
     "for xs in ([0.0, 1.0] | {missing})^n : float, f(xs) >= 0",
     "missing for xs (pandas.Series): nan, null, NA, NaT"),
    (polars_mean, "for xs in [0, 1]^n, f(xs) >= 0",
     "for xs in ([0.0, 1.0] | {missing})^n : float, f(xs) >= 0",
     "missing for xs (polars.Series): null, nan"),
    (array_mean, "for xs in R^n, f(xs) >= 0", "for xs in R^n, f(xs) >= 0", None),
])
def test_the_record_renders_the_completed_domain(fn, text, statement, note):
    probe = run(fn, text)
    assert probe.statement == statement
    if note is None:
        assert "missing for" not in (probe.note or "")
    else:
        assert note in (probe.note or "")


def test_a_stated_type_clause_with_no_suffix_excludes():
    assert run(bare, "for x in [0, 100] subset Z, f(x) >= 0").statement == \
        "for x in [0, 100] : int, f(x) >= 0"


def test_a_written_clause_that_admits_more_widens_the_type():
    probe = run(plain, "for x in [0, 1] : float|None|missing, f(x) >= 0")
    assert probe.statement == "for x in [0.0, 1.0] : float|None|missing, f(x) >= 0"
    assert "x: the claim widens the type float" in probe.note


def test_a_written_clause_that_admits_less_narrows_the_type():
    probe = run(optional, "for x in [0, 1] : float, f(x) >= 0")
    assert probe.statement == "for x in [0.0, 1.0] : float, f(x) >= 0"
    assert "x: the claim narrows the type float" in probe.note


def test_a_listed_absence_on_a_float_widens_the_type():
    probe = run(plain, "for x in {0.25, None}, f(x) >= 0")
    assert "x: the claim widens the type float" in probe.note


def test_a_datetime_slot_holds_nat():
    policy = missing_policy_from_signature(signature)["i"]
    assert policy.slot_type == "datetime" and policy.members == ("NaT",)
