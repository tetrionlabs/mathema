# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim with lines under it prints as a block: the claim and its
overall verdict on one line, then one line per aspect of what is known
about it (the mathematics over the numbers, the computation in float,
and the policy at each value that is not a number: f(nan), f(None),
f([])), each with its verdict first. The claim is falsified when any of
its lines is, and a falsified absence or missing line says the possible
fixes."""
import math
from typing import Optional

import mathema


def root_opt(x: Optional[float]) -> float:
    return math.sqrt(x)


def first(xs: list) -> float:
    return xs[0]


def _lines(rec) -> list:
    return repr(rec).splitlines()


def test_a_claim_with_lines_prints_as_a_block():
    rec = mathema.check(root_opt, claims=[mathema.claim(
        "for x in [0, 4], f(x) >= 0", name="nonneg")])
    lines = _lines(rec)
    start = next(i for i, line in enumerate(lines) if line.startswith("  nonneg  "))
    head, *block = lines[start:start + 6]
    assert head.endswith("falsified at x = None"), head
    assert block[0].split() [:2] == ["proven", "mathematics"], block[0]
    assert "for x in [0.0, 4.0] ⊂ ℝ, f(x) >= 0" in block[0], block[0]
    assert block[1].split()[:2] == ["holds", "computation"], block[1]
    assert "for x in [0.0, 4.0] : float, f(x) >= 0" in block[1], block[1]
    assert block[1].rstrip().endswith("draws"), block[1]
    assert block[2].split()[:3] == ["proven", "policy", "f(nan)"], block[2]
    assert block[3].split()[:3] == ["falsified", "policy", "f(None)"], block[3]
    assert "no absent policy stated; raises TypeError" in block[3], block[3]
    assert block[4].strip() == (
        "possible fixes: (i) mathema claims test_a_claim_reads_as_its_lines.root_opt "
        "--adopt 'absent[x]'  (ii) exclude None  (iii) handle None at entry"), block[4]


def test_the_verdict_words_are_spelled_out():
    rec = mathema.check(root_opt, claims=[mathema.claim(
        "for x in [0, 4], f(x) >= 0", name="nonneg")])
    assert "FALSIFY" not in repr(rec)


def test_the_empty_input_line_sits_in_the_block():
    rec = mathema.check(first, claims=[mathema.claim(
        "for xs in [0, 1]^n, f(xs) >= 0", name="lead")])
    lines = _lines(rec)
    start = next(i for i, line in enumerate(lines) if line.startswith("  lead  "))
    assert lines[start].endswith("falsified at xs = []"), lines[start]
    empty = next(line for line in lines[start + 1:] if "f([])" in line)
    assert empty.split()[:3] == ["falsified", "policy", "f([])"], empty
