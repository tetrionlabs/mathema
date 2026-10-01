# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""is_compendium_safe(<library>): the function never silently produces a
non-finite output (nan/inf) through an unguarded call into a compendium-
covered library function. Driven by the compendium (numpy's sqrt/log/
arcsin nan regions), parameterised by library, expandable by adding a
compendium YAML."""
import textwrap

import pytest


def _load(tmp_path, body, name="m"):
    import importlib.util
    p = tmp_path / f"{name}.py"
    p.write_text(textwrap.dedent(body))
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _v(fn, law):
    from mathema.conjecture import check_conjectures, claim
    (pr,) = check_conjectures(fn, [claim(law, route="best")])
    return pr


def test_the_numpy_compendium_covers_the_expected_surface():
    from mathema.compendium import compendium_functions
    numpy = {k: v for k, v in compendium_functions().items()
             if k.startswith("numpy.")}

    def defined_on(key):
        return [c["statement"] for c in numpy[key].get("claims") or []
                if c["name"] == "is_defined"]

    def overflow_safe_on(key):
        return [c["statement"] for c in numpy[key].get("claims") or []
                if c["name"] == "is_overflow_safe"]

    # expanded coverage across the hazard categories (domain nan,
    # overflow, division, reductions, bounds)
    assert len(numpy) >= 25
    # domain-nan functions state the region where they return a value
    assert defined_on("numpy.sqrt") == ["x >= 0"]
    assert defined_on("numpy.arcsin") == ["-1 <= x <= 1"]
    assert defined_on("numpy.log1p") == ["x > -1"]
    assert defined_on("numpy.arccosh") == ["x >= 1"]
    assert defined_on("numpy.arctanh") == ["-1 < x < 1"]
    # overflow / division functions are covered (caught empirically)
    assert {"numpy.exp", "numpy.divide", "numpy.reciprocal"} <= set(numpy)
    # the exponentials are mathematically total (a bare is_defined) and
    # overflow-safe only below their threshold, an inf past it: the
    # threshold is a computation fact, stated by an is_overflow_safe row
    assert overflow_safe_on("numpy.exp") == ["x <= 709.782712893384"]
    assert overflow_safe_on("numpy.expm1") == ["x <= 709.782712893384"]
    assert overflow_safe_on("numpy.exp2") == ["x < 1024"]
    assert overflow_safe_on("numpy.cosh") == ["-710.475860073944 < x < 710.475860073944"]
    assert overflow_safe_on("numpy.sinh") == ["-710.475860073944 < x < 710.475860073944"]
    for key in ("numpy.exp", "numpy.expm1", "numpy.exp2", "numpy.cosh",
                "numpy.sinh"):
        assert defined_on(key) == ["is_defined(f)"], key
    # reductions are defined on a non-empty array only
    assert defined_on("numpy.mean") == ["dim(a) >= 1"]
    # bounds carry claims, not hazards
    assert len(numpy["numpy.clip"]["claims"]) == 3
    assert numpy["numpy.tanh"]["claims"]


def test_unguarded_numpy_nan_falsifies_with_a_finite_witness(tmp_path):
    pytest.importorskip("numpy")
    mod = _load(tmp_path, '''
        import numpy as np
        def risky(x: float) -> float:
            """sqrt with no domain guard."""
            return float(np.sqrt(x))
    ''')
    pr = _v(mod.risky, "is_compendium_safe(numpy)")
    assert pr.verdict == "falsified"
    assert "non-finite" in pr.counterexample and "numpy" in pr.counterexample


def test_a_domain_excluding_the_nan_region_holds(tmp_path):
    pytest.importorskip("numpy")
    mod = _load(tmp_path, '''
        import numpy as np
        def risky(x: float) -> float:
            """sqrt."""
            return float(np.sqrt(x))
    ''')
    assert _v(mod.risky, "for x in [0, 1e6], is_compendium_safe(numpy)").verdict \
        == "holds"


def test_a_guarded_numpy_call_holds(tmp_path):
    pytest.importorskip("numpy")
    mod = _load(tmp_path, '''
        import numpy as np
        def clamped(x: float) -> float:
            """Guards the negative region before sqrt."""
            return float(np.sqrt(max(x, 0.0)))
    ''')
    assert _v(mod.clamped, "is_compendium_safe(numpy)").verdict == "holds"


def test_suggested_only_when_a_covered_numpy_function_is_called(tmp_path):
    pytest.importorskip("numpy")
    from mathema.compendium import libraries_called
    from mathema.analysis import analyze_source
    from mathema.suggest import suggest_claims
    mod = _load(tmp_path, '''
        import numpy as np
        def uses_numpy(x: float) -> float:
            """Calls a covered numpy function."""
            return float(np.arcsin(x))
        def pure(x: float) -> float:
            """No numpy at all."""
            return x + 1.0
    ''')
    assert libraries_called(mod.uses_numpy, analyze_source(mod.uses_numpy)) == {"numpy"}
    assert libraries_called(mod.pure, analyze_source(mod.pure)) == set()
    assert "is_compendium_safe[numpy]" in {c.name for c in suggest_claims(mod.uses_numpy)}
    assert "is_compendium_safe[numpy]" not in {c.name for c in suggest_claims(mod.pure)}


def test_a_bound_supersedes_the_compendium_falsification():
    # the falsification -> guard/bound -> holds progression the docs and
    # lexicon show: unguarded numpy.arcsin falsifies is_compendium_safe,
    # and constraining the input to the safe region makes it hold.
    pytest.importorskip("numpy")
    from mathema.lexicon import unguarded_arcsin
    unguarded = _v(unguarded_arcsin, "is_compendium_safe(numpy)")
    assert unguarded.verdict == "falsified"
    bounded = _v(unguarded_arcsin,
                 "for x in [-1, 1], is_compendium_safe(numpy)")
    assert bounded.verdict == "holds"


def test_a_raise_inside_the_library_falsifies(tmp_path):
    # numpy.average raises ZeroDivisionError from its own code when the
    # weights sum to zero: a failure of the covered call, not a guard
    pytest.importorskip("numpy")
    mod = _load(tmp_path, '''
        import numpy as np
        def weighted(x: float) -> float:
            """Average of 1 and 2, weighted by x and -x."""
            return float(np.average([1.0, 2.0], weights=[x, -x]))
    ''', name="raising_lib")
    pr = _v(mod.weighted, "for x in [1, 2], is_compendium_safe(numpy)")
    assert pr.verdict == "falsified"
    assert "raised ZeroDivisionError inside numpy" in pr.counterexample


def test_the_callers_own_guard_is_not_a_library_failure(tmp_path):
    pytest.importorskip("numpy")
    mod = _load(tmp_path, '''
        import numpy as np
        def to_angle(x: float) -> float:
            """Angle whose sine is x, refusing out-of-range input."""
            if abs(x) > 1:
                raise ValueError("x must lie in [-1, 1]")
            return float(np.arcsin(x))
    ''', name="guarded_lib")
    assert _v(mod.to_angle, "is_compendium_safe(numpy)").verdict == "holds"
