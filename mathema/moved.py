# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Moved functions: a verified record whose key no longer resolves (an
orphan) paired with a function that has no record but the same form
hash. The pairing is a suggestion for a human, never an action: the
rename itself is `mathema accept NEW --as reconciled --from OLD`.

The project's functions are found by parsing source, never by
importing it, so looking for a move runs no project code. The form
hash is computed from the AST alone (`identity.form_hash`), which is
what makes that possible."""
from __future__ import annotations

import ast
import os

_SKIP_DIRS = {".git", ".hg", ".svn", ".venv", "venv", "env", ".tox",
              ".nox", "node_modules", "__pycache__", ".mathema",
              "site-packages", "build", "dist", ".eggs"}


def rename_command(new_key: str, old_key: str) -> str:
    """The exact command that renames `old_key`'s record to `new_key`."""
    return f"mathema accept {new_key} --as reconciled --from {old_key}"


def _function_defs(tree: ast.Module, prefix: str):
    """Intent:
        Every function a store key can name in one parsed module:
        module-level functions and methods of (possibly nested)
        classes, as `(qualified_key, FunctionDef)` pairs.
    """
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield f"{prefix}.{node.name}", node
        elif isinstance(node, ast.ClassDef):
            yield from _function_defs(ast.Module(body=node.body,
                                                 type_ignores=[]),
                                      f"{prefix}.{node.name}")


def _python_files(root: str):
    """Intent:
        The `.py` files under `root`, skipping version control, virtual
        environments (any directory holding a `pyvenv.cfg`), build
        output, caches and the store itself.
    """
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            d for d in dirnames
            if d not in _SKIP_DIRS and not d.startswith(".")
            and not d.endswith(".egg-info")
            and not os.path.exists(os.path.join(dirpath, d, "pyvenv.cfg")))
        for name in sorted(filenames):
            if name.endswith(".py"):
                yield os.path.join(dirpath, name)


def project_forms(root: str) -> dict:
    """Intent:
        `{form_hash: [key, ...]}` over every function defined in the
        project's source, keyed the way the store keys them (the
        dotted module name the file imports as, then the qualname). A
        file that does not parse, or whose name is not importable, is
        skipped.
    """
    from .identity import form_hash
    from .targets import TargetError, _dotted_name_for_file
    out: dict = {}
    for path in _python_files(root):
        try:
            module, _ = _dotted_name_for_file(path)
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read(), filename=path)
        except (TargetError, SyntaxError, UnicodeDecodeError, OSError,
                ValueError):
            continue
        for key, fdef in _function_defs(tree, module):
            try:
                form = form_hash(fdef)
            except Exception:
                continue
            out.setdefault(form, []).append(key)
    return out


def find_moved(root: str, verified: dict, declared: dict,
               resolve) -> dict:
    """Intent:
        Pair every orphan record with the unrecorded functions sharing
        its form hash: `{old_key: [new_key, ...]}`, only orphans with
        at least one candidate. `verified` and `declared` are the
        loaded layers (`load_verified`, `load_declared`), `resolve`
        maps a key to its live callable or None. An orphan is a
        verified key that `resolve` cannot find and that holds more
        than compendium testimony (a library that is merely not
        installed here is not a move). A candidate is a function in
        the project's source, or a declared key that resolves, with no
        verified record.

    Notes:
        Source is parsed only when an orphan exists, so a store with
        none pays one resolve per key and nothing else.
    """
    orphans: dict = {}
    for key, info in verified.items():
        entry = (info or {}).get("entry") or {}
        form = (entry.get("identity") or {}).get("form")
        rows = entry.get("claims") or []
        if not form or (rows and all(
                (r.get("meta") or {}).get("mathema.surface") == "compendium"
                for r in rows if isinstance(r, dict))):
            continue
        if resolve(key) is None:
            orphans[key] = form
    if not orphans:
        return {}
    by_form = {form: [k for k in keys if k not in verified]
               for form, keys in project_forms(root).items()}
    for key in sorted(set(declared) - set(verified)):
        fn = resolve(key)
        if fn is None:
            continue
        try:
            from .analysis import quiet_facts
            facts = quiet_facts(fn)
        except Exception:
            facts = None
        form = getattr(facts, "form", None)
        if form and key not in by_form.setdefault(form, []):
            by_form[form].append(key)
    out: dict = {}
    for old, form in sorted(orphans.items()):
        new = sorted(k for k in by_form.get(form, []) if k != old)
        if new:
            out[old] = new
    return out
