# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A method of a runtime type as a function of its receiver.

A library claim key can name a method or an attribute of a runtime
type's class: `pandas.Series.std`, `numpy.ndarray.T`. Its claims are
stated about the receiver as an ordinary first parameter named `a`,
the name numpy gives the array its functions take:

    pandas.Series.std:
      claims:
        - name: definition
          statement: "for a in R^n \\ {∅}, f(a) == std(a, ddof=1)"

`receiver_form(key)` is the function those claims are adjudicated
against: `f(a, ...)` calls `a.std(...)` (or reads `a.T` for an
attribute), its parameter `a` is annotated with the class so it is
sampled as that runtime type, and its signature is the method's own
with the receiver renamed, so the defaults a claim does not bind are
passed at their values.
"""
from __future__ import annotations

import functools
import importlib
import inspect

#: the name a method's receiver takes in its claims
RECEIVER = "a"


def _runtime_class(dotted: str):
    """The class a runtime type adapter is registered under the dotted
    name of (`pandas.Series`), or None when no adapter has that name or
    its library is not importable."""
    from . import adapters
    if dotted not in adapters() or "." not in dotted:
        return None
    module, _, name = dotted.rpartition(".")
    try:
        cls = getattr(importlib.import_module(module), name, None)
    except Exception:
        return None
    return cls if isinstance(cls, type) else None


def _renamed_signature(member, cls) -> "inspect.Signature | None":
    """The method's signature with its receiver parameter named `a`
    and annotated with the class; None when the signature cannot be
    read or another parameter is already named `a`."""
    try:
        sig = inspect.signature(member)
    except (TypeError, ValueError):
        return None
    params = list(sig.parameters.values())
    if not params or any(p.name == RECEIVER for p in params[1:]):
        return None
    receiver = params[0].replace(name=RECEIVER, annotation=cls,
                                 kind=inspect.Parameter.POSITIONAL_ONLY
                                 if params[0].kind
                                 is inspect.Parameter.POSITIONAL_ONLY
                                 else inspect.Parameter.POSITIONAL_OR_KEYWORD)
    return sig.replace(parameters=[receiver, *params[1:]],
                       return_annotation=inspect.Signature.empty)


@functools.lru_cache(maxsize=None)
def receiver_form(key: str):
    """Intent:
        The function a claim key naming a runtime type's method or
        attribute (`pandas.Series.std`, `numpy.ndarray.T`) is
        adjudicated against, one object per key; None for any other
        key.

    Notes:
        A method gives `f(a, *args, **kwargs) = a.<name>(*args,
        **kwargs)` with the method's signature (receiver renamed `a`);
        an attribute gives `f(a) = a.<name>`. Its `__module__` and
        `__qualname__` spell the key, so the key is its dotted name.
    """
    owner, _, name = key.rpartition(".")
    if not owner or name.startswith("_"):
        return None
    cls = _runtime_class(owner)
    if cls is None:
        return None
    member = inspect.getattr_static(cls, name, None)
    if member is None:
        return None
    if isinstance(member, (staticmethod, classmethod)):
        return None
    if isinstance(member, property) or inspect.isgetsetdescriptor(member) \
            or inspect.ismemberdescriptor(member):
        def attribute(a):
            return getattr(a, name)
        fn = attribute
        sig = inspect.Signature([inspect.Parameter(
            RECEIVER, inspect.Parameter.POSITIONAL_OR_KEYWORD,
            annotation=cls)])
    elif callable(member):
        def method(a, *args, **kwargs):
            return getattr(a, name)(*args, **kwargs)
        fn = method
        sig = _renamed_signature(getattr(cls, name), cls)
        if sig is None:
            return None
    else:
        return None
    fn.__name__ = name
    fn.__qualname__ = f"{owner.rpartition('.')[2]}.{name}"
    fn.__module__ = owner.rpartition(".")[0]
    fn.__annotations__ = {RECEIVER: cls}
    fn.__signature__ = sig  # type: ignore[attr-defined]
    return fn
