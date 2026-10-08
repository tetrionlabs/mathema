# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The signature of a callable, numpy ufuncs included, and the module
scope its names resolve in.

numpy releases before 2.3 give a ufunc no `inspect.signature`; the
signature numpy documents for every ufunc (and reports from 2.3 on) is
fixed by the ufunc's `nin` and `nout`, and is built from them here.
"""
from __future__ import annotations

from typing import Any, Callable

import inspect

_P = inspect.Parameter


def _is_ufunc(fn) -> bool:
    """Whether `fn` is a numpy ufunc, read without importing numpy."""
    kind = type(fn)
    return kind.__name__ == "ufunc" and kind.__module__ == "numpy"


def _no_value():
    """numpy's no-value sentinel, the default of a keyword a gufunc
    accepts but does not pass on unless given."""
    import numpy as np
    try:
        return np._globals._NoValue
    except AttributeError:
        return getattr(np, "_NoValue", None)


def ufunc_signature(fn) -> inspect.Signature:
    """Intent:
        The signature numpy documents for the ufunc `fn`: its inputs as
        positional-only `x` (one input) or `x1, x2, ...`, then `out`
        (`None`, or a tuple of `None` per output when there are
        several), then the keyword-only ufunc arguments. A generalized
        ufunc (one with a core `signature`, such as `matmul`) takes
        `axes`, `axis` and `keepdims` in place of `where`.
    """
    nin, nout = int(fn.nin), int(fn.nout)
    names = ["x"] if nin == 1 else [f"x{i}" for i in range(1, nin + 1)]
    params = [_P(n, _P.POSITIONAL_ONLY) for n in names]
    out = None if nout == 1 else (None,) * nout
    params.append(_P("out", _P.POSITIONAL_OR_KEYWORD, default=out))
    if getattr(fn, "signature", None):
        missing = _no_value()
        extra = [("axes", missing), ("axis", missing), ("keepdims", False)]
    else:
        extra = [("where", True)]
    extra += [("casting", "same_kind"), ("order", "K"), ("dtype", None),
              ("subok", True), ("signature", None)]
    params += [_P(n, _P.KEYWORD_ONLY, default=d) for n, d in extra]
    return inspect.Signature(params)


def callable_signature(fn: Callable[..., Any]) -> inspect.Signature:
    """Intent:
        `inspect.signature(fn)`, with a numpy ufunc that has none read
        as `ufunc_signature(fn)`, so a ufunc has the same parameters on
        every numpy.

    Raises:
        ValueError, TypeError: as `inspect.signature` does, for any
            other callable without a readable signature.
    """
    try:
        return inspect.signature(fn)
    except ValueError:
        if _is_ufunc(fn):
            return ufunc_signature(fn)
        return documented_signature(fn)


def documented_signature(fn) -> inspect.Signature:
    """Intent:
        The signature a compiled callable's docstring opens with, by
        numpy's convention: a first line `dot(a, b, out=None)` naming
        the callable itself. Each default is read as a Python literal.

    Raises:
        ValueError: the docstring opens with no call of that name, or
            the call does not read as a parameter list.
    """
    import ast
    name = getattr(fn, "__name__", "") or ""
    doc = getattr(fn, "__doc__", None) or ""
    first = next((line.strip() for line in doc.splitlines() if line.strip()), "")
    if not name or not first.startswith(f"{name}(") or not first.endswith(")"):
        raise ValueError(f"no signature found for {name or fn!r}")
    try:
        tree = ast.parse(f"def _f({first[len(name) + 1:-1]}): pass")
        args = tree.body[0].args  # type: ignore[attr-defined]
        positional = args.posonlyargs + args.args
        defaults = [None] * (len(positional) - len(args.defaults)) \
            + list(args.defaults)
        params = []
        for i, arg in enumerate(positional):
            kind = _P.POSITIONAL_ONLY if i < len(args.posonlyargs) \
                else _P.POSITIONAL_OR_KEYWORD
            default = defaults[i]
            params.append(_P(arg.arg, kind) if default is None else
                          _P(arg.arg, kind, default=ast.literal_eval(default)))
        if args.vararg is not None:
            params.append(_P(args.vararg.arg, _P.VAR_POSITIONAL))
        for arg, default in zip(args.kwonlyargs, args.kw_defaults):
            params.append(_P(arg.arg, _P.KEYWORD_ONLY) if default is None
                          else _P(arg.arg, _P.KEYWORD_ONLY,
                                  default=ast.literal_eval(default)))
        if args.kwarg is not None:
            params.append(_P(args.kwarg.arg, _P.VAR_KEYWORD))
        return inspect.Signature(params)
    except (SyntaxError, ValueError, TypeError) as exc:
        raise ValueError(f"no signature found for {name}") from exc


def module_scope(fn) -> dict:
    """Intent:
        The globals of the module that defines `fn`: a function under a
        decorator (a wrapper function setting `__wrapped__`, as
        `functools.wraps` does) is followed to the function it wraps,
        whose source is the one read, so its names resolve where it was
        written rather than in the decorator's module. Empty for a
        callable with no globals of its own, such as a numpy dispatcher.
    """
    own = getattr(fn, "__globals__", None)
    if not own:
        return {}
    try:
        inner = inspect.unwrap(fn)
    except ValueError:
        return own
    return getattr(inner, "__globals__", None) or own
