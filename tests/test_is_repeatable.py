# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`is_repeatable(f)` is the roll-up for the third question, is it
repeatable. The seed is the differentiator: a function that takes a
seed or a generator is held to `is_reproducible` (same seed, same
answer), any other to `is_deterministic` (same input, same answer), and
`is_state_safe` always joins. `is_computation_safe` covers only the
other two questions: does it run, and is it right in float64."""
import textwrap

import pytest

np = pytest.importorskip("numpy")


def _load(tmp_path, body, name):
    import importlib.util
    p = tmp_path / f"{name}.py"
    p.write_text(textwrap.dedent(body))
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _one(fn, law):
    from mathema.conjecture import check_conjectures, claim
    (p,) = check_conjectures(fn, [claim(law, route="best")])
    return p


_SEEDED = '''
    import numpy as np

    def draw(n: int, seed: int) -> float:
        """The sum of n standard normal draws from a seeded generator."""
        return float(np.random.default_rng(seed).normal(size=n).sum())
'''

_NOISY = '''
    import random

    def noisy(x: float) -> float:
        """x plus uniform noise."""
        return x + random.random()
'''


def test_a_seeded_function_is_repeatable_through_reproducibility(tmp_path):
    draw = _load(tmp_path, _SEEDED, "rep_draw").draw
    p = _one(draw, "is_repeatable(f)")
    assert p.verdict == "holds", (p.verdict, p.note, p.counterexample)
    children = p.meta["mathema.children"]
    assert set(children) == {"is_reproducible", "is_state_safe"}, children
    assert children["is_reproducible"] in ("holds", "proven"), children
    assert "is_reproducible: " in (p.note or "")


def test_an_unseeded_noisy_function_is_not_repeatable(tmp_path):
    noisy = _load(tmp_path, _NOISY, "rep_noisy").noisy
    p = _one(noisy, "is_repeatable(f)")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert (p.counterexample or "").startswith("is_deterministic"), \
        p.counterexample
    assert set(p.meta["mathema.children"]) == {"is_deterministic",
                                               "is_state_safe"}


def test_the_roll_up_never_reaches_proven(tmp_path):
    half = _load(tmp_path, '''
        def half(x: float) -> float:
            """Half."""
            return x / 2
    ''', "rep_half").half
    p = _one(half, "is_repeatable(f)")
    assert p.verdict == "holds", (p.verdict, p.note)


def test_computation_safety_leaves_repeatability_out(tmp_path):
    draw = _load(tmp_path, _SEEDED, "rep_draw_cs").draw
    p = _one(draw, "for n in [1, 50], is_computation_safe(f)")
    children = p.meta.get("mathema.children") or {}
    assert children, (p.verdict, p.note)
    assert not any(n.startswith(("is_deterministic", "is_reproducible",
                                 "is_state_safe")) for n in children), \
        children
    assert not (p.counterexample or "").startswith("is_deterministic")


def test_is_reproducible_holds_the_seed_fixed(tmp_path):
    draw = _load(tmp_path, _SEEDED, "rep_draw_seed").draw
    from mathema.conjecture import check_conjectures, claim
    (p,) = check_conjectures(draw, [claim("f(n, seed) == f(n, seed)",
                                          name="is_reproducible")])
    assert p.verdict == "holds", (p.verdict, p.note, p.counterexample)


_SIGNATURES = [
    ("(n, seed)", True), ("(x, rng)", True), ("(x, random_state)", True),
    ("(x, key)", True), ("(x: float, g: 'np.random.Generator')", True),
    ("(x, g: np.random.Generator)", True),
    ("(x, r: random.Random)", True), ("(x, s: np.random.RandomState)", True),
    ("(x, y)", False),
]


@pytest.mark.parametrize("index", range(len(_SIGNATURES)))
def test_the_seed_parameter_is_recognised(tmp_path, index):
    sig, seeded = _SIGNATURES[index]
    from mathema.claim_families import seed_parameter
    mod = _load(tmp_path, f'''
        import random

        import numpy as np

        def g{sig}:
            return 0.0
    ''', f"rep_sig_{index}")
    from mathema import analyze
    fn = mod.g
    assert (seed_parameter(fn, analyze(fn)) is not None) == seeded


def test_is_repeatable_credits_no_clarity_source():
    from mathema.badges import _NO_SOURCE, _SAFETY_SOURCE
    assert "is_repeatable" not in _SAFETY_SOURCE
    assert "is_repeatable" in _NO_SOURCE
