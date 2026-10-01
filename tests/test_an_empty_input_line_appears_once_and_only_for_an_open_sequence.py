# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The empty-input line asks what f does at the empty list for a
sequence the claim leaves open. A claim that calls f only with literal
arguments (`f([1.0]) == 1`) leaves nothing open and has no such line.
A line under a claim mathema suggested is part of that suggestion and,
like it, never gates; a failure the gate does report is stated once."""
from mathema import check
from mathema.records import Probe
from mathema.verify import gate


def total(xs: list) -> float:
    s = 0.0
    for v in xs:
        s = s * 2 + v
    return s


def first(x: list, alpha: float) -> float:
    return x[0] * alpha


def test_a_claim_with_only_literal_arguments_has_no_empty_input_line():
    rows = check(total, claims=["f([1.0]) == 1"]).probes
    assert not [p for p in rows if p.name.startswith("is_empty_safe")], \
        [p.name for p in rows]


def test_a_claim_over_an_open_sequence_keeps_its_line():
    rows = check(first, claims=["f(x, 1.0) == x[0]"]).probes
    lines = [p for p in rows if p.name == "is_empty_safe[x]"]
    assert len(lines) == 1 and lines[0].verdict == "falsified"


def _line(parent: str):
    return Probe("is_empty_safe[x]", "is_empty_safe(x)", "falsified",
                 route="probe:algorithmic", counterexample="x = []",
                 meta={"mathema.companion_of": parent,
                       "mathema.family": "is_empty_safe"})


def test_the_line_under_a_suggestion_never_gates():
    suggested = [Probe(f"law{i}", "f(x) >= 0", "holds",
                       meta={"mathema.surface": "mathema"}) for i in range(3)]
    report = gate(suggested + [_line(f"law{i}") for i in range(3)],
                  strict=False)
    assert report.problems == []


def test_a_gating_failure_is_stated_once_per_claim_and_names_it():
    written = [Probe(f"law{i}", "f(x) >= 0", "holds") for i in range(3)]
    report = gate(written + [_line(f"law{i}") for i in range(3)] + [_line("law0")],
                  strict=False)
    empty = [p for p in report.problems if p.startswith("empty (")]
    assert len(empty) == 3, report.problems
    for i in range(3):
        assert sum(f"under law{i}" in p for p in empty) == 1, empty
