# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Computation safety is a hierarchy under `is_computation_safe(f)`: each
child is a fact about one implementation, adjudicated by execution, and
a child's restriction form states the region where the implementation
is safe in that respect. `is_overflow_safe` carries overflow (an
infinity or an OverflowError from finite inputs), `is_recursion_safe`
carries the recursion limit, and the roll-up runs every relevant child
and names each verdict. Memory safety is planned and not part of this
release: a claim naming it fails as any unknown predicate does, with
one sentence saying so."""
import math
import textwrap

import pytest

import mathema
from mathema.conjecture import InvalidConjecture, check_conjectures, claim


def _load(tmp_path, body, name):
    import importlib.util
    p = tmp_path / f"{name}.py"
    p.write_text(textwrap.dedent(body))
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _one(fn, law, **kw):
    (p,) = check_conjectures(fn, [claim(law, route="best", **kw)])
    return p


def _declared(fn, statement):
    (p,) = [p for p in mathema.check(fn, claims=[statement]).probes
            if p.meta.get("mathema.surface") == "declared"]
    return p


# --- is_overflow_safe -------------------------------------------------


def test_the_overflow_safe_region_of_math_exp_holds():
    p = _declared(math.exp, claim("x <= 709.782712893384",
                                  name="is_overflow_safe"))
    assert p.verdict == "holds", (p.verdict, p.note, p.sketch)
    assert p.route.startswith("probe")


def test_bare_overflow_safety_over_a_domain_that_overflows_is_falsified():
    p = _declared(math.exp, "for x in [0, 1000], is_overflow_safe(x)")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "OverflowError" in (p.counterexample or "")
    assert p.meta.get("mathema.witness_executed") is True


def test_a_square_over_the_reals_overflows_to_inf_at_the_float_corner(tmp_path):
    sq = _load(tmp_path, '''
        def sq(x: float) -> float:
            """Square."""
            return x * x
    ''', "hier_sq").sq
    p = _one(sq, "for x in R, is_overflow_safe(x)")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "e+308" in (p.counterexample or "")
    assert "returned inf" in (p.counterexample or "")
    assert (p.stratum or {}).get("cause") == "implementation:overflow"


def test_a_bounded_square_is_overflow_safe(tmp_path):
    sq = _load(tmp_path, '''
        def sq(x: float) -> float:
            """Square."""
            return x * x
    ''', "hier_sq_bounded").sq
    p = _one(sq, "for x in [-1e100, 1e100], is_overflow_safe(x)")
    assert p.verdict == "holds", (p.verdict, p.note)


def test_overflow_safe_restriction_on_a_project_function_holds(tmp_path):
    ex = _load(tmp_path, '''
        import numpy as np

        def ex(x: float) -> float:
            """Exponential through numpy."""
            return float(np.exp(x))
    ''', "hier_ex").ex
    pytest.importorskip("numpy")
    p = _declared(ex, claim("x <= 709.782712893384", name="is_overflow_safe"))
    assert p.verdict == "holds", (p.verdict, p.note, p.sketch)
    # the restriction form is computation: derive never proves it
    assert p.route.startswith("probe"), p.route


def test_a_region_too_wide_is_falsified_where_the_call_overflows():
    p = _declared(math.exp, claim("x <= 800", name="is_overflow_safe"))
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "inside the stated region" in (p.counterexample or "")
    assert "OverflowError" in (p.counterexample or "")


def test_a_chained_overflow_region_is_one_region():
    np = pytest.importorskip("numpy")
    p = _declared(np.cosh, claim("-710.475860073944 < x < 710.475860073944",
                                 name="is_overflow_safe"))
    assert p.verdict == "holds", (p.verdict, p.note, p.sketch)


def test_overflow_safety_is_suggested_for_powers_and_exponentials(tmp_path):
    from mathema.suggest import suggest_claims
    mod = _load(tmp_path, '''
        import math

        def cube(x: float) -> float:
            """Cube."""
            return x ** 3

        def grow(x: float) -> float:
            """Exponential."""
            return math.exp(x)

        def double(x: float) -> float:
            """Double."""
            return 2 * x
    ''', "hier_suggest")
    assert "is_overflow_safe[x]" in {c.name for c in suggest_claims(mod.cube)}
    assert "is_overflow_safe[x]" in {c.name for c in suggest_claims(mod.grow)}
    assert not any(n.startswith("is_overflow_safe")
                   for n in {c.name for c in suggest_claims(mod.double)})


# --- is_recursion_safe ------------------------------------------------


@pytest.fixture()
def down(tmp_path):
    return _load(tmp_path, '''
        def down(n):
            """Count down to zero, recursively."""
            return down(n - 1) if n > 0 else 0
    ''', "hier_down").down


def test_recursion_past_the_limit_is_falsified_with_the_raise(down):
    p = _one(down, "for n in [0, 100000], is_recursion_safe(n)")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "RecursionError" in (p.counterexample or "")
    assert (p.stratum or {}).get("cause") == "implementation:recursion-depth"


def test_shallow_recursion_holds(down):
    p = _one(down, "for n in [0, 100], is_recursion_safe(n)")
    assert p.verdict == "holds", (p.verdict, p.note)


def test_recursion_safety_is_suggested_for_a_recursive_body(down, tmp_path):
    from mathema.suggest import suggest_claims
    assert "is_recursion_safe[n]" in {c.name for c in suggest_claims(down)}
    flat = _load(tmp_path, '''
        def flat(n):
            """No recursion."""
            return n + 1
    ''', "hier_flat").flat
    assert not any(n.startswith("is_recursion_safe")
                   for n in {c.name for c in suggest_claims(flat)})


# --- memory safety is not part of this release ------------------------


def test_a_claim_naming_memory_safety_fails_as_an_unknown_predicate():
    from mathema.families import families
    assert "is_memory_safe" not in families()
    with pytest.raises(InvalidConjecture) as err:
        claim("is_memory_safe(f)", route="best")
    text = str(err.value)
    assert "no relation" in text, text
    assert "is_memory_safe is planned and is not part of this release" in text


def test_the_roll_up_is_never_suggested(down):
    from mathema.suggest import suggest_claims
    names = {c.name.split("[", 1)[0] for c in suggest_claims(down)}
    assert "is_computation_safe" not in names


# --- is_computation_safe ----------------------------------------------


def test_the_roll_up_holds_on_a_small_pure_function_and_names_its_children(tmp_path):
    half = _load(tmp_path, '''
        def half(x: float) -> float:
            """Half."""
            return x / 2
    ''', "hier_half").half
    p = _one(half, "for x in [-1e6, 1e6], is_computation_safe(f)")
    assert p.verdict == "holds", (p.verdict, p.note)
    assert p.route == "probe:algorithmic"
    children = p.meta.get("mathema.children")
    assert isinstance(children, dict) and children
    # the children are the overflow, representation and recursion
    # families (decision A); accuracy is is_numerically_stable's own
    # question and repeatability is is_repeatable's
    assert {name.split("[", 1)[0] for name in children} <= {
        "is_overflow_safe", "is_representation_safe", "is_recursion_safe"}
    for name, verdict in children.items():
        assert f"{name}: {verdict}" in (p.note or "")
    assert all(v in ("holds", "proven") for v in children.values()), children


def test_the_roll_up_is_falsified_by_an_overflowing_child(tmp_path):
    pytest.importorskip("numpy")
    ex = _load(tmp_path, '''
        import numpy as np

        def ex(x: float) -> float:
            """Exponential through numpy."""
            return float(np.exp(x))
    ''', "hier_ex_rollup").ex
    p = _one(ex, "for x in [0, 1000], is_computation_safe(f)")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "is_overflow_safe" in (p.counterexample or "")
    children = p.meta.get("mathema.children")
    assert children.get("is_overflow_safe[x]") == "falsified", children


def test_the_roll_up_holds_where_its_children_hold_by_execution(tmp_path):
    # a roll-up is proven only when every child is; the children here
    # are facts settled by executing the computation, which hold
    half = _load(tmp_path, '''
        def half(x: float) -> float:
            """Half."""
            return x / 2
    ''', "hier_half_proven").half
    p = _one(half, "for x in [-1e6, 1e6], is_computation_safe(f)")
    assert p.verdict == "holds"


# --- registration, groups, badges -------------------------------------


def test_the_hierarchy_is_registered():
    from mathema.families import families
    have = families()
    for name in ("is_overflow_safe", "is_recursion_safe",
                 "is_computation_safe"):
        assert name in have, name


def test_the_computation_safe_group_lists_the_children():
    from mathema.families import GROUPS
    members = set(GROUPS["computation_safe"])
    assert {"is_overflow_safe", "is_recursion_safe",
            "is_numerically_stable"} <= members
    assert not members & {"is_deterministic", "is_reproducible",
                          "is_state_safe"}
    assert "is_computation_safe" not in members
    assert "is_defined" not in members
    # the existing groups are untouched
    assert "defined_within_domain" in GROUPS and "stateless" in GROUPS


def test_the_new_families_credit_existing_clarity_buckets_only():
    from mathema.badges import _SAFETY_SOURCE
    assert _SAFETY_SOURCE["is_overflow_safe"] == "is_representation_safe"
    assert _SAFETY_SOURCE["is_recursion_safe"] == "is_arbitrary_input_safe"
    assert "is_computation_safe" not in _SAFETY_SOURCE
    assert set(_SAFETY_SOURCE.values()) == {
        "is_state_safe", "is_deterministic", "is_numerically_stable",
        "is_representation_safe", "is_missing_safe",
        "is_arbitrary_input_safe"}
    # a call's hazard is read from the callee's own record (clarity @1.2)
    assert "is_compendium_safe" not in _SAFETY_SOURCE


def test_region_row_kind_names_the_two_region_families():
    from mathema.conjecture import region_row_kind
    assert region_row_kind("is_defined") == "is_defined"
    assert region_row_kind("is_defined[2]") == "is_defined"
    assert region_row_kind("is_overflow_safe") == "is_overflow_safe"
    assert region_row_kind("is_overflow_safe[x]") == "is_overflow_safe"
    assert region_row_kind("is_extremity_safe[x]") is None
    assert region_row_kind("exp_positive") is None
