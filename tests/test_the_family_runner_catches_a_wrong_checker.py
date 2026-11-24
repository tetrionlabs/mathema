# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The family runner, run with stand-in checkers that are wrong on
purpose: one that proves everything, one that falsifies everything at
a point where the claim holds, one that prints the planted marker. The
runner must call each of them wrong, without asking mathema."""
from mathema._devtools import verdict_families as V
from mathema.records import Probe

CASES = V.cases_of(V.FAMILIES)


def _stub(verdict, counterexample=None, sketch=None):
    def checker(fn, text):
        cx = counterexample(text) if callable(counterexample) else counterexample
        return [Probe(name="c", statement=text, verdict=verdict, counterexample=cx, sketch=sketch)]
    return checker


def _judged(case, checker):
    outcome = V.check_case(case, honour_rules=False, checker=checker)
    return V.judge(case, outcome, V.ground_truth(case, V._witness_points(case, [outcome])))


def test_a_checker_that_proves_everything_is_wrong_on_every_false_case():
    false_cases = [c for c in CASES if V.known_truth(c, V.ground_truth(c)) is False]
    statuses = {c.name: _judged(c, _stub("proven")).status for c in false_cases}
    assert len(false_cases) > 40
    assert sorted(n for n, s in statuses.items() if s != V.WRONG) == []


def test_a_checker_that_proves_everything_is_not_wrong_on_a_true_case():
    true_cases = [c for c in CASES if V.known_truth(c, V.ground_truth(c)) is True]
    assert len(true_cases) > 40
    assert [c.name for c in true_cases if _judged(c, _stub("proven")).status == V.WRONG] == []


def _first_point(case):
    parsed = V.parse_claim(case.claim, case.points)
    return {n: d.points()[0] for n, d in parsed.bindings}


def test_a_falsification_whose_witness_holds_is_wrong():
    # value and raise claims true at every point: the witness is the first domain point
    cases = [c for c in CASES if c.truth is True and c.points is None
             and V._top_word(V.parse_claim(c.claim).body)[1] is None
             and V.parse_claim(c.claim).bindings]
    assert len(cases) > 15

    def witness(case):
        return ", ".join(f"{n} = {v!r}" for n, v in _first_point(case).items()) + ": 0 vs 1"

    wrong = []
    for case in cases:
        found = _judged(case, _stub("falsified", counterexample=lambda text, c=case: witness(c)))
        if found.status != V.WRONG:
            wrong.append((case.name, found.reason))
    assert wrong == []


def test_a_row_that_shows_the_marker_is_a_leak():
    marked = [c for c in CASES if c.marker]
    assert len(marked) >= 5
    shown = "-".join(("ZQX", "MK", "7f3a")).replace("-", "")
    found = {c.name: _judged(c, _stub("proven", sketch=f"_held became a {shown} object")).status
             for c in marked}
    assert set(found.values()) == {V.LEAK}


def test_a_row_without_the_marker_is_no_leak():
    marked = [c for c in CASES if c.marker]
    found = {c.name: _judged(c, _stub("proven", sketch="_held changed")).status for c in marked}
    assert V.LEAK not in found.values()


def test_the_ground_truth_never_confirms_a_proof():
    case = V.Case("toy.true", "tests.families.functions.safety:pure",
                  "for x in [0, 1], f(x) == 2 * x", "toy")
    assert V.ground_truth(case).kind == V.TRUE_EVERYWHERE
    assert V.ground_truth(case).known is None


def test_a_ground_truth_call_leaves_the_module_as_it_was():
    from tests.families.functions import safety
    before = list(safety._log)
    case = V.Case("toy.write", "tests.families.functions.safety:appends",
                  "for x in [0, 1], not is_state_safe(f)", "toy")
    assert V.ground_truth(case).kind == V.TRUE_AT
    assert safety._log == before
