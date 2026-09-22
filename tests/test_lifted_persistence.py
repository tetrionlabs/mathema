# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The proved closed form survives into the record.

A lift is the derive route's subject: the function's body as a sympy
expression. The record's `math` section carries its two human
projections (unicode, latex) and, when the lift is a single
expression, the exact `srepr`, which `sympy.sympify` round-trips, so a
consumer can compute with what was proved rather than re-deriving it.
"""
import importlib
import sys
import textwrap

import pytest
import sympy

import mathema
from mathema.spec import to_spec


@pytest.fixture
def modfile(tmp_path, monkeypatch):
    def load(name, src):
        (tmp_path / f"{name}.py").write_text(textwrap.dedent(src))
        monkeypatch.syspath_prepend(str(tmp_path))
        sys.modules.pop(name, None)
        importlib.invalidate_caches()
        return importlib.import_module(name)

    return load


def test_a_derivable_function_records_its_closed_form(modfile):
    mod = modfile("liftedmod", '''
        import math

        def damped(x: float) -> float:
            """Exponentially damped square."""
            return x * x * math.exp(-x)
    ''')
    rec = mathema.check(mod.damped, claims=["f(x) >= 0"])
    assert rec.lifted is not None
    math_block = to_spec(rec)["math"]
    assert math_block is not None
    assert math_block["unicode"] and math_block["latex"]
    expr = sympy.sympify(math_block["srepr"])
    x = sympy.Symbol("x", real=True)
    assert sympy.simplify(expr - x**2 * sympy.exp(-x)) == 0


def test_an_unliftable_body_still_writes_a_null_math_section(modfile):
    mod = modfile("unliftmod", '''
        def lookup(d: dict) -> float:
            """Read a value out of a mapping by a computed key."""
            total = 0.0
            for k in d:
                total += d[k] * d[k]
            return total
    ''')
    rec = mathema.check(mod.lookup, claims=["f(d) >= 0"])
    assert to_spec(rec)["math"] is None


def test_srepr_is_null_for_a_tuple_valued_lift(modfile):
    # a lift can be tuple-valued (no single expression); the rendered
    # projections still appear, srepr honestly does not
    from mathema.spec import _math_section

    class FakeLifted:
        unicode = "u"
        latex = "l"
        expr = (sympy.Symbol("a"), sympy.Symbol("b"))

    section = _math_section(FakeLifted())
    assert section == {"unicode": "u", "latex": "l", "srepr": None}
