# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A witness argument with a runtime type is written as the call
received it, one evaluable line (`xs = pandas.Series([-1.0])`,
`df = pandas.DataFrame({'w': [-0.5]})`, `a = numpy.array([-1.0])`), so
the witness replays as written: the function called on the printed
arguments gives the printed value."""
import math

import pytest

from mathema.claims import check_conjectures, claim

pd = pytest.importorskip("pandas")
np = pytest.importorskip("numpy")


def _top_level_split(text: str, sep: str) -> list:
    # `text` split at `sep` where no bracket or quote is open
    out, depth, quote, start, i = [], 0, None, 0, 0
    while i < len(text):
        ch = text[i]
        if quote:
            quote = None if ch == quote else quote
        elif ch in "'\"":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif depth == 0 and text.startswith(sep, i):
            out.append(text[start:i])
            start = i + len(sep)
            i += len(sep)
            continue
        i += 1
    out.append(text[start:])
    return out


def replay(fn, witness: str, namespace: dict):
    """The printed arguments read back and f called on them, with the
    left side the witness printed (`<point>: <lhs> vs <rhs>`)."""
    point, said = _top_level_split(witness, ": ")[:2]
    args = {}
    for part in _top_level_split(point, ", "):
        name, value = part.split(" = ", 1)
        args[name] = eval(value, dict(namespace))
    return args, fn(**args), said.split(" vs ")[0]


def _namespace():
    out = {"pandas": pd, "numpy": np, "nan": math.nan, "inf": math.inf}
    try:
        import polars
        out["polars"] = polars
    except ImportError:
        pass
    return out


def last_of_series(xs: pd.Series) -> float:
    return float(xs.iloc[-1])


def total_of_frame(df: pd.DataFrame) -> float:
    return float(df["w"].sum())


def first_of_array(a: np.ndarray) -> float:
    return float(a[0])


@pytest.mark.parametrize("fn, text, kind", [
    (last_of_series, "for xs in R^n, f(xs) >= 0", pd.Series),
    (total_of_frame, "for df.w in [-1, 0]^n, f(df) > 0", pd.DataFrame),
    (first_of_array, "for a in R^n, f(a) >= 0", np.ndarray),
])
@pytest.mark.parametrize("route", [{}, {"route": "probe"}])
def test_a_runtime_typed_witness_replays_as_written(fn, text, kind, route):
    (p,) = check_conjectures(fn, [claim(text, **route)])
    assert p.verdict == "falsified", (p.verdict, p.note)
    args, value, printed = replay(fn, p.counterexample, _namespace())
    assert all(isinstance(v, kind) for v in args.values()), (p.counterexample, args)
    assert value == float(printed), (p.counterexample, value)


def test_a_polars_witness_replays_as_written():
    pl = pytest.importorskip("polars")

    def last_of_polars(xs: pl.Series) -> float:
        return float(xs[-1])
    (p,) = check_conjectures(last_of_polars, [claim("for xs in R^n, f(xs) >= 0",
                                                    route="probe")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    args, value, printed = replay(last_of_polars, p.counterexample, _namespace())
    assert all(isinstance(v, pl.Series) for v in args.values()), p.counterexample
    assert value == float(printed), (p.counterexample, value)
