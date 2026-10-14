# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A string parameter whose domain is a finite set (a `Literal`, a
guard to a set, `@enforce_domain` to a set) admits no arbitrary text,
so clarity charges it no arbitrary-input source. A bare `str` keeps
it."""
from typing import Literal

from mathema import enforce_domain
from mathema.badges import _clarity_profile, _clarity_sources


def bare(side: str) -> str:
    """The side in capitals."""
    return side.upper()


def literal(side: Literal["buy", "sell"]) -> str:
    """The side in capitals."""
    return side.upper()


@enforce_domain({"side": {"buy", "sell"}})
def enforced(side: str) -> str:
    """The side in capitals."""
    return side.upper()


def _arbitrary_text(fn) -> int:
    return sum(1 for _dim, _bits, reducer in _clarity_sources(
        _clarity_profile(fn, library_keys=frozenset()))
        if reducer == "safety:is_arbitrary_input_safe")


def test_a_bare_str_parameter_is_charged_for_arbitrary_text():
    assert _arbitrary_text(bare) == 1


def test_a_finite_text_domain_is_not():
    assert _arbitrary_text(literal) == _arbitrary_text(enforced) == 0
