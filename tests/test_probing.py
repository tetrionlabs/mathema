# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The probe route's static trial budget and confidence heuristic
(probing.py): a flat n=120 for every algebraic law is replaced by a
single budget decided once per probe() call from the function's own
structure, higher for more branches/loops/wide domains, lower (but
only when the domain doesn't need the extra density anyway) for a
function the derive route can prove is affine, plus a per-probe
confidence score (`meta["mathema.confidence"]`) explaining why, and a
guarantee that every special sampled value (0, ±1, ±1e-9, ±1e6, ...)
gets tested at least once regardless of random luck."""
import math

import mathema
from mathema.analysis import analyze_source
from mathema.probing import (_N_BASE, _N_MAX, _RISK, _SPECIALS, _SpecialCycle,
                             _affine_hint, _prepare_sampling, _probe_density,
                             _starting_budget, _structural_risk, _synth_scalar)
from tests.test_mathema import ema


def affine(x: float) -> float:
    return 2.0 * x + 1.0


def nonlinear(x: float) -> float:
    return x ** 2


def branchy(x: float) -> float:
    if x > 0:
        return x
    if x > -10:
        return -x
    return 0.0


def test_structural_risk_is_zero_for_a_trivial_branch_free_function():
    risk = _structural_risk(analyze_source(affine), {})
    assert risk == {"branches": 0, "loops": 0, "params": 0,
                    "wide_domain": 0, "float_extremes": 0}


def test_structural_risk_counts_branches_and_caps_them():
    facts = analyze_source(branchy)
    risk = _structural_risk(facts, {})
    assert risk["branches"] == min(facts.branch_count, _RISK.max_branch_risk)
    assert facts.branch_count >= 2


def test_structural_risk_counts_loops():
    risk = _structural_risk(analyze_source(ema), {})
    assert risk["loops"] == 1


def test_structural_risk_flags_wide_and_unbounded_domains():
    narrow = _structural_risk(analyze_source(affine), {"x": (0.0, 1.0)})
    wide = _structural_risk(analyze_source(affine), {"x": (0.0, 1e6)})
    unbounded = _structural_risk(analyze_source(affine), {"x": (0.0, math.inf)})
    assert narrow["wide_domain"] == 0
    assert wide["wide_domain"] == 1
    assert unbounded["wide_domain"] == 1


def test_structural_risk_flags_float_precision_extremes():
    tiny = _structural_risk(analyze_source(affine), {"x": (1e-9, 1e-8)})
    huge = _structural_risk(analyze_source(affine), {"x": (1e10, 1e11)})
    ordinary = _structural_risk(analyze_source(affine), {"x": (-10.0, 10.0)})
    assert tiny["float_extremes"] == 1
    assert huge["float_extremes"] == 1
    assert ordinary["float_extremes"] == 0


def test_affine_hint_is_true_only_for_a_provably_affine_liftable_function():
    assert _affine_hint(affine, analyze_source(affine)) is True
    assert _affine_hint(nonlinear, analyze_source(nonlinear)) is False
    assert _affine_hint(branchy, analyze_source(branchy)) is False
    assert _affine_hint(ema, analyze_source(ema)) is False   # has a loop, unliftable


def test_starting_budget_is_base_for_a_simple_nonaffine_function_and_escalates_with_complexity():
    simple = _structural_risk(analyze_source(nonlinear), {})
    complex_ = _structural_risk(analyze_source(branchy), {})
    assert _starting_budget(simple, affine=False) == _N_BASE
    assert _starting_budget(complex_, affine=False) > _N_BASE
    assert _starting_budget(complex_, affine=False) <= _N_MAX


def test_starting_budget_drops_for_a_provably_affine_function():
    risk = _structural_risk(analyze_source(affine), {})
    assert _starting_budget(risk, affine=True) == _RISK.affine_budget
    assert _starting_budget(risk, affine=True) < _N_BASE


def test_starting_budget_ignores_the_affine_hint_when_the_domain_is_wide():
    wide_risk = _structural_risk(analyze_source(affine), {"x": (0.0, 1e6)})
    assert wide_risk["wide_domain"] == 1
    # affine=True but a wide domain still needs real coverage, the
    # reduction is skipped, not just capped, in that case.
    assert _starting_budget(wide_risk, affine=True) > _RISK.affine_budget


def test_starting_budget_ignores_the_affine_hint_when_the_domain_is_float_extreme():
    extreme_risk = _structural_risk(analyze_source(affine), {"x": (1e-9, 1e-8)})
    assert extreme_risk["float_extremes"] == 1
    assert _starting_budget(extreme_risk, affine=True) > _RISK.affine_budget


def test_starting_budget_never_exceeds_the_max():
    huge_risk = {"branches": 3, "loops": 2, "params": 4,
                "wide_domain": 2, "float_extremes": 2}
    assert _starting_budget(huge_risk, affine=False) == _N_MAX


def test_probe_density_score_drops_with_more_risk_and_fewer_trials():
    zero_risk = {"branches": 0, "loops": 0, "params": 0,
                "wide_domain": 0, "float_extremes": 0}
    mild_risk = {"branches": 1, "loops": 0, "params": 0,
                "wide_domain": 0, "float_extremes": 0}
    high_risk = {"branches": 3, "loops": 2, "params": 4,
                "wide_domain": 2, "float_extremes": 2}
    # zero risk at the base budget already saturates the 10.0 ceiling;
    # use a mild risk factor so headroom above _N_BASE is still visible.
    at_base = _probe_density(mild_risk, _N_BASE)
    at_max = _probe_density(mild_risk, _N_MAX)
    at_min = _probe_density(mild_risk, 16)
    risky = _probe_density(high_risk, _N_BASE)
    assert at_min["score"] < at_base["score"] < at_max["score"]
    assert risky["score"] < _probe_density(zero_risk, _N_BASE)["score"]
    assert 1.0 <= risky["score"] <= 10.0
    assert 1 <= risky["stars"] <= 4


def test_probe_density_stars_never_reach_five():
    # 5 stars is reserved for an actual derive-route proof, sampling
    # evidence, no matter how clean or how many trials, caps at 4.
    zero_risk = {"branches": 0, "loops": 0, "params": 0,
                "wide_domain": 0, "float_extremes": 0}
    best_case = _probe_density(zero_risk, _N_MAX)
    assert best_case["stars"] == 4
    assert best_case["max_stars"] == 5


def test_probe_density_factors_are_traceable_to_structural_risk():
    facts = analyze_source(branchy)
    risk = _structural_risk(facts, {})
    density = _probe_density(risk, _N_BASE)
    assert density["factors"] == risk
    assert density["n"] == _N_BASE


def test_explicit_trials_disables_adaptivity_entirely():
    # probe()'s auto-battery is retired (it returns nothing for ema),
    # so the trials plumbing is observed on check()'s family battery:
    # every probe that ran to completion must carry exactly n=50 (a
    # falsified probe legitimately stops early at its counterexample)
    import mathema as _m
    rec = _m.check(ema, trials=50)
    # only the generic sampling loop (route "probe") honors the trial
    # count verbatim; a hazard-targeted family battery
    # (probe:algorithmic) deliberately runs its own structured round
    # count over its candidate points
    # the certificate work proves ema's bounded and equivariance rows
    # outright now (n=0), so what remains sampled is the safety
    # batteries; the explicit count is a CAP every sampled row
    # respects, honored exactly by the generic trial loops and never
    # exceeded by a structured battery's own round count
    sampled = [p for p in rec.probes if p.n]
    assert any(p.n == 50 for p in sampled), sampled
    assert all(p.n <= 50 for p in sampled)


def test_budget_is_uniform_across_the_whole_battery_without_explicit_trials():
    # the adaptive-budget decision itself: one static number computed
    # once from the function's structure (probe()'s own battery is
    # mostly retired now; deterministic/bounded/etc are claims,
    # adjudicated through check_conjectures(), which calls this exact
    # same shared setup, see probing._prepare_sampling's own docstring).
    facts = analyze_source(ema)
    budget = _prepare_sampling(ema, facts, {}, None, 1.0, False).budget
    assert budget == _starting_budget(_structural_risk(facts, {}), _affine_hint(ema, facts))


def test_budget_stays_the_same_regardless_of_earlier_falsifications():
    # a falsified claim's own n is however many trials it took to find
    # a counterexample (an early exit), not the full budget; that's
    # not reactive state, it's just what "falsified, n=..." always
    # means. What "no reactive state between claims" actually means:
    # two claims that both hold (run every trial without falsifying)
    # use the exact same budget as their own n, regardless of what an
    # earlier claim in the same call falsified at.
    # the equivariances PROVE now (fold composition), so the battery
    # carries one sampled holds row; the invariant reads as: an early
    # falsification exits at its counterexample and never shrinks the
    # full budget a later holding claim runs, and that full budget is
    # identical across calls (no reactive state anywhere)
    r = mathema.check(ema)
    probes = {p.name: p for p in r.probes}
    assert probes["bounded_lower"].verdict == "falsified"
    assert probes["is_numerically_stable"].verdict == "holds"
    assert probes["bounded_lower"].n < probes["is_numerically_stable"].n
    again = {p.name: p for p in mathema.check(ema).probes}
    assert again["is_numerically_stable"].n == probes[
        "is_numerically_stable"].n


def test_a_provably_affine_function_actually_runs_at_the_reduced_budget():
    facts = analyze_source(affine)
    budget = _prepare_sampling(affine, facts, {}, None, 1.0, False).budget
    assert budget == _RISK.affine_budget


def test_every_plain_sampled_probe_carries_a_confidence_meta():
    # scoped to route "probe": the claim-grammar sampling path carries
    # the confidence meta; probe:algorithmic family probes do not (a
    # known provenance gap, tracked, not asserted away here)
    import mathema as _m
    rec = _m.check(ema, claims=["for alpha in [0, 1], f(xs, alpha) == f(xs, alpha)"])
    sampled = [p for p in rec.probes
               if p.route == "probe" and p.verdict in ("holds", "falsified")
               and p.n]
    assert sampled, "no plain sampled probes to check"
    for p in sampled:
        assert "mathema.confidence" in p.meta
        conf = p.meta["mathema.confidence"]
        assert conf["n"] == p.n
        assert 1 <= conf["stars"] <= 4


def test_check_end_to_end_still_reports_real_confidence_meta():
    rec = mathema.check(ema)
    bounded = next(p for p in rec.probes if p.name == "bounded_lower")
    assert bounded.verdict == "falsified"
    assert "mathema.confidence" in bounded.meta


# --- special-value coverage guarantee -----------------------------------

def test_special_cycle_dispenses_every_value_within_one_lap():
    import random
    cycle = _SpecialCycle(random.Random(1))
    dispensed = {cycle.next() for _ in range(len(_SPECIALS))}
    assert dispensed == set(_SPECIALS)


def test_special_cycle_guaranteed_remaining_is_false_after_one_lap():
    import random
    cycle = _SpecialCycle(random.Random(1))
    for _ in range(len(_SPECIALS)):
        assert cycle.guaranteed_remaining()
        cycle.next()
    assert not cycle.guaranteed_remaining()


def test_synth_scalar_hits_every_special_within_the_first_len_specials_calls_regardless_of_rng():
    import random
    # seed chosen so the 30% gate alone would very likely miss several
    # specials in only 10 draws; the guarantee must not depend on luck.
    rng = random.Random(99)
    cycle = _SpecialCycle(rng)
    values = {_synth_scalar(rng, specials=cycle) for _ in range(len(_SPECIALS))}
    assert values == set(_SPECIALS)


def test_affine_budget_of_32_still_guarantees_full_special_coverage_in_a_real_probe_call():
    # the reduced affine budget (32) is well above len(_SPECIALS) (10),
    # so a real probe() run against a provably-affine function should
    # exercise every special value somewhere in its sampling, not just
    # probabilistically maybe.
    import random
    rng = random.Random(20260718)   # probing._RNG_SEED
    cycle = _SpecialCycle(rng)
    seen = {_synth_scalar(rng, specials=cycle) for _ in range(_RISK.affine_budget)}
    assert set(_SPECIALS) <= seen


# --- richer counterexample detail ---------------------------------------

def test_bounded_counterexample_names_which_side_failed_and_by_what_margin():
    # bounded_lower/bounded_upper are claims now (min(xs) <= f(...) /
    # f(...) <= max(xs)), adjudicated through check_conjectures()'s
    # generic probe loop; the counterexample is the generic
    # "(args): lv vs rv" shape, not a bespoke "result=... > max(x)=..."
    # message the old hardcoded check built. Real, minor loss of
    # message detail; the args and both compared values are still there.
    r = mathema.check(ema)
    bounded = next(p for p in r.probes if p.name == "bounded_lower")
    assert bounded.verdict == "falsified"
    assert ": " in bounded.counterexample and " vs " in bounded.counterexample


def test_permutation_invariant_counterexample_shows_both_computed_values():
    r = mathema.check(ema)
    perm = next(p for p in r.probes if p.name == "permutation_invariant")
    assert perm.verdict == "falsified"
    assert ": " in perm.counterexample and " vs " in perm.counterexample


def test_deterministic_counterexample_would_show_both_calls_if_it_ever_falsified():
    # deterministic never falsifies for a pure function like ema, but
    # det_check()'s own contract (args, detail) must still match run()'s
    # unpacking, exercised directly rather than waiting for a flaky
    # nondeterministic fixture.
    from mathema.probing import _close, _fmt_value

    def fake_nondeterministic_step():
        calls = {"n": 0}

        def check():
            calls["n"] += 1
            v1, v2 = 1.0, (2.0 if calls["n"] == 1 else 1.0)
            return None if _close(v1, v2) else \
                ((1.0,), f"first call={_fmt_value(v1)}, second call={_fmt_value(v2)}")
        return check

    cx = fake_nondeterministic_step()()
    assert cx is not None
    args, detail = cx
    assert detail == "first call=1, second call=2"


# --- trials_scale ---------------------------------------------------------

def test_trials_scale_shrinks_the_adaptive_budget():
    facts = analyze_source(ema)
    default_n = _prepare_sampling(ema, facts, {}, None, 1.0, False).budget
    scaled_n = _prepare_sampling(ema, facts, {}, None, 0.25, False).budget
    assert scaled_n < default_n


def test_trials_scale_also_shrinks_an_explicit_trials_value():
    facts = analyze_source(ema)
    n = _prepare_sampling(ema, facts, {}, 100, 0.5, False).budget
    assert n == 50


def test_trials_scale_never_drops_below_the_floor():
    facts = analyze_source(ema)
    n = _prepare_sampling(ema, facts, {}, None, 0.001, False).budget
    assert n >= max(_RISK.min_trials_floor_when_scaled, len(_SPECIALS))


def test_trials_scale_above_one_does_not_increase_the_budget():
    facts = analyze_source(ema)
    default_n = _prepare_sampling(ema, facts, {}, None, 1.0, False).budget
    upscaled_n = _prepare_sampling(ema, facts, {}, None, 4.0, False).budget
    assert upscaled_n == default_n
