# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The call graph is built from each function's dependency edges alone:
the `(key, kind)` pairs `function_dependencies` lists, read without
working out any callee's form, reach or chain."""
import inspect
import sys

import pytest

from mathema import inventory
from mathema.centrality import build_call_graph
from mathema.inventory import dependency_edges, function_dependencies

_HELPERS = '''\
def helper(x):
    return x + 1


def twice(x):
    return helper(helper(x))
'''

_CORE = '''\
import math
from dataclasses import dataclass

import edgepkg.helpers as hp
from edgepkg import helpers
from edgepkg.helpers import helper as aliased

SCALE = 2.5
LIMIT = 3


@dataclass
class Point:
    x: float

    def norm(self) -> float:
        return math.sqrt(self.x * self.x) + aliased(self.x)


def ping(n):
    if n <= 0:
        return 0
    return pong(n - 1)


def pong(n):
    return tri(n - 1) + SCALE


def tri(n):
    return ping(n - 1) * LIMIT


def outer(x):
    def inner(y):
        return aliased(y)
    return inner(x) + helpers.helper(x) + hp.twice(x) + len([x]) + math.floor(x)


def uses_class(p: Point) -> float:
    return Point(p.x).norm() + abs(p.x)


def selfrec(n):
    return selfrec(n - 1) if n else 0


def takes_callable(f: "object", g=None):
    return outer(1)
'''


@pytest.fixture
def population(tmp_path, monkeypatch):
    pkg = tmp_path / "edgepkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "helpers.py").write_text(_HELPERS)
    (pkg / "core.py").write_text(_CORE)
    monkeypatch.syspath_prepend(str(tmp_path))
    for name in [m for m in sys.modules if m.split(".")[0] == "edgepkg"]:
        monkeypatch.delitem(sys.modules, name)
    import edgepkg.core as core
    import edgepkg.helpers as helpers
    fns = {}
    for mod in (core, helpers):
        for name, obj in vars(mod).items():
            if inspect.isfunction(obj) and obj.__module__ == mod.__name__:
                fns[f"{mod.__name__}.{obj.__qualname__}"] = obj
    fns["edgepkg.core.Point.norm"] = core.Point.norm
    yield fns
    for name in [m for m in sys.modules if m.split(".")[0] == "edgepkg"]:
        sys.modules.pop(name, None)


def _graph_from_dependencies(functions):
    keys = set(functions)
    edges = {k: set() for k in keys}
    for key, fn in functions.items():
        for dep in function_dependencies(fn):
            callee = dep.get("key")
            if dep.get("kind") == "function" and callee in keys and callee != key:
                edges[key].add(callee)
    return edges


def test_the_edges_are_the_pairs_the_dependencies_list(population):
    for key, fn in population.items():
        expected = [(d.get("key"), d.get("kind")) for d in function_dependencies(fn)]
        assert dependency_edges(fn) == expected, key


def test_the_fixture_covers_every_kind_of_edge(population):
    kinds = {k for fn in population.values() for _key, k in dependency_edges(fn)}
    assert {"function", "class", "module"} <= kinds
    outer = dict(dependency_edges(population["edgepkg.core.outer"]))
    assert "edgepkg.helpers.twice" in outer
    assert "edgepkg.helpers.helper" in outer


def test_the_call_graph_is_the_one_the_dependencies_give(population):
    graph = build_call_graph(population)
    assert graph == _graph_from_dependencies(population)
    assert "edgepkg.core.pong" in graph["edgepkg.core.ping"]
    assert "edgepkg.core.ping" in graph["edgepkg.core.tri"]
    assert graph["edgepkg.core.selfrec"] == set()


def test_the_call_graph_works_out_no_reach(population, monkeypatch):
    def refuse(obj):
        raise AssertionError(f"dependency_reach({obj!r}) called")
    monkeypatch.setattr(inventory, "dependency_reach", refuse)
    monkeypatch.setattr(inventory, "class_reach", refuse)
    build_call_graph(population)
