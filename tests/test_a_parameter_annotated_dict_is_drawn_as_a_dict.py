# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A parameter annotated as a mapping (a bare `dict`, `dict[str, int]`,
`typing.Dict`, `Mapping` or `MutableMapping`) is drawn as a dict, so a
claim over it is decided on values of its declared type: the function
is only ever called with a dict, and `f(order) == f(order)` is not
falsified by a witness outside the type."""
from typing import Dict, Mapping, MutableMapping

import pytest

from mathema.conjecture import check_conjectures, claim


def bare(order: dict) -> int:
    return sum(order.values())


def generic(order: dict[str, int]) -> int:
    return sum(order.values())


def typing_dict(order: Dict[str, int]) -> int:
    return sum(order.values())


def mapping(order: Mapping[str, int]) -> int:
    return sum(order.values())


def bare_mapping(order: Mapping) -> int:
    return sum(order.values())


def mutable(order: MutableMapping) -> int:
    return sum(order.values())


@pytest.mark.parametrize("fn", [bare, generic, typing_dict, mapping,
                                bare_mapping, mutable],
                         ids=lambda fn: fn.__name__)
def test_a_claim_over_a_mapping_parameter_is_not_falsified(fn):
    (p,) = check_conjectures(fn, [claim("f(order) == f(order)")])
    assert p.verdict in ("proven", "holds"), (p.verdict, p.counterexample,
                                              p.note)
    assert p.counterexample is None


@pytest.mark.filterwarnings("ignore::mathema.analysis.StateDependenceWarning")
def test_every_draw_of_a_dict_parameter_is_a_dict():
    seen: list = []

    def total_qty(order: dict) -> int:
        seen.append(type(order))
        return sum(order.values())

    (p,) = check_conjectures(total_qty, [claim("f(order) == f(order)")])
    assert p.verdict in ("proven", "holds"), (p.verdict, p.counterexample)
    assert seen and set(seen) == {dict}, set(seen)
