# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Shape certificates and hazard channels from the second batch:
idempotence proves through the guard-boundary split (pinned here as a
contract, the mechanism predates the pin), homogeneity is suggested
only when it will prove, and the hazard registry's finite values reach
the probe sampler's candidate lists."""
import textwrap

import pytest


@pytest.fixture(scope="module")
def shapes(tmp_path_factory):
    p = tmp_path_factory.mktemp("shapes") / "shapes.py"
    p.write_text(textwrap.dedent('''
        def clamp01(x: float) -> float:
            """x clamped into [0, 1]."""
            if x < 0.0:
                return 0.0
            if x > 1.0:
                return 1.0
            return x


        def halve(x: float) -> float:
            """Half of x, NOT idempotent."""
            return x / 2.0


        def weighted_span(x: float, y: float) -> float:
            """Weighted spread, homogeneous of degree one."""
            return 3.0 * x - 0.5 * y
    '''))
    import importlib.util

    spec = importlib.util.spec_from_file_location("shapes", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_idempotence_proves_for_projection_shapes(shapes):
    from mathema.conjecture import check_conjectures, claim
    (p,) = check_conjectures(shapes.clamp01,
                             [claim("for x in [-5, 5], f(f(x)) == f(x)",
                                    route="derive")])
    assert p.verdict == "proven", (p.verdict, p.note)


def test_non_idempotence_falsifies_with_a_witness(shapes):
    from mathema.conjecture import check_conjectures, claim
    (p,) = check_conjectures(shapes.halve,
                             [claim("for x in [-5, 5], f(f(x)) == f(x)",
                                    route="derive")])
    assert p.verdict == "falsified"
    assert p.counterexample


def test_homogeneity_is_suggested_only_when_it_proves(shapes):
    import mathema
    rec = mathema.check(shapes.weighted_span)
    (row,) = [p for p in rec.probes if p.name == "scale_equivariant"]
    assert row.verdict == "proven", (row.verdict, row.note)

    def curved(x: float) -> float:
        """Not homogeneous."""
        return x * x + 1.0

    rec2 = mathema.check(curved)
    assert not any(p.name == "scale_equivariant" for p in rec2.probes)


def test_the_decade_sweep_reaches_the_sampler_hints(shapes):
    # the hazard channel is its own helper, merged beside the critical
    # points in _prepare_sampling; _critical_hint itself stays exactly
    # what its name says
    from mathema.analysis import analyze_source
    from mathema.probing import _critical_hint, _hazard_hint_values
    facts = analyze_source(shapes.weighted_span)
    assert _critical_hint(shapes.weighted_span, facts, {}) == {}
    # by default only function-specific kinds reach sampling; the
    # generic sweep is request-side, by kind
    assert _hazard_hint_values(shapes.weighted_span, facts, {}) == {}
    hints = _hazard_hint_values(shapes.weighted_span, facts, {},
                                kinds=("magnitude",))
    for param in ("x", "y"):
        values = hints.get(param, [])
        assert any(abs(v) == 1e300 for v in values), (param, values[:5])
        assert any(v == 5e-324 for v in values)
        assert all(v == v and abs(v) != float("inf") for v in values)
