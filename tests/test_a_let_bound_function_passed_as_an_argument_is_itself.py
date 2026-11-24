# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A name bound by `let` to a function and passed as an argument is the
bound function itself: what the called function sees is the object the
reference names, with its own signature. A `let` name that is called
(`g(x)`, `f =:= g`) is called as before."""
import inspect

import pytest

from mathema.conjecture import check_conjectures, claim

_HERE = __name__


def halve(x: float) -> float:
    return x / 2


def also_halve(x: float) -> float:
    return 0.5 * x


def describe(function) -> str:
    sig = inspect.signature(function)
    params = ", ".join(p.annotation.__name__ for p in sig.parameters.values())
    return f"({params}) -> {sig.return_annotation.__name__}"


def same_object(function) -> bool:
    return function is halve


def _row(fn, text):
    rows = check_conjectures(fn, [claim(text)])
    return next(r for r in rows if not r.name.endswith("[float]"))


def test_a_let_bound_function_passed_as_an_argument_keeps_its_signature():
    p = _row(describe,
             f'let stage = {_HERE}.halve, describe(stage) == "(float) -> float"')
    assert p.verdict in ("proven", "holds"), \
        (p.verdict, p.route, p.counterexample, p.note)


def test_the_argument_is_the_bound_object():
    p = _row(same_object, f"let stage = {_HERE}.halve, f(stage) == True")
    assert p.verdict in ("proven", "holds"), \
        (p.verdict, p.route, p.counterexample, p.note)


def test_a_false_claim_about_the_argument_is_falsified():
    p = _row(describe,
             f'let stage = {_HERE}.halve, describe(stage) == "(int) -> int"')
    assert p.verdict == "falsified", (p.verdict, p.route, p.sketch, p.note)


@pytest.mark.parametrize("text", [
    "let g = {here}.also_halve, for x in [0, 1], g(x) == x / 2",
    "let g = {here}.also_halve, for x in [0, 1], f(x) == g(x)",
    "let g = {here}.also_halve, f =:= g",
])
def test_a_let_bound_function_that_is_called_is_called_as_before(text):
    p = _row(halve, text.format(here=_HERE))
    assert p.verdict in ("proven", "holds"), \
        (p.verdict, p.route, p.counterexample, p.note)


def test_a_called_let_bound_function_that_differs_is_falsified():
    p = _row(halve, f"let g = {_HERE}.describe, for x in [0, 1], f(x) == g(x)")
    assert p.verdict != "proven", (p.verdict, p.route, p.sketch, p.note)
    p = _row(also_halve,
             f"let g = {_HERE}.halve, for x in [1, 2], f(x) == g(x) + 1")
    assert p.verdict == "falsified", (p.verdict, p.route, p.sketch, p.note)
