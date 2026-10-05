# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`a ~= b` means `abs(a - b) <= ε` on both lines: decided exactly on
the mathematics line, in float64 on the computation line, with ε the
claim's declared tolerance or else 1e-9. The record says how it read
the claim. `==` stays exact equality on the mathematics line, and a
bundled definition row, an axiom derive rewrites through, is an exact
equation written with `==`."""
import glob
import os

import pytest
import yaml

import mathema
from mathema.conjecture import _parse_assuming_relation, claim
from mathema.lexicon import LEXICON, exact_offset, sin3

_COMPENDIA = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                          "mathema", "compendium")


def _main(fn, law, **kw):
    rows = mathema.check(fn, claims=[claim(law, **kw)]).probes
    (main,) = [p for p in rows if "[" not in p.name
               and not p.name.startswith(("missing", "absent", "is_"))]
    return main, rows


def test_an_offset_below_epsilon_is_proven_approximately_equal():
    main, _ = _main(exact_offset, LEXICON["exact_offset_vs_approx"])
    assert (main.verdict, main.route) == ("proven", "derive"), main.note


def test_the_same_offset_falsifies_exact_equality():
    main, _ = _main(exact_offset, LEXICON["exact_offset_vs_approx_trap"])
    assert main.verdict == "falsified", main.note


def test_the_record_states_how_it_read_approximate_equality():
    main, _ = _main(exact_offset, LEXICON["exact_offset_vs_approx"])
    assert "read as abs(f(x) - x) <= ε, ε = 1e-9 (the default)" in main.note


def test_a_declared_tolerance_is_the_epsilon_the_record_names():
    main, _ = _main(exact_offset, "for x in [0, 1], f(x) ~= x",
                    tolerance=1e-7)
    assert main.verdict == "proven", main.note
    assert "read as abs(f(x) - x) <= ε, ε = 1e-7 (declared)" in main.note


def test_a_gap_above_epsilon_falsifies_approximate_equality():
    main, _ = _main(sin3, LEXICON["approx_too_wide"])
    assert main.verdict == "falsified", main.note
    assert main.counterexample, main.note


def test_a_truncated_taylor_series_is_not_exactly_the_sine():
    main, _ = _main(sin3, LEXICON["approx_taylor_sin_exact_fails"])
    assert main.verdict == "falsified", main.note


def test_a_premise_reads_approximate_equality_within_epsilon():
    link = _parse_assuming_relation("x ~= 1")
    assert (link.lhs, link.relation, link.rhs) == ("abs((x) - (1))", "<=", "ε")


def test_a_premise_within_epsilon_admits_the_points_it_names():
    from mathema.lexicon import double
    (p,) = mathema.claims.check(double, [claim(
        "for x in [0, 2], assuming x ~= 1, f(x) >= 1.99")])
    assert p.verdict in ("proven", "holds"), p.note
    (q,) = mathema.claims.check(double, [claim(
        "for x in [0, 2], assuming x ~= 1, f(x) ~= 2")])
    assert q.verdict == "falsified", q.note   # 2x is within 2e-9 of 2


def _definition_rows():
    for path in sorted(glob.glob(os.path.join(_COMPENDIA, "**", "*.yaml"),
                                 recursive=True)):
        with open(path, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh) or {}
        for key, entry in doc.items():
            if not isinstance(entry, dict):
                continue
            for row in entry.get("claims") or ():
                name = str(row.get("name", ""))
                if name == "definition" or name.startswith("definition@"):
                    yield os.path.relpath(path, _COMPENDIA), key, name, \
                        row.get("statement", "")


def test_every_bundled_definition_row_is_an_exact_equation():
    rows = list(_definition_rows())
    assert len(rows) > 20
    approximate = [(p, k, n) for p, k, n, s in rows if "~=" in s]
    assert approximate == []


def tenth_times_ten(x: float) -> float:
    """`x`, computed as a tenth of it times ten: equal in the
    mathematics, a rounding away from it in float64."""
    return x * 0.1 * 10


def test_a_rounding_gap_at_large_magnitude_is_within_the_computation_allowance():
    (p,) = mathema.claims.check(tenth_times_ten, [claim(
        "for x in [1e8, 1e9], f(x) ~= x", route="probe")])
    assert p.verdict == "holds", (p.verdict, p.counterexample, p.note)


def test_the_probe_reads_a_premise_within_epsilon():
    """`assuming x ~= 1` admits only the points within ε of 1, so a
    draw far from 1 is never a counterexample."""
    from mathema.lexicon import double
    (p,) = mathema.claims.check(double, [claim(
        "for x in [0, 2], assuming x ~= 1, f(x) >= 1.99", route="probe")])
    assert p.verdict != "falsified", (p.verdict, p.counterexample, p.note)


@pytest.mark.parametrize("law", [
    "for x in [0, 2], assuming x ~= 1, f(x) ~= 2",
    "for x in [0, 2], assuming abs(x - 1) <= 0.5, f(x) <= 1",
])
def test_a_derive_disproof_under_a_premise_is_corroborated(law):
    """Derive's witness (2x is 2e-9 from 2 at x = 1 + 1e-9, past ε) is
    executed and the violation reproduced, as for any other disproof."""
    from mathema.lexicon import double
    (p,) = mathema.claims.check(double, [claim(law)])
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "UNCORROBORATED" not in p.note, p.note
