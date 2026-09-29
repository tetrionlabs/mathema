# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The derive sketch and the record say what a binding fixed: "xs of
length 30", "A of shape 30 by 15", never "every length" or "any length"
when a length is fixed. The sampling note prints one fixed size, never
a range, and a literal dimension that contradicts a length premise is
the vacuous premise the engine already reports, naming both."""
import importlib.util
import textwrap

import pytest

from mathema.conjecture import check_conjectures, claim

_MODULE = '''
import numpy as np


def total(xs: list) -> float:
    """Sum."""
    return sum(xs)


def gram_trace(A: np.ndarray) -> float:
    """Trace of A A^T."""
    return float(np.trace(A @ A.T))


def entries(A: np.ndarray) -> float:
    """Sum of every entry."""
    return float(A.sum())
'''


@pytest.fixture()
def mod(tmp_path):
    p = tmp_path / "sketch_length_mod.py"
    p.write_text(textwrap.dedent(_MODULE))
    spec = importlib.util.spec_from_file_location("sketch_length_mod", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.mark.needs_full_proof_budget
def test_the_sketch_names_a_fixed_length(mod):
    (p,) = check_conjectures(mod.total, [claim(
        "for xs in [0, 1]^30, f(xs) >= 0", route="derive")])
    assert p.verdict == "proven", (p.verdict, p.sketch)
    assert "xs of length 30" in (p.sketch or ""), p.sketch
    assert "any length" not in (p.sketch or ""), p.sketch
    assert "every length" not in (p.sketch or ""), p.sketch


@pytest.mark.needs_full_proof_budget
def test_the_sketch_keeps_every_length_when_none_is_fixed(mod):
    (p,) = check_conjectures(mod.total, [claim(
        "for xs in [0, 1]^n, f(xs) >= 0", route="derive")])
    assert p.verdict == "proven", (p.verdict, p.sketch)
    assert "of length" not in (p.sketch or ""), p.sketch


@pytest.mark.needs_full_proof_budget
def test_the_sketch_names_a_fixed_matrix_shape(mod):
    pytest.importorskip("numpy")
    (p,) = check_conjectures(mod.gram_trace, [claim(
        "for A in R^(30,15), f(A) >= 0", route="derive")])
    assert p.verdict == "proven", (p.verdict, p.sketch)
    assert "A of shape 30 by 15" in (p.sketch or ""), p.sketch


def test_the_sampling_note_prints_one_fixed_length(mod):
    (p,) = check_conjectures(mod.total, [claim(
        "for xs in [0, 1]^30, f(xs) == f(xs)", route="probe")])
    note = p.meta["mathema.sampling"]
    assert "len=30" in note, note
    assert "len∈" not in note, note


def test_the_sampling_note_prints_one_fixed_matrix_size(mod):
    pytest.importorskip("numpy")
    (p,) = check_conjectures(mod.entries, [claim(
        "for A in R^(30,15), f(A) == f(A)", route="probe")])
    note = p.meta["mathema.sampling"]
    assert "size=(30,15)" in note, note
    assert "∈" not in note.split("A~", 1)[1].split(";", 1)[0], note


def test_a_fixed_axis_beside_a_free_one_prints_the_range_on_the_free_axis(mod):
    pytest.importorskip("numpy")
    (p,) = check_conjectures(mod.entries, [claim(
        "for A in R^(n,15), f(A) == f(A)", route="probe")])
    note = p.meta["mathema.sampling"]
    assert "size∈[(" in note, note
    assert ",15)" in note, note


def test_a_literal_length_contradicted_by_a_premise_is_a_vacuous_premise(mod):
    for route in ("probe", "best"):
        (p,) = check_conjectures(mod.total, [claim(
            "for xs in [0, 1]^30, assuming len(xs) == 5, f(xs) >= 0",
            route=route)])
        assert p.verdict == "skipped", (route, p.verdict, p.note)
        note = p.note or ""
        assert "vacuous" in note, note
        assert "dim(xs, 0) == 5" in note, note
        assert "length 30" in note, note
        assert p.meta.get("mathema.empty_premise") == "xs", p.meta
