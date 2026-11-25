# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The raise reader (`read_raise_path`) resolves names only where the
function cannot change them: a name the function assigns through
`global` or `nonlocal` is not read as the builtin or global it held when
the function was defined. An `import` is read as finishing only when the
module is a real module in `sys.modules` and `__import__` is the
builtin one. A builtin constructor that checks its arguments, given an
argument whose type is not known, may run that argument's own code, so
the path is not read as ending in an exception either."""
import ast
import builtins
import inspect
import sys
import textwrap

import pytest

from mathema._raise_reading import ANY, ReadRaise, UnreadRaise, ValueKind, read_raise_path


def _read(fn, kinds):
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn))).body[0]
    body = [s for s in tree.body if not isinstance(s, (ast.Global, ast.Nonlocal))]
    return read_raise_path(fn, [("stmt", s) for s in body[:-1]], body[-1], kinds)


def rebinds_the_class(x):
    global ValueError
    ValueError = KeyError  # noqa: F841
    raise ValueError("neg")


def rebinds_str(x: float):
    global str
    str = len  # noqa: F841
    raise ValueError(str(x))


def _enclosing():
    E = ValueError

    def rebinds_through_nonlocal(x):
        nonlocal E
        E = KeyError
        raise E("neg")
    return rebinds_through_nonlocal


def builds_a_group_of(x):
    raise ExceptionGroup("m", x)  # noqa: F821


def builds_a_decode_error_at(x):
    raise UnicodeDecodeError("a", b"", x, 1, "r")


@pytest.mark.parametrize("fn,kinds", [
    (rebinds_the_class, {"x": ANY}),
    (rebinds_str, {"x": ValueKind(frozenset({float}))}),
    (_enclosing(), {"x": ANY}),
], ids=["global class", "global str", "nonlocal class"])
def test_a_name_the_function_rebinds_is_not_read(fn, kinds):
    reading = _read(fn, kinds)
    assert isinstance(reading, UnreadRaise), reading
    assert not reading.halts or fn is rebinds_str, reading


@pytest.mark.skipif(not hasattr(builtins, "ExceptionGroup"), reason="Python 3.11 or later")
@pytest.mark.parametrize("fn", [builds_a_group_of, builds_a_decode_error_at],
                         ids=lambda f: f.__name__)
def test_a_checking_constructor_given_an_unknown_argument_is_not_read_to_finish(fn):
    reading = _read(fn, {"x": ANY})
    assert isinstance(reading, UnreadRaise) and not reading.halts, reading


@pytest.mark.skipif(not hasattr(builtins, "ExceptionGroup"), reason="Python 3.11 or later")
def test_a_checking_constructor_given_known_scalars_still_ends_in_an_exception():
    reading = _read(builds_a_decode_error_at, {"x": ValueKind(frozenset({int}), 5.0)})
    assert isinstance(reading, UnreadRaise) and reading.halts, reading


_IMPORTS = '''
def imports_it(x):
    import {name}
    raise ValueError("neg")
'''


def test_an_import_of_a_module_blocked_in_sys_modules_is_not_read(monkeypatch):
    monkeypatch.setitem(sys.modules, "mathema_test_blocked_module", None)
    space: dict = {}
    exec(_IMPORTS.format(name="mathema_test_blocked_module"), space)
    fn = space["imports_it"]
    with pytest.raises(ImportError):
        fn(1)
    tree = ast.parse(_IMPORTS.format(name="mathema_test_blocked_module")).body[0]
    reading = read_raise_path(fn, [("stmt", tree.body[0])], tree.body[1], {"x": ANY})
    assert not isinstance(reading, ReadRaise), reading


def test_an_import_through_a_replaced_import_function_is_not_read():
    def refusing(*args, **kwargs):
        raise KeyError("no imports")
    space: dict = {"__builtins__": {**vars(builtins), "__import__": refusing}}
    exec(_IMPORTS.format(name="math"), space)
    fn = space["imports_it"]
    with pytest.raises(KeyError):
        fn(1)
    tree = ast.parse(_IMPORTS.format(name="math")).body[0]
    reading = read_raise_path(fn, [("stmt", tree.body[0])], tree.body[1], {"x": ANY})
    assert not isinstance(reading, ReadRaise), reading


def test_an_import_of_a_loaded_module_is_still_read():
    space: dict = {}
    exec(_IMPORTS.format(name="math"), space)
    fn = space["imports_it"]
    tree = ast.parse(_IMPORTS.format(name="math")).body[0]
    reading = read_raise_path(fn, [("stmt", tree.body[0])], tree.body[1], {"x": ANY})
    assert isinstance(reading, ReadRaise) and reading.cls is ValueError, reading
