# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""What mathema says about an annotation does not depend on the Python
version running it. An annotation that admits None reads
`Optional[float]` whether the source wrote `Optional[float]` or
`float | None` (Python 3.14 renders both as `float | None`); a union
without None reads `Union[int, str]`; a generic keeps its own name with
its arguments read the same way."""
from typing import List, Optional, Union

from mathema._annotation_text import annotation_text


def test_an_annotation_admitting_none_reads_optional():
    assert annotation_text(Optional[float]) == "Optional[float]"
    assert annotation_text(float | None) == "Optional[float]"
    assert annotation_text(Union[int, str, None]) == "Optional[Union[int, str]]"


def test_a_union_without_none_reads_union():
    assert annotation_text(Union[int, str]) == "Union[int, str]"
    assert annotation_text(int | str) == "Union[int, str]"


def test_plain_and_generic_annotations():
    assert annotation_text(float) == "float"
    assert annotation_text(None) == "None"
    assert annotation_text("float") == "float"
    assert annotation_text(list[float]) == "list[float]"
    assert annotation_text(List[float]) == "List[float]"
    assert annotation_text(list[Optional[float]]) == "list[Optional[float]]"
    assert annotation_text(dict[str, float | None]) == \
        "dict[str, Optional[float]]"
