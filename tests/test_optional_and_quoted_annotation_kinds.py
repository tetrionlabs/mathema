# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A parameter's kind is read through `Optional[...]`, `X | None`,
`Union[X, None]` and a quoted annotation (every annotation under
`from __future__ import annotations` is one), so each spelling of an
optional string is a string parameter and of an optional float a
scalar one."""
import ast

import pytest

from mathema.analysis import _param_kinds


def _kind(annotation: str) -> str:
    fdef = ast.parse(f"def f(x: {annotation}):\n    return x").body[0]
    return _param_kinds(fdef, ["x"])["x"]


@pytest.mark.parametrize("annotation,kind", [
    ("str", "string"), ("str | None", "string"), ("None | str", "string"),
    ("Optional[str]", "string"), ("typing.Optional[str]", "string"),
    ("Union[str, None]", "string"), ("Union[None, str]", "string"),
    ("'str'", "string"), ("'str | None'", "string"), ('"Optional[str]"', "string"),
    ("float | None", "scalar"), ("Optional[float]", "scalar"), ("'float'", "scalar"),
    ("Optional[int]", "int"), ("'list[float] | None'", "sequence"),
    ("Union[str, int]", "unknown"),
])
def test_optional_and_quoted_spellings_read_as_their_type(annotation, kind):
    assert _kind(annotation) == kind
