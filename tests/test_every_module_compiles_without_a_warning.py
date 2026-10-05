# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Installing mathema byte-compiles every module, and a module that
raises a SyntaxWarning (an invalid escape sequence in a docstring)
prints it at the user's first install or import."""
import pathlib
import warnings

_PACKAGE = pathlib.Path(__file__).resolve().parent.parent / "mathema"


def test_no_module_raises_a_syntax_warning():
    found = []
    for path in sorted(_PACKAGE.rglob("*.py")):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        found += [f"{path.relative_to(_PACKAGE)}: {w.message}"
                  for w in caught if issubclass(w.category, SyntaxWarning)]
    assert not found, found
