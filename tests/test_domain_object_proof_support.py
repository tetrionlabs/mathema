# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The domain model's symbolic projection, as the prover consumes it:
the `Q.ne` exclusion facts and best-effort `Or(...)` union context from
`domain.bound_context`, the symbol-assumption keywords from
`domain.bound_assumptions`, the degenerate-point pin from
`domain.bound_pin`, and the proof-sketch `domain_desc()` closure's
rendering, which since the domain-model extraction is
`domain.render_domain` itself; one renderer for the claim text and
the proof quantifier, never two that drift. Covers the mechanism
directly against real `Domain` objects (built through
`split_quantifier`, not hand-assembled, so a grammar-level regression
here would show up as a test failure), mirrors
`test_power_tower_sign.py`'s own white-box style."""
import sympy

from mathema.conjecture import claim, check_conjectures
from mathema.domain import (bound_assumptions, bound_context, bound_pin,
                            render_domain)
from mathema.grammar import normalize, split_quantifier
from mathema.symbolic._proof_support import _quantifier_clause


def _dom(text: str):
    domain, _ = split_quantifier(normalize(text))
    return domain["x"]


def test_bound_context_for_a_single_interval_piece_is_a_plain_and():
    x = sympy.Symbol("x", real=True)
    dom = _dom("for x in [0, 1] \\subset Z, True")
    ctx = bound_context(x, dom)
    assert ctx == sympy.And(sympy.Q.ge(x, 0.0), sympy.Q.le(x, 1.0))


def test_bound_context_for_a_union_is_an_or_of_each_piece():
    x = sympy.Symbol("x", real=True)
    dom = _dom("for x in [-10, -1) | (1, 10], True")
    ctx = bound_context(x, dom)
    assert isinstance(ctx, sympy.Or)
    assert len(ctx.args) == 2


def test_bound_context_carries_a_q_ne_fact_for_each_excluded_value():
    # the excluded value keeps the type it was written as, so `\ {0}`
    # states Q.ne(x, 0) over the integer, not over a float that merely
    # compares equal to it; sympy holds Integer(0) and Float(0.0) as
    # distinct objects, so the fact has to name the one the text did
    x = sympy.Symbol("x", real=True)
    dom = _dom("for x in [-1, 1] \\ {0}, True")
    ctx = bound_context(x, dom)
    assert sympy.Q.ne(x, 0) in (ctx.args if isinstance(ctx, sympy.And) else [ctx])


def test_bound_context_keeps_a_float_excluded_value_a_float():
    x = sympy.Symbol("x", real=True)
    dom = _dom("for x in [-1, 1] \\ {0.5}, True")
    ctx = bound_context(x, dom)
    assert sympy.Q.ne(x, 0.5) in (ctx.args if isinstance(ctx, sympy.And) else [ctx])


def test_bound_context_never_states_a_q_ne_fact_for_missing_itself():
    # MISSING isn't a value sympy's symbolic algebra can state a fact
    # about (a real symbol can't "equal" a missing value), only a
    # genuine excluded number/string becomes a Q.ne clause. The
    # interval piece itself still contributes its own And(...), but no
    # Q.ne(x, ...) clause is generated for the excluded MISSING entry.
    x = sympy.Symbol("x", real=True)
    dom = _dom("for x in [-1, 1] \\ {missing}, True")
    ctx = bound_context(x, dom)
    parts = ctx.args if isinstance(ctx, sympy.And) else [ctx]
    assert not any(str(c).startswith("Q.ne") for c in parts)


def test_single_interval_domain_assumption_gets_integer_and_sign_facts():
    dom = _dom("for x in [1, 10] \\subset Z, True")
    kwargs = bound_assumptions(dom)
    new_sym = sympy.Symbol("x", **kwargs)
    assert new_sym.is_integer
    assert new_sym.is_positive


def test_union_domain_gets_no_symbol_level_sign_assumption():
    # a union can straddle zero, nothing sound to assume beyond
    # real=True, so bound_context (the Or(...) above) is the only
    # source of whatever reasoning is possible.
    dom = _dom("for x in [-10, -1) | (1, 10], True")
    assert bound_assumptions(dom) is None
    assert bound_pin(dom) == (False, None)


def test_proof_sketch_domain_rendering_states_missing_policy_explicitly():
    lenient = _dom("for x in [0, 100], True")
    # stating a type (⊂ Z) never excludes missing by default, only an
    # explicit exclusion clause does, regardless of type.
    typed_but_included = _dom("for x in [0, 100] \\subset Z, True")
    strict = _dom("for x in [0, 100] \\subset Z \\ {missing}, True")
    assert render_domain(strict, ascii_mode=False).endswith("\\ {∅}")
    assert render_domain(typed_but_included, ascii_mode=False).endswith("∪ {∅}")
    assert lenient != strict


def test_quantifier_clause_states_missing_included_for_a_bare_named_type():
    # a hand-built domain dict may pass "Z"/"N" directly (not through a
    # Domain object); this bare-string shape must state the same
    # missing-included-by-default policy the Domain-object path does.
    assert _quantifier_clause({"x"}, ["x"], {"x": "Z"}, set()) == "∀ x ∈ ℤ ∪ {∅}"
    assert _quantifier_clause({"x"}, ["x"], {"x": "N"}, set()) == "∀ x ∈ ℕ ∪ {∅}"


# --- end-to-end: the derive route accepts an excluded/union domain
# --- without crashing and reaches a real verdict, never a silently
# --- wrong "proven" -------------------------------------------------

def test_derive_route_handles_an_excluded_pole_without_crashing(tmp_path):
    fixture = tmp_path / "fixture.py"
    fixture.write_text(
        "def recip_times(r: float) -> float:\n"
        "    return (1.0 / (1.0 - r)) * (1.0 - r)\n")
    import sys
    sys.path.insert(0, str(tmp_path))
    try:
        from fixture import recip_times
        results = check_conjectures(
            recip_times, [claim("for r in [-1, 1] \\ {1}, f(r) == 1", route="derive")])
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("fixture", None)
    # pinned: derive leaves the excluded-pole simplification undecided
    # today and the empirical fallback supplies holds, a derive-side
    # improvement flips this to proven deliberately
    assert results[0].verdict == "holds"


def test_derive_route_handles_a_union_domain_without_crashing(tmp_path):
    fixture = tmp_path / "fixture_union.py"
    fixture.write_text(
        "def square(r: float) -> float:\n"
        "    return r * r\n")
    import sys
    sys.path.insert(0, str(tmp_path))
    try:
        from fixture_union import square
        results = check_conjectures(
            square, [claim("for r in [-10, -1) | (1, 10], f(r) >= 0", route="derive")])
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("fixture_union", None)
    assert results[0].verdict == "proven"
