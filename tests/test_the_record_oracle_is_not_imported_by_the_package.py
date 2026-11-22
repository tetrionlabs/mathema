# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The record-language oracle is a test helper: no module of the
package imports it, so it is never a route a user reaches."""
import ast
import pathlib

PACKAGE = pathlib.Path(__file__).resolve().parent.parent / "mathema"
NAMES = ("record_language", "_record_language_oracle")


def _imported(path: pathlib.Path) -> set:
    found = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.add(node.module or "")
            found.update(f"{node.module or ''}.{alias.name}" for alias in node.names)
    return found


def test_no_module_of_the_package_imports_the_record_oracle():
    found = [(str(path.relative_to(PACKAGE)), name)
             for path in sorted(PACKAGE.rglob("*.py"))
             for name in _imported(path) if name.rsplit(".", 1)[-1] in NAMES]
    assert found == []
    assert not (PACKAGE / "record_language.py").exists()
