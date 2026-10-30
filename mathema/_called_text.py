# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A witness argument as the call received it.

A parameter with a runtime type (a pandas, polars or numpy object) is
drawn as plain values and realised through its adapter just before the
call, so the drawn list is not what the function received. The
realising call files each realised argument here under the drawn
value's identity, and a witness renders that argument as a one-line
constructor call that evaluates back to the object the call received
(`pandas.Series([0.0])`, `pandas.DataFrame({"w": [0.5]})`,
`numpy.array([1.0, 2.0])`, `polars.Series(values=[1, None])`), read
with `pandas`, `polars`, `numpy`, `nan` and `inf` in scope.
"""
from __future__ import annotations

import contextvars
import math

#: the arguments realised for the current claim's calls, `{id(drawn):
#: (drawn, realised)}`, most recent last
_REALISED: contextvars.ContextVar = contextvars.ContextVar(
    "mathema_realised_arguments", default=None)

#: how many realised arguments are kept: the witness is written right
#: after the call that failed, so only the latest few are read
_KEPT = 64


#: the latest realised argument of each parameter, `{name: (drawn,
#: realised)}`
_BY_NAME: contextvars.ContextVar = contextvars.ContextVar(
    "mathema_realised_by_name", default=None)


def file_realised(drawn, realised, name: "str | None" = None) -> None:
    """Intent:
        Remember that a call received `realised` where `drawn` was the
        value drawn for it (for the parameter `name`), so a witness
        naming `drawn` renders what the call received.
    """
    if realised is drawn:
        return
    kept = _REALISED.get()
    if kept is None:
        kept = {}
        _REALISED.set(kept)
    kept.pop(id(drawn), None)
    kept[id(drawn)] = (drawn, realised)
    while len(kept) > _KEPT:
        kept.pop(next(iter(kept)))
    if name is not None:
        named = _BY_NAME.get()
        if named is None:
            named = {}
            _BY_NAME.set(named)
        named[name] = (drawn, realised)


def split_witness(text: str) -> "tuple[str, str]":
    """Intent:
        A witness `<point>: <what was found>` split at its first colon
        outside brackets and quotes, so a point holding a table
        (`df = pandas.DataFrame({'w': [0.5]})`) stays whole; the text
        and an empty remainder when there is no such colon.
    """
    depth, quote = 0, None
    for i, ch in enumerate(text):
        if quote:
            quote = None if ch == quote else quote
        elif ch in "'\"":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif depth == 0 and text.startswith(": ", i):
            return text[:i], text[i + 2:]
    return text, ""


def forget_realised() -> None:
    """Start a claim with nothing filed: what an earlier claim's calls
    received never names this claim's arguments."""
    _REALISED.set({})
    _BY_NAME.set({})


def received_as(name: str, value):
    """Intent:
        The object the latest call received for parameter `name` when it
        was drawn as `value` (the same object, or one that prints the
        same, since the probe passes a copy of its draw), else
        `received(value)`.
    """
    found = (_BY_NAME.get() or {}).get(name)
    if found is not None and (found[0] is value
                              or _same_draw(found[0], value)):
        return found[1]
    return received(value)


def _same_draw(a, b) -> bool:
    try:
        return type(a) is type(b) and repr(a) == repr(b)
    except Exception:
        return False


def received(value):
    """The object a call received for the drawn `value`, or `value`
    itself when no realised argument was filed for it."""
    kept = _REALISED.get() or {}
    found = kept.get(id(value))
    if found is not None and found[0] is value:
        return found[1]
    return value


def called_text(value) -> "str | None":
    """Intent:
        `value` as a one-line constructor call that evaluates to an
        equal object, when it is a pandas Series or DataFrame, a numpy
        array or a polars Series or DataFrame; None for anything else.
        The element type is written only where the values as printed
        would read back as another one (an empty or all-hole column, an
        object or nullable dtype).
    """
    module = type(value).__module__.split(".")[0]
    name = type(value).__name__
    try:
        if module == "pandas" and name == "Series":
            return _pandas_series(value)
        if module == "pandas" and name == "DataFrame":
            return _pandas_frame(value)
        if module == "numpy" and name == "ndarray":
            return _numpy_array(value)
        if module == "polars" and name == "Series":
            return _polars_series(value)
        if module == "polars" and name == "DataFrame":
            return _polars_frame(value)
    except Exception:
        return None
    return None


