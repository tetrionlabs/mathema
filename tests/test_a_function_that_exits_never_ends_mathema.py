# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A `SystemExit` raised by the function under test (an exit inside a
function it calls, argparse's error path) is a raise of that function
at the call that made it, read like any other raise: it never ends
mathema's own process. Every place mathema calls the function reads it
so, the structural witness search of is_defined included."""
import importlib.util
import textwrap

import pytest

import mathema
from mathema._exits import ExitRaised
from mathema.conjecture import check_conjectures, claim

BODY = '''
import argparse
import sys


def _bail(code):
    sys.exit(code)


def leaves(x: float) -> float:
    if x > 0.5:
        _bail(2)
    return x / 2.0


def pair(x: float, y: float) -> float:
    if x > y + 0.5:
        _bail(2)
    return x - y


def parsed(s: str) -> int:
    parser = argparse.ArgumentParser(prog="parsed")
    parser.add_argument("--n", type=int, required=True)
    return parser.parse_args(["--n", s]).n
'''


@pytest.fixture
def mod(tmp_path):
    path = tmp_path / "exiting_module.py"
    path.write_text(textwrap.dedent(BODY))
    spec = importlib.util.spec_from_file_location("exiting_module", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _rows(fn, text):
    try:
        return check_conjectures(fn, [claim(text, route="best")])
    except SystemExit as exc:          # pragma: no cover, the defect itself
        pytest.fail(f"SystemExit({exc.code!r}) escaped mathema for {text}")


def _exits_at(fn, counterexample):
    """Whether `fn` exits at the point a witness `x = 1, y = 2` names."""
    from mathema._exits import call
    point = {k.strip(): float(v) for k, v in
             (part.split("=") for part in counterexample.split(","))}
    try:
        call(fn, **point)
    except ExitRaised:
        return True
    return False


@pytest.mark.parametrize("text", ["is_defined(x)", "is_defined(f)"])
def test_is_defined_reads_a_callee_exit_as_a_raise(mod, text):
    (row,) = _rows(mod.leaves, text)
    assert row.verdict == "falsified", (row.verdict, row.note)
    assert _exits_at(mod.leaves, row.counterexample), row.counterexample


def test_is_defined_on_two_parameters_reads_the_exit_as_a_raise(mod):
    (row,) = _rows(mod.pair, "is_defined(x)")
    assert row.verdict == "falsified", (row.verdict, row.note)
    assert _exits_at(mod.pair, row.counterexample), row.counterexample


def test_an_argparse_error_is_a_raise_of_the_function(mod):
    rows = _rows(mod.parsed, "is_language_defined(s)")
    assert rows and all(r.verdict for r in rows)


def test_the_bare_check_completes_on_a_function_that_exits(mod):
    for fn in (mod.leaves, mod.pair, mod.parsed):
        try:
            mathema.check(fn)
        except SystemExit as exc:      # pragma: no cover, the defect itself
            pytest.fail(f"SystemExit({exc.code!r}) escaped check({fn.__name__})")


class _Unsigned:
    """A callable whose signature cannot be read, so its arity is found
    by calling it; it exits on every call."""
    __signature__ = "unreadable"

    def __call__(self, x):
        import sys
        sys.exit(4)


def test_a_callable_found_by_calling_it_is_analysed_when_it_exits():
    facts = mathema.analyze(_Unsigned())
    assert facts.params == ["x"]


def test_the_shared_call_boundaries_turn_an_exit_into_a_raise(mod):
    from mathema.claim_families import _call_with_target
    from mathema.conjecture import _call_by_name, _with_pins
    facts = mathema.analyze(mod.leaves)
    with pytest.raises(ExitRaised) as err:
        _call_with_target(mod.leaves, facts, "x", [0.0], 0.9)
    assert err.value.code == 2
    with pytest.raises(ExitRaised):
        _call_by_name(mod.leaves, {"x": 0.9})
    with pytest.raises(ExitRaised):
        _with_pins(mod.pair, {"y": 0.0})(x=0.9)
    import inspect

    from mathema.types import _call
    with pytest.raises(ExitRaised):
        _call(mod.leaves, inspect.signature(mod.leaves), {"x": 0.9})


def test_a_keyboard_interrupt_still_passes_through():
    from mathema.conjecture import _call_by_name

    def interrupted(x):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        _call_by_name(interrupted, {"x": 1.0})
