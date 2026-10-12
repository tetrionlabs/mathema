# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Injected facts are the facts of a callable at every entry.

A callable carrying `__mathema_facts__` is read through those facts
wherever mathema analyses a callable, never through the source of the
wrapper that carries them. `effective_facts` is the one place that
decides this, so no module calls `analyze_source` directly.
"""
import ast
import inspect
import pathlib
from dataclasses import replace

import pytest

import mathema
from mathema.analysis import analyze_source, quiet_facts
from mathema.symbolic import try_prove


def _double(x: float) -> float:
    """Twice x."""
    return 2 * x


def _halve(y: float) -> float:
    """Half y.

    Claims:
        halves: f(2*y) == y
    """
    return y / 2


def _proxy(impl, params, form="ext:0011223344ab"):
    """A callable shaped like an adaptor proxy: an opaque closure body,
    an empty module, a signature of its own and injected facts with no
    syntax tree and a namespaced form."""
    def proxy(*args, **kwargs):
        return impl(*args, **kwargs)
    proxy.__name__ = impl.__name__
    proxy.__qualname__ = f"ext:src/{impl.__name__}#{impl.__name__}"
    proxy.__module__ = ""
    proxy.__signature__ = inspect.Signature([
        inspect.Parameter(p, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        for p in params])
    proxy.__mathema_facts__ = replace(analyze_source(impl), tree=None,
                                      form=form)
    return proxy


def test_a_bound_proxy_is_described_by_its_injected_facts():
    g = _proxy(_halve, ["y"])
    r = try_prove(_double, analyze_source(_double), "f(g(x))", "x", "==",
                  funcs={"g": g})
    assert r.status == "unliftable"
    assert "ext:0011223344ab" in r.sketch, r.sketch
    # the wrapper takes no named parameters and calls `impl`; neither
    # may surface as a fact about g
    assert "no-parameters" not in r.sketch, r.sketch
    assert "impl" not in r.sketch, r.sketch


def test_effective_facts_returns_the_injected_facts():
    from mathema.analysis import effective_facts
    g = _proxy(_halve, ["y"])
    assert effective_facts(g) is g.__mathema_facts__
    assert effective_facts(g).params == ["y"]


def test_effective_facts_analyses_a_plain_callable():
    from mathema.analysis import effective_facts
    facts = effective_facts(_double)
    assert facts.params == ["x"]
    assert facts.tree is not None


def test_quiet_facts_honours_injected_facts():
    g = _proxy(_halve, ["y"])
    assert quiet_facts(g) is g.__mathema_facts__


def test_docstring_write_back_refuses_a_callable_with_injected_facts():
    from mathema.sync import write_claims_into_docstring
    g = _proxy(_halve, ["y"])
    with pytest.raises(ValueError, match="injected facts"):
        write_claims_into_docstring(g, [("doubles", "f(y) == y / 2")])


def _analyze_source_calls(tree):
    """(enclosing function name, line) for every call to
    `analyze_source` in a module's syntax tree, by bare name or as an
    attribute."""
    found = []

    def walk(node, owner):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                walk(child, child.name)
                continue
            if isinstance(child, ast.Call):
                fn = child.func
                name = fn.id if isinstance(fn, ast.Name) else \
                    fn.attr if isinstance(fn, ast.Attribute) else None
                if name == "analyze_source":
                    found.append((owner, child.lineno))
            walk(child, owner)
    walk(tree, None)
    return found


def test_no_module_analyses_a_callable_around_effective_facts():
    package = pathlib.Path(mathema.__file__).parent
    calls = []
    for path in sorted(package.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        calls += [(str(path.relative_to(package)), owner, line)
                  for owner, line in _analyze_source_calls(tree)]
    stray = [c for c in calls
             if (c[0], c[1]) != ("analysis.py", "effective_facts")]
    assert stray == []
    assert [c[:2] for c in calls] == [("analysis.py", "effective_facts")]
