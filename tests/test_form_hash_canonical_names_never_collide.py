# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A form hash is unchanged by a pure rename and changed by anything
else, so the names it gives locals and the function itself can never
be names the source already uses. A parameter that shadows the
function's name is a local like any other, and a free name is kept as
written whatever it is called."""
import ast

from mathema.identity import form_hash


def _hash(src: str) -> str:
    return form_hash(ast.parse(src).body[0])


def test_a_parameter_named_like_its_function_is_renamed_like_any_local():
    assert _hash("def g(g):\n    return g + 1\n") == _hash("def g(x):\n    return x + 1\n")


def test_a_free_name_spelled_like_a_canonical_local_is_not_a_local():
    assert _hash("def a(x):\n    return v0\n") != _hash("def a(x):\n    return x\n")


def test_a_call_to_a_global_f_is_not_a_recursive_call():
    assert _hash("def a(x):\n    return f(x)\n") != _hash("def a(x):\n    return a(x)\n")


def test_recursion_still_hashes_the_same_under_a_rename():
    assert _hash("def a(x):\n    return a(x - 1)\n") == _hash("def b(y):\n    return b(y - 1)\n")


def test_normalizing_a_normalized_function_changes_nothing():
    from mathema.identity import form_text, normalized
    for src in ("def g(x, y):\n    t = x + y\n    return g(t)\n",
                "def a(x):\n    for i in range(x):\n        x += i\n    return x\n"):
        once = normalized(ast.parse(src).body[0])
        assert form_text(normalized(once)) == form_text(once)
