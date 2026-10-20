# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim stated with route derive asks for derive's verdict. When
derive cannot settle it (a body it cannot read, a branch it cannot
decide, a timeout) the probe still samples it, as a falsifier only: an
executed counterexample falsifies the claim, named on its probe route
with derive's reason in the note, and draws that find no counterexample
leave the claim unknown on the derive route, never holds. A proof, its
[float] companion and a disproof's executed witness are as on any route.
The default route, best, still takes the probe's holds."""
import math

import pytest

from mathema.conjecture import check_conjectures, claim
from mathema.types import Vec

_NO_VERDICT = "on the derive route a sampled pass is not a verdict"


def guarded(x: float) -> float:
    if x < 0:
        raise ValueError("neg")
    return x + 1


def head(xs: Vec("n")) -> float:
    return xs[0]


def paid(payment: float) -> float:
    total = 0.0
    month = 0
    while month < 12:
        total = total + payment * (1.01 ** month)
        month += 1
    return total


def double(x: float) -> float:
    return 2 * x


_FALSE = [
    (guarded, "assuming x >= 5, for x in [-10, 10], f(x) >= 7"),
    (paid, "for payment in [-10, 10], f(payment) >= 0"),
]

_TRUE_UNREAD = [
    (head, "f(xs) == xs[0]"),
    (paid, "for payment in [-10, 10], f(payment) >= -1000"),
    (paid, "for payment in [-10, 10], d(f(payment), payment) >= 0"),
    (paid, "for payment in [-10, 10], 0 <= f(payment) - f(payment) <= 1"),
]


@pytest.mark.parametrize("fn, text", _FALSE)
def test_a_false_claim_derive_cannot_settle_is_falsified_by_the_probe(fn, text):
    (p,) = check_conjectures(fn, [claim(text, name="c", route="derive")])
    assert p.verdict == "falsified", p
    assert (p.route or "").startswith("probe"), p
    assert p.counterexample
    assert "derive could not decide" in p.note


@pytest.mark.parametrize("fn, text", _TRUE_UNREAD)
def test_a_true_claim_derive_cannot_settle_is_unknown_never_holds(fn, text):
    (p,) = check_conjectures(fn, [claim(text, name="c", route="derive")])
    assert (p.verdict, p.route) == ("unknown", "derive"), p
    assert "the probe decided it" not in p.note


def test_the_note_carries_derives_reason_and_the_draws():
    (p,) = check_conjectures(head, [claim("f(xs) == xs[0]", name="c",
                                          route="derive")])
    assert "derive could not decide it (" in p.note
    assert "draws found no counterexample" in p.note
    assert _NO_VERDICT in p.note
    assert p.meta["mathema.derive_status"] == "unliftable"
    assert p.meta["mathema.routes_attempted"].startswith(
        "routes attempted, derive: underivable")


@pytest.mark.parametrize("fn, text", _TRUE_UNREAD[:2])
def test_the_default_route_still_takes_the_probes_holds(fn, text):
    (p,) = check_conjectures(fn, [claim(text, name="c")])
    assert p.verdict == "holds", p
    assert (p.route or "").startswith("probe"), p
    assert _NO_VERDICT not in (p.note or "")


def count_up(x: float) -> float:
    n = 0
    while n < x:
        n += 1
    return n


def ceiling_at_zero(x: float) -> float:
    return max(math.ceil(x), 0)


def floor_at_zero(x: float) -> float:
    return max(math.floor(x), 0)


def test_an_equivalence_on_derive_samples_as_a_falsifier_only():
    text = "for x in [-5, 5], f =:= g"
    (agree,) = check_conjectures(count_up, [claim(
        text, name="c", route="derive", funcs={"g": ceiling_at_zero})])
    assert agree.verdict == "unknown"
    assert agree.route != "probe"
    assert "found no disagreement, which on the derive route is not a " \
        "verdict" in agree.note
    (differ,) = check_conjectures(count_up, [claim(
        text, name="c", route="derive", funcs={"g": floor_at_zero})])
    assert (differ.verdict, differ.route) == ("falsified", "probe")
    (best,) = check_conjectures(count_up, [claim(
        text, name="c", funcs={"g": ceiling_at_zero})])
    assert (best.verdict, best.route) == ("holds", "probe")


def test_a_decided_derive_claim_is_unchanged():
    (p,) = check_conjectures(double, [claim("for x in [-10, 10], f(x) == 2*x",
                                            name="c", route="derive")])
    assert (p.verdict, p.route) == ("proven", "derive:extensive")
    assert "corroborated by the extensive rungs" in p.note
    assert _NO_VERDICT not in (p.note or "")


def test_a_derive_proof_keeps_its_float_companion():
    rows = {p.name: p for p in check_conjectures(double, [claim(
        "for x in [-10, 10], f(x) == 2*x", name="c", route="derive")],
        float_companions=True)}
    assert (rows["c"].verdict, rows["c"].route) == ("proven", "derive:extensive")
    assert rows["c"].meta["mathema.float_companion"] == "c[float]"
    assert rows["c[float]"].verdict == "holds"


def test_a_derive_disproof_keeps_its_executed_witness():
    (p,) = check_conjectures(double, [claim(
        "for x in [0, 4], f(x) == 3*x", name="c", route="derive")])
    assert p.verdict == "falsified"
    assert p.route in ("derive", "probe:semi_analytical")
    assert p.meta["mathema.corroboration"] == "reproduced"
    assert p.counterexample


def test_an_uncorroborated_derive_disproof_is_unknown_with_the_flag(monkeypatch):
    from mathema.symbolic import _proof_support as ps

    def forged_disproof(lhs, rhs, diff, relation, domain, bound_context, params,
                        tolerance=1e-9):
        return ps.ProofResult("disproven", sketch="forged sign error",
                              witness={"x": 3.0}, disproof_hint=None)

    monkeypatch.setitem(ps._RELATION_DECIDERS, ">=", forged_disproof)

    def sq(x):
        return x * x
    (p,) = check_conjectures(sq, [claim("for x in [-5, 5], f(x) >= 0",
                                        name="c", route="derive")])
    assert (p.verdict, p.route) == ("unknown", "derive")
    assert p.meta.get("mathema.corroboration") == "uncorroborated"
    assert "mathema bug" in p.note
    assert _NO_VERDICT in p.note


def lifted(x: float) -> float:
    return x * x + 1


def test_a_derive_proof_over_the_reals_is_corroborated_by_the_extensive_rungs():
    (p,) = check_conjectures(lifted, [claim("f(x) >= 1", name="c",
                                            route="derive")])
    assert (p.verdict, p.route) == ("proven", "derive:extensive")
    assert "corroborated by the extensive rungs" in p.note


def test_the_default_routes_proof_is_not_re_decided():
    (p,) = check_conjectures(lifted, [claim("f(x) >= 1", name="c")])
    assert (p.verdict, p.route) == ("proven", "derive")
    assert "corroborated by the extensive rungs" not in (p.note or "")


def test_a_corroborated_proof_keeps_its_computation_line():
    import mathema
    rec = mathema.check(lifted, claims=[claim("f(x) >= 1", name="c",
                                              route="derive")])
    rows = {p.name: p for p in rec.probes}
    assert rows["c"].route == "derive:extensive"
    assert rows["c"].meta["mathema.float_companion"] == "c[float]"
    assert "c[float]" in rows
    text = repr(rec)
    assert "computation" in text and "mathematics" in text
