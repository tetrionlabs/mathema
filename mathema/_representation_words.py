# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The words that name a representation, in one table.

`NUMBER_REPRESENTATIONS` are the number representations the claim
grammar reserves (`let Z be i64`) and `representations.PROFILES` holds
a profile for. `REPRESENTATION_WORDS` adds the representations a KOINE
parameter line may also name that the grammar does not reserve: the
complex double `c128`, `bool` and `str`. `PYTHON_CARRIED` are the
representations whose values Python's own `float`, `int`, `complex`,
`bool` and `str` carry with the same arithmetic, which are the ones
the KOINE interpreter runs.
"""
from __future__ import annotations

__all__ = ["NUMBER_REPRESENTATIONS", "PYTHON_CARRIED", "REPRESENTATION_WORDS"]

NUMBER_REPRESENTATIONS: tuple[str, ...] = (
    "i8", "i16", "i32", "i64", "i128",
    "u8", "u16", "u32", "u64", "u128",
    "f16", "f32", "f64", "bigint", "f64int",
)

REPRESENTATION_WORDS: tuple[str, ...] = NUMBER_REPRESENTATIONS + ("c128", "bool", "str")

PYTHON_CARRIED: frozenset[str] = frozenset({"f64", "f64int", "bigint", "c128", "bool", "str"})
