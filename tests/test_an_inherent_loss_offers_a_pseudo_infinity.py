# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A computation line whose loss is inherent (no float64 computation
could deliver the result at the witness) along an unbounded direction
offers `let |inf| be B`, which bounds only the computation: a proof
keeps its full domain. B is the power of ten below where the condition
number times the unit roundoff meets the relative allowance, and the
offer is made only after the claim with that binding has been run and
its computation line holds. A bounded wide domain, with no unbounded
direction for `|inf|` to bound, keeps the offer to narrow it."""
import re

import mathema
from mathema.conjecture import check_conjectures, claim


def running_total(xs: list, y0: float) -> float:
    total = y0
    for v in xs:
        total = v + total
    return total


def walk_total(xs: list, y0: float) -> float:
    total = y0
    i = 0
    while i < len(xs):
        total = xs[i] + total
        i += 1
    return total


_SHIFT = "f(xs, y0) == f(xs, 0) + y0"


def _rows(fn, statement):
    rec = mathema.check(fn, claims=[mathema.claim(statement, name="law")])
    return {p.name: p for p in rec.probes}, rec


def _offer(found) -> str:
    assert re.fullmatch(r"let \|inf\| be \S+", found["narrow"] or ""), found
    return found["narrow"]


def test_a_proofs_computation_line_offers_a_pseudo_infinity():
    rows, rec = _rows(running_total, _SHIFT)
    assert rows["law"].verdict == "proven"
    line = rows["law[float]"]
    assert line.verdict == "falsified", line.note
    found = line.meta["mathema.conditioning"]
    assert found["inherent"] is True, found
    offer = _offer(found)
    text = repr(rec)
    assert ("if inputs this large are out of scope, bound the computation "
            f"alone (the claim keeps its domain): {offer}") in text, text
    assert "narrow the domain" not in text, text
    # the offer was run: the claim with it is still proven over its full
    # domain, and its computation line holds
    bound, _ = _rows(running_total, f"{offer}, {_SHIFT}")
    assert bound["law"].verdict == "proven"
    assert bound["law[float]"].verdict == "holds", bound["law[float]"].sketch


def _offered_only_where_it_holds(found, fn, statement, **kw):
    """An unbounded direction offers no narrowing; it offers `let |inf|
    be B` only where the claim with that binding holds."""
    narrow = found["narrow"]
    if narrow is None:
        return
    offer = _offer(found)
    (held,) = check_conjectures(fn, [claim(f"{offer}, {statement}",
                                           name="law", **kw)])
    assert held.verdict == "holds", (held.verdict, held.counterexample)


def test_a_probe_only_line_offers_a_pseudo_infinity_only_where_it_holds():
    # derive cannot read the while loop, so the probe is the only line;
    # f run on the exact numbers says the claim holds at the witness
    statement = f"for y0 in [-10, 10], {_SHIFT}"
    rows, _rec = _rows(walk_total, statement)
    line = rows["law"]
    assert line.verdict == "falsified"
    assert line.route == "probe"
    assert "law[float]" not in rows
    found = line.meta["mathema.conditioning"]
    assert found["inherent"] is True, found
    _offered_only_where_it_holds(found, walk_total, statement)


def test_a_claim_on_the_probe_route_offers_it_only_where_it_holds():
    statement = f"for xs in R^n, y0 in [-10, 10], {_SHIFT}"
    (p,) = check_conjectures(running_total, [claim(statement, route="probe")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    _offered_only_where_it_holds(p.meta["mathema.conditioning"],
                                 running_total, statement, route="probe")


def test_a_probe_only_lines_offer_names_the_claim_itself(monkeypatch):
    # the rendering of an offer the run confirmed, on a line that is the
    # claim itself: accepting it is accepting the whole claim
    from mathema import conjecture
    monkeypatch.setattr(conjecture, "_computation_holds_with",
                        lambda rerun, bound: True)
    rows, rec = _rows(walk_total, f"for y0 in [-10, 10], {_SHIFT}")
    offer = _offer(rows["law"].meta["mathema.conditioning"])
    text = repr(rec)
    assert ("if inputs this large are out of scope, bound the computation "
            f"alone (the claim keeps its domain): {offer}") in text, text
    assert re.search(r"run: mathema accept \S*walk_total law --as discovery",
                     text), text


def test_a_bounded_wide_domain_still_offers_to_narrow_it():
    rows, rec = _rows(running_total,
                      f"for xs in [-1e16, 1e16]^2, y0 in {{1}}, {_SHIFT}")
    found = rows["law[float]"].meta["mathema.conditioning"]
    assert found["narrow"] == "for xs in [-1e8, 1e8]^2", found
    assert "|inf|" not in repr(rec).split("possible fixes:")[1].split(
        "policy")[0]


def test_an_offer_whose_computation_still_fails_is_not_made(monkeypatch):
    # with every run of the bound claim failing, nothing is offered: the
    # loss stays acceptable on its own, the binding is not suggested
    from mathema import conjecture
    real = conjecture._computation_holds_with

    def never(*args, **kwargs):
        real(*args, **kwargs)
        return False

    monkeypatch.setattr(conjecture, "_computation_holds_with", never)
    rows, rec = _rows(running_total, _SHIFT)
    found = rows["law[float]"].meta["mathema.conditioning"]
    assert found["inherent"] is True
    assert found["narrow"] is None, found
    assert "|inf|" not in repr(rec).split("possible fixes:")[1]
    assert '"law[float]" --as discovery' in repr(rec)


def test_a_chains_computation_line_offers_one_the_whole_chain_holds_under():
    statement = "f(xs, 0) + y0 <= f(xs, y0) <= f(xs, 0) + y0"
    rows, _rec = _rows(running_total, statement)
    assert rows["law"].verdict == "proven"
    line = rows["law[float]"]
    assert line.verdict == "falsified"
    offer = _offer(line.meta["mathema.conditioning"])
    bound, _ = _rows(running_total, f"{offer}, {statement}")
    assert bound["law"].verdict == "proven"
    assert bound["law[float]"].verdict == "holds", bound["law[float]"].sketch
