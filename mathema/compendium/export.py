# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Export a library's own verified claims into a compendium SKELETON.

A library author who has run `mathema verify` on their package holds a
verified store of claims about their own functions. `export_compendium`
transfers that into a compendium pack a downstream project can consume:
verified bound/behavioural claims become `claims`, verified `raises(...)`
contracts become `raises_when`, and any `nan`/`inf` a function returns
by a recognisable AST guard becomes `nan_when`. What cannot be read from
positive claims (prose limitations, and the nan regions no guard spells
out) is left as an explicit TODO.

The result is deliberately a PARTIAL SKELETON: the header says so, a
curator reviews and completes it, and, crucially, a consumer still has
to verify or trust it, a compendium row is DECLARED until then, never
silently trusted (see the package docstring).
"""
from __future__ import annotations

import ast


def _is_nonfinite_literal(node) -> bool:
    """Whether an AST expression is a nan/inf literal reference:
    `float('nan')`/`float('inf')`, `math.nan`/`np.nan`/`numpy.inf`, or a
    bare `nan`/`inf` name."""
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "float" and len(node.args) == 1
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
            and node.args[0].value.strip().lstrip("+-").lower() in ("nan", "inf")):
        return True
    if isinstance(node, ast.Attribute) and node.attr in ("nan", "inf"):
        return True
    return isinstance(node, ast.Name) and node.id in ("nan", "inf")


def ast_nan_regions(tree) -> list[str]:
    """The conditions under which a function returns nan/inf, read
    statically from its AST. An `if <cond>: return float('nan')` guard
    yields `<cond>`; a nan/inf returned at the top level (no guard)
    yields the sentinel `'True'` (it always can). Coarse and best-effort,
    a skeleton hint a curator refines, never an authoritative region."""
    regions: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            if any(isinstance(s, ast.Return) and s.value is not None
                   and _is_nonfinite_literal(s.value) for s in node.body):
                try:
                    regions.append(ast.unparse(node.test))
                except Exception:
                    continue
    # an unconditional nan/inf return (a direct child of the body)
    for stmt in getattr(tree, "body", []):
        if (isinstance(stmt, ast.Return) and stmt.value is not None
                and _is_nonfinite_literal(stmt.value)):
            regions.append("True")
    deduped: list[str] = []
    for region in regions:
        if region not in deduped:
            deduped.append(region)
    return deduped


def _exception_of(statement: str) -> str | None:
    """The exception name in a `raises(f(...), Exc)` claim statement, or
    None when the statement is not a typed raises claim."""
    m = ast.parse(statement.strip(), mode="eval").body if statement else None
    if (isinstance(m, ast.Call) and isinstance(m.func, ast.Name)
            and m.func.id == "raises" and len(m.args) == 2
            and isinstance(m.args[1], ast.Name)):
        return m.args[1].id
    return None


_SUPPORTED = ("proven", "holds")


def export_compendium(library: str, root: str = ".") -> dict:
    """Intent:
        A partial compendium pack for `library`, built from its verified
        store: `{package, versions, functions: {key: {...}}, _skeleton}`.
        Only verified (proven/holds) claims transfer. A bound/behavioural
        claim becomes a `claims` row; a `raises(...)` claim becomes a
        `raises_when` row; AST-detected nan/inf returns become `nan_when`;
        `limitations` is a single TODO stub.
    Notes:
        `versions` is stamped `">=<installed>"` from the running package.
        Every function carries `provenance: exported-skeleton` so a
        reader never mistakes it for a curated, complete entry.
    """
    from ..conjecture import _resolve_func_ref
    from ..spec import load_verified
    import inspect

    installed = _installed(library)
    functions: dict = {}
    for key, info in sorted(load_verified(root).items()):
        if key.split(".")[0] != library:
            continue
        entry = (info.get("entry") if isinstance(info, dict) else info) or {}
        claims, raises_when = [], []
        for c in entry.get("claims") or []:
            if c.get("verdict") not in _SUPPORTED:
                continue
            statement = c.get("statement") or c.get("law") or ""
            # skip internal freshness / pseudo-claims (a bare identifier
            # whose statement is just its own name, e.g. dependencies_
            # current), they are not library behaviour to publish
            if not statement or statement == c.get("name"):
                continue
            try:
                exc = _exception_of(statement)
            except SyntaxError:
                exc = None
            if exc is not None:
                raises_when.append(
                    {"condition": c.get("condition")
                     or "TODO: the input region that raises",
                     "exception": exc})
            else:
                claims.append({"name": c.get("name"), "statement": statement,
                               "route": c.get("route", "best")})
        params, nan_when = [], []
        fn = None
        try:
            fn = _resolve_func_ref(key)
        except Exception:
            fn = None
        if fn is not None:
            try:
                params = list(inspect.signature(fn).parameters)
            except (TypeError, ValueError):
                params = []
            try:
                from ..analysis import get_tree
                nan_when = ast_nan_regions(get_tree(fn)[1])
            except Exception:
                nan_when = []
        functions[key] = {
            "params": params,
            **({"claims": claims} if claims else {}),
            **({"raises_when": raises_when} if raises_when else {}),
            **({"nan_when": nan_when} if nan_when else {}),
            "limitations": ["TODO: review and complete this skeleton entry"],
            "provenance": "exported-skeleton",
        }
    return {"package": library,
            "versions": f">={installed}" if installed else "*",
            "functions": functions,
            "_skeleton": True}


def _installed(library: str) -> str | None:
    try:
        from importlib import metadata
        return metadata.version(library)
    except Exception:
        return None


_SKELETON_HEADER = (
    "PARTIAL SKELETON exported from this project's verified claims.\n"
    "Review and complete before shipping: curate `limitations`, fill any\n"
    "`TODO` regions, and confirm `nan_when` (AST-guessed from nan/inf\n"
    "returns). A compendium row is DECLARED until a consumer verifies or\n"
    "accepts it, never silently trusted.")


def write_compendium(library: str, root: str = ".", out_dir: str | None = None
                     ) -> str:
    """Write `export_compendium(library)` to a version-suffixed YAML under
    `out_dir` (default `<root>/compendium/<library>/`), returning the
    path. The filename carries the installed version as a suffix
    (`<library>-<major.minor>.yaml`), the lightweight convention for
    letting several version-specific packs coexist in one directory."""
    import os

    from ..spec import write_yaml
    pack = export_compendium(library, root)
    installed = _installed(library)
    suffix = ("-" + ".".join(installed.split(".")[:2])) if installed else ""
    out_dir = out_dir or os.path.join(root, "compendium", library)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{library}{suffix}.yaml")
    body = {k: v for k, v in pack.items() if k != "_skeleton"}
    write_yaml(path, body, header=_SKELETON_HEADER)
    return path
