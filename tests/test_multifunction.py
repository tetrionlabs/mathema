# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Multi-function claims on the derive route, and claim-text function
resolution: a bound function lifts to its own closed form and its calls
substitute like f's own; a bare call name binds automatically from f's
module scope or the calling scope's local variables, with every binding
named in the note."""
from mathema.conjecture import claim, check_conjectures


def cobb_douglas_utility(x, y, a):
    return x ** a * y ** (1 - a)


def budget_line(x, I, px, py):   # noqa: E741
    return (I - px * x) / py


def halve(x):
    return x / 2


def halve_twin(x):
    return 0.5 * x


def _verdict(fn, law, **kw):
    return check_conjectures(fn, [claim(law, **kw)])[0]


def test_two_function_equality_proves_on_derive():
    r = _verdict(halve, "f(x) == g(x)", funcs={"g": halve_twin}, route="derive")
    assert r.verdict == "proven"


def test_two_function_wrong_equality_is_falsified_on_derive():
    r = _verdict(halve, "f(x) == g(x) + 1", funcs={"g": halve_twin},
                 route="derive")
    assert r.verdict == "falsified"


def test_bare_name_binds_from_the_target_functions_module():
    # budget_line is defined next to f in this module: the claim can
    # call it by name with no funcs= at all, and the note names the
    # binding explicitly
    r = _verdict(cobb_douglas_utility,
                 "let I be [10, 1000], let px be [0.5, 20], let py be [0.5, 20], "
                 "d(budget_line(x,I,px,py),x) == -px/py",
                 route="derive")
    assert r.verdict == "proven"
    assert "bound budget_line" in r.note
    assert "budget_line" in r.note and "module" in r.note

    # unquantified py includes 0, where budget_line divides by zero:
    # a bound function's raise regions gate the claim exactly like
    # f's own (derive and probe agree here by design)
    r = _verdict(cobb_douglas_utility,
                 "let I be [10, 1000], let px be [0.5, 20], let py be [-20, 20], "
                 "d(budget_line(x,I,px,py),x) == -px/py", route="derive")
    assert r.verdict == "falsified"
    assert "budget_line" in (r.sketch or "")


def test_bare_name_binds_from_the_calling_scopes_locals():
    def local_twin(x):
        return x * 0.5

    r = _verdict(halve, "f(x) == local_twin(x)", route="derive")
    assert r.verdict == "proven"
    assert "bound local_twin" in r.note
    assert "calling scope" in r.note


def test_explicit_funcs_binding_wins_over_scope_resolution():
    def shifted(x):
        return x / 2 + 1

    # the module holds halve_twin, but the explicit binding points the
    # same name at a different function; the explicit one is used
    r = _verdict(halve, "f(x) == halve_twin(x) - 1",
                 funcs={"halve_twin": shifted}, route="derive")
    assert r.verdict == "proven"


def test_derivative_claims_span_both_functions():
    # the MRS closed form: the shape the two-function cobb-douglas
    # tangency claim needs (its full identity is only true at the
    # optimum, so this proves the ratio's own closed form instead)
    r = _verdict(cobb_douglas_utility,
                 "for a in [0.1,0.9], d(f(x,y,a),x)/d(f(x,y,a),y) "
                 "== a*y/((1-a)*x)", route="derive")
    assert r.verdict == "proven"


def test_let_alias_of_a_same_scope_function_resolves():
    # `let g = budget_line` substitutes the bare name into the law,
    # and the name then binds from the module like a direct call
    r = _verdict(cobb_douglas_utility,
                 "let g = budget_line, let I be [10, 1000], "
                 "let px be [0.5, 20], let py be [0.5, 20], "
                 "d(g(x,I,px,py),x) == -px/py",
                 route="derive")
    assert r.verdict == "proven"


def test_unresolvable_name_names_the_repair():
    r = _verdict(halve, "f(x) == mystery_fn(x)", route="derive")
    assert r.verdict == "skipped"
    assert "mystery_fn" in (r.note or "")
    assert "funcs=" in (r.note or "")


def test_unliftable_bound_function_names_itself():
    def whiley(x):
        total = x
        while abs(total) > 1.0:
            total = total / 2.0
        return total

    r = _verdict(halve, "f(x) == g(x)", funcs={"g": whiley}, route="derive")
    # derive names the blocking function; the probe fallback then calls
    # both for real, and the identity is simply false
    assert r.verdict == "falsified"
    assert "bound function g" in (r.note or "")


def test_range_loop_bound_function_now_lifts():
    # the shape the naming pin above used to use: a branch-free range
    # loop closes through the sum machinery, so derive adjudicates the
    # (false) identity directly instead of declining on g
    def loopy(x):
        total = 0.0
        for i in range(3):
            total += x * i
        return total

    r = _verdict(halve, "f(x) == g(x)", funcs={"g": loopy}, route="derive")
    assert r.verdict == "falsified"
    r = _verdict(halve, "f(x) == g(x)/6", funcs={"g": loopy}, route="derive")
    assert r.verdict == "proven", (r.verdict, r.note)


def test_counterexample_respects_let_declared_free_variable_domains():
    # regression: the disproof corroborator once sampled px = -2.7 for
    # a claim whose let-declaration bounds px to [0.5, 20], a witness
    # outside the declared domain falsifies nothing
    r = _verdict(cobb_douglas_utility,
                 "let I be [10,1000], let px be [0.5,20], let py be [0.5,20], "
                 "for a in [0.1,0.9], "
                 "d(f(x,y,a),x)/d(f(x,y,a),y) == d(budget_line(x,I,px,py),x)",
                 route="derive")
    # false away from the optimum, but a calculus form has no point
    # evaluation against the function, so the symbolic disproof has no
    # executed witness and the verdict is unknown, flagged
    assert r.verdict == "unknown"
    assert (r.meta or {}).get("mathema.corroboration") == "uncorroborated"
    cx = r.counterexample or r.sketch or ""
    import re
    for name, lo, hi in (("px", 0.5, 20.0), ("py", 0.5, 20.0)):
        m = re.search(rf"{name}=([-0-9.e+]+)", cx)
        if m:
            assert lo <= float(m.group(1)) <= hi


def test_probe_route_uses_the_same_resolved_binding():
    r = _verdict(halve, "f(x) == budget_line(x, 1, 0, 1) * 0 + x/2")
    assert r.verdict == "proven"   # best route lifts both sides
    assert "bound budget_line" in r.note


def test_a_claim_naming_the_function_under_test_survives_its_own_record():
    """`f` is shorthand, so a claim may call the function under test by
    its own name. The stored spelling has to KEEP that name: a function
    rename only round trips where the claim has a `let <alias> = <target>`
    binding site to write the short name back at, and a bare call
    resolved from f's module has none, so shortening it to `g` produced a
    record that reparsed to nothing and rebound to nothing.
    """
    from mathema.conjecture import claim
    from mathema.spec import canonical_claim_text

    law = "for x in [0, 10], halve(x) <= x"
    r = _verdict(halve, law)
    assert r.verdict == "proven"
    # the real name is what the record carries, never an orphan short one
    assert "halve(x)" in r.statement
    assert "g(" not in r.statement
    assert "halve(x)" in canonical_claim_text(claim(law))


def test_a_second_function_is_still_bound_as_one():
    """The counterpart: a name that is genuinely another function keeps
    being bound, so the rule above cannot swallow a real multi-function
    claim."""
    r = _verdict(halve, "f(x) == budget_line(x, 1, 0, 1) * 0 + x/2")
    assert r.verdict == "proven"
    assert "bound budget_line" in r.note


def test_a_domain_in_the_claim_bounds_the_builtin_battery_too():
    """A `for` quantifier states where a claim applies, and the built-in
    battery has to respect it as well, not just the claim it was written
    on. Sampling a parameter outside the declared region and reporting
    that the function raised there manufactures a gap that is an
    artefact of the battery rather than a fact about the code.

    The suite missed this for a while because it produces no wrong
    verdict: the stated claim still proved, and the spurious entry sat
    beside it where a test looking up one claim's verdict never saw it.
    So this asserts the SHAPE of the result, not a verdict.
    """
    import math

    import mathema

    def bounded(x: float) -> float:
        """Raises on anything outside (0, 1], so an unbounded draw
        cannot call it at all."""
        return math.log(x)

    law = "for x in [0.1, 1], f(x) <= 0"
    r = mathema.check(bounded, claims=[law])
    gaps = [p for p in r.probes
            if (p.meta or {}).get("mathema.probe_gap") == "input-synthesis"]
    assert not gaps, (
        "the claim declared x in [0.1, 1]; the built-in battery sampled "
        f"outside it and reported {[p.note for p in gaps]}")
    stated = [p for p in r.probes if p.statement]
    assert stated and stated[0].verdict in ("proven", "holds")
