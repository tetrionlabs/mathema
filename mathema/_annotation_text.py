# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""One spelling for a type annotation in everything mathema says, the
same on every Python version: a union with None reads `Optional[X]`, a
union without it `Union[X, Y]`, a generic its own name with its
arguments read the same way, and a class its name; and the binding
an int annotation completes (`int_completed`), read the same by every
layer."""
from __future__ import annotations

import types
import typing


def _is_union(ann) -> bool:
    return typing.get_origin(ann) in (typing.Union, types.UnionType)


def annotation_text(ann) -> str:
    """Intent:
        An annotation as mathema writes it: `Optional[float]` for
        `Optional[float]` and `float | None` alike, `Union[int, str]`,
        `list[Optional[float]]`, `float`. A string annotation is kept
        as written.
    """
    if isinstance(ann, str):
        return ann
    if ann is None or ann is type(None):
        return "None"
    if ann is Ellipsis:
        return "..."
    if isinstance(ann, list):
        return "[" + ", ".join(annotation_text(a) for a in ann) + "]"
    if _is_union(ann):
        args = typing.get_args(ann)
        rest = [a for a in args if a is not type(None)]
        inner = (annotation_text(rest[0]) if len(rest) == 1 else
                 "Union[" + ", ".join(annotation_text(a) for a in rest) + "]")
        return f"Optional[{inner}]" if len(rest) < len(args) else inner
    args = typing.get_args(ann)
    if args and typing.get_origin(ann) is not None:
        head = repr(ann).replace("typing.", "").split("[", 1)[0]
        return f"{head}[" + ", ".join(annotation_text(a) for a in args) + "]"
    if isinstance(ann, type):
        return ann.__name__
    return repr(ann).replace("typing.", "")


def int_completed(bound, kind: "str | None"):
    """Intent:
        A real binding that states no type, completed to the integers
        when its parameter is annotated `int` (`[0, 10]` on `n: int` is
        `[0, 10] : int`), or when it bounds the elements of a sequence
        whose annotation states int elements (`[0, 1]^n` on `xs:
        list[int]`, `kind` then the slot type `list[int]`, is `[0, 1]^n
        : int`); any other binding unchanged. A type the claim states
        wins.
    """
    from dataclasses import replace

    from .domain import _as_domain
    from .domain import is_sentinel
    elements = isinstance(kind, str) and kind.endswith("[int]")
    if not (kind == "int" or elements) or bound is None \
            or isinstance(bound, (str, frozenset)):
        return bound
    dom = _as_domain(bound)
    # a piece listing values is a set the claim states; a piece of
    # sentinels only (`| {missing}`) states the missing values beside
    # the range
    if dom.explicit_type or dom.base_type != "R" or (dom.dims and not elements) \
            or not dom.pieces \
            or any(isinstance(piece, frozenset)
                   and not all(is_sentinel(v) for v in piece)
                   for piece in dom.pieces):
        return bound
    return replace(dom, base_type="Z", explicit_type=True)
