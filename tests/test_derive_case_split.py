# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""symbolic/_proof_support.py's derive-route case-split fallback:
_split_domain_pieces/_exact() mechanics, _prove_relation_case_split's
soundness rules (pole exclusion, at-point check for a non-pole kind,
disproven-piece short-circuit), and a real end-to-end claim() through
try_prove() that only resolves because of the split."""
import sympy

from mathema.conjecture import claim, check_conjectures
from mathema.grammar import Interval
from mathema.symbolic._proof_support import (_domain_assumptions, _exact,
                                              _prove_relation_case_split,
                                              _split_domain_pieces)

x = sympy.Symbol("x", real=True)


def test_split_domain_pieces_returns_none_with_no_interior_point():
    assert _split_domain_pieces(-5.0, 8.0, True, True, [-5.0, 8.0, 100.0]) is None


def test_split_domain_pieces_opens_the_new_boundary_on_each_side():
    pieces = _split_domain_pieces(-5.0, 8.0, True, True, [2.0])
    assert pieces == [(-5.0, 2.0, True, False), (2.0, 8.0, False, True)]


def test_split_domain_pieces_handles_multiple_interior_points():
    pieces = _split_domain_pieces(0.0, 10.0, True, True, [7.0, 3.0])
    assert pieces == [(0.0, 3.0, True, False), (3.0, 7.0, False, False),
                      (7.0, 10.0, False, True)]


def test_exact_snaps_a_lossless_float_to_an_integer():
    snapped = _exact(-5.0)
    assert snapped == -5
    assert snapped.is_Integer


def test_exact_leaves_a_non_exact_float_unchanged():
    # 0.1 itself round-trips cleanly to the exact Rational(1, 10),
    # not a bug, nsimplify correctly recognizes a simple rational. A
    # value with no clean rational (or recognized constant) match
    # within tolerance is the real "falls back unchanged" case.
    assert _exact(0.123456789012345) == 0.123456789012345


def test_case_split_proves_an_abs_claim_undecided_in_a_single_context():
    # |x - 2| - (x - 2) >= 0 over [-5, 8]: sympy.refine can't resolve
    # the raw Abs expression in one shot (validated directly), but
    # splitting at the kink x=2 lets each piece simplify to something
    # ask() settles cleanly.
    expr = sympy.Abs(x - 2) - (x - 2)
    domain = {"x": Interval(-5.0, 8.0)}
    _, bound_context, params, _pins = _domain_assumptions({"x": x}, domain)
    result = _prove_relation_case_split(expr, sympy.Integer(0), ">=", domain,
                                        bound_context, params, "x", [2.0], "domain_transition")
    assert result.status == "proven"
    assert "split at x = 2" in result.sketch


def test_case_split_works_with_exact_int_bounds_too():
    expr = sympy.Abs(x - 2) - (x - 2)
    domain = {"x": Interval(-5, 8)}
    _, bound_context, params, _pins = _domain_assumptions({"x": x}, domain)
    result = _prove_relation_case_split(expr, sympy.Integer(0), ">=", domain,
                                        bound_context, params, "x", [2], "domain_transition")
    assert result.status == "proven"


def test_case_split_pole_sketch_names_the_excluded_pole_explicitly():
    expr = sympy.Abs(x - 2) - (x - 2)
    domain = {"x": Interval(-5.0, 8.0)}
    _, bound_context, params, _pins = _domain_assumptions({"x": x}, domain)
    result = _prove_relation_case_split(expr, sympy.Integer(0), ">=", domain,
                                        bound_context, params, "x", [2.0], "pole")
    assert result.status == "proven"
    assert "undefined" in result.sketch
    assert "excluded" in result.sketch


def test_case_split_a_disproven_piece_falsifies_the_whole_claim():
    domain = {"x": Interval(-5.0, 8.0)}
    result = _prove_relation_case_split(x, sympy.Integer(0), ">=", domain, None,
                                        {"x": x}, "x", [-1.0], "stationary")
    assert result.status == "disproven"


def test_case_split_returns_none_with_no_plain_interval_domain():
    result = _prove_relation_case_split(x, sympy.Integer(0), ">=", {}, None,
                                        {"x": x}, "x", [2.0], "stationary")
    assert result is None


# --- end-to-end: the real claim()/try_prove() pipeline reaches this ---------

def test_derive_route_claim_resolves_via_case_split(tmp_path):
    fixture = tmp_path / "abs_shift_fixture.py"
    fixture.write_text(
        "def abs_shift(x: float) -> float:\n"
        "    return abs(x - 2) - (x - 2)\n")
    import sys
    sys.path.insert(0, str(tmp_path))
    try:
        from abs_shift_fixture import abs_shift
        results = check_conjectures(
            abs_shift, [claim("for x in [-5, 8], f(x) >= 0", route="derive")])
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("abs_shift_fixture", None)
    assert results[0].verdict == "proven"
    assert "split at x = 2" in results[0].sketch
    # record-schema.md's own route field: a plain derive proof and one
    # that only resolved via the case-split fallback are different
    # strengths of evidence, distinguished with a colon subroute.
    assert results[0].route == "derive:extensive"


def test_a_plain_derive_proof_reports_the_base_route_not_extensive(tmp_path):
    fixture = tmp_path / "affine_fixture.py"
    fixture.write_text(
        "def line(x: float) -> float:\n"
        "    return 3.0 * x + 1.0\n")
    import sys
    sys.path.insert(0, str(tmp_path))
    try:
        from affine_fixture import line
        results = check_conjectures(
            line, [claim("f(x) - f(x) == 0", route="derive")])
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("affine_fixture", None)
    assert results[0].verdict == "proven"
    assert results[0].route == "derive"
