# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A matrix or vector witness above a small size prints its shape, the
first few entries and one sentence about the rest ("30 by 15, every
entry -1.79769e+308"), on the probe route and in the companion a proof
spawns; the full value stays in `meta["mathema.counterexample_args"]`."""
import importlib.util
import textwrap

import pytest

import mathema
from mathema.conjecture import check_conjectures, claim

_MODULE = '''
import numpy as np


def spread(A: np.ndarray) -> float:
    """Largest entry minus smallest: 0 exactly for a constant matrix."""
    return float(A.max() - A.min())


def gram_trace(A: np.ndarray) -> float:
    """Trace of A A^T."""
    return float(np.trace(A @ A.T))
'''


@pytest.fixture()
def mod(tmp_path):
    pytest.importorskip("numpy")
    p = tmp_path / "large_witness_mod.py"
    p.write_text(textwrap.dedent(_MODULE))
    spec = importlib.util.spec_from_file_location("large_witness_mod", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_a_probe_witness_prints_the_shape_and_a_first_row(mod):
    # a constant matrix meets the claim, so the witness is a matrix
    # whose entries differ
    (p,) = check_conjectures(mod.spread, [claim(
        "for A in [0, 1]^(30,15), f(A) == 0", route="probe")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    cx = p.counterexample or ""
    assert "30 by 15" in cx, cx
    assert "450 entries" in cx, cx
    assert len(cx) < 400, len(cx)
    (full,) = p.meta["mathema.counterexample_args"]
    assert len(full) == 30 and all(len(row) == 15 for row in full)


@pytest.mark.needs_full_proof_budget
def test_a_companion_witness_at_a_corner_names_the_shape_and_the_entry(mod):
    rec = mathema.check(mod.gram_trace, claims=["for A in R^(30,15), f(A) >= 0"])
    (companion,) = [p for p in rec.probes if p.name.startswith("f_a_ge_0[")]
    assert companion.verdict == "falsified", (companion.verdict, companion.note)
    cx = companion.counterexample or ""
    assert "30 by 15, every entry" in cx, cx
    assert len(cx) < 200, len(cx)
    assert len(companion.sketch or "") < 600, len(companion.sketch)
