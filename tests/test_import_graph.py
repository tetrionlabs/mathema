# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Structural guards on the package's import graph.

Two invariants, both established by the 2026-08 module restructuring:

1. The *top-level* intra-package import graph is a DAG. Python enforces
   this only lazily (a cycle crashes whichever import order hits it
   first), so an explicit check catches a new cycle at test time rather
   than in whatever consumer happens to import modules in the unlucky
   order.

2. `probing` is a sampling-engine leaf: it never imports `conjecture`,
   `spec`, `suggest`, or `claim_families`, not even inside a function
   body. Those modules sit above it; the old deferred imports that
   reached back down from probing were what held the package's big
   import cycle together.
"""
import ast
import os

PKG = os.path.join(os.path.dirname(__file__), os.pardir, "mathema")


def _module_name(path: str) -> str:
    rel = os.path.relpath(path, PKG)
    parts = rel[:-len(".py")].split(os.sep)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) if parts else "__init__"


def _intra_package_edges(top_level_only: bool):
    """{module: set(imported modules)} for `from .x import ...` /
    `from . import x` style imports, resolved to top-level module names
    (`symbolic._dot` counts as `symbolic`)."""
    edges: dict[str, set[str]] = {}
    for dirpath, _dirs, files in os.walk(PKG):
        if "__pycache__" in dirpath:
            continue
        for fname in files:
            if not fname.endswith(".py"):
                continue
            path = os.path.join(dirpath, fname)
            mod = _module_name(path)
            with open(path) as fh:
                tree = ast.parse(fh.read())
            nodes = (tree.body if top_level_only
                     else list(ast.walk(tree)))
            targets = edges.setdefault(mod.split(".")[0] or "__init__", set())
            for node in nodes:
                if not isinstance(node, ast.ImportFrom) or not node.level:
                    continue
                # resolve the relative import to a package-rooted name
                if node.module:
                    name = node.module.split(".")[0]
                    targets.add(name)
                else:
                    for alias in node.names:
                        targets.add(alias.name.split(".")[0])
    return edges


def test_top_level_import_graph_is_acyclic():
    edges = _intra_package_edges(top_level_only=True)
    # iterative DFS three-color cycle detection
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {m: WHITE for m in edges}
    for root in edges:
        if color[root] != WHITE:
            continue
        stack = [(root, iter(sorted(edges.get(root, ()))))]
        color[root] = GRAY
        while stack:
            mod, it = stack[-1]
            advanced = False
            for dep in it:
                if dep == mod or dep not in color:
                    continue
                if color[dep] == GRAY:
                    cycle = [m for m, _ in stack] + [dep]
                    raise AssertionError(
                        "top-level import cycle: " + " -> ".join(cycle))
                if color[dep] == WHITE:
                    color[dep] = GRAY
                    stack.append((dep, iter(sorted(edges.get(dep, ())))))
                    advanced = True
                    break
            if not advanced:
                color[mod] = BLACK
                stack.pop()


def test_probing_never_imports_the_layers_above_it():
    forbidden = {"conjecture", "spec", "suggest", "claim_families"}
    with open(os.path.join(PKG, "probing.py")) as fh:
        tree = ast.parse(fh.read())
    hit = [node.module or "" for node in ast.walk(tree)
           if isinstance(node, ast.ImportFrom) and node.level
           and (node.module or "").split(".")[0] in forbidden]
    hit += [alias.name for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.level
            and not node.module
            for alias in node.names if alias.name in forbidden]
    assert not hit, f"probing.py imports upward-layer modules: {hit}"


def _module_level_statements(tree):
    """Statements that run at import time: module body, descending
    through if/try/with but never into a function or class."""
    stack = list(tree.body)
    while stack:
        node = stack.pop()
        yield node
        for field in ("body", "orelse", "finalbody"):
            if isinstance(node, (ast.If, ast.Try, ast.With)):
                stack += getattr(node, field, []) or []
        for handler in getattr(node, "handlers", []) or []:
            stack += handler.body


def test_interfaces_is_never_imported_at_module_level():
    """`interfaces` re-exports and serves; nothing in the library reaches
    back into it as it loads. A deferred import inside a function is the
    supported way to reach one (cli's `mcp serve` does exactly that);
    an import-time one would make an optional extra's dependency
    reachable from a base install."""
    offenders = []
    for dirpath, _dirs, files in os.walk(PKG):
        if "__pycache__" in dirpath or os.sep + "interfaces" in dirpath:
            continue
        for fname in files:
            if not fname.endswith(".py"):
                continue
            path = os.path.join(dirpath, fname)
            with open(path) as fh:
                tree = ast.parse(fh.read())
            for node in _module_level_statements(tree):
                if not isinstance(node, ast.ImportFrom) or not node.level:
                    continue
                if (node.module or "").split(".")[0] == "interfaces":
                    offenders.append(_module_name(path))
                elif not node.module:
                    offenders += [_module_name(path) for a in node.names
                                  if a.name == "interfaces"]
    assert not offenders, f"modules importing interfaces: {sorted(set(offenders))}"
