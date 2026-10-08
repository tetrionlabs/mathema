# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""One spelling for a type annotation in everything mathema says, the
same on every Python version: a union with None reads `Optional[X]`, a
union without it `Union[X, Y]`, a generic its own name with its
arguments read the same way, and a class its name."""
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
