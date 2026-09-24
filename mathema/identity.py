# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Identity: the two Mathema hashes.

form   ; how it's written: rename/format-invariant structural hash
          (locals and parameters replaced by binding-order names).
sig    ; the coarsest facet of meaning: the typed shape of the transformation.

Line-anchored artifacts bind to form; everything else binds to meaning
(signature + lifted normal form, when available).
"""
from __future__ import annotations

import ast
import hashlib
import inspect


def local_names(fdef: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """Names bound inside the function (params, assignments, loop/with/comp
    targets, `except ... as name`), in order of first binding; the set
    that alpha-normalization is allowed to rename. Free names (imports,
    globals, builtins) stay.

    `except X as name` matters here for two reasons: form_hash should
    treat `except E as exc` and `except E as err` as the same shape (the
    handler variable's name is no more meaningful than any other local's;
    alpha-normalization already does this for every other binding
    kind), and analysis.py's scope-dependency scan (_global_captures())
    reuses this same function to decide what's "bound", without this
    case, any reference to a normal exception variable inside its own
    `except` block (e.g. `except Exception as exc: raise Y from exc`,
    completely ordinary code) was wrongly reported as an unresolved free
    name, since Python's implicit end-of-block `del exc` has nothing to
    do with whether the name is bound *within* the block at all."""
    order: list[str] = []
    seen: set[str] = set()

    def bind(name: str) -> None:
        if name not in seen:
            seen.add(name)
            order.append(name)

    args = fdef.args
    for a in (
        *args.posonlyargs, *args.args,
        *([args.vararg] if args.vararg else []),
        *args.kwonlyargs,
        *([args.kwarg] if args.kwarg else []),
    ):
        bind(a.arg)

    for node in ast.walk(fdef):
        if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                for n in ast.walk(t):
                    if isinstance(n, ast.Name):
                        bind(n.id)
        elif isinstance(node, ast.For):
            for n in ast.walk(node.target):
                if isinstance(n, ast.Name):
                    bind(n.id)
        elif isinstance(node, ast.comprehension):
            for n in ast.walk(node.target):
                if isinstance(n, ast.Name):
                    bind(n.id)
        elif isinstance(node, ast.withitem) and node.optional_vars is not None:
            for n in ast.walk(node.optional_vars):
                if isinstance(n, ast.Name):
                    bind(n.id)
        elif isinstance(node, ast.NamedExpr):
            bind(node.target.id)
        elif isinstance(node, ast.ExceptHandler) and node.name is not None:
            bind(node.name)
    return order


class _Alpha(ast.NodeTransformer):
    def __init__(self, mapping: dict[str, str]):
        self.mapping = mapping

    def visit_Name(self, node: ast.Name) -> ast.Name:
        if node.id in self.mapping:
            node.id = self.mapping[node.id]
        return node

    def visit_arg(self, node: ast.arg) -> ast.arg:
        self.generic_visit(node)
        if node.arg in self.mapping:
            node.arg = self.mapping[node.arg]
        return node

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> ast.ExceptHandler:
        # node.name is a bare string, not an ast.Name, visit_Name never
        # reaches it, so without this the handler's own binding
        # (`except E as exc:`) would stay unrenamed while every reference
        # to it inside the block got renamed, an inconsistent result.
        self.generic_visit(node)
        if node.name in self.mapping:
            node.name = self.mapping[node.name]
        return node


def normalized(fdef: ast.FunctionDef | ast.AsyncFunctionDef) -> ast.AST:
    """Alpha-normalized copy: locals renamed by binding order, docstring
    stripped, function name canonicalized (so recursion normalizes too)."""
    tree = ast.parse(ast.unparse(fdef))  # deep, location-free copy
    f = tree.body[0]
    body = f.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
        f.body = body or [ast.Pass()]
    mapping = {name: f"v{i}" for i, name in enumerate(local_names(f))}
    mapping[f.name] = "f"
    _Alpha(mapping).visit(f)
    f.name = "f"
    return f


def form_text(node) -> str:
    """The text a form hash is taken over: each node as its class name
    and its fields, with every empty list, absent field and None-valued
    field left out. Each Python version adds fields of its own to the
    tree (3.12 gives every function a `type_params=[]`), always empty
    by default, so a text that carries only the fields holding content
    reads the same under every supported interpreter."""
    if isinstance(node, ast.AST):
        parts = []
        for name in node._fields:
            value = getattr(node, name, None)
            if value is None or (isinstance(value, list) and not value):
                continue
            parts.append(f"{name}={form_text(value)}")
        return f"{type(node).__name__}({', '.join(parts)})"
    if isinstance(node, list):
        return "[" + ", ".join(form_text(v) for v in node) + "]"
    return repr(node)


def form_hash(fdef: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """The `form` identity: a 12-hex-char hash of the function's
    alpha-normalized AST (`normalized()`, locals/parameters replaced
    by binding-order names, so a pure rename doesn't change it, but any
    real structural change does), rendered by `form_text` so the hash
    is the same on every supported Python."""
    return hashlib.sha256(form_text(normalized(fdef)).encode()).hexdigest()[:12]


def signature_string(fn) -> str:
    """`fn`'s signature as `inspect.signature()` would render it
    (`"(x: float, y: float = 0.0) -> float"`). `"(?)"` if the signature
    can't be introspected at all (some builtins/C extensions)."""
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return "(?)"
    return str(sig)


def sig_hash(fn) -> str:
    """The `sig` identity: a 12-hex-char hash of `signature_string(fn)`,
    the coarsest facet of meaning, the typed shape of the
    transformation independent of the body."""
    return hashlib.sha256(signature_string(fn).encode()).hexdigest()[:12]
