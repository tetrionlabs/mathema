# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Every parameter starts at the bits of nothing known about it, so an
annotation, like any domain the function states, counts as known and
can never lower a score: `x: float` scores at least what a bare `x`
does, with or without claims."""
import pytest

from mathema.badges import clarity_score


def bare(x, y):
    """The sum of x and y."""
    return x + y


def typed(x: float, y: float) -> float:
    """The sum of x and y."""
    return x + y


_ROW = [{"name": "adds", "statement": "f(x, y) == x + y",
         "verdict": "holds", "route": "probe"}]


@pytest.mark.parametrize("rows", [[], _ROW], ids=["unclaimed", "claimed"])
def test_an_annotated_function_scores_at_least_the_bare_one(rows):
    assert clarity_score(typed, verified_claims=rows, library_keys=frozenset()) \
        >= clarity_score(bare, verified_claims=rows, library_keys=frozenset())
