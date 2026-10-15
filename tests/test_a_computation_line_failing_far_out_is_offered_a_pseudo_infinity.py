# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A computation line falsified along an unbounded direction of a proven
claim is offered `let |inf| be B` whenever the claim with that binding
has been run and its computation line holds, whether or not a condition
number was read at the witness: an overflow, a nan and a raise at
float64's edge are offered it too. B is the largest power of ten below
the witness's magnitude at which the run holds, found by bisection on
the exponent within a fixed number of runs. The binding bounds only the
computation: the proof under it is the same proof over the full domain.
Where the condition number gives a B (an inherent loss), that B is kept
when its run holds. Where no power of ten holds, nothing is offered."""
import math

import mathema
from mathema import conjecture
from mathema.records import PseudoInfinity

_OFFER = "mathema.infinity_offer"


def gauss(x: float) -> float:
    return math.exp(-x ** 2 / 2) / math.sqrt(2 * math.pi)


def squares_cancel(x: float) -> float:
    return x * x - x * x


def exponential(x: float) -> float:
    return math.exp(x)


def plus_one_minus(x: float) -> float:
    return (x + 1.0) - x


def running_total(xs: list, y0: float) -> float:
    total = y0
    for v in xs:
        total = v + total
    return total


def shifted_back(x: float) -> float:
    return (x + 1.5e308) - 1.5e308


def _rows(fn, statement):
    rec = mathema.check(fn, claims=[mathema.claim(statement, name="law")])
    return {p.name: p for p in rec.probes}, rec


def _offered(fn, statement):
    rows, rec = _rows(fn, statement)
    assert rows["law"].verdict == "proven", rows["law"].sketch
    line = rows["law[float]"]
    assert line.verdict == "falsified", line.note
    return line, rec


def _bound_of(line) -> float:
    offer = line.meta[_OFFER]
    bound = offer["bound"]
    assert offer["words"] == PseudoInfinity(bound, "claim").render(), offer
    assert math.log10(bound) == round(math.log10(bound)), bound
    return bound


def _holds_under(fn, statement, bound) -> tuple:
    words = PseudoInfinity(bound, "claim").render()
    rows, _rec = _rows(fn, f"{words}, {statement}")
    return rows["law"], rows["law[float]"]


def _largest_holding(fn, statement, bound):
    law, line = _holds_under(fn, statement, bound)
    # the proof is the same proof over the full domain
    assert law.verdict == "proven"
    assert "|inf|" not in (law.condition or ""), law.condition
    assert line.verdict == "holds", (line.counterexample, line.sketch)
    _law, wider = _holds_under(fn, statement, bound * 10)
    assert wider.verdict == "falsified", wider.note


def test_an_overflow_is_offered_the_largest_binding_that_holds():
    line, rec = _offered(gauss, "f(x) >= 0")
    assert "mathema.conditioning" not in (line.meta or {})
    bound = _bound_of(line)
    assert bound == 1e154
    _largest_holding(gauss, "f(x) >= 0", bound)
    text = repr(rec)
    assert ("bound the computation alone (the claim keeps its "
            f"domain): {line.meta[_OFFER]['words']}") in text, text


def test_a_nan_is_offered_the_largest_binding_that_holds():
    statement = "for x in R, f(x) == 0"
    line, _rec = _offered(squares_cancel, statement)
    assert "mathema.conditioning" not in (line.meta or {})
    bound = _bound_of(line)
    assert bound == 1e154
    _largest_holding(squares_cancel, statement, bound)


def test_a_raise_is_offered_the_largest_binding_that_holds():
    # math.exp raises OverflowError past about 709.78
    line, _rec = _offered(exponential, "f(x) >= 0")
    assert "mathema.conditioning" not in (line.meta or {})
    bound = _bound_of(line)
    assert bound == 100
    _largest_holding(exponential, "f(x) >= 0", bound)


def test_a_loss_that_is_the_codes_is_offered_a_binding_too():
    statement = "for x in [0, oo], f(x) == 1"
    line, rec = _offered(plus_one_minus, statement)
    assert line.meta["mathema.conditioning"]["inherent"] is False
    bound = _bound_of(line)
    # x + 1.0 is exact below 2**53, about 9e15
    assert bound == 1e15
    _largest_holding(plus_one_minus, statement, bound)
    assert line.meta[_OFFER]["words"] in repr(rec), repr(rec)


def test_the_conditionings_own_bound_is_kept_where_it_holds():
    statement = "f(xs, y0) == f(xs, 0) + y0"
    rows, _rec = _rows(running_total, statement)
    line = rows["law[float]"]
    found = line.meta["mathema.conditioning"]
    assert found["inherent"] is True
    from mathema._conditioning import _magnitude_bound
    assert _bound_of(line) == _magnitude_bound(found["kappa"], found["scale"])


def test_a_conditioning_bound_that_fails_gives_way_to_the_search():
    # at x = -1.8e308 exp gives 0.0, an inherent loss whose condition
    # number puts B near 1e6, where exp(-1e6) is 0.0 again
    line, _rec = _offered(exponential, "f(x) > 0")
    assert line.meta["mathema.conditioning"]["inherent"] is True
    bound = _bound_of(line)
    assert bound == 100
    _largest_holding(exponential, "f(x) > 0", bound)


def test_a_bounded_domain_offers_no_binding():
    statement = "for x in [-1e300, 1e300], f(x) == 0"
    line, _rec = _offered(squares_cancel, statement)
    assert _OFFER not in (line.meta or {})


def test_where_no_power_of_ten_holds_nothing_is_offered(monkeypatch):
    real = conjecture._computation_holds_with
    runs = []

    def counted(rerun, bound):
        runs.append(bound)
        return real(rerun, bound)

    monkeypatch.setattr(conjecture, "_computation_holds_with", counted)
    line, rec = _offered(shifted_back, "for x in [0, oo], f(x) == x")
    assert _OFFER not in (line.meta or {})
    assert "|inf|" not in repr(rec).split("possible fixes:")[-1], repr(rec)
    # the search ran, within its fixed number of runs, each a power of
    # ten, every run through the one that files its calls apart from the
    # check's own evidence
    assert 0 < len(runs) <= conjecture._INFINITY_RERUNS, runs
    assert all(math.log10(b) == round(math.log10(b)) for b in runs), runs

