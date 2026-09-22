# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""mathema/probing.py's critical-point sampling integration: _critical_hint()
threads a function's own analytically discovered points into
_synth_scalar's boundary/special candidates, so probing can reach an
interior pole no fixed boundary/midpoint/_SPECIALS candidate could ever
land on."""
import mathema
from mathema.analysis import analyze_source
from mathema.probing import _critical_hint


def _load(tmp_path, name, source):
    fixture = tmp_path / f"{name}.py"
    fixture.write_text(source)
    import sys
    sys.path.insert(0, str(tmp_path))
    try:
        mod = __import__(name)
    finally:
        sys.path.remove(str(tmp_path))
    return mod


def test_critical_hint_finds_an_interior_pole(tmp_path):
    mod = _load(tmp_path, "hint_fixture",
               "def f(x: float) -> float:\n"
               "    return 1 / (x - 0.37)\n")
    facts = analyze_source(mod.f)
    hints = _critical_hint(mod.f, facts, {})
    assert hints["x"] == [0.37]


def test_critical_hint_ignores_a_fold_shaped_function(tmp_path):
    # the same branch-free/loop-free restriction _affine_hint() already
    # applies; a fold-lifted closed form is too expensive to
    # differentiate and solve on every probe() call automatically.
    mod = _load(tmp_path, "hint_fold_fixture",
               "def ema(x: list, alpha: float) -> float:\n"
               "    y = x[0]\n"
               "    for v in x[1:]:\n"
               "        y = alpha * v + (1 - alpha) * y\n"
               "    return y\n")
    facts = analyze_source(mod.ema)
    assert _critical_hint(mod.ema, facts, {}) == {}


def test_derive_falsifies_is_numerically_stable_at_an_interior_pole(tmp_path):
    # a declared domain that provably contains a pole is now settled by
    # the registered is_numerically_stable family's own derive route
    # (domain_hazards()-based), a real proof, not a sample. See
    # test_probe_semi_analytical_route_pinned_to_probe below for the
    # probe-route sampling mechanics this file is otherwise about.
    mod = _load(tmp_path, "interior_pole_fixture",
               "def f(x: float) -> float:\n"
               "    return 1 / (x - 0.37)\n")
    r = mathema.check(mod.f, domain={"x": (-1.0, 1.0)}, trials=32)
    st = next(p for p in r.probes if p.name == "is_numerically_stable")
    assert st.verdict == "falsified"
    assert st.route == "examine"


def test_probe_semi_analytical_route_pinned_to_probe_still_finds_the_pole(tmp_path):
    # route="probe" pinned explicitly (not suggest_claims()'s own
    # route="best" default) so this keeps testing critical-point-
    # informed *sampling* specifically, unaffected by numerically_
    # stable's own registered derive route, the project's own
    # standing testing principle for exactly this situation (a fixture
    # whose liftability/derive-capability keeps growing).
    from mathema.conjecture import check_conjectures, claim
    mod = _load(tmp_path, "interior_pole_probe_fixture",
               "def f(x: float) -> float:\n"
               "    return 1 / (x - 0.37)\n")
    facts = analyze_source(mod.f)
    results = check_conjectures(
        mod.f, [claim("g(f, x) == 1", name="is_numerically_stable", route="probe",
                      funcs={"g": "mathema.f.finite_no_error"})],
        domain={"x": (-1.0, 1.0)}, trials=32, facts=facts)
    st = results[0]
    assert st.verdict == "falsified"
    # record-schema.md's own route field: sampling that was actually
    # informed by an analytically discovered critical point is a
    # distinct, stronger sub-route than blind probing.
    assert st.route == "probe:semi_analytical"


def test_probe_route_stays_plain_with_no_critical_points(tmp_path):
    # a plain line has no pole, no stationary point (the derivative is
    # the nonzero constant 1, never zero), and no domain-transition;
    # x * x, for contrast, DOES have a stationary point at x=0 and
    # would trip this test the other way. route="probe" is pinned
    # explicitly on the claim under test, not left to suggest_claims()'s
    # own route="best" default: x + 1.0 trivially lifts, so an unpinned
    # "deterministic" claim proves via derive today regardless of
    # critical points, which is a different thing than what this test
    # means to check (whether the *probe* route's own route value stays
    # plain "probe" with nothing to inform it).
    mod = _load(tmp_path, "no_critical_points_fixture",
               "def f(x: float) -> float:\n"
               "    return x + 1.0\n")
    cj = mathema.claim("f(x) == f(x)", name="deterministic", route="probe")
    r = mathema.check(mod.f, claims=[cj], trials=16)
    det = next(p for p in r.probes if p.name == "deterministic")
    assert det.route == "probe"
