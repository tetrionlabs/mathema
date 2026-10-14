# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A method of an array, a frame or a series that returns a new object
(`add`, `sub`, `mul`, `div`, `pow`, the comparisons, `copy`, `astype`)
leaves its receiver as it was, so calling one on an argument is not a
write to that argument. A method that changes its receiver in place
still is: `inplace=True`, an in-place operator or its method form
(`__iadd__`), an assignment through `.loc`, `update` on a series, and
`append`/`update`/`add` on a list, a dict or a set."""
import pytest

from mathema._examine import examine

np = pytest.importorskip("numpy")
pd = pytest.importorskip("pandas")


def _texts(effects) -> list:
    return [s.text for s in (*effects.writes, *effects.unknown_writes,
                             *effects.unknowns)]


def series_arithmetic(returns: pd.Series) -> pd.Series:
    a = returns.add(1)
    b = returns.sub(1).mul(2).div(3).pow(2)
    c = returns.truediv(2).floordiv(2).mod(2).radd(1).rsub(1)
    d = returns.eq(0) | returns.ne(0) | returns.lt(0) | returns.le(0)
    e = returns.gt(0) & returns.ge(0)
    return a + b + c + d + e


def series_conversions(returns: pd.Series) -> pd.Series:
    return returns.copy().astype(float)


def frame_arithmetic(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.add(1).sub(frame.mul(2)).div(2).pow(2).copy()


def array_conversions(x: np.ndarray) -> np.ndarray:
    return x.copy().astype(float)


@pytest.mark.parametrize("fn", [series_arithmetic, series_conversions,
                                frame_arithmetic, array_conversions])
def test_a_method_returning_a_new_object_changes_nothing(fn):
    effects = examine(fn)
    assert _texts(effects) == []
    assert effects.arg_writes == []


def series_inplace_keyword(returns: pd.Series) -> pd.Series:
    returns.clip(lower=0, inplace=True)
    return returns


def series_augmented(returns: pd.Series) -> pd.Series:
    returns += 1
    return returns


def series_iadd(returns: pd.Series) -> pd.Series:
    returns.__iadd__(1)
    return returns


def series_update(returns: pd.Series, other: pd.Series) -> pd.Series:
    returns.update(other)
    return returns


def frame_loc(frame: pd.DataFrame) -> pd.DataFrame:
    frame.loc[0, "a"] = 1.0
    return frame


def list_iadd(xs: list) -> list:
    xs.__iadd__([1])
    return xs


def list_append(xs: list) -> list:
    xs.append(1)
    return xs


def dict_update(d: dict) -> dict:
    d.update(a=1)
    return d


def set_add(s: set) -> set:
    s.add(1)
    return s


@pytest.mark.parametrize("fn, param", [
    (series_inplace_keyword, "returns"), (series_augmented, "returns"),
    (series_iadd, "returns"), (series_update, "returns"),
    (frame_loc, "frame"), (list_iadd, "xs"), (list_append, "xs"),
    (dict_update, "d"), (set_add, "s")])
def test_a_method_changing_its_receiver_is_a_write(fn, param):
    effects = examine(fn)
    assert any(f"its argument {param}" in s.text for s in effects.writes), \
        _texts(effects)
