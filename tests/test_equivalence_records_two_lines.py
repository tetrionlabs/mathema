# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`f =:= g` records two lines. The claim's own row is the mathematics:
derive's exact ladder (one canonical form, the symbolic difference, the
closed forms, refusal regions coinciding), where a disproof stands once
both sides evaluated exactly at derive's witness confirm it, however
small the difference. The computation row, `NAME[float]`, runs both
functions at shared points under the claim's tolerance. The claim is
falsified when either line is. When derive cannot reach the bodies, the
probe's row is the claim's only row, as for a value claim."""
import math
from dataclasses import replace

import mathema
from mathema.analysis import analyze_source
from mathema.conjecture import check_conjectures, claim
from tests._equivalence_rows import claim_row, computation_row


def tri_naive(a, b, c):
    return (1 * a + 2 * b + 3 * c) / 6.0


def tri_incr(a, b, c):
    acc = a
    acc = acc + 2 * b
    acc = acc + 3 * c
    return acc / 6.0


def _root(x: float) -> float:
    return math.sqrt(x)


def _nudged_root(x: float) -> float:
    return math.sqrt(x) + 1e-12


def _big_plus(x: float) -> float:
    return x + 1e-3


def _identity(x: float) -> float:
    return x


def _cancelling(x: float) -> float:
    return (x + 1e20) - 1e20


def _rows(f, g, law, **kwargs):
    return check_conjectures(f, [claim(law, funcs={"g": g}, **kwargs)])


def test_a_proven_pair_records_its_computation_beside_the_proof():
    rows = _rows(tri_naive, tri_incr,
                 "for a in [-3, 3], b in [-3, 3], c in [-3, 3], f =:= g")
    main, computation = claim_row(rows), computation_row(rows)
    assert main.verdict == "proven" and main.route == "derive"
    assert computation is not None, rows
    assert computation.name == f"{main.name}[float]"
    assert computation.meta["mathema.companion_of"] == main.name
    assert computation.statement == main.statement
    assert computation.verdict == "holds", (computation.verdict,
                                            computation.note)
    assert computation.route == "probe"
    assert computation.n >= 24
    assert computation.meta["mathema.equivalence.sampling"]["seed"] \
        == 20260718
    # the computation row follows the claim it belongs to
    assert rows.index(computation) == rows.index(main) + 1


def test_a_difference_below_the_sampling_tolerance_is_falsified_exactly():
    rows = _rows(_root, _nudged_root, "for x in [0, 4], f =:= g")
    main, computation = claim_row(rows), computation_row(rows)
    assert main.verdict == "falsified", (main.verdict, main.note)
    assert main.route == "derive"
    assert main.meta["mathema.corroboration"] == "reproduced"
    assert main.counterexample.startswith("x = "), main.counterexample
    # the computation runs both functions in float, where 1e-12 is
    # inside the default tolerance
    assert computation is not None
    assert computation.verdict == "holds", (computation.verdict,
                                            computation.note)


def test_a_tolerance_applies_to_the_computation_line_only():
    rows = _rows(_big_plus, _identity, "for x in [1e7, 1e8], f =:= g",
                 tolerance=1e-2)
    main, computation = claim_row(rows), computation_row(rows)
    assert main.verdict == "falsified", (main.verdict, main.note)
    assert main.route == "derive"
    assert main.meta["mathema.corroboration"] == "reproduced"
    assert computation.verdict == "holds", (computation.verdict,
                                            computation.note)
    # the declared tolerance is the computation's whole allowance
    tight = _rows(_big_plus, _identity, "for x in [1e7, 1e8], f =:= g",
                  tolerance=1e-4)
    assert claim_row(tight).verdict == "falsified"
    assert computation_row(tight).verdict == "falsified"
    assert computation_row(tight).counterexample.startswith("x = ")


def test_a_computation_that_breaks_a_proven_equivalence_falsifies_the_claim():
    rows = _rows(_cancelling, _identity, "for x in [0, 1], f =:= g")
    main, computation = claim_row(rows), computation_row(rows)
    assert main.verdict == "proven", (main.verdict, main.note)
    assert computation.verdict == "falsified", (computation.verdict,
                                                computation.note)
    assert computation.counterexample.startswith("x = ")
    record = mathema.check(_cancelling, claims=[
        mathema.claim("for x in [0, 1], f =:= g",
                      funcs={"g": _identity})])
    lines = repr(record).splitlines()
    (head,) = [ln for ln in lines if ln.startswith(f"  {main.name}  ")]
    assert head.split("   ")[-1].startswith("falsified"), head
    assert any(ln.split()[:2] == ["proven", "mathematics"] for ln in lines)
    assert any(ln.split()[:2] == ["falsified", "computation"]
               for ln in lines)


def test_derive_out_of_reach_leaves_the_probe_row_alone():
    def opaque_twin(*args):
        return (1 * args[0] + 2 * args[1] + 3 * args[2]) / 6.0
    opaque_twin.__mathema_facts__ = replace(analyze_source(tri_naive),
                                            tree=None, form="doc:00aa11bb22")
    rows = _rows(tri_naive, opaque_twin,
                 "for a in [-2, 2], b in [-2, 2], c in [-2, 2], f =:= g",
                 route="probe")
    assert len(rows) == 1, rows
    (row,) = rows
    assert row.verdict == "holds" and row.route == "probe"
    assert computation_row(rows) is None


def _planted_disproof(monkeypatch, witness):
    """The symbolic difference reports a disproof at `witness`, and the
    closed forms decline, whatever the two bodies are."""
    from mathema import equivalence, symbolic
    from mathema.symbolic import ProofResult

    def planted(*args, **kwargs):
        return ProofResult("disproven", sketch="a planted disproof",
                           witness=dict(witness),
                           meta={"mathema.exact_disproof": True})
    monkeypatch.setattr(symbolic, "try_prove", planted)
    monkeypatch.setattr(equivalence, "_closed_forms_identical",
                        lambda *a, **k: None)


def test_a_disproof_exact_evaluation_does_not_confirm_stays_unknown(
        monkeypatch):
    def doubled(x: float) -> float:
        return 2 * x

    def summed(x: float) -> float:
        return x + x
    _planted_disproof(monkeypatch, {"x": 1.5})
    rows = _rows(doubled, summed, "for x in [0, 4], f =:= g")
    main = claim_row(rows)
    assert main.verdict == "unknown", (main.verdict, main.note)
    assert main.meta["mathema.corroboration"] == "uncorroborated"
    assert "mathema bug" in main.note


def test_two_bodies_differing_below_any_float_tolerance_are_falsified():
    from mathema.interfaces.extension import prove_bodies_equal
    from tests.test_two_lifted_bodies_proven_equal_on_a_domain import (
        NOT_NEGATIVE, ROOT, ROOT_NUDGED, body, guarded, returns)
    for left, right, bound in (
            (body(returns(ROOT)), body(returns(ROOT_NUDGED), language="ext"),
             [0.0, 4.0]),
            (body(guarded(ROOT)),
             body(guarded(ROOT_NUDGED, admits=NOT_NEGATIVE)), [-4.0, 4.0])):
        answer = prove_bodies_equal(left, right, {"x": bound})
        assert answer.verdict == "falsified", answer
        assert answer.rung == "symbolic"
        assert answer.meta["mathema.corroboration"] == "reproduced"
        assert 0 <= answer.point["x"] <= 4


def test_a_body_disproof_exact_evaluation_does_not_confirm_stays_unknown(
        monkeypatch):
    from mathema.interfaces.extension import prove_bodies_equal
    from tests.test_two_lifted_bodies_proven_equal_on_a_domain import (
        SUM_WITH_ITSELF, TWICE, body)
    _planted_disproof(monkeypatch, {"x": 1.5})
    answer = prove_bodies_equal(body(TWICE),
                                body(SUM_WITH_ITSELF, language="ext"),
                                {"x": [-4.0, 4.0]})
    assert answer.rung != "form"
    assert answer.verdict == "unknown", answer
    assert answer.meta["mathema.corroboration"] == "uncorroborated"
