# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A verdict and its witness are the same in every process. Python
randomises the hash of a string per process (PYTHONHASHSEED), so a set
of dimension names iterates in a different order in each run; the
shape checks draw their sizes in the order the names first appear in
the signature, so the draws, the verdicts and the witnesses never
depend on that seed."""
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

_SCRIPT = textwrap.dedent("""
    import json

    import numpy as np

    import mathema
    from mathema.types import Mat, Vec


    def factor_exposure(weights: Vec("n"), betas: Mat("n", "k")) -> Vec("k"):
        return list(np.asarray(betas) @ np.asarray(weights))


    rec = mathema.check(factor_exposure, claims=["is_dimension_safe(f)"])
    print(json.dumps([[p.name, p.verdict, p.counterexample, p.note]
                      for p in rec.probes]))
""")

_SEEDS = ("0", "1", "2", "3", "17")


def _rows_under(seed: str) -> list:
    env = {**os.environ, "PYTHONHASHSEED": seed}
    root = Path(__file__).resolve().parent.parent
    done = subprocess.run([sys.executable, "-c", _SCRIPT], env=env,
                          cwd=root, capture_output=True, text=True,
                          check=True, timeout=300)
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_shape_verdicts_and_witnesses_are_identical_under_every_seed():
    pytest.importorskip("numpy")
    runs = {seed: _rows_under(seed) for seed in _SEEDS}
    first = runs[_SEEDS[0]]
    for seed, rows in runs.items():
        assert rows == first, (seed, rows, first)
    by_name = {name: (verdict, cx) for name, verdict, cx, _ in first}
    # betas @ weights needs k == n: a consistent call at n != k raises
    verdict, cx = by_name["result_dimensions"]
    assert verdict == "falsified", by_name
    # the witness names the dimensions in signature order
    assert cx.startswith("dims={'n': "), cx
    assert by_name["is_dimension_safe[f]"][0] == "falsified", by_name


_SIZES_SCRIPT = textwrap.dedent("""
    import json
    import random
    from types import SimpleNamespace

    from mathema import dimensions
    from mathema.types import Mat, Vec, shapes_from_signature


    def blend(a: Mat("m", "n"), b: Mat("n", "p"), c: Vec("q")) -> float:
        return 0.0


    facts = SimpleNamespace(params=["a", "b", "c"], param_kinds={})
    resolver = dimensions.resolve(facts, shapes_from_signature(blend))
    rng = random.Random(7)
    draws = [resolver.draw_sizes(rng) for _ in range(5)]
    print(json.dumps([sorted(d.items()) for d in draws]))
""")


def test_dimension_sizes_are_drawn_in_the_same_order_under_every_seed():
    root = Path(__file__).resolve().parent.parent
    outs = set()
    for seed in _SEEDS:
        env = {**os.environ, "PYTHONHASHSEED": seed}
        done = subprocess.run([sys.executable, "-c", _SIZES_SCRIPT],
                              env=env, cwd=root, capture_output=True,
                              text=True, check=True, timeout=300)
        outs.add(done.stdout.strip().splitlines()[-1])
    assert len(outs) == 1, outs
