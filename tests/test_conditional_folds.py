# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Conditional accumulator updates lift as exact Piecewise summands,
and sign claims over symbolic-length sums prove by the termwise rung:
each term's sign decided over the declared element domain (branch
conditions baked into the element symbol), strictness only from a
provably nonempty sum. A condition reading the accumulator is a
genuine recurrence and stays declined; else-branches stay out for
now."""
import textwrap

from mathema.conjecture import check_conjectures, claim


def _mod(tmp_path, body, name):
    import importlib
    import sys
    path = tmp_path / f"{name}.py"
    path.write_text(textwrap.dedent(body))
    sys.path.insert(0, str(tmp_path))
    try:
        mod = importlib.import_module(name)
        importlib.reload(mod)
    finally:
        sys.path.remove(str(tmp_path))
    return mod


_BODY = """
def sum_positives(values: list) -> float:
    total = 0.0
    for v in values:
        if v > 0:
            total += v
    return total


def count_above(xs: list, thresh: float) -> float:
    count = 0.0
    for x in xs:
        if x >= thresh:
            count += 1.0
    return count


def guarded_scaled(values: list, scale: float) -> float:
    if scale <= 0:
        raise ValueError("scale must be positive")
    total = 0.0
    for v in values:
        if v > 0:
            total += v * scale
    return total


def acc_condition(values: list) -> float:
    total = 0.0
    for v in values:
        if total < 100:
            total += v
    return total


def with_orelse(values: list) -> float:
    total = 0.0
    for v in values:
        if v > 0:
            total += v
        else:
            total -= v
    return total
"""


def test_sum_of_positives_proves_over_the_whole_line(tmp_path):
    mod = _mod(tmp_path, _BODY, "condf_a")
    (p,) = check_conjectures(mod.sum_positives, [claim(
        "f(values) >= 0", route="derive")])
    assert p.verdict == "proven", (p.verdict, p.note)
    assert "each term of the sum" in p.sketch


def test_count_above_proves(tmp_path):
    mod = _mod(tmp_path, _BODY, "condf_b")
    (p,) = check_conjectures(mod.count_above, [claim(
        "for thresh in [-5,5], f(xs, thresh) >= 0", route="derive")])
    assert p.verdict == "proven", (p.verdict, p.note)


def test_lead_guard_strips_and_gates_for_the_sum_shape(tmp_path):
    mod = _mod(tmp_path, _BODY, "condf_c")
    (p,) = check_conjectures(mod.guarded_scaled, [claim(
        "for scale in [0.5, 5], f(values, scale) >= 0", route="derive")])
    assert p.verdict == "proven", (p.verdict, p.note)
    # a domain reaching the guard never proves: pedantic raise verdict
    # (falsified with an executed witness) or the honest guidance
    (p,) = check_conjectures(mod.guarded_scaled, [claim(
        "for scale in [-1, 5], f(values, scale) >= 0", route="derive")])
    assert p.verdict != "proven"


def test_accumulator_condition_declines_honestly(tmp_path):
    mod = _mod(tmp_path, _BODY, "condf_d")
    (p,) = check_conjectures(mod.acc_condition, [claim(
        "f(values) >= -1000000", route="derive")])
    assert p.verdict != "proven"
    assert "guarded-fold" in (p.note or "")


def test_else_branch_now_proves(tmp_path):
    # formerly the declared follow-up (else stays out); landed;
    # flipped deliberately, see test_else_branch_absolute_sum_proves
    mod = _mod(tmp_path, _BODY, "condf_e")
    (p,) = check_conjectures(mod.with_orelse, [claim(
        "f(values) >= 0", route="derive")])
    assert p.verdict == "proven"


def test_else_branch_absolute_sum_proves(tmp_path):
    # `else: total -= v` completes the Piecewise summand, and the
    # termwise rung decides the else branch under the NEGATION of the
    # earlier condition (v <= 0 makes -v nonnegative)
    mod = _mod(tmp_path, _BODY, "condf_g")
    (p,) = check_conjectures(mod.with_orelse, [claim(
        "f(values) >= 0", route="derive")])
    assert p.verdict == "proven", (p.verdict, p.note)
