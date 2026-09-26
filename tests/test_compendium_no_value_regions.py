# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A library function's `is_defined` row makes its no-value region part
of every caller's claims: numpy's sqrt returns nan for a negative input
and log returns nan or -inf at or below zero, so a value claim over a
region that reaches them is false there, with a witness the executed
call reproduces, and true where the region is excluded, by the domain
or by `assuming is_defined(f)`."""
import textwrap

import pytest

pytest.importorskip("numpy")


def _load(tmp_path, body, name):
    import importlib.util
    p = tmp_path / f"{name}.py"
    p.write_text(textwrap.dedent(body))
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def installed():
    from mathema.compendium import install, uninstall
    install(".")
    yield
    uninstall(".")


@pytest.fixture()
def g(tmp_path):
    return _load(tmp_path, '''
        import numpy as np

        def g(x: float) -> float:
            """Square root through numpy."""
            return float(np.sqrt(x))
    ''', "nv_sqrt").g


def _verdict(fn, law):
    from mathema.conjecture import check_conjectures, claim
    (p,) = check_conjectures(fn, [claim(law, route="best")])
    return p


@pytest.mark.needs_full_proof_budget
def test_a_value_claim_over_the_no_value_region_is_falsified(installed, g):
    p = _verdict(g, "for x in [-4, 4], f(x)*f(x) == x")
    assert p.verdict == "falsified", p.note
    # the executed call at the witness returned nan: an executed witness
    assert p.meta.get("mathema.corroboration") == "reproduced"
    assert p.counterexample and "x = -" in p.counterexample
    assert "has no value inside the declared domain" in (p.sketch or "")


@pytest.mark.needs_full_proof_budget
def test_the_same_claim_where_sqrt_has_a_value_is_proven(installed, g):
    assert _verdict(g, "for x in [0, 4], f(x)*f(x) == x").verdict == "proven"


@pytest.mark.needs_full_proof_budget
def test_assuming_is_defined_excludes_the_region(installed, g):
    p = _verdict(g, "assuming is_defined(f), for x in [-4, 4], f(x)*f(x) == x")
    assert p.verdict == "proven", p.note


@pytest.mark.needs_full_proof_budget
def test_log_through_numpy_has_no_value_at_or_below_zero(installed,
                                                         tmp_path):
    h = _load(tmp_path, '''
        import numpy as np

        def h(x: float) -> float:
            """Natural log through numpy."""
            return float(np.log(x))
    ''', "nv_log").h
    p = _verdict(h, "for x in [-4, 4], exp(f(x)) == x")
    assert p.verdict == "falsified", p.note


def test_the_no_value_region_is_the_callers_definedness_region(installed, g):
    from mathema.analysis import analyze_source
    from mathema.conjecture import _collect_definedness_guards
    from mathema.partiality import NO_VALUE
    guards = _collect_definedness_guards(g, analyze_source(g))
    assert [exc for _cond, exc in guards] == [NO_VALUE]


def test_an_executed_non_finite_return_corroborates_only_no_value():
    import sympy

    from mathema.partiality import NO_VALUE
    from mathema.symbolic._prove import _witness_corroborated
    x = sympy.Symbol("x", real=True)

    def nan_at_negative(v):
        return float("nan") if v < 0 else v

    assert _witness_corroborated(nan_at_negative, [x], {x: -1}, NO_VALUE)
    assert not _witness_corroborated(nan_at_negative, [x], {x: -1},
                                     "ValueError")
    assert not _witness_corroborated(nan_at_negative, [x], {x: 1}, NO_VALUE)


def test_two_sides_with_no_value_on_the_same_region_agree(installed,
                                                          tmp_path):
    # the no-value label reads like an exception type: two functions
    # that both have no value exactly for x < 0 coincide there
    import sympy

    from mathema.analysis import analyze_source
    from mathema.equivalence import _raise_regions
    from mathema.partiality import NO_VALUE
    mod = _load(tmp_path, '''
        import numpy as np

        def a(x: float) -> float:
            """Root, one way."""
            return float(np.sqrt(x))

        def b(x: float) -> float:
            """Root, doubled and halved."""
            return float(np.sqrt(4 * x)) / 2
    ''', "nv_pair")
    ra = _raise_regions(mod.a, analyze_source(mod.a), {}, "t")
    rb = _raise_regions(mod.b, analyze_source(mod.b), {}, "t")
    assert set(ra) == set(rb) == {NO_VALUE}
    assert ra[NO_VALUE] == rb[NO_VALUE] == sympy.Interval.open(-sympy.oo, 0)


@pytest.mark.needs_full_proof_budget
def test_mathema_check_installs_the_library_claims(tmp_path):
    import json
    import subprocess
    import sys
    (tmp_path / "roots.py").write_text(textwrap.dedent('''
        import numpy as np

        def g(x: float) -> float:
            """Square root through numpy."""
            return float(np.sqrt(x))
    '''))
    script = ("import sys; from mathema.cli import main; "
              "sys.exit(main(['check', 'roots.py:g', '--claim', "
              "'for x in [-4, 4], f(x)*f(x) == x', '--format', 'json']))")
    r = subprocess.run([sys.executable, "-c", script], cwd=str(tmp_path),
                       capture_output=True, text=True)
    (row,) = json.loads(r.stdout)["functions"]
    (claim,) = [c for c in row["claims"] if c["name"] == "f_x_f_x_eq_x"]
    assert claim["verdict"] == "falsified", claim
    assert r.returncode == 1


def _named(record, name):
    (p,) = [p for p in record.probes if p.name == name]
    return p


@pytest.mark.needs_full_proof_budget
def test_check_applies_the_bundled_library_claims_unasked(g):
    # no install(): the bundled compendium is the engine's own knowledge
    from mathema import check
    from mathema.compendium import uninstall
    uninstall()
    rec = check(g, claims=["for x in [-4, 4], f(x)*f(x) == x"])
    p = _named(rec, "f_x_f_x_eq_x")
    assert p.verdict == "falsified", p.note
    assert p.meta.get("mathema.corroboration") == "reproduced"


@pytest.mark.needs_full_proof_budget
def test_check_with_the_bundled_claims_proves_where_sqrt_has_a_value(g):
    from mathema import check
    from mathema.compendium import uninstall
    uninstall()
    rec = check(g, claims=["for x in [0, 4], f(x)*f(x) == x"])
    assert _named(rec, "f_x_f_x_eq_x").verdict == "proven"


@pytest.fixture()
def ex(tmp_path):
    return _load(tmp_path, '''
        import numpy as np

        def ex(x: float) -> float:
            """Exponential through numpy."""
            return float(np.exp(x))
    ''', "nv_exp").ex


@pytest.mark.needs_full_proof_budget
def test_an_overflow_region_is_computation_the_proof_stands_and_the_companion_falls(ex):
    # numpy.exp's overflow is an `is_overflow_safe` row, never a derive
    # guard: exp(x) >= 0 is proven over the reals, and the float
    # companion carries the overflow at x = 1000
    from mathema import check
    by_name = {p.name: p for p in
               check(ex, claims=["for x in [700, 1000], f(x) >= 0"]).probes}
    parent, companion = by_name["f_x_ge_0"], by_name["f_x_ge_0[float]"]
    assert parent.verdict == "proven", (parent.verdict, parent.note)
    assert parent.route == "derive", parent.route
    assert companion.verdict == "falsified", (companion.verdict,
                                              companion.note)
    assert "x=1000" in (companion.counterexample or "")
    assert "returned inf" in (companion.sketch or ""), companion.sketch


@pytest.mark.needs_full_proof_budget
def test_below_the_overflow_threshold_exp_stays_proven(ex):
    assert _verdict(ex, "for x in [-700, 700], f(x) > 0").verdict == "proven"
