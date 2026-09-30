# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Every witness names its arguments, `x = nan` with spaces, only the
ones the claim reads, in signature order; no positional `(...)` tuple is
left. A claim that names the function under test renders without a
`let` binding it to itself."""
import re

from mathema.conjecture import check_conjectures, claim


def midpoint(a: float, b: float) -> float:
    return (a + b) // 2


def gap(x: float, unused: float = 1.0) -> float:
    return x - 1.0


def count_up(n: int) -> int:
    return n + 1


def ema(x: list, alpha: float) -> float:
    y = x[0]
    for v in x[1:]:
        y = alpha * v + (1 - alpha) * y
    return y


def _cx(fn, text, **kw):
    (row,) = check_conjectures(fn, [claim(text, **kw)])
    assert row.verdict == "falsified", (row.verdict, row.note)
    return row.counterexample


def test_a_probe_witness_names_every_argument_with_spaces():
    cx = _cx(midpoint, "for a in [0, 100], b in [0, 100], min(a, b) <= f(a, b)",
             route="probe")
    assert re.match(r"^a = \S+, b = \S+: ", cx), cx


def test_a_witness_leaves_out_what_the_claim_never_reads():
    cx = _cx(gap, "for x in [0, 10], f(x) >= 0", route="probe")
    assert cx.startswith("x = ") and "unused" not in cx, cx


def test_a_witness_names_a_literal_the_claim_passes():
    cx = _cx(gap, "for x in [0, 10], f(x, 2.0) >= 0", route="probe")
    assert cx.startswith("x = ") and re.search(r"unused = 2(\.0)?:", cx), cx


def test_a_brute_force_witness_is_named():
    cx = _cx(count_up, "for n in [0, 5] subset Z, f(n) <= 5")
    assert cx.startswith("n = 5"), cx


def test_a_sequence_witness_is_named():
    cx = _cx(ema, "let g = mathema.f.reverse_seq, for x in [0, 1]^n, "
             "alpha in [0.1, 0.9], f(x, alpha) == f(g(x), alpha)")
    assert cx.startswith("x = [") and ", alpha = " in cx and not cx.startswith("("), cx


def test_a_claim_naming_the_function_under_test_binds_nothing():
    (row,) = check_conjectures(midpoint, [claim(
        "for a in [0, 100], b in [0, 100], min(a, b) <= midpoint(a, b) <= max(a, b)",
        funcs={"midpoint": midpoint})])
    assert not row.statement.startswith("let midpoint"), row.statement
    assert "bound midpoint" not in (row.note or ""), row.note
