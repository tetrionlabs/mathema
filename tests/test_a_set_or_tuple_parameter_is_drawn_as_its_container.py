# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A parameter annotated as a set, a frozenset or a tuple is called with
a set, a frozenset or a tuple on every route, never with a list: a
value claim over `items: set` is decided on sets, its witness is a
set, and the holes and the absence its annotation admits are drawn
inside that container. A set meets the magnitude corners a list meets,
its two same-sign entries kept apart so the set still holds two of
them."""
import ast
import math
import re
import sys
from typing import AbstractSet, FrozenSet, Optional, Set

import pytest

from mathema.conjecture import check_conjectures, claim

pytestmark = pytest.mark.filterwarnings(
    "ignore::mathema.analysis.StateDependenceWarning")


def add_to(items: set) -> int:
    items.add(1.0)
    return len(items)


@pytest.mark.parametrize("law", ["f(items) >= 1",
                                 "for items in R^n, f(items) >= 1"])
def test_a_value_claim_over_a_set_is_not_falsified_by_a_list(law):
    (p,) = check_conjectures(add_to, [claim(law)])
    assert "AttributeError" not in (p.counterexample or ""), p.counterexample
    assert p.verdict in ("holds", "proven"), (p.verdict, p.counterexample)


def as_key(items: tuple) -> int:
    return len({items: 1})


def test_a_tuple_parameter_is_hashable_on_every_draw():
    (p,) = check_conjectures(as_key, [claim("f(items) == 1")])
    assert "TypeError" not in (p.counterexample or ""), p.counterexample
    assert p.verdict in ("holds", "proven"), (p.verdict, p.counterexample)


#: every value a recording function below is called with
_SEEN: list = []


def takes_set(items: set) -> int:
    _SEEN.append(items)
    return 1


def takes_typing_set(items: Set[float]) -> int:
    _SEEN.append(items)
    return 1


def takes_abstract_set(items: AbstractSet[float]) -> int:
    _SEEN.append(items)
    return 1


def takes_frozenset(items: frozenset) -> int:
    _SEEN.append(items)
    return 1


def takes_typing_frozenset(items: FrozenSet[float]) -> int:
    _SEEN.append(items)
    return 1


def takes_tuple(items: tuple) -> int:
    _SEEN.append(items)
    return 1


def takes_optional_set(items: Optional[set]) -> int:
    _SEEN.append(items)
    return 1


CONTAINERS = [
    (takes_set, set, False),
    (takes_typing_set, set, False),
    (takes_abstract_set, set, False),
    (takes_frozenset, frozenset, False),
    (takes_typing_frozenset, frozenset, False),
    (takes_tuple, tuple, False),
    (takes_optional_set, set, True),
]


@pytest.mark.parametrize("law", ["f(items) == 1",
                                 "for items in R^n, f(items) == 1"])
@pytest.mark.parametrize("fn, container, optional", CONTAINERS,
                         ids=[row[0].__name__ for row in CONTAINERS])
def test_every_call_is_made_with_the_annotated_container(fn, container,
                                                         optional, law):
    _SEEN.clear()
    (p,) = check_conjectures(fn, [claim(law)])
    assert p.verdict in ("holds", "proven"), (p.verdict, p.counterexample)
    assert _SEEN, fn.__name__
    outside = [v for v in _SEEN
               if not isinstance(v, container)
               and not (optional and v is None)]
    assert not outside, (fn.__name__, outside[:3])


def _witness_value(counterexample: str, name: str):
    text = re.search(rf"\b{name} = (.+?)(?=: |, \w+ = |$)",
                     counterexample).group(1)
    return ast.literal_eval(text.replace("inf", "1e999"))


def largest_is_small(items: set) -> int:
    return int(max(items, default=0.0) < 5)


def test_a_witness_for_a_set_parameter_is_a_set():
    (p,) = check_conjectures(largest_is_small, [claim("f(items) == 1")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    witness = _witness_value(p.counterexample, "items")
    assert isinstance(witness, set), p.counterexample


def set_total(items: set) -> float:
    return float(sum(items))


def list_total(items: list) -> float:
    return float(sum(items))


@pytest.mark.parametrize("fn", [set_total, list_total],
                         ids=lambda fn: fn.__name__)
def test_a_set_meets_the_same_sign_corner_a_list_meets(fn):
    (p,) = check_conjectures(fn, [claim("f(items) == sum(items)")])
    assert p.verdict == "falsified", (fn.__name__, p.verdict, p.note)
    assert "returned inf" in p.counterexample, p.counterexample
    witness = _witness_value(p.counterexample, "items")
    big = [e for e in witness if abs(e) > sys.float_info.max / 2]
    assert len(big) >= 2, p.counterexample
    assert all(math.isfinite(e) for e in witness), p.counterexample


def holey_set(items: set[Optional[float]]) -> int:
    _SEEN.append(items)
    return 1


def holey_tuple(items: tuple[Optional[float], ...]) -> int:
    _SEEN.append(items)
    return 1


def plain_set(items: set) -> int:
    _SEEN.append(items)
    return 1


@pytest.mark.parametrize("fn, container", [(holey_set, set),
                                           (holey_tuple, tuple),
                                           (plain_set, set)],
                         ids=lambda v: getattr(v, "__name__", str(v)))
def test_the_holes_a_container_admits_are_drawn_inside_it(fn, container):
    _SEEN.clear()
    check_conjectures(fn, [claim("f(items) == 1")])
    holding_none = [v for v in _SEEN if isinstance(v, container)
                    and any(e is None for e in v)]
    holding_nan = [v for v in _SEEN if isinstance(v, container)
                   and any(isinstance(e, float) and e != e for e in v)]
    assert holding_none, (fn.__name__, _SEEN[:5])
    assert holding_nan, (fn.__name__, _SEEN[:5])


def optional_mapping(order: Optional[dict]) -> int:
    _SEEN.append(order)
    return 1


def test_an_optional_mapping_is_drawn_absent():
    _SEEN.clear()
    check_conjectures(optional_mapping, [claim("f(order) == 1")])
    assert any(v is None for v in _SEEN), _SEEN[:5]
    assert all(v is None or isinstance(v, dict) for v in _SEEN), _SEEN[:5]


def sum_of_set(items: set[Optional[float]]) -> float:
    return float(sum(items))


def sum_of_list(items: list[Optional[float]]) -> float:
    return float(sum(items))


def test_a_set_and_its_list_twin_read_their_holes_alike():
    (s,) = check_conjectures(sum_of_set, [claim("f(items) == f(items)")])
    (t,) = check_conjectures(sum_of_list, [claim("f(items) == f(items)")])
    assert s.verdict == t.verdict, (s.verdict, s.counterexample,
                                    t.verdict, t.counterexample)
    missing_s = (s.meta or {}).get("mathema.missing") or {}
    missing_l = (t.meta or {}).get("mathema.missing") or {}
    assert sorted(missing_s.get("behaviour", {}).get("items", {})) == \
        sorted(missing_l.get("behaviour", {}).get("items", {})), \
        (missing_s, missing_l)
