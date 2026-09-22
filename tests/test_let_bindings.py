# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim's own text can bind three things a bare `for` quantifier
can't: a fresh name shared across multiple real-parameter positions
(forcing them equal, e.g. the equal-masses boundary of a two-body
claim), a callable letter resolved from a dotted import path without a
separate `funcs=` argument, and a genuinely free variable with its own
domain but no real parameter to alias (e.g. a gauge-invariance claim's
arbitrary shift constant). All three are spelled `let name <op> value,
...`; one binding per `let`, comma-terminated, sitting directly in
the same leading comma-list a `for` quantifier's own bindings occupy
(see `grammar.extract_let_bindings`): `=` for the first two (alias or
function), `be` for the third (deliberately not `in`, so a free
variable's own declaration never reads like a `for` binding). The
separate, unrelated `let name = expr in rest` form (collapsing an
oversized expression to fit inside `|...|` bars) keeps working exactly
as before."""
from mathema.conjecture import ConflictingDomainBinding, check_conjectures, claim
from mathema.grammar import Domain, domain_contains, extract_let_bindings, normalize


def center_of_mass_two_body(m1: float, x1: float, m2: float, x2: float) -> float:
    return (m1 * x1 + m2 * x2) / (m1 + m2)


def gibbs_free_energy(dh: float, t: float, ds: float) -> float:
    if t < 0:
        raise ValueError("absolute temperature cannot be negative")
    return dh - t * ds


def identity(x: float) -> float:
    return x


def test_shared_alias_forces_two_parameters_equal():
    law = ("let m = m1, for m1 in [0.1,1000], x1 in [-100,100], "
           "x2 in [-100,100], f(m,x1,m,x2) == (x1+x2)/2")
    cj = claim(law, route="derive")
    assert cj.domain == {"m1": (0.1, 1000.0), "x1": (-100.0, 100.0),
                         "x2": (-100.0, 100.0)}
    result = check_conjectures(center_of_mass_two_body, [cj], extensive=False)[0]
    assert result.verdict == "proven"


def test_old_in_terminated_alias_spelling_still_works():
    law = ("let m = m1 in for m1 in [0.1,1000], x1 in [-100,100], "
           "x2 in [-100,100], f(m,x1,m,x2) == (x1+x2)/2")
    result = check_conjectures(
        center_of_mass_two_body, [claim(law, route="derive")], extensive=False)[0]
    assert result.verdict == "proven"


def test_bare_non_parameter_domain_key_without_let_still_rejected():
    # the idiom this feature replaces: a domain key that matches no real
    # parameter must still be rejected, not silently accepted; let is
    # the migration path, not a bypass of that validation.
    law = ("for m in [0.1,1000], x1 in [-100,100], x2 in [-100,100], "
           "f(m,x1,m,x2) == (x1+x2)/2")
    result = check_conjectures(
        center_of_mass_two_body, [claim(law, route="derive")], extensive=False)[0]
    assert result.verdict == "skipped"
    assert "domain key" in result.note


def test_multiline_claim_text_parses_the_same_as_one_line():
    law = """let m = m1,
    for m1 in [0.1,1000],
        x1 in [-100,100],
        x2 in [-100,100],
    f(m,x1,m,x2) == (x1+x2)/2
    """
    result = check_conjectures(
        center_of_mass_two_body, [claim(law, route="derive")], extensive=False)[0]
    assert result.verdict == "proven"


def test_dotted_path_function_binding_resolves_and_evaluates():
    law = "let g = math.sqrt, for x in (0,100], g(x) >= 0"
    cj = claim(law, route="probe")
    assert cj.funcs == {"g": "math.sqrt"}
    assert cj.lhs == "g(x)"
    result = check_conjectures(identity, [cj], extensive=False)[0]
    assert result.verdict == "holds"


def test_unresolvable_dotted_path_is_skipped_naming_the_function():
    law = "let g = nope.not.real, for x in (0,100], g(x) >= 0"
    result = check_conjectures(
        identity, [claim(law, route="probe")], extensive=False)[0]
    assert result.verdict == "skipped"
    assert "g" in result.note


def test_multiple_function_bindings_in_one_let_chain():
    law = "let g = math.sqrt, let h = math.fabs, for x in (-100,100], g(h(x)) >= 0"
    cj = claim(law, route="probe")
    assert cj.funcs == {"g": "math.sqrt", "h": "math.fabs"}
    result = check_conjectures(identity, [cj], extensive=False)[0]
    assert result.verdict == "holds"


def test_one_let_covers_multiple_comma_separated_bindings():
    # matches _expand_let's own ergonomics: one leading `let` opens a
    # run, later bindings don't need to repeat the keyword.
    law = "let m = m1, g = math.sqrt, for m1 in [0.1,1000], f(m,g(m)) >= 0"
    cj = claim(law, route="probe")
    assert cj.funcs == {"g": "math.sqrt"}
    assert cj.lhs == "f((m1),g((m1)))"
    assert cj.domain == {"m1": (0.1, 1000.0)}


def test_repeating_let_per_binding_is_also_accepted():
    law = "let m = m1, let g = math.sqrt, for m1 in [0.1,1000], f(m,g(m)) >= 0"
    cj = claim(law, route="probe")
    assert cj.funcs == {"g": "math.sqrt"}
    assert cj.lhs == "f((m1),g((m1)))"


def test_bare_undotted_name_is_not_treated_as_a_function_binding():
    # no dot in the right-hand side; this is the plain alias/expression
    # substitution, not a function binding, matching _expand_let's own
    # existing semantics.
    law = "let two = 2, for x in [0,10], f(x) <= two"
    cj = claim(law, route="probe")
    assert cj.funcs == {}
    assert cj.lhs == "f(x)"
    assert cj.rhs == "(2)"


def test_bar_expression_let_form_is_unaffected():
    text = "let y = a + b in |y| < 1"
    assert extract_let_bindings(text) == ({}, {}, text, {}, None)
    assert normalize(text) == "abs((a + b)) < 1"


#; free variables: `let name be bounds` -----------------------------

def test_free_variable_gauge_invariance_claim_proven():
    # the concrete case this shape exists for: a gauge-invariance claim
    # needs an arbitrary shift constant with no real parameter to alias.
    law = ("let c be [-1e6,1e6], for dh in [-1e6,1e6], t in [0,1000], "
           "ds in [-1e6,1e6], d(f(dh+c,t,ds), t) == d(f(dh,t,ds), t)")
    cj = claim(law, route="derive")
    assert cj.free_vars == frozenset({"c"})
    result = check_conjectures(gibbs_free_energy, [cj], extensive=False)[0]
    assert result.verdict == "proven"


def test_probe_route_actually_samples_within_the_declared_free_domain():
    # a real bug, not a hypothetical: aux names used to always be sampled
    # from a fixed uniform(-5, 5), ignoring any declared domain entirely;
    # a claim true only because c is pinned to exactly 5 would come
    # back falsified against some unrelated sampled value instead.
    law = "let c be [5, 5], for x in [0,10], f(x) + c >= 0"
    result = check_conjectures(identity, [claim(law, route="probe")], extensive=False)[0]
    assert result.verdict == "holds"
    # and the declared domain is genuinely used, not just tolerated:
    # pin c somewhere that makes the claim false, and it must be caught.
    law2 = "let c be [-1000, -900], for x in [0,10], f(x) + c >= 0"
    result2 = check_conjectures(identity, [claim(law2, route="probe")], extensive=False)[0]
    assert result2.verdict == "falsified"


def test_free_variable_interval_closedness_is_semantically_correct():
    # tuple equality on an Interval ignores closed_lo/closed_hi (it's a
    # tuple subclass), so this checks membership at the exact boundary
    # via domain_contains(), the actual semantics, rather than just
    # confirming the shape parsed.
    _, free_domain, _, _, _ = extract_let_bindings("let c be [-1, 1], f(c) >= 0")
    dom = free_domain["c"]
    assert domain_contains(-1, dom) and domain_contains(1, dom)

    _, free_domain, _, _, _ = extract_let_bindings("let c be (-1, 1), f(c) >= 0")
    dom = free_domain["c"]
    assert not domain_contains(-1, dom) and not domain_contains(1, dom)
    assert domain_contains(0, dom)

    _, free_domain, _, _, _ = extract_let_bindings("let c be (-1, 1], f(c) >= 0")
    dom = free_domain["c"]
    assert not domain_contains(-1, dom) and domain_contains(1, dom)

    _, free_domain, _, _, _ = extract_let_bindings("let c be [-1, 1), f(c) >= 0")
    dom = free_domain["c"]
    assert domain_contains(-1, dom) and not domain_contains(1, dom)


def test_free_variable_be_accepts_a_bare_scalar_as_a_degenerate_point():
    _, free_domain, _, _, _ = extract_let_bindings("let c be 2.0, f(c) >= 0")
    assert free_domain["c"] == Domain(pieces=((2.0, 2.0),))
    assert domain_contains(2.0, free_domain["c"])
    assert not domain_contains(2.1, free_domain["c"])

    _, free_domain, _, _, _ = extract_let_bindings("let c be -3.5, f(c) >= 0")
    assert domain_contains(-3.5, free_domain["c"])


def test_free_variable_defaults_to_an_explicit_real_domain():
    # no source of type info exists for a free variable (unlike a real
    # parameter, which has its own annotation), so unlike an ordinary
    # `for` binding, which leaves an untyped domain as a bare Interval,
    # a `let ... be ...` binding always renders an explicit Domain,
    # assumed real when nothing else is stated.
    _, free_domain, _, _, _ = extract_let_bindings("let c be [0, 1], f(c) >= 0")
    assert free_domain["c"].base_type == "R"


def test_free_variable_subset_clause_accepts_every_requested_spelling():
    for spelling in (r"\subset", r"\sub", "subset", "⊂"):
        for type_name, expected in (("Z", "Z"), ("N", "N"), ("R", "R"),
                                    ("int", "Z"), ("integer", "Z"),
                                    ("float", "R"), ("real", "R")):
            law = f"let c be [1,100] {spelling} {type_name}, f(c) >= 0"
            _, free_domain, _, _, _ = extract_let_bindings(law)
            assert free_domain["c"].base_type == expected, law


def test_conflicting_let_and_for_binding_for_the_same_name_raises():
    law = ("let dh be [-1e6,1e6], for dh in [-2e6,2e6], t in [0,1000], "
           "ds in [-1e6,1e6], f(dh,t,ds) >= 0")
    try:
        claim(law, route="derive")
        assert False, "expected ConflictingDomainBinding"
    except ConflictingDomainBinding as e:
        assert "dh" in str(e)


def test_free_variable_matching_a_real_parameter_with_no_separate_for_defers_to_it():
    # harmless: only one declared bound exists here (the let itself),
    # no error, no skip, adjudicates exactly as an ordinary `for` would,
    # noted rather than left implicit.
    law = ("let dh be [-1e6,1e6], for t in [0,1000], ds in [-1e6,1e6], "
           "f(dh,t,ds) == dh - t*ds")
    result = check_conjectures(
        gibbs_free_energy, [claim(law, route="derive")], extensive=False)[0]
    assert result.verdict == "proven"
    assert "deferred to the real parameter's own kind" in result.note


def test_explicit_type_disagreeing_with_the_real_parameter_kind_is_flagged():
    # dh is a float (`scalar`-kind) real parameter; stating `subset
    # integer` for it is a deliberate override, not silently reconciled,
    # so it's called out rather than left for a reader to notice later.
    law = ("let dh be [1,100] subset integer, for t in [0,1000], "
           "ds in [-1e6,1e6], f(dh,t,ds) == dh - t*ds")
    result = check_conjectures(
        gibbs_free_energy, [claim(law, route="derive")], extensive=False)[0]
    assert "states 'Z'" in result.note
    assert "'scalar'" in result.note


def test_explicit_type_agreeing_with_the_real_parameter_kind_is_silent():
    law = ("let dh be [1,100] subset real, for t in [0,1000], "
           "ds in [-1e6,1e6], f(dh,t,ds) == dh - t*ds")
    result = check_conjectures(
        gibbs_free_energy, [claim(law, route="derive")], extensive=False)[0]
    assert "states" not in result.note
