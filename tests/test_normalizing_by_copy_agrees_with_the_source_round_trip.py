# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`normalized()` copies a function's tree with `copy.deepcopy`. Up to
0.6.5 it copied by printing the tree and parsing the text back
(`ast.parse(ast.unparse(fdef))`). For any tree parsed from source the
two copies give the same form text, so no stored form hash moves. They
differ on exactly one kind of tree: one whose names are not Python
identifiers, such as an already normalized function (`def <self>(<local
0>)`), whose printed text does not parse back. There the round trip
raised, and the copy normalizes it to itself."""
import ast
import sys

import pytest

from mathema.identity import _Alpha, form_text, local_names, normalized


def _normalized_by_round_trip(fdef):
    # the 0.6.5 algorithm, kept here as the reference
    tree = ast.parse(ast.unparse(fdef))
    f = tree.body[0]
    body = f.body
    if body and isinstance(body[0], ast.Expr) \
            and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
        f.body = body or [ast.Pass()]
    mapping = {name: f"<local {i}>" for i, name in enumerate(local_names(f))}
    if f.name not in mapping:
        mapping[f.name] = "<self>"
    _Alpha(mapping).visit(f)
    f.name = "<self>"
    return f


SOURCES = {
    "nested f-string with a format spec":
        'def f(x, w):\n    return f"{x!r:>{w}} and {x:.{w}f}"\n',
    "implicitly joined strings":
        'def f(x):\n    return "a" "b" f"{x}" u"c"\n',
    "a literal past the float range":
        'def f(x):\n    return x * 1e309 + 1e309j\n',
    "a negative zero":
        'def f(x):\n    return -0.0 + x\n',
    "walrus and comprehension":
        'def f(xs):\n    return [y for x in xs if (y := x * 2) > 1]\n',
    "starred and keyword-only":
        'def f(*args, k=1, **kw):\n    a, *b = args\n    return (*b, k, kw)\n',
    "nested function and nonlocal":
        'def f(x):\n    t = 0\n    def g():\n        nonlocal t\n        t += x\n'
        '    g()\n    return t\n',
    "decorated with a docstring only":
        '@staticmethod\ndef f(x):\n    """doc"""\n',
    "async with await and async for":
        'async def f(xs):\n    async for x in xs:\n        await x\n'
        '    async with xs as y:\n        return y\n',
    "match statement":
        'def f(x):\n    match x:\n        case [a, *rest] if a > 0:\n'
        '            return rest\n        case {"k": v}:\n            return v\n'
        '        case _:\n            return None\n',
    "parenthesised tuple and slices":
        'def f(a):\n    return (a[1:2, ::3], a[...], (1,))\n',
}
if sys.version_info >= (3, 12):
    SOURCES["type parameters"] = 'def f[T](x: T) -> T:\n    return x\n'


@pytest.mark.parametrize("source", SOURCES.values(), ids=SOURCES.keys())
def test_the_copy_and_the_round_trip_give_the_same_form_text(source):
    fdef = ast.parse(source).body[0]
    assert form_text(normalized(fdef)) == \
        form_text(_normalized_by_round_trip(fdef))


def test_an_already_normalized_function_is_the_one_tree_they_differ_on():
    once = normalized(ast.parse("def g(x):\n    y = x + 1\n    return y\n").body[0])
    with pytest.raises(SyntaxError):
        _normalized_by_round_trip(once)
    assert form_text(normalized(once)) == form_text(once)
