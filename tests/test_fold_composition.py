# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Elementwise transforms compose through a fold's closed form on the
derive route: `f(g(xs, c))` with g bound to mathema.f.scale_seq or
shift_seq substitutes `seq[k] -> map(seq[k], c)`, so a linear fold's
equivariance is PROVEN (weights summing to 1 pass a shift through,
any linear fold passes a scale through), and a false additivity is
symbolically refuted. The geometric-sum identity behind the shift
proof closes through the Sum-in-closed-form rung."""
import textwrap

import pytest


@pytest.fixture(scope="module")
def folds(tmp_path_factory):
    p = tmp_path_factory.mktemp("folds") / "foldmod.py"
    p.write_text(textwrap.dedent('''
        def ema(x: list, alpha: float) -> float:
            """Exponentially weighted moving average."""
            y = x[0]
            for v in x[1:]:
                y = alpha * v + (1 - alpha) * y
            return y


        def total(xs: list) -> float:
            """Sum of the sequence."""
            y = 0.0
            for v in xs:
                y = y + v
            return y
    '''))
    import importlib.util

    spec = importlib.util.spec_from_file_location("foldmod", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _one(fn, law, funcs, route="derive"):
    from mathema.conjecture import check_conjectures, claim
    (p,) = check_conjectures(fn, [claim(law, route=route, funcs=funcs)])
    return p


def test_scale_composes_and_proves_for_any_linear_fold(folds):
    for fn, law in (
        (folds.ema, "for alpha in [0,1], let c be [0.1, 10], "
                    "c*f(x, alpha) == f(g(x, c), alpha)"),
        (folds.total, "let c be [0.1, 10], c*f(xs) == f(g(xs, c))"),
    ):
        p = _one(fn, law, {"g": "mathema.f.scale_seq"})
        assert p.verdict == "proven", (fn.__name__, p.verdict, p.note)


@pytest.mark.needs_full_proof_budget
def test_shift_proves_exactly_when_the_weights_sum_to_one(folds):
    p = _one(folds.ema,
             "for alpha in [0,1], let c be [-5, 5], "
             "f(x, alpha) + c == f(g(x, c), alpha)",
             {"g": "mathema.f.shift_seq"})
    assert p.verdict == "proven", (p.verdict, p.note)
    assert "Sum evaluated in closed form" in (p.sketch or "")

    # total's weights sum to L, not 1: the same law is false, the
    # derive route refutes it symbolically, and the corroboration gate
    # reproduces that against the real function with a list witness
    q = _one(folds.total, "let c be [1, 5], f(xs) + c == f(g(xs, c))",
             {"g": "mathema.f.shift_seq"}, route="best")
    assert q.verdict == "falsified"
    assert q.counterexample and "xs = [" in q.counterexample
    assert (q.meta or {}).get("mathema.corroboration") == "reproduced"


def test_the_battery_equivariances_now_prove_on_linear_folds(folds):
    # the mathematics: each equivariance is proven over non-empty lists
    from mathema.conjecture import check_conjectures
    import mathema
    for name in ("scale_equivariant", "translation_equivariant"):
        law = next(c for c in mathema.suggest_claims(folds.ema)
                   if getattr(c, "name", None) == name)
        (p,) = check_conjectures(folds.ema, [law])
        assert p.verdict == "proven", (name, p.verdict, p.note)
    # the check: ema reads x[0], so its empty-input line is falsified
    # with the empty list, and so is each claim
    rows = {p.name: p for p in mathema.check(folds.ema).probes}
    for name in ("scale_equivariant", "translation_equivariant"):
        assert rows[name].verdict == "falsified", (name, rows[name].verdict)
        assert rows[name].counterexample.startswith("x = []"), \
            rows[name].counterexample
    assert rows["is_empty_safe[x]"].verdict == "falsified"


def test_an_unregistered_transform_still_refuses_loudly(folds):
    p = _one(folds.total, "let c be [1, 5], f(g(xs, c)) >= 0",
             {"g": "mathema.f.reverse_seq"})
    assert p.verdict in ("unknown", "holds", "skipped")
    text = (p.note or "") + (p.sketch or "")
    assert "bare reference" in text or "not derivable" in text
