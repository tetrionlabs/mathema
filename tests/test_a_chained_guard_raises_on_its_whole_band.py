# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A raise under a chained comparison guard, lifted symbolically.

The lifted raise region must be exactly the set where the written
condition holds in exact arithmetic (each decimal literal read as its
written value), at both ends of the band and with each end closed
exactly where its comparison is non-strict.
"""
import importlib.util
import re
import sys
import textwrap
from fractions import Fraction

import pytest
import sympy

from mathema import analyze, claim
from mathema.conjecture import check_conjectures
from mathema.symbolic._conditioned import lift_piecewise

_GUARDS = {
    "closed_square_band": ("1.0 <= x * x <= 4.0",
                           ["-3", "-2", "-1.5", "-1", "0", "1", "1.5", "2", "3"]),
    "strict_square_band": ("1.0 < x * x < 4.0",
                           ["-3", "-2", "-1.5", "-1", "0", "1", "1.5", "2", "3"]),
    "closed_low_strict_high": ("1.0 <= x * x < 4.0",
                               ["-2", "-1.5", "-1", "1", "1.5", "2"]),
    "strict_low_closed_high": ("1.0 < x * x <= 4.0",
                               ["-2", "-1.5", "-1", "1", "1.5", "2"]),
    "band_symmetric_about_zero": ("-1.5 <= x <= 1.5",
                                  ["-2", "-1.5", "0", "1.5", "2"]),
    "one_sided_band": ("0.0 < x <= 2.0",
                       ["-1", "0", "1", "2", "3"]),
    "knife_edge": ("1.0 <= x * x <= 1.0000000000000002",
                   ["-1", "1", "0", "2", "-2"]),
}


def _exact(condition: str, value: str) -> bool:
    """The guard evaluated in exact rational arithmetic, every decimal
    literal read as the number it is written as."""
    source = re.sub(r"\d+\.\d+", lambda m: f"Fraction('{m.group(0)}')",
                    condition)
    return bool(eval(source, {"Fraction": Fraction},
                     {"x": Fraction(value)}))


def _function(tmp_path, name: str, condition: str):
    source = textwrap.dedent(f"""\
        def {name}(x: float) -> float:
            if {condition}:
                raise ValueError("edge")
            return 0.0
        """)
    path = tmp_path / f"chained_{name}.py"
    path.write_text(source)
    spec = importlib.util.spec_from_file_location(f"chained_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return getattr(mod, name)


@pytest.mark.parametrize("name", sorted(_GUARDS))
def test_the_lifted_raise_region_is_the_guard_exactly(tmp_path, name):
    condition, points = _GUARDS[name]
    fn = _function(tmp_path, name, condition)
    pw = lift_piecewise(fn, analyze(fn))
    assert pw is not None and pw.raise_guards
    (x,) = pw.params.values()
    for value in points:
        lifted = any(bool(cond.subs(x, sympy.Rational(value)))
                     for cond, _exc in pw.raise_guards)
        assert lifted == _exact(condition, value), (
            name, value, [c for c, _e in pw.raise_guards])


@pytest.mark.parametrize("name, value", [
    ("knife_edge", "-1"),
    ("closed_square_band", "-2"),
    ("closed_square_band", "-1"),
    ("closed_low_strict_high", "-1"),
])
def test_a_raising_boundary_point_is_never_proven(tmp_path, name, value):
    condition, _points = _GUARDS[name]
    assert _exact(condition, value)
    fn = _function(tmp_path, name, condition)
    (p,) = check_conjectures(
        fn, [claim(f"for x in [{value}, {value}], f(x) == 0",
                   route="derive")])
    assert p.verdict != "proven", (p.verdict, p.sketch)
