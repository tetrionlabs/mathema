# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Inside a run scope the dependency walk reads each function's and
class's source once: its form and the names its body uses are kept for
the run, while every name is still resolved against the live globals.
What the walk returns inside a scope is what it returns outside one,
whatever changes during the run: a caller mutating what it was handed,
a function collected and another made in its place, a replaced code
object, a module constant or global rebound, a source file rewritten,
a call cycle entered from any node, injected facts, a registered
frontend, or a stated scope."""
import contextlib
import copy
import dataclasses
import gc
import itertools
import os
import sys
import types
import weakref

import pytest

from mathema import _run_scope, analysis, inventory
from mathema._run_scope import run_scope
from mathema.inventory import dependency_reach, function_dependencies


@contextlib.contextmanager
def _outside_the_scope():
    state = _run_scope._STATE
    _run_scope._STATE = None
    try:
        yield
    finally:
        _run_scope._STATE = state


def _unscoped(fn, read=dependency_reach):
    with _outside_the_scope():
        return read(fn)


_HELPERS = '''\
def leaf(x):
    return x + 1


def other_leaf(x):
    return x - 1


def helper(x):
    return leaf(x) * 2


class Box:
    size: float = 1.0

    def grow(self):
        return leaf(self.size)
'''

_CORE = '''\
from walkpkg.helpers import Box, helper, leaf, other_leaf

SCALE = 2.0


def top(x):
    return helper(x) + SCALE


def boxed(x):
    return Box().grow() + x


def a(x):
    return leaf(x)


def b(x):
    return other_leaf(x)


def head(x):
    return c1(x)


def c1(x):
    return c2(x) + t1(x)


def c2(x):
    return c3(x) + t2(x)


def c3(x):
    return c1(x) + t3(x)


def t1(x):
    return leaf(x)


def t2(x):
    return x


def t3(x):
    return other_leaf(x)
'''


@pytest.fixture
def walkpkg(tmp_path, monkeypatch):
    pkg = tmp_path / "walkpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "helpers.py").write_text(_HELPERS)
    (pkg / "core.py").write_text(_CORE)
    monkeypatch.syspath_prepend(str(tmp_path))
    for name in [m for m in sys.modules if m.split(".")[0] == "walkpkg"]:
        monkeypatch.delitem(sys.modules, name)
    import walkpkg.core as core
    yield core
    for name in [m for m in sys.modules if m.split(".")[0] == "walkpkg"]:
        sys.modules.pop(name, None)


def _counting(monkeypatch):
    calls = {"facts": 0, "tree": 0}
    facts, tree = inventory.quiet_facts, analysis.get_tree

    def counted_facts(fn):
        calls["facts"] += 1
        return facts(fn)

    def counted_tree(fn):
        calls["tree"] += 1
        return tree(fn)
    monkeypatch.setattr(inventory, "quiet_facts", counted_facts)
    monkeypatch.setattr(analysis, "get_tree", counted_tree)
    return calls


def test_inside_a_scope_the_walk_reads_each_source_once(walkpkg, monkeypatch):
    calls = _counting(monkeypatch)
    expected = dependency_reach(walkpkg.top)
    for _ in range(2):
        calls.update(facts=0, tree=0)
        assert dependency_reach(walkpkg.top) == expected
        assert calls["facts"] > 0 and calls["tree"] > 0
    helper, boxed = dependency_reach(walkpkg.helper), dependency_reach(walkpkg.boxed)
    with run_scope():
        assert dependency_reach(walkpkg.top) == expected
        calls.update(facts=0, tree=0)
        assert dependency_reach(walkpkg.top) == expected
        assert dependency_reach(walkpkg.helper) == helper
        assert calls == {"facts": 0, "tree": 0}
        assert dependency_reach(walkpkg.boxed) == boxed
        calls.update(facts=0, tree=0)
        assert dependency_reach(walkpkg.boxed) == boxed
        assert calls == {"facts": 0, "tree": 0}


def test_outside_a_scope_nothing_is_kept(walkpkg):
    dependency_reach(walkpkg.top)
    assert _run_scope._STATE is None
    assert inventory._walk_memo("form") is None


def test_a_caller_mutating_what_it_was_handed_reaches_no_other_caller(walkpkg):
    with run_scope():
        reach = dependency_reach(walkpkg.top)
        kept = copy.deepcopy(reach)
        reach[0]["form"] = "py:000000000000"
        reach.append({"key": "x", "kind": "function", "form": "y"})
        facts = analysis.quiet_facts(walkpkg.helper)
        facts.form = "py:111111111111"
        facts.global_funcs.append("other_leaf")
        assert dependency_reach(walkpkg.top) == kept
        assert analysis.quiet_facts(walkpkg.helper) is not facts
        assert analysis.analyze_source(walkpkg.helper).form != facts.form
        deps = function_dependencies(walkpkg.top)
        deps[0]["reaches"] = []
        assert function_dependencies(walkpkg.top) == _unscoped(
            walkpkg.top, function_dependencies)
    assert kept == dependency_reach(walkpkg.top)


def test_a_function_made_where_a_collected_one_was_gets_its_own_entry(walkpkg):
    core = walkpkg
    codes = (core.a.__code__, core.b.__code__)
    expected = (_unscoped(core.a), _unscoped(core.b))
    assert expected[0] != expected[1]
    with run_scope():
        first = types.FunctionType(codes[0], core.__dict__, "same")
        assert dependency_reach(first) == expected[0]
        gone = weakref.ref(first)
        del first
        gc.collect()
        assert gone() is None
        for i in range(1, 60):
            fn = types.FunctionType(codes[i % 2], core.__dict__, "same")
            assert dependency_reach(fn) == expected[i % 2], i
            del fn
            gc.collect()


def test_a_replaced_code_object_is_read_afresh(walkpkg):
    core = walkpkg
    with run_scope():
        fn = types.FunctionType(core.a.__code__, core.__dict__, "swap")
        assert dependency_reach(fn) == _unscoped(core.a)
        fn.__code__ = core.b.__code__
        assert dependency_reach(fn) == _unscoped(core.b)
        assert dependency_reach(fn) != _unscoped(core.a)


def test_a_changed_constant_or_rebound_global_changes_the_result(walkpkg, monkeypatch):
    core = walkpkg
    with run_scope():
        deps = function_dependencies(core.top)
        reach = dependency_reach(core.top)
        assert {"name": "SCALE", "kind": "constant", "value": 2.0} in deps
        monkeypatch.setattr(core, "SCALE", 3.0)
        moved = function_dependencies(core.top)
        assert {"name": "SCALE", "kind": "constant", "value": 3.0} in moved
        assert moved == _unscoped(core.top, function_dependencies)
        import walkpkg.helpers as helpers
        monkeypatch.setattr(helpers, "leaf", helpers.other_leaf)
        rebound = dependency_reach(core.top)
        assert rebound != reach
        assert rebound == _unscoped(core.top)
        assert function_dependencies(core.top) == _unscoped(
            core.top, function_dependencies)


def _rewrite(path, old, new, *, same_size=False):
    text = open(path).read()
    assert old in text
    if same_size:
        assert len(old) == len(new)
    stat = os.stat(path)
    with open(path, "w") as fh:
        fh.write(text.replace(old, new))
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))


def test_a_source_rewritten_inside_the_scope_is_read_afresh(walkpkg):
    import walkpkg.helpers as helpers
    with run_scope():
        before = dependency_reach(walkpkg.top)
        assert "walkpkg.helpers.leaf" in {e["key"] for e in before}
        _rewrite(helpers.__file__, "return leaf(x) * 2", "return other_leaf(x) * 2")
        after = dependency_reach(walkpkg.top)
        assert after == _unscoped(walkpkg.top)
        assert "walkpkg.helpers.other_leaf" in {e["key"] for e in after}
        _rewrite(helpers.__file__, "return other_leaf(x) * 2",
                 "return other_leaf(x) * 3", same_size=True)
        assert dependency_reach(walkpkg.top) == _unscoped(walkpkg.top)
        assert dependency_reach(walkpkg.top) != after


def test_writing_a_docstring_drops_the_kept_walk(walkpkg):
    from mathema.docstring import write_docstring
    with run_scope():
        dependency_reach(walkpkg.top)
        assert _run_scope._STATE.get(inventory._WALK)
        write_docstring(walkpkg.t2, "Intent:\n    The input.")
        assert not _run_scope._STATE.get(inventory._WALK)


def test_writing_claims_into_a_docstring_drops_the_kept_walk(walkpkg):
    from mathema.sync import write_claims_into_docstring
    import walkpkg.helpers as helpers
    path = helpers.__file__
    text = open(path).read().replace(
        "def leaf(x):\n",
        "def leaf(x):\n    '''One more.\n\n    Claims:\n        one: f(0) = 1\n    '''\n")
    with open(path, "w") as fh:
        fh.write(text)
    sys.modules.pop("walkpkg.helpers", None)
    import importlib
    helpers = importlib.import_module("walkpkg.helpers")
    with run_scope():
        dependency_reach(helpers.helper)
        assert _run_scope._STATE.get(inventory._WALK)
        assert write_claims_into_docstring(helpers.leaf, [("two", "f(1) = 2")])
        assert not _run_scope._STATE.get(inventory._WALK)


def test_a_call_cycle_gives_the_same_reach_from_every_node(walkpkg):
    nodes = ["head", "c1", "c2", "c3", "t1", "t2", "t3"]
    expected = {n: _unscoped(getattr(walkpkg, n)) for n in nodes}
    assert "walkpkg.core.c1" in {e["key"] for e in expected["c3"]}
    for order in itertools.islice(itertools.permutations(nodes), 0, 5040, 97):
        with run_scope():
            for n in order:
                assert dependency_reach(getattr(walkpkg, n)) == expected[n], (order, n)
            for n in reversed(order):
                assert dependency_reach(getattr(walkpkg, n)) == expected[n], (order, n)


def test_facts_injected_inside_the_scope_are_read(walkpkg):
    import walkpkg.helpers as helpers
    with run_scope():
        before = dependency_reach(walkpkg.top)
        stated = dataclasses.replace(analysis.analyze_source(helpers.helper),
                                     form="py:222222222222")
        helpers.helper.__mathema_facts__ = stated
        try:
            after = dependency_reach(walkpkg.top)
            assert after == _unscoped(walkpkg.top)
            assert after != before
            assert {"key": "walkpkg.helpers.helper", "kind": "function",
                    "form": "py:222222222222"} in after
        finally:
            del helpers.helper.__mathema_facts__
        assert dependency_reach(walkpkg.top) == before


def test_a_stated_scope_set_inside_the_scope_is_read(walkpkg):
    import walkpkg.helpers as helpers
    with run_scope():
        before = dependency_reach(walkpkg.helper)
        helpers.helper.__mathema_scope__ = {**helpers.__dict__,
                                            "leaf": helpers.other_leaf}
        try:
            after = dependency_reach(walkpkg.helper)
            assert after == _unscoped(walkpkg.helper)
            assert after != before
        finally:
            del helpers.helper.__mathema_scope__
        assert dependency_reach(walkpkg.helper) == before


_CALLS_GROWTH = '''\
from sample_targets import growth


def caller(x, r):
    return growth(x, r) + 1
'''


def test_a_frontend_registered_inside_the_scope_is_read(tmp_path, monkeypatch):
    from mathema.koine import frontends
    from tests.test_registered_frontend_supplies_the_body import TARGETS, _install
    frontends._reset_discovery()
    (tmp_path / "sample_targets.py").write_text(TARGETS)
    (tmp_path / "calls_growth.py").write_text(_CALLS_GROWTH)
    monkeypatch.syspath_prepend(str(tmp_path))
    for name in ("sample_targets", "calls_growth"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    import calls_growth
    try:
        with run_scope():
            before = dependency_reach(calls_growth.caller)
            _install(tmp_path, monkeypatch, "sample = sample_frontend:write\n")
            after = dependency_reach(calls_growth.caller)
            assert after == _unscoped(calls_growth.caller)
            assert after != before
    finally:
        frontends._reset_discovery()
        for name in ("sample_targets", "calls_growth", "sample_frontend"):
            sys.modules.pop(name, None)


class _Dispatcher:
    __slots__ = ("__wrapped__",)

    def __init__(self, fn):
        self.__wrapped__ = fn

    def __call__(self, *args):
        return self.__wrapped__(*args)


def test_a_callable_that_takes_no_weak_reference_is_read_every_time(walkpkg):
    import walkpkg.helpers as helpers
    dispatcher = _Dispatcher(helpers.helper)
    with pytest.raises(TypeError):
        weakref.ref(dispatcher)
    expected = dependency_reach(dispatcher)
    with run_scope():
        assert dependency_reach(dispatcher) == expected
        assert dependency_reach(dispatcher) == expected
