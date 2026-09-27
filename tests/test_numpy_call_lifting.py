# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A numpy call lifts to a sympy function only when it is the function
the name says: `np.sin(x)` is sin, but `np.linalg.norm(v)` is not `norm`
of anything the lift knows, and `np.max(x, 0)` is not the two-argument
max (numpy's second argument is the axis), so neither is proven by
reading it as one."""
import ast
import textwrap

import pytest

from mathema._math_vocab import _call_name

pytest.importorskip("numpy")


def _call(src: str) -> ast.Call:
    return ast.parse(src, mode="eval").body


@pytest.mark.parametrize("src, name", [
    ("np.sin(x)", "sin"),
    ("numpy.sqrt(x)", "sqrt"),
    ("math.exp(x)", "exp"),
    ("sin(x)", "sin"),
    ("np.max(x)", "max"),
    ("max(x, 0)", "max"),
    ("np.linalg.norm(v)", None),
    ("np.max(x, 0)", None),
    ("numpy.min(x, 0)", None),
    ("np.amax(x, 0)", None),
])
def test_call_names(src, name):
    assert _call_name(_call(src)) == name


def _load(tmp_path, body, name):
    import importlib.util
    p = tmp_path / f"{name}.py"
    p.write_text(textwrap.dedent(body))
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("axis, witness", [
    # numpy accepts axis 0 on a scalar and returns it, so a negative
    # input is the counterexample; axis 1 does not exist on a scalar
    ("0", "-1.0 vs 0"),
    ("1", "raised AxisError"),
])
def test_numpy_max_with_an_axis_is_not_a_two_argument_max(tmp_path, axis,
                                                          witness):
    from mathema.conjecture import check_conjectures, claim
    mod = _load(tmp_path, f'''
        import numpy as np

        def top(x: float) -> float:
            """The largest element, the second argument read as an axis."""
            return float(np.max(x, {axis}))
    ''', f"np_axis_{axis}")
    (derived,) = check_conjectures(mod.top, [claim("f(x) >= 0",
                                                   route="derive")])
    assert derived.verdict != "proven", derived.sketch
    (best,) = check_conjectures(mod.top, [claim("f(x) >= 0", route="best")])
    assert best.verdict == "falsified"
    assert witness in (best.counterexample or "") + (best.note or ""), best
