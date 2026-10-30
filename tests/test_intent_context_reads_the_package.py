# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`docstring.intent_context` reports the intent around a function at
every level: the function, its module, its package (the package's
`__init__.py` docstring, else the package directory's README.md), and
the codebase README. Context is reported, never inherited: a function
that states no intent of its own is still a gap."""
import importlib
import sys

import pytest

from mathema.docstring import docstring_sync_checklist, intent_context


def _forget(prefix):
    for name in [m for m in sys.modules
                 if m == prefix or m.startswith(prefix + ".")]:
        del sys.modules[name]


@pytest.fixture
def tree(tmp_path, monkeypatch):
    (tmp_path / "README.md").write_text(
        "# demo\n\n## Intent\n\nA toy project.\n")
    a = tmp_path / "ctxinit"
    a.mkdir()
    (a / "__init__.py").write_text(
        '"""Helpers.\n\nIntent:\n    Shapes values for display.\n"""\n')
    (a / "m.py").write_text(
        "def bare(x):\n    return x\n\n\n"
        "def stated(x):\n    \"\"\"Doubles x.\"\"\"\n    return 2 * x\n")
    b = tmp_path / "ctxreadme"
    b.mkdir()
    (b / "__init__.py").write_text("")
    (b / "README.md").write_text("# b\n\nIntent:\n    Rounds things.\n")
    (b / "m.py").write_text("def f(x):\n    return x\n")
    (tmp_path / "ctxflat.py").write_text("def g(x):\n    return x\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    for p in ("ctxinit", "ctxreadme", "ctxflat"):
        _forget(p)
    yield tmp_path
    for p in ("ctxinit", "ctxreadme", "ctxflat"):
        _forget(p)


def test_the_package_level_reads_init_first(tree):
    fn = importlib.import_module("ctxinit.m").stated
    ctx = intent_context(fn, root=str(tree))
    assert set(ctx) == {"function", "module", "package", "readme"}
    assert ctx["package"] == {"text": "Shapes values for display.",
                              "evidence": "explicit"}
    assert ctx["function"] == {"text": "Doubles x.", "evidence": "implicit"}
    assert ctx["module"] is None
    assert ctx["readme"]["text"] == "A toy project."


def test_the_package_level_falls_back_to_its_readme(tree):
    fn = importlib.import_module("ctxreadme.m").f
    ctx = intent_context(fn, root=str(tree))
    assert ctx["package"] == {"text": "Rounds things.",
                              "evidence": "explicit"}


def test_a_module_outside_any_package_has_no_package_level(tree):
    fn = importlib.import_module("ctxflat").g
    assert intent_context(fn, root=str(tree))["package"] is None


def test_context_is_never_inherited(tree):
    fn = importlib.import_module("ctxinit.m").bare
    ctx = intent_context(fn, root=str(tree))
    assert ctx["function"] is None
    assert ctx["package"]["text"] == "Shapes values for display."


def test_the_checklist_shows_the_package_level(tree):
    from mathema.docstring import docstring_sync
    fn = importlib.import_module("ctxinit.m").stated
    lines = docstring_sync_checklist(docstring_sync(fn, root=str(tree)))
    (ctx_line,) = [ln for ln in lines if ln.startswith("· intent context")]
    assert ctx_line == ("· intent context: function ✓ implicit, module ✗, "
                        "package ✓ explicit, readme ✓ explicit (not scored)")
