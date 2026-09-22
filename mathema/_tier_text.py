# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`describe`'s rendering: the five-tier ladder `tiers.py` computes
node-level text for, shown as plain indented lines. No callee
inlining and no name shortening, so a call site renders as an ordinary
statement and a long name prints in full.
"""
from __future__ import annotations

import ast

from . import tiers as tiers_mod

_INDENT = "    "


def _line(text: str, depth: int) -> str:
    return _INDENT * depth + text


def _stmt_lines(stmt: ast.stmt, tier: str, *, name_map: dict | None,
                seq_params: frozenset, depth: int) -> list[str]:
    if isinstance(stmt, ast.If):
        cond = tiers_mod.render_condition(stmt.test, tier, name_map=name_map)
        header = cond.text if cond.available else "?"
        lines = [_line(f"if {header}:", depth)]
        lines.extend(_block_lines(stmt.body, tier, name_map=name_map,
                                  seq_params=seq_params, depth=depth + 1))
        if stmt.orelse:
            lines.append(_line("else:", depth))
            lines.extend(_block_lines(stmt.orelse, tier, name_map=name_map,
                                      seq_params=seq_params, depth=depth + 1))
        return lines
    if isinstance(stmt, ast.For):
        kind_label = None
        if tier == "structural":
            from .symbolic import bare_seq_name, classify_loop_header, seq_one_colon
            classified = classify_loop_header(stmt, set(seq_params))
            if classified is not None:
                kind_label = tiers_mod.LOOP_KIND_LABEL.get(classified[0])
            elif isinstance(stmt.target, ast.Name):
                for seq_name in seq_params:
                    if seq_one_colon(stmt.iter, seq_name) or bare_seq_name(stmt.iter, seq_name):
                        kind_label = "fold"
                        break
        header = tiers_mod.render_loop_header(stmt, tier, seq_params=seq_params,
                                              kind_label=kind_label, name_map=name_map)
        # render_loop_header's own text is already tier-appropriate and
        # self-contained, "for x in y:" at source/normalized, a bare
        # "loop"/"fold" label at structural, "∀ i ∈ [...]" at canonical,
        # never a fragment that needs an outer "for ...:" wrapper.
        lines = [_line(header.text if header.available else "(loop)", depth)]
        lines.extend(_block_lines(stmt.body, tier, name_map=name_map,
                                  seq_params=seq_params, depth=depth + 1))
        return lines
    if tier == "structural":
        return [_line("return" if isinstance(stmt, ast.Return) else "step", depth)]
    if tier == "source":
        text = ast.unparse(stmt)
    elif tier == "normalized":
        text = tiers_mod.unparse_normalized(stmt, name_map)
    else:
        raise ValueError(f"_stmt_lines: unsupported tier {tier!r}")
    return [_line(line, depth) for line in text.split("\n")]


def _block_lines(stmts: list[ast.stmt], tier: str, *, name_map: dict | None,
                 seq_params: frozenset, depth: int) -> list[str]:
    if not stmts:
        return [_line("(empty)", depth)]
    lines: list[str] = []
    for stmt in stmts:
        lines.extend(_stmt_lines(stmt, tier, name_map=name_map,
                                 seq_params=seq_params, depth=depth))
    return lines


def render_structure_plain(fdef: ast.FunctionDef, tier: str, *,
                           name_map: dict | None = None,
                           seq_params: frozenset = frozenset()) -> str:
    """The `source`/`normalized`/`structural` tiers, as plain indented
    counterpart. Every statement gets *some* line, same as the diagram
    renderer's own guarantee; nothing is silently dropped."""
    if tier not in ("source", "normalized", "structural"):
        raise ValueError(f"render_structure_plain: tier {tier!r} isn't part of "
                         "this rendering; use render_lifted_plain for 'lifted'")
    from .symbolic import strip_docstring

    body = strip_docstring(fdef.body)
    return "\n".join(_block_lines(body, tier, name_map=name_map,
                                  seq_params=seq_params, depth=0))


def _sympy_node_lines(node, depth: int = 0) -> list[str]:
    import sympy

    if isinstance(node, sympy.Symbol):
        label = f"Symbol({node.name})"
    elif isinstance(node, sympy.Dummy):
        label = f"Dummy({node.name})"
    elif isinstance(node, sympy.Number) or not getattr(node, "args", ()):
        label = f"{type(node).__name__}({node})"
    else:
        label = type(node).__name__
    lines = [_line(label, depth)]
    for child in getattr(node, "args", ()):
        lines.extend(_sympy_node_lines(child, depth + 1))
    return lines


def render_lifted_plain(expr) -> str:
    """The `lifted` tier's zero-install rendering: the same real sympy
    connectors, shown here as plain 4-space indentation instead."""
    return "\n".join(_sympy_node_lines(expr))
