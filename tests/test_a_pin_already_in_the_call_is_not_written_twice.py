# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A pin a call to f already passes is not written into it again.

When f's signature takes its keywords through `**kwargs` (as the
receiver adapter of a library method does where Python cannot read the
method's own signature), a keyword the call passes binds into
`kwargs`, not under its own name. Writing the claim's pins into its
calls still leaves out every keyword the call already passes, so
`f(a, ddof=1)` stays `f(a, ddof=1)` and its stored text reads back.
"""
import pytest

from mathema import conjecture
from mathema.conjecture import claim, pins_into_calls


def through_kwargs(a, /, **kwargs):
    return len(kwargs)


def named(a, ddof=0):
    return ddof


@pytest.mark.parametrize("fn", [through_kwargs, named])
def test_a_keyword_the_call_passes_is_kept_once(monkeypatch, fn):
    monkeypatch.setattr(conjecture, "call_defaults",
                        lambda fn, cj: ({}, {"ddof": 1}, None))
    cj = claim("for a in [0, 1], f(a, ddof=1) == 1")
    assert pins_into_calls(cj, fn).lhs == "f(a, ddof=1)"


def test_a_pin_the_call_leaves_out_is_still_written(monkeypatch):
    monkeypatch.setattr(conjecture, "call_defaults",
                        lambda fn, cj: ({}, {"ddof": 1}, None))
    cj = claim("for a in [0, 1], f(a) == 1")
    assert pins_into_calls(cj, through_kwargs).lhs == "f(a, ddof=1)"
