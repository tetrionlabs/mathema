# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""mathema/diagnostics.py's motif library: containment-based, legible,
AST-scanned detection of specific structural patterns, clamp calls,
dot-product calls, fold/sum-shaped loop headers, deliberately working
whether or not the whole function lifts, since a syntactic pattern is
real signal independent of full liftability, and the primary use case
is exactly the functions that don't fully lift."""
import numpy as np

from mathema.analysis import analyze_source
from mathema.diagnostics import (
    has_accumulator_fold, has_clamp, has_dot_product_call, motifs,
)


def clamped(x: float, lo: float, hi: float) -> float:
    return max(lo, min(x, hi))


def dot_product(a: list, b: list) -> float:
    return float(np.dot(a, b))


def running_sum(xs: list) -> float:
    total = 0.0
    for x in xs:
        total += x
    return total


def plain_scalar(x: float, y: float) -> float:
    return x * 2 + y


def clamp_inside_unliftable_branch(x: float, y: float) -> float:
    if x > 0:
        return max(0.0, min(x, 10.0))
    return y


def test_has_clamp_finds_min_and_max_with_real_line_numbers():
    facts = analyze_source(clamped)
    hits = has_clamp(clamped, facts)
    assert {h["motif"] for h in hits} == {"clamp"}
    assert all(h["line"] == 2 for h in hits)
    assert all(h["file"] for h in hits)


def test_has_clamp_absent_for_a_function_without_one():
    facts = analyze_source(plain_scalar)
    assert has_clamp(plain_scalar, facts) == []


def test_has_dot_product_call_finds_the_call():
    facts = analyze_source(dot_product)
    hits = has_dot_product_call(dot_product, facts)
    assert len(hits) == 1
    assert hits[0]["motif"] == "dot_product"
    assert hits[0]["line"] == 2


def test_has_accumulator_fold_finds_the_recognized_loop_header():
    facts = analyze_source(running_sum)
    hits = has_accumulator_fold(running_sum, facts)
    assert len(hits) == 1
    assert hits[0]["motif"] == "loop_item"
    assert hits[0]["line"] == 3


def test_has_accumulator_fold_absent_when_no_loop():
    facts = analyze_source(plain_scalar)
    assert has_accumulator_fold(plain_scalar, facts) == []


def test_motifs_are_found_even_inside_a_function_that_does_not_lift_as_a_whole():
    # the core requirement: a branch elsewhere in the function blocks
    # full lifting (confirmed separately via derivability_report), but
    # the clamp inside one branch is still real, checkable signal at
    # its own line.
    from mathema.inventory import derivability_report
    assert derivability_report(clamp_inside_unliftable_branch)["liftable"] is False

    facts = analyze_source(clamp_inside_unliftable_branch)
    hits = has_clamp(clamp_inside_unliftable_branch, facts)
    assert {h["motif"] for h in hits} == {"clamp"}
    assert all(h["line"] == 3 for h in hits)


def clamped_fold(xs: list, hi: float) -> float:
    total = 0.0
    for x in xs:
        total += min(x, hi)
    return max(0.0, total)


def test_motifs_bundles_all_detectors():
    # a fixture carrying TWO motif kinds: the bundle must report both,
    # so a detector silently dropped from motifs() fails here
    facts = analyze_source(clamped_fold)
    kinds = {h["motif"] for h in motifs(clamped_fold, facts)}
    assert "clamp" in kinds
    assert kinds & {"accumulator_fold", "loop_item"}, kinds
