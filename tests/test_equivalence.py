# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The equivalence relation `f =:= g` (word alias `equiv`, unicode ≡):
two live Python functions adjudicated by canonical form hash, then the
symbolic difference of their lifts, then code-vs-code sampling with
both real functions executed on shared draws. Complexity annotations
ride the record without bearing on the verdict."""
from mathema.claims import check_conjectures, claim
from mathema.spec import render_claim_text


def tri_naive(a, b, c):
    return (1 * a + 2 * b + 3 * c) / 6.0


def tri_incr(a, b, c):
    acc = a
    acc = acc + 2 * b
    acc = acc + 3 * c
    return acc / 6.0


def test_equivalent_implementations_prove_symbolically():
    (p,) = check_conjectures(tri_naive, [claim("f =:= g",
                                               funcs={"g": tri_incr},
                                               route="derive")])
    assert p.verdict == "proven"
    assert "symbolic difference" in p.sketch or "canonical form" in p.sketch


def test_loop_and_closed_form_agree():
    def sum_loop(n: int) -> float:
        total = 0.0
        for k in range(n):
            total += k + 1
        return total

    def sum_closed(n: int) -> float:
        return n * (n + 1) / 2.0
    (p,) = check_conjectures(sum_loop, [claim(
        "for n in [0, 30] subset Z, f =:= g", funcs={"g": sum_closed},
        route="derive")])
    # rung 2b compares the two READ-ONLY closed forms directly, so the
    # loop lift meets the scalar closed form symbolically
    assert p.verdict == "proven"
    assert "closed forms are identical" in p.sketch


def test_inequivalent_functions_falsify_with_an_executed_witness():
    def scaled(a, b, c):
        return (a + 2 * b + 3 * c) / 5.0
    (p,) = check_conjectures(tri_naive, [claim("f =:= g",
                                               funcs={"g": scaled},
                                               route="derive")])
    assert p.verdict == "falsified"
    assert p.counterexample and " vs " in p.counterexample


def test_equiv_word_alias_and_unicode_render():
    cj = claim("f equiv g", funcs={"g": tri_incr})
    assert cj.relation == "=:="
    assert "≡" in render_claim_text(cj)
    assert "=:=" in render_claim_text(cj, unicode=False)


def test_arity_mismatch_is_a_misspecification_not_a_verdict():
    def two_args(a, b):
        return a + b
    (p,) = check_conjectures(tri_naive, [claim("f =:= g",
                                               funcs={"g": two_args},
                                               route="derive")])
    assert p.verdict == "skipped:misspecified"
    assert "arity" in p.note


def test_unbound_name_gets_guidance():
    (p,) = check_conjectures(tri_naive, [claim("f =:= g", route="derive")])
    assert p.verdict == "skipped:misspecified"
    assert "funcs=" in p.note


def test_complexity_annotations_ride_the_record():
    (p,) = check_conjectures(tri_naive, [claim("f =:= g",
                                               funcs={"g": tri_incr},
                                               route="derive")])
    ann = (p.meta or {}).get("mathema.equivalence.complexity")
    assert ann and set(ann) == {"f", "g"}


def test_check_keeps_a_live_funcs_binding_through_the_declared_merge():
    """`mathema.check(f, claims=[claim("f =:= g", funcs={"g": proxy})])`
    routes call-site claims through the declared round trip, whose
    serialized form keeps only importable dotted refs. A binding with
    no importable path (a foreign proxy, a nested def) must survive as
    the in-hand callable, not come back as "'g' is not bound"."""
    import inspect

    import mathema

    def local_twin(a, b, c):
        return (1 * a + 2 * b + 3 * c) / 6.0

    proxy = lambda *args: local_twin(*args)  # noqa: E731
    proxy.__name__ = "tri"
    proxy.__qualname__ = "ts:src/tri.ts#tri"
    proxy.__module__ = ""
    proxy.__signature__ = inspect.Signature([
        inspect.Parameter(p, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        for p in ("a", "b", "c")])
    from dataclasses import replace

    from mathema.analysis import analyze_source
    proxy.__mathema_facts__ = replace(analyze_source(local_twin),
                                      tree=None, form="ts:0011223344ab")
    rec = mathema.check(tri_naive, claims=[
        mathema.claim("for a in [-3, 3], b in [-3, 3], c in [-3, 3], "
                      "f =:= g", funcs={"g": proxy})])
    (p,) = [q for q in rec.probes if "=:=" in q.statement]
    assert p.verdict == "holds", (p.verdict, p.note)


# --- the honest sampling tallies (verdicts unchanged) -----------------------

def test_discarded_points_are_tallied_never_silent():
    """Points where both sides raise the same exception agree: the two
    behave the same there. They do not vanish into the agreement count
    unseen: the sampling meta counts them separately and the note says
    so."""
    from dataclasses import replace

    from mathema.analysis import analyze_source

    def partial_naive(a, b, c):
        if a < 0:
            raise ValueError("half the domain refused")
        return (1 * a + 2 * b + 3 * c) / 6.0

    def partial_twin(*args):
        if args[0] < 0:
            raise ValueError("half the domain refused")
        return (1 * args[0] + 2 * args[1] + 3 * args[2]) / 6.0
    # opaque facts: nothing lifts, so only the sampling rung sees the
    # refusals and must count them
    partial_twin.__mathema_facts__ = replace(analyze_source(tri_naive),
                                             tree=None, form="doc:ffee0011")

    (p,) = check_conjectures(partial_naive, [claim(
        "for a in [-5, 5], b in [-1, 1], c in [-1, 1], f =:= g",
        funcs={"g": partial_twin}, route="probe")])
    assert p.verdict == "holds", (p.verdict, p.note)
    sampling = p.meta["mathema.equivalence.sampling"]
    assert sampling["both_raised"] > 0
    assert "not_compared" not in sampling.get("discarded", {})
    assert sampling["checked"] >= 24
    assert "raised the same exception" in (p.note or "")


def test_one_side_raising_where_the_other_returns_falsifies():
    """`f =:= g` means `for x in D, f(x) == g(x)`: a point where one
    side raises and the other returns a value is a counterexample, and
    the executed raise is its witness."""
    from dataclasses import replace

    from mathema.analysis import analyze_source

    def partial_twin(*args):
        if args[0] < 0:
            raise ValueError("half the domain refused")
        return (1 * args[0] + 2 * args[1] + 3 * args[2]) / 6.0
    partial_twin.__mathema_facts__ = replace(analyze_source(tri_naive),
                                             tree=None, form="doc:ffee0011")

    (p,) = check_conjectures(tri_naive, [claim(
        "for a in [-5, 5], b in [-1, 1], c in [-1, 1], f =:= g",
        funcs={"g": partial_twin}, route="probe")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "g raised ValueError" in p.counterexample
    a = float(p.counterexample.split("a=")[1].split(",")[0])
    assert a < 0


def test_the_deciding_rung_is_stamped():
    (identical,) = check_conjectures(tri_naive, [claim(
        "f =:= g", funcs={"g": tri_naive})])
    assert identical.meta["mathema.equivalence.rung"] == "form"

    (symbolic,) = check_conjectures(tri_naive, [claim(
        "f =:= g", funcs={"g": tri_incr}, route="derive")])
    assert symbolic.meta["mathema.equivalence.rung"] in (
        "symbolic", "closed-forms")

    from dataclasses import replace

    from mathema.analysis import analyze_source

    def opaque_twin(*args):
        return (1 * args[0] + 2 * args[1] + 3 * args[2]) / 6.0
    # facts with no syntax tree: nothing to lift, so only the sampling
    # rung can decide
    opaque_twin.__mathema_facts__ = replace(analyze_source(tri_naive),
                                            tree=None, form="doc:00aa11bb22")
    (sampled,) = check_conjectures(tri_naive, [claim(
        "for a in [-2, 2], b in [-2, 2], c in [-2, 2], f =:= g",
        funcs={"g": opaque_twin}, route="probe")])
    assert sampled.verdict == "holds"
    assert sampled.meta["mathema.equivalence.rung"] == "sampled"
    assert sampled.meta["mathema.equivalence.sampling"]["seed"] == 20260718


def test_a_sequence_argument_counterexample_formats_cleanly():
    """The divergence formatter must handle a sequence-valued argument
    (the old %.6g formatting crashed with TypeError at the moment of
    falsification)."""
    def total(xs, k: float) -> float:
        """Sum of xs scaled by k."""
        acc = 0.0
        for x in xs:
            acc += x * k
        return acc

    def total_off_by_one(xs, k: float) -> float:
        acc = 1.0
        for x in xs:
            acc += x * k
        return acc

    (p,) = check_conjectures(total, [claim(
        "for k in [0, 1], f =:= g", funcs={"g": total_off_by_one},
        route="probe")])
    assert p.verdict == "falsified"
    assert " vs " in (p.counterexample or "")
    assert "xs=" in p.counterexample


def test_fallthrough_route_reflects_what_actually_ran():
    """When nothing decides, the route reports the strongest mechanism
    that produced information: probe when points executed, never a
    bare derive label with nothing derived."""
    from dataclasses import replace

    from mathema.analysis import analyze_source

    def wordy(a, b, c):
        return "positive" if a + b + c > 0 else "negative"

    def wordy_twin(*args):
        return "negative" if sum(args) <= 0 else "positive"
    # opaque facts on g: nothing lifts on that side, so no symbolic
    # mechanism can engage and only sampling produces information
    wordy_twin.__mathema_facts__ = replace(analyze_source(wordy),
                                           tree=None, form="doc:aa5566")

    (p,) = check_conjectures(wordy, [claim(
        "for a in [-1, 1], b in [-1, 1], c in [-1, 1], f =:= g",
        funcs={"g": wordy_twin}, route="probe")])
    assert p.verdict == "unknown"
    assert p.route == "probe"
    sampling = p.meta["mathema.equivalence.sampling"]
    assert sampling["discarded"]["non_numeric"] > 0


# --- the dispatch hook ------------------------------------------------------

def _register_equivalence_family(route_fn, handles=True):
    from mathema import families

    class _Family:
        def can_handle(self, fn, facts, claim_name):
            return handles

        def routes(self):
            return {"equivalence": route_fn}
    families.register("equivalence", _Family())
    return families


def test_a_registered_equivalence_family_is_consulted_first():
    def decide(fn, facts, gfn, gfacts, **kwargs):
        return {"verdict": "holds", "route": "probe:algorithmic", "n": 7,
                "note": "decided by the registered family",
                "meta": {"mathema.equivalence.rung": "sampled"}}
    families = _register_equivalence_family(decide)
    try:
        (p,) = check_conjectures(tri_naive, [claim(
            "f =:= g", funcs={"g": tri_incr})])
        assert p.verdict == "holds" and p.route == "probe:algorithmic"
        assert p.n == 7
        assert "registered family" in (p.note or "")
    finally:
        families._REGISTRY.pop("equivalence", None)


def test_a_declining_family_falls_back_to_the_built_in_ladder():
    families = _register_equivalence_family(
        lambda fn, facts, gfn, gfacts, **kwargs: None)
    try:
        (p,) = check_conjectures(tri_naive, [claim(
            "f =:= g", funcs={"g": tri_incr}, route="derive")])
        assert p.verdict == "proven"
    finally:
        families._REGISTRY.pop("equivalence", None)


def test_a_family_falsification_without_a_witness_is_a_loud_bug():
    import pytest

    families = _register_equivalence_family(
        lambda fn, facts, gfn, gfacts, **kwargs: {"verdict": "falsified"})
    try:
        with pytest.raises(ValueError, match="witness|counterexample"):
            check_conjectures(tri_naive, [claim(
                "f =:= g", funcs={"g": tri_incr})])
    finally:
        families._REGISTRY.pop("equivalence", None)


# --- the pre-call domain filter --------------------------------------------

def test_the_domain_filter_rejects_nonfinite_and_excluded_draws():
    from mathema.equivalence import _draw_in_domain
    from mathema.domain import parse_binding

    bound = parse_binding("x in [0, 1]")[1]
    assert _draw_in_domain(0.5, bound)
    assert not _draw_in_domain(float("inf"), bound)
    assert not _draw_in_domain(float("nan"), bound)

    excluded = parse_binding("x in [0, 1] exclude={0.5}")[1]
    assert not _draw_in_domain(0.5, excluded)
    assert _draw_in_domain(0.25, excluded)
    # a bare unbounded draw is fine; only nonfinite is rejected there
    assert _draw_in_domain(123.0, None)
    assert not _draw_in_domain(float("inf"), None)


# --- raise regions -----------------------------------------------------------

def _self_ratio(x: float) -> float:
    return x / x


def _one(x: float) -> float:
    return 1.0


def _removable(x: float) -> float:
    return (x * x - 1.0) / (x - 1.0)


def _line(x: float) -> float:
    return x + 1.0


def _root_squared(x: float) -> float:
    import math
    return math.sqrt(x) ** 2


def _identity(x: float) -> float:
    return x


def test_a_side_that_raises_inside_the_domain_is_never_proven_equivalent():
    """x / x and 1.0 share a closed form, but x / x raises at 0; the
    algebra of the two lifts says nothing about the point where one
    side has no value, so equivalence is not proven there."""
    for f, g, law in ((_self_ratio, _one, "f =:= g"),
                      (_self_ratio, _one, "for x in [-1, 1], f =:= g"),
                      (_removable, _line, "f =:= g"),
                      (_removable, _line, "for x in [0, 2], f =:= g"),
                      (_root_squared, _identity, "f =:= g"),
                      (_root_squared, _identity,
                       "for x in [-1, 1], f =:= g")):
        (p,) = check_conjectures(f, [claim(law, funcs={"g": g},
                                           route="derive")])
        assert p.verdict != "proven", (f.__name__, law, p.sketch)


def test_the_raising_point_is_named_in_the_record():
    (p,) = check_conjectures(_self_ratio, [claim(
        "for x in [-1, 1], f =:= g", funcs={"g": _one}, route="derive")])
    assert "ZeroDivisionError" in (p.note or "")
    assert "x = 0" in (p.note or "")


def test_raise_free_closed_forms_still_prove():
    (p,) = check_conjectures(_root_squared, [claim(
        "for x in [0, 4], f =:= g", funcs={"g": _identity},
        route="derive")])
    assert p.verdict == "proven", (p.verdict, p.sketch, p.note)


def test_a_raise_region_found_symbolically_falsifies_with_its_witness():
    for f, g, law, raised in (
            (_self_ratio, _one, "for x in [-1, 1], f =:= g",
             "ZeroDivisionError"),
            (_removable, _line, "for x in [0, 2], f =:= g",
             "ZeroDivisionError"),
            (_root_squared, _identity, "for x in [-1, 1], f =:= g",
             "ValueError")):
        (p,) = check_conjectures(f, [claim(law, funcs={"g": g},
                                           route="derive")])
        assert p.verdict == "falsified", (f.__name__, p.verdict, p.note)
        assert f"f raised {raised}" in p.counterexample, p.counterexample


# --- complex results ----------------------------------------------------------

def _half_power(x: float) -> float:
    return x ** 0.5


def _abs_half_power(x: float) -> float:
    return abs(x) ** 0.5


def test_a_complex_result_on_one_side_falsifies():
    (p,) = check_conjectures(_half_power, [claim(
        "for x in [-1, 1], f =:= g", funcs={"g": _abs_half_power})])
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "complex" in p.counterexample


# --- the declared tolerance --------------------------------------------------

def _big_plus(x: float) -> float:
    return x + 1e-3


def test_a_declared_tolerance_is_the_whole_allowance():
    """With x near 1e7 a relative term of 1e-9 alone would allow 1e-2;
    a declared tolerance of 1e-4 allows exactly 1e-4, so a gap of 1e-3
    is a counterexample."""
    (p,) = check_conjectures(_big_plus, [claim(
        "for x in [1e7, 1e8], f =:= g", funcs={"g": _identity},
        tolerance=1e-4)])
    assert p.verdict == "falsified", (p.verdict, p.note)


def test_a_declared_tolerance_still_admits_a_gap_within_it():
    (p,) = check_conjectures(_big_plus, [claim(
        "for x in [1e7, 1e8], f =:= g", funcs={"g": _identity},
        tolerance=1e-2)])
    assert p.verdict in ("proven", "holds"), (p.verdict, p.note)
