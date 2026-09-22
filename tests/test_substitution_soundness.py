# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Regressions for the two confidently-wrong substitution bugs found in
field use: the fold route's double substitution (a scaling claim's
multiplier came back exactly squared) and pin-then-swap (two degenerate
pins collapsed the lifted expression to a constant before an
`f(q, p)` call's argument order could mean anything, "proving"
`f(q, p) == f(p, q)` for an asymmetric function). Every other failure
mode skips; these two lied, hence dedicated, direct regressions."""
import importlib.util
import sys
import textwrap

import pytest
import sympy

from mathema.analysis import analyze_source
from mathema.conjecture import check_conjectures, claim
from mathema.symbolic import lift_fold
from mathema.symbolic._fold import _fold_eval_at


def _load_module(tmp_path, name, source):
    path = tmp_path / f"{name}.py"
    path.write_text(textwrap.dedent(source))
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    _LOADED_FIXTURE_MODULES.append(name)
    spec.loader.exec_module(mod)
    return mod


_LOADED_FIXTURE_MODULES: list = []


@pytest.fixture(autouse=True)
def _unload_fixture_modules():
    # fixture modules registered in sys.modules must not outlive their
    # test: inspect.getsource resolves against currently-loaded module
    # state, so a leaked name is cross-test contamination waiting to
    # collide
    yield
    while _LOADED_FIXTURE_MODULES:
        sys.modules.pop(_LOADED_FIXTURE_MODULES.pop(), None)


def test_fold_scalar_substitution_applies_exactly_once(tmp_path):
    mod = _load_module(tmp_path, "fold_scale_fixture", '''\
    def compound(xs: list, g: float) -> float:
        total = xs[0]
        for v in xs[1:]:
            total = total * g
        return total
    ''')
    fold = lift_fold(mod.compound, analyze_source(mod.compound))
    g = fold.other_params["g"]
    # f(xs, 2g) must scale by (2g)**(L-1), the old order ran the
    # substitution over the already-substituted accumulator too, giving
    # 4**(L-1): the multiplier exactly squared.
    val = sympy.simplify(_fold_eval_at(fold, {g: 2 * g}))
    L = fold.length
    expected = sympy.simplify((2 * g) ** (L - 1) * fold.seq[0])
    assert sympy.simplify(val - expected) == 0, val


def test_two_pins_never_collapse_argument_order(tmp_path):
    mod = _load_module(tmp_path, "pin_swap_fixture", '''\
    def diff2(q: float, p: float) -> float:
        return q - 2.0 * p
    ''')
    # with q=3 and p=5: f(q, p) = -7 and f(p, q) = -1. The claim is
    # false; the old pre-baked pins collapsed the lift to -7 before the
    # argument order existed, and "proved" it.
    (swapped,) = check_conjectures(mod.diff2, [claim(
        "for q in [3,3], p in [5,5], f(q, p) == f(p, q)", route="derive")])
    assert swapped.verdict == "falsified"

    # the true pinned statements still prove, both orders
    (direct,) = check_conjectures(mod.diff2, [claim(
        "for q in [3,3], p in [5,5], f(q, p) == -7", route="derive")])
    assert direct.verdict == "proven"
    (reordered,) = check_conjectures(mod.diff2, [claim(
        "for q in [3,3], p in [5,5], f(p, q) == -1", route="derive")])
    assert reordered.verdict == "proven"


def test_pinned_scalar_composes_with_a_transformed_argument(tmp_path):
    mod = _load_module(tmp_path, "pin_arg_fixture", '''\
    def scaled(x: float, k: float) -> float:
        return k * x
    ''')
    # k pinned to 3; the claim passes 2*k as the argument, the pin
    # must flow through the argument expression (2*3 = 6), never
    # collapse the body first.
    (p,) = check_conjectures(mod.scaled, [claim(
        "for k in [3,3], f(x, 2*k) == 6*x", route="derive")])
    assert p.verdict == "proven"
