# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The is_missing_safe[param] claim family: a function's runtime
behavior on a literal NaN input must honor the declared domain's
missing-value policy, reject (raise) when the domain excludes missing
(`\\ {∅}`), accept (never raise) when missing is included (the
default). The structural half proves an excluded policy from an
explicit raising guard; the empirical half calls the real function with
NaN and reports under a probe route, never relabeled as derive."""

from mathema.claim_families import (_is_missing_safe_derive,
                                    _missing_guard_params, _missing_probe)
from mathema.conjecture import check_conjectures, claim
from mathema.suggest import suggest_claims


def guarded_sqrt_like(x: float) -> float:
    if x != x:
        raise ValueError("missing input")
    return x * x


def silent_passthrough(x: float) -> float:
    return x + 0.0


def propagating_mean(x: float, y: float) -> float:
    return (x + y) / 2.0


def _facts(fn):
    from mathema.analysis import analyze_source
    return analyze_source(fn)


def test_missing_guard_params_detects_nan_self_inequality_guard():
    assert _missing_guard_params(_facts(guarded_sqrt_like)) == {"x"}
    assert _missing_guard_params(_facts(silent_passthrough)) == set()


def test_guard_detection_recognizes_is_none_and_isnan_forms(tmp_path):
    import sys
    fixture = tmp_path / "fixture_guards.py"
    fixture.write_text(
        "import math\n\n"
        "def none_guarded(a: float) -> float:\n"
        "    if a is None:\n"
        "        raise TypeError('missing')\n"
        "    return a\n\n"
        "def isnan_guarded(b: float) -> float:\n"
        "    if math.isnan(b):\n"
        "        raise ValueError('missing')\n"
        "    return b\n")
    sys.path.insert(0, str(tmp_path))
    try:
        from fixture_guards import isnan_guarded, none_guarded
        assert _missing_guard_params(_facts(none_guarded)) == {"a"}
        assert _missing_guard_params(_facts(isnan_guarded)) == {"b"}
    finally:
        sys.path.remove(str(tmp_path))
        import sys as _s
        _s.modules.pop("fixture_guards", None)


def fully_guarded(x: float) -> float:
    if x is None or x != x:
        raise ValueError("missing input")
    return x * x


def none_tolerant_mean(x: float) -> float:
    if x is None:
        return float("nan")
    return x / 2.0


def test_derive_proves_exclusion_enforced_for_both_spellings():
    # both missing spellings (NaN and None) carry explicit raising
    # guards, so structure alone proves the exclusion enforced
    cj = claim("for x in [0, 10] \\ {missing}, is_missing_safe(x)",
               name="is_missing_safe[x]", route="best")
    (probe,) = check_conjectures(fully_guarded, [cj])
    assert probe.verdict == "proven"
    assert probe.route == "examine"
    assert "both missing spellings" in probe.sketch


def test_partial_guard_settles_exhaustively_through_the_trials():
    # only the NaN spelling is guarded: structure can't vouch for the
    # None spelling, so the structural half declines, and the
    # trials find the body rejects None anyway (TypeError from the
    # arithmetic). With a single parameter, both missing spellings
    # ARE the whole hazard class, so the examination is exhaustive:
    # an established fact, proven even though it came from trials
    cj = claim("for x in [0, 10] \\ {missing}, is_missing_safe(x)",
               name="is_missing_safe[x]", route="best")
    (probe,) = check_conjectures(guarded_sqrt_like, [cj])
    assert probe.verdict == "proven"
    assert probe.route == "probe:algorithmic"
    assert "exhaustive" in probe.sketch


def test_derive_disproves_a_guard_that_contradicts_the_default_policy():
    # no exclusion declared -> missing included by default -> a raising
    # guard contradicts the declared domain.
    cj = claim("for x in [0, 10], is_missing_safe(x)",
               name="is_missing_safe[x]", route="best")
    (probe,) = check_conjectures(guarded_sqrt_like, [cj])
    assert probe.verdict == "falsified"
    assert probe.route == "examine"


def test_probe_falsifies_an_asserted_but_unenforced_exclusion():
    # domain says missing excluded, but the function silently accepts
    # NaN; the exclusion is asserted, not earned. Structure can't
    # decide (no guard), so the empirical NaN call settles it, under a
    # probe route.
    cj = claim("for x in [0, 10] \\ {missing}, is_missing_safe(x)",
               name="is_missing_safe[x]", route="best")
    (probe,) = check_conjectures(silent_passthrough, [cj])
    assert probe.verdict == "falsified"
    assert probe.route == "probe:algorithmic"
    assert "asserted, not enforced" in probe.counterexample


def test_nan_propagation_alone_no_longer_satisfies_the_default_policy():
    # the default policy admits a missing value in EITHER spelling:
    # (x + y) / 2 propagates NaN fine but raises TypeError on None,
    # so the admitted None spelling falsifies with that witness
    cj = claim("for x in [0, 10], y in [0, 10], is_missing_safe(x)",
               name="is_missing_safe[x]", route="best")
    (probe,) = check_conjectures(propagating_mean, [cj])
    assert probe.verdict == "falsified"
    assert probe.route == "probe:algorithmic"
    assert "x=None raised TypeError" in probe.counterexample


def test_function_wide_spelling_covers_every_numeric_parameter():
    # is_missing_safe(f): the conjunction over all numeric parameters,
    # falsified at the first parameter with a real witness (named)
    cj = claim("is_missing_safe(f)", route="best")
    (probe,) = check_conjectures(propagating_mean, [cj])
    assert probe.name == "is_missing_safe[f]"
    assert probe.verdict == "falsified"
    assert probe.counterexample.startswith("x: ")


def test_function_wide_spelling_holds_when_every_parameter_does():
    def handled(x: float, y: float) -> float:
        if x is None or y is None:
            return float("nan")
        return (x + y) / 2.0
    (probe,) = check_conjectures(handled,
                                 [claim("f is missing safe", route="best")])
    assert probe.verdict == "holds"
    assert "every parameter" in probe.note


def test_both_spellings_handled_proves_exhaustively_for_one_param():
    # NaN propagates, None is converted to NaN, neither missing
    # spelling raises, honoring the default missing-included policy;
    # single parameter => the two spellings are the whole class
    cj = claim("for x in [0, 10], is_missing_safe(x)",
               name="is_missing_safe[x]", route="best")
    (probe,) = check_conjectures(none_tolerant_mean, [cj])
    assert probe.verdict == "proven"
    assert probe.route == "probe:algorithmic"
    assert "exhaustive" in probe.sketch
    assert probe.n > 0


def test_suggested_only_where_a_guard_exists():
    names = {c.name for c in suggest_claims(guarded_sqrt_like)}
    assert "is_missing_safe[x]" in names
    suggested = next(c for c in suggest_claims(guarded_sqrt_like)
                     if c.name == "is_missing_safe[x]")
    assert suggested.route == "examine"
    assert "is_missing_safe[x]" not in {c.name for c in suggest_claims(silent_passthrough)}


def test_round_trips_through_render_claim_text():
    from mathema.spec import render_claim_text
    cj = claim("for x in [0, 10] \\ {missing}, is_missing_safe(x)")
    text = render_claim_text(cj, unicode=True)
    # unicode prefers the postfix reading; the spaced form still
    # reparses to the same claim
    assert "x is missing safe" in text
    reparsed = claim(text)
    assert reparsed.relation == "is_missing_safe"
    assert reparsed.lhs == "x"


def test_probe_helper_declines_a_parameter_the_function_does_not_have():
    import random
    cj = claim("is_missing_safe(zz)")
    assert _missing_probe(silent_passthrough, _facts(silent_passthrough), cj,
                          {}, random.Random(0), 16) is None


def test_derive_helper_stays_undecided_without_structure():
    result = _is_missing_safe_derive(silent_passthrough,
                                     _facts(silent_passthrough),
                                     "x", "", "is_missing_safe", domain={})
    assert result is None