def element_text(v) -> str:
    """One element, as it evaluates back: a float at full precision
    with its point (`0.0`, `nan`, `-inf`), pandas' missing markers by
    name (`pandas.NA`, `pandas.NaT`), anything else by its repr."""
    module = type(v).__module__.split(".")[0]
    if v is None:
        return "None"
    if module == "pandas" and type(v).__name__ == "NAType":
        return "pandas.NA"
    if module == "pandas" and type(v).__name__ == "NaTType":
        return "pandas.NaT"
    if module == "pandas" and type(v).__name__ == "Timestamp":
        return f"pandas.Timestamp({str(v)!r})"
    if isinstance(v, bool):
        return repr(v)
    if isinstance(v, float) or (module == "numpy" and hasattr(v, "dtype")
                                and getattr(v.dtype, "kind", "") == "f"):
        f = float(v)
        if math.isnan(f):
            return "nan"
        if math.isinf(f):
            return "inf" if f > 0 else "-inf"
        return repr(f)
    if module == "numpy" and hasattr(v, "item"):
        return element_text(v.item())
    if isinstance(v, list):
        return "[" + ", ".join(element_text(x) for x in v) + "]"
    return repr(v)


def _items(values) -> str:
    return "[" + ", ".join(element_text(x) for x in values) + "]"


def _pandas_series(s) -> str:
    import pandas as pd
    values = s.tolist()
    parts = [_items(values)]
    if pd.Series(values, dtype=None if values else object).dtype != s.dtype:
        parts.append(f"dtype={str(s.dtype)!r}")
    index = _index_text(s.index)
    if index is not None:
        parts.append(f"index={index}")
    if s.name is not None:
        parts.append(f"name={s.name!r}")
    return f"pandas.Series({', '.join(parts)})"


def _index_text(index) -> "str | None":
    """The `index=` a pandas object needs to read back with the labels
    the call received: None for the positions 0, 1, ... (and for no
    rows), `pandas.date_range('2020-01-01', periods=3)` for consecutive
    days, else the labels."""
    import pandas as pd
    n = len(index)
    if index.name is None and (n == 0 or index.equals(pd.RangeIndex(n))):
        return None
    if isinstance(index, pd.DatetimeIndex) and index.name is None \
            and index.tz is None:
        start = (str(index[0].date()) if index[0] == index[0].normalize()
                 else str(index[0]))
        for maker in ("bdate_range", "date_range"):
            if index.equals(getattr(pd, maker)(index[0], periods=n)):
                return f"pandas.{maker}({start!r}, periods={n})"
    return _items(index.tolist())


def _pandas_frame(df) -> str:
    import pandas as pd
    columns = {c: df[c].tolist() for c in df.columns}
    body = "{" + ", ".join(f"{c!r}: {_items(v)}" for c, v in columns.items()) + "}"
    text = f"pandas.DataFrame({body}"
    index = _index_text(df.index)
    if index is not None:
        text += f", index={index}"
    text += ")"
    plain = pd.DataFrame(columns, index=df.index)
    differ = {c: str(df[c].dtype) for c in df.columns
              if plain[c].dtype != df[c].dtype}
    if differ:
        text += ".astype({" + ", ".join(f"{c!r}: {t!r}" for c, t in differ.items()) + "})"
    return text


def _numpy_array(a) -> str:
    import numpy as np
    values = a.tolist()
    text = _items(values) if a.ndim else element_text(values)
    if np.array(values).dtype != a.dtype or a.size == 0:
        return f"numpy.array({text}, dtype={str(a.dtype)!r})"
    return f"numpy.array({text})"


def _polars_series(s) -> str:
    import polars as pl
    values = s.to_list()
    parts = []
    if s.name:
        parts.append(f"name={s.name!r}")
    parts.append(f"values={_items(values)}")
    if pl.Series(values=values).dtype != s.dtype:
        parts.append(f"dtype=polars.{s.dtype}")
    return f"polars.Series({', '.join(parts)})"


def _polars_frame(df) -> str:
    import polars as pl
    columns = {c: df[c].to_list() for c in df.columns}
    body = "{" + ", ".join(f"{c!r}: {_items(v)}" for c, v in columns.items()) + "}"
    plain = pl.DataFrame(columns)
    if plain.schema != df.schema:
        schema = "{" + ", ".join(f"{c!r}: polars.{t}" for c, t in df.schema.items()) + "}"
        return f"polars.DataFrame({body}, schema={schema})"
    return f"polars.DataFrame({body})"
