# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Missing values on scalars: every row of the core battery, each
asserting the verdict a claim over a missing value comes to and, where
one is named, the member its witness holds.

`None` is the absence of the object; `missing` is a hole in a slot,
resolved per slot type (a `float` slot's hole is `nan`). A row carries
a strict `xfail` naming the stage of the build that makes it pass, so a
row that starts passing early fails the suite and is noticed."""
import math
from typing import Optional

import pytest

import mathema


def sqrt_plain(x: float) -> float:
    return math.sqrt(x)


def sqrt_guarded(x: float) -> float:
    if x is None or x != x:
        raise ValueError("missing")
    return math.sqrt(x)


def double_or_missing(x: Optional[float]) -> Optional[float]:
    if x is None:
        return None
    return 2 * x


def zero_if_missing(x: Optional[float]) -> float:
    if x is None or x != x:
        return 0.0
    return float(x)


def ident(x):
    return x


def add(x: float, y: float) -> float:
    return x + y


def stage(n: int):
    """The strict marker of a row a later stage of the build owns."""
    return pytest.mark.xfail(strict=True, reason=f"missing values stage {n}")


def run(fn, text: str):
    """The claim's own row and its companions, as `(probe, companions)`."""
    report = mathema.check(fn, claims=[mathema.claim(text, name="c")])
    rows = [p for p in report.probes if p.name == "c" or p.name.startswith("c[")]
    main = next(p for p in rows if p.name == "c")
    return main, [p for p in rows if p.name != "c"]


def witness(probe) -> str:
    return probe.counterexample or ""


def tried(probe) -> dict:
    """The values each parameter's admitted sentinels were executed as."""
    return ((probe.meta or {}).get("mathema.missing") or {}).get("tried") or {}


def behaviour(*probes) -> dict:
    """What the code did at each missing input the rows executed, `{param:
    {member: behaviour}}`, over every row given."""
    out: dict = {}
    for probe in probes:
        found = ((probe.meta or {}).get("mathema.missing") or {}).get("behaviour") or {}
        for p, members in found.items():
            for member, seen in members.items():
                out.setdefault(p, {}).setdefault(member, seen)
    return out


def assert_row(fn, text, verdicts, *, member=None, raised=None,
               companion=None, companion_member=None, executed=None,
               companions_none=False, behaves=None):
    """Intent:
        Adjudicate `text` over `fn` and check the row: the verdict is
        one of `verdicts`, the witness names `member` and the exception
        `raised` when given, a companion comes to `companion` with its
        witness naming `companion_member` when given, the main claim
        executed each value in `executed` (`{param: [value, ...]}`),
        with `companions_none` no companion was spawned, and with
        `behaves` the behaviour at each missing input the rows executed
        is the one given (`{param: {member: behaviour}}`).
    """
    probe, companions = run(fn, text)
    assert probe.verdict in verdicts, (probe.verdict, probe.note, witness(probe))
    for p, values in (executed or {}).items():
        assert set(values) <= set(tried(probe).get(p, [])), (p, tried(probe))
    if companions_none:
        assert not companions, [(c.name, c.verdict) for c in companions]
    if member is not None:
        assert f"={member}" in witness(probe) or f"({member}" in witness(probe), \
            witness(probe)
    if raised is not None:
        said = f"{witness(probe)} {probe.note or ''} {probe.sketch or ''}"
        assert raised in said, said
    if companion is not None:
        assert any(c.verdict == companion for c in companions), \
            [(c.name, c.verdict, witness(c)) for c in companions]
        if companion_member is not None:
            assert any(c.verdict == companion and companion_member in witness(c)
                       for c in companions), \
                [(c.name, c.verdict, witness(c)) for c in companions]
    if behaves is not None:
        assert behaviour(probe, *companions) == behaves, \
            behaviour(probe, *companions)
    return probe, companions


PROVEN = ("proven",)
PROVEN_OR_HOLDS = ("proven", "holds")
FALSIFIED = ("falsified",)


def test_s1_a_float_proof_carries_a_companion_that_holds_on_values():
    assert_row(sqrt_plain, "for x in [0, 1], f(x) >= 0", PROVEN,
               companion="holds", behaves={"x": {"nan": "propagates"}})


def test_s3_a_raise_at_a_listed_none_is_classified():
    assert_row(sqrt_plain, "for x in {0.25, None}, f(x) >= 0", PROVEN,
               executed={"x": ["None"]}, behaves={"x": {"None": "raises"}})


def test_s4_a_propagated_listed_nan_is_classified():
    assert_row(sqrt_plain, "for x in {0.25, nan}, f(x) >= 0", PROVEN,
               executed={"x": ["nan"]}, behaves={"x": {"nan": "propagates"}})


def test_s5_a_guarded_float_companion_holds_and_the_guard_raises():
    assert_row(sqrt_guarded, "for x in [0, 1], f(x) >= 0", PROVEN,
               companion="holds", behaves={"x": {"nan": "raises"}})


def test_s6_a_listed_none_raising_valueerror_is_classified():
    probe, _ = assert_row(sqrt_guarded, "for x in {0.25, None}, f(x) >= 0", PROVEN,
                          behaves={"x": {"None": "raises"}})
    assert probe.meta["mathema.missing"]["executed"]["x"]["None"] == "raised ValueError"


def test_s7_an_optional_float_companion_holds_and_both_kinds_propagate():
    assert_row(double_or_missing, "for x in [0, 1], f(x) >= 0", PROVEN,
               companion="holds",
               behaves={"x": {"None": "propagates", "nan": "propagates"}})


def test_s8_a_propagated_absence_is_classified():
    assert_row(double_or_missing, "for x in {0.25, None}, f(x) >= 0", PROVEN,
               executed={"x": ["None"]}, behaves={"x": {"None": "propagates"}})


def test_s9_a_replaced_hole_holds_on_both_halves():
    probe, companions = assert_row(zero_if_missing, "for x in [0, 1], f(x) >= 0",
                                   PROVEN, behaves={"x": {"None": "drops", "nan": "drops"}})
    assert companions and all(c.verdict in PROVEN_OR_HOLDS for c in companions)
    assert any(set(tried(c).get("x", [])) >= {"None", "nan"} for c in companions)


def test_s10_a_replaced_absence_is_proven_by_execution_alone():
    assert_row(zero_if_missing, "for x in {0.25, None}, f(x) >= 0", PROVEN,
               executed={"x": ["None"]}, companions_none=True,
               behaves={"x": {"None": "drops"}})


def test_s11_propagation_is_classified_and_the_companion_holds():
    probe, companions = assert_row(ident, "for x in [0, 1], f(x) == x", PROVEN,
                                   behaves={"x": {"None": "propagates",
                                                  "nan": "propagates"}})
    assert companions and all(c.verdict in PROVEN_OR_HOLDS for c in companions)
    assert any("nan" in tried(c).get("x", []) for c in companions)


def test_s12_absence_propagates_through_the_identity():
    assert_row(ident, "for x in {0.25, None}, f(x) == x", PROVEN,
               executed={"x": ["None"]}, behaves={"x": {"None": "propagates"}})


def test_s13_a_hole_propagates_through_the_identity():
    assert_row(ident, "for x in {0.25, nan}, f(x) == x", PROVEN,
               executed={"x": ["nan"]}, behaves={"x": {"nan": "propagates"}})


def test_s16_a_raise_at_the_second_parameters_absence_is_classified():
    assert_row(add, "for x in [0, 1], y in {0.5, None}, f(x, y) >= 0", PROVEN,
               executed={"y": ["None"]},
               behaves={"y": {"None": "raises"}, "x": {"nan": "propagates"}})


def test_p1_a_policy_that_does_not_raise_at_nan_is_falsified():
    assert_row(sqrt_plain, "for x in {missing}, raises(f(x))", FALSIFIED,
               member="nan")


def test_p2_the_one_member_raises_the_stated_exception():
    assert_row(sqrt_guarded, "for x in {missing}, raises(f(x), ValueError)", PROVEN,
               executed={"x": ["nan"]})


def test_p3_a_replacement_policy_is_proven():
    assert_row(zero_if_missing, "for x in {missing}, f(x) == 0", PROVEN,
               executed={"x": ["nan"]}, behaves={"x": {"nan": "drops"}})


def test_p4_membership_by_class_is_proven():
    assert_row(double_or_missing, "for x in {missing}, f(x) in {missing}", PROVEN,
               executed={"x": ["nan"]})


def test_v0_a_value_claim_over_a_propagated_hole_alone_is_unknown():
    assert_row(sqrt_plain, "for x in {missing}, f(x) >= 0", ("unknown",),
               behaves={"x": {"nan": "propagates"}})


# the policy claims each behaviour above states

@pytest.mark.parametrize("fn, text, verdicts", [
    (sqrt_plain, "missing(f, x) propagates", PROVEN_OR_HOLDS),
    (sqrt_plain, "absent(f, x) raises(TypeError)", PROVEN_OR_HOLDS),
    (sqrt_guarded, "missing(f, x) raises(ValueError)", PROVEN_OR_HOLDS),
    (double_or_missing, "absent(f, x) propagates", PROVEN_OR_HOLDS),
    (zero_if_missing, "missing(f, x) drops", PROVEN_OR_HOLDS),
    (zero_if_missing, "absent(f, x) drops", PROVEN_OR_HOLDS),
    (ident, "missing(f, x) propagates", PROVEN_OR_HOLDS),
    (add, "absent(f, y) raises(TypeError)", PROVEN_OR_HOLDS),
    (sqrt_plain, "missing(f, x) drops", FALSIFIED),
])
def test_the_behaviour_is_a_policy_claim(fn, text, verdicts):
    assert_row(fn, text, verdicts)


def test_m1_nan_propagating_through_a_float_is_missing_safe():
    assert_row(sqrt_plain, "is_missing_safe(f)", PROVEN)


def test_m3_a_guard_is_read_as_missing_raises():
    assert_row(sqrt_guarded, "is_missing_safe(f)", PROVEN)


def test_m4_an_optional_float_is_missing_safe():
    assert_row(double_or_missing, "is_missing_safe(f)", PROVEN)


def test_m5_a_replacing_function_is_missing_safe():
    assert_row(zero_if_missing, "is_missing_safe(f)", PROVEN)


def test_m6_an_unannotated_identity_is_missing_safe():
    assert_row(ident, "is_missing_safe(f)", PROVEN)


def test_l1_a_gate_is_not_a_premise():
    probe, _ = run(sqrt_guarded, "assuming is_missing_safe(f), for x in [0, 1], f(x) >= 0")
    assert probe.verdict == "skipped:misspecified", (probe.verdict, probe.note)
    assert probe.note == (
        "assuming is_missing_safe(f) is not a premise: a value claim is never judged "
        "where f returns a missing value, so the premise would change nothing. State "
        "what f does with a missing x as its own claim (`missing(f, x) propagates`, "
        "`drops` or `raises`), or write `\\ {missing}` in the domain so f is not "
        "called with one.")
    probe, _ = run(sqrt_guarded, "assuming is_absent_safe(f), for x in [0, 1], f(x) >= 0")
    assert probe.verdict == "skipped:misspecified", (probe.verdict, probe.note)
    assert probe.note == (
        "assuming is_absent_safe(f) is not a premise: a value claim is never judged "
        "where f returns None, so the premise would change nothing. State what f does "
        "when x is None as its own claim (`absent(f, x) raises(TypeError)`), or write "
        "`\\ {absent}` in the domain so f is not called with None.")
