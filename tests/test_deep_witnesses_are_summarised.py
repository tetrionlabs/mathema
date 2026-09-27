# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A witness too deep for Python's own repr is summarised, never an
exception out of adjudication: a function that crashes on a value
nested past the recursion limit is falsified, and the witness names
the value's type and how deep it goes."""
import sys
from dataclasses import dataclass, field

from mathema.conjecture import check_conjectures, claim
from mathema.languages import Problem, register_language, unregister_language
from mathema.probing import _fmt_value


@dataclass
class Node:
    value: int
    children: list = field(default_factory=list)


def _spine(n):
    root = cur = Node(0)
    for i in range(1, n):
        nxt = Node(i)
        cur.children.append(nxt)
        cur = nxt
    return root


def size(t) -> int:
    """How many nodes, counted recursively."""
    return 1 + sum(size(c) for c in t.children)


class _Trees:
    """Trees, the deep spine among the hazards."""
    name = "deep_trees"
    kind = "object"
    level = "predicate"

    def contains(self, v):
        return isinstance(v, Node)

    def explain(self, v):
        return None if self.contains(v) else [Problem("", "Node", v)]

    def sample(self, rng):
        return Node(rng.randint(0, 9))

    def members(self, limit):
        return None

    def hazards(self):
        from mathema.languages import HazardValue
        return (HazardValue("length", _spine(sys.getrecursionlimit() + 50), "a deep spine"),)

    def outside(self, rng):
        return None

    def shrink(self, v):
        return ()

    def fields(self):
        return None

    def render(self, ascii_mode=True):
        return "L[deep_trees]"

    def to_json(self):
        return {}


def test_a_value_too_deep_for_repr_is_summarised():
    n = sys.getrecursionlimit() + 50
    text = _fmt_value(_spine(n))
    assert text == f"<Node nested {2 * n} levels deep ({n} Node records)>", text
    deep_list: list = []
    for _ in range(sys.getrecursionlimit() + 50):
        deep_list = [deep_list]
    assert _fmt_value(deep_list) == f"<list nested {sys.getrecursionlimit() + 51} levels deep>"
    assert _fmt_value([1, 2]) == "[1, 2]"


def test_a_crash_on_a_deep_value_is_a_witness_not_an_exception():
    register_language("deep_trees", _Trees())
    try:
        (p,) = check_conjectures(size, [claim("for t in L[deep_trees], f(t) >= 1")])
    finally:
        unregister_language("deep_trees")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "RecursionError" in p.counterexample and "levels deep" in p.counterexample, p.counterexample
