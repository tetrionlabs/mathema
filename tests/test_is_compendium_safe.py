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
    # expanded coverage across the hazard categories (domain nan,
    # overflow, division, reductions, bounds)
    assert len(numpy) >= 25
    # domain-nan functions carry precise single-variable nan_when regions
    assert numpy["numpy.sqrt"].nan_when == ("x < 0",)
    assert numpy["numpy.arcsin"].nan_when == ("abs(x) > 1",)
    assert numpy["numpy.log1p"].nan_when == ("x < -1",)
    assert numpy["numpy.arccosh"].nan_when == ("x < 1",)
    # overflow / division functions are covered (caught empirically)
    assert {"numpy.exp", "numpy.divide", "numpy.reciprocal"} <= set(numpy)
    # reductions carry the empty-input region
    assert numpy["numpy.mean"].nan_when == ("len(a) == 0",)
    # bounds carry claims, not hazards
    assert len(numpy["numpy.clip"].claims) == 2
    assert numpy["numpy.tanh"].claims


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
