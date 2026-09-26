# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Compendium rows are typed by stratum. An `is_defined` row is
mathematics and registers a derive guard; a computation-safety family in
restriction form (`is_overflow_safe: x <= 709.78`) and a `raises` row
whose type is a machine failure are computation: they feed the hazard
points, `is_compendium_safe`'s diagnosis, the reach of the key's own
`is_defined` probe and the float companion's sketch, and never a derive
guard."""
import textwrap

import pytest

np = pytest.importorskip("numpy")


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))


def _load(tmp_path, body, name):
    import importlib.util
    p = tmp_path / f"{name}.py"
    p.write_text(textwrap.dedent(body))
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def ex(tmp_path):
    return _load(tmp_path, '''
        import numpy as np

        def ex(x: float) -> float:
            """Exponential through numpy."""
            return float(np.exp(x))
    ''', "cr_exp").ex


def _one(fn, law, **kw):
    from mathema.conjecture import check_conjectures, claim
    (p,) = check_conjectures(fn, [claim(law, route="best")], **kw)
    return p


def test_the_bundled_overflow_rows_are_overflow_safe_rows_with_a_bare_is_defined():
    from mathema.compendium import compendium_functions
    numpy = compendium_functions()

    def rows(key, name):
        return [c["statement"] for c in numpy[key].get("claims") or []
                if c["name"] == name]

    assert rows("numpy.exp", "is_overflow_safe") == ["x <= 709.782712893384"]
    assert rows("numpy.expm1", "is_overflow_safe") == ["x <= 709.782712893384"]
    assert rows("numpy.exp2", "is_overflow_safe") == ["x < 1024"]
    assert rows("numpy.cosh", "is_overflow_safe") == [
        "-710.475860073944 < x < 710.475860073944"]
    assert rows("numpy.sinh", "is_overflow_safe") == [
        "-710.475860073944 < x < 710.475860073944"]
    for key in ("numpy.exp", "numpy.exp2", "numpy.expm1", "numpy.cosh",
                "numpy.sinh"):
        assert rows(key, "is_defined") == ["is_defined(f)"], key
    assert rows("math.exp", "is_overflow_safe") == ["x <= 709.782712893384"]
    # the computation is exercised up to the carrier's maximum, never at
    # infinity itself (math.exp(inf) is inf, not an overflow)
    assert rows("math.exp", "exp_overflow_raises") == [
        "let |inf| be 1e308, for x in (709.782712893384, oo), "
        "raises(f(x), OverflowError)"]


def test_an_overflow_safe_row_never_reaches_the_partiality_registry(ex):
    from mathema.analysis import analyze_source
    from mathema.compendium import ensure_bundled
    from mathema.conjecture import _collect_definedness_guards
    from mathema.symbolic._partiality import _PARTIALITY_LEMMAS
    ensure_bundled()
    assert "numpy.exp" not in _PARTIALITY_LEMMAS
    assert "math.exp" not in _PARTIALITY_LEMMAS
    assert _collect_definedness_guards(ex, analyze_source(ex)) == []


def test_computation_rows_are_in_the_computation_registry():
    from mathema.compendium import computation_region, ensure_bundled
    ensure_bundled()
    (row,) = computation_region("numpy.exp", "is_overflow_safe")
    assert row["texts"] == ["x <= 709.782712893384"]
    assert row["params"] == ["x"]
    assert row["exception"] is None
    assert row["source"].startswith("compendium:numpy")
    rows = computation_region("math.exp")
    assert {r["family"] for r in rows} == {"is_overflow_safe", "raises"}
    (raising,) = [r for r in rows if r["family"] == "raises"]
    assert raising["exception"] == "OverflowError"
    assert computation_region("numpy.sqrt") == []


def test_a_machine_failure_raises_row_is_computation(tmp_path):
    from mathema.compendium import computation_region, register_library_claims
    from mathema.symbolic._partiality import _PARTIALITY_LEMMAS
    _write(tmp_path / "claims" / "math.claims.yaml", """
        compendium: math
        math.acosh:
          claims:
            - name: is_defined
              statement: 'x >= 1'
            - name: below_one_raises
              statement: 'for x in [-10, 10], assuming x < 1, raises(f(x), ValueError)'
        math.cosh:
          claims:
            - name: is_overflow_safe
              statement: '-710.475860073944 < x < 710.475860073944'
            - name: cosh_overflow_raises
              statement: 'for x in (710.475860073944, oo), raises(f(x), OverflowError)'
    """)
    names = register_library_claims(str(tmp_path))
    assert ("math.acosh", "is_defined") in names
    assert ("math.acosh", "below_one_raises") in names
    assert ("math.cosh", "is_overflow_safe") in names
    assert ("math.cosh", "cosh_overflow_raises") in names
    # a ValueError is the author's contract: mathematics, on derive
    assert [label for _b, label in _PARTIALITY_LEMMAS["math.acosh"]] == [
        "no value", "ValueError"]
    # an OverflowError is the machine giving out: computation only
    assert "math.cosh" not in _PARTIALITY_LEMMAS
    rows = computation_region("math.cosh")
    assert [r["family"] for r in rows] == ["is_overflow_safe", "raises"]
    assert rows[1]["exception"] == "OverflowError"


def test_uninstall_clears_the_computation_registry():
    from mathema.compendium import computation_region, ensure_bundled, uninstall
    ensure_bundled()
    assert computation_region("numpy.exp")
    uninstall()
    assert computation_region("numpy.exp") == []
    ensure_bundled()
    assert computation_region("numpy.exp")


def test_the_overflow_boundary_is_still_a_hazard_point_for_a_caller(ex):
    from mathema.analysis import analyze_source
    from mathema.compendium import ensure_bundled
    from mathema.hazards import hazard_points
    ensure_bundled()
    points = hazard_points(ex, analyze_source(ex), kinds=["compendium"])
    assert any(p.value == 709.782712893384 and "numpy.exp" in p.at
               for p in points), points


def test_is_compendium_safe_names_the_overflow_safe_region(ex):
    p = _one(ex, "for x in [0, 1000], is_compendium_safe(numpy)")
    assert p.verdict == "falsified", (p.verdict, p.note)
    cx = p.counterexample or ""
    assert "numpy.exp is overflow-safe only for x <= 709.78" in cx, cx
    assert "lies outside it" in cx, cx


def test_the_bare_is_defined_of_numpy_exp_holds_inside_its_overflow_safe_region():
    import mathema
    (p,) = [p for p in mathema.check(np.exp, claims=["is_defined(f)"]).probes
            if p.meta.get("mathema.surface") == "declared"]
    assert p.verdict == "holds", (p.verdict, p.note, p.counterexample)
    assert "overflow-safe region" in (p.note or ""), p.note


@pytest.mark.needs_full_proof_budget
def test_the_companion_sketch_names_the_covered_calls_overflow_region(ex):
    import mathema
    rec = mathema.check(ex, claims=["for x in [700, 1000], f(x) >= 0"])
    by_name = {p.name: p for p in rec.probes}
    parent = by_name["f_x_ge_0"]
    companion = by_name["f_x_ge_0[float]"]
    assert parent.verdict == "proven", (parent.verdict, parent.note)
    assert companion.verdict == "falsified", (companion.verdict,
                                              companion.note)
    assert "x=1000" in (companion.counterexample or "")
    assert ("the covered call numpy.exp is overflow-safe only for "
            "x <= 709.78") in (companion.sketch or ""), companion.sketch


def test_verify_adjudicates_the_numpy_and_math_exp_rows_by_execution(tmp_path,
                                                                    monkeypatch):
    from mathema.verify import verify_project
    monkeypatch.syspath_prepend(str(tmp_path))
    _write(tmp_path / "quant.py", '''
        import math

        import numpy as np


        def ex(x: float) -> float:
            """Exponential through numpy."""
            return float(np.exp(x))


        def grow(x: float) -> float:
            """Exponential through math."""
            return math.exp(x)
    ''')
    _write(tmp_path / "claims" / "quant.claims.yaml", """
        quant.ex:
          claims:
            - name: positive
              statement: 'for x in [0, 1], f(x) > 0'
        quant.grow:
          claims:
            - name: positive
              statement: 'for x in [0, 1], f(x) > 0'
    """)
    result = verify_project(str(tmp_path))
    rows = {entry["key"]: {c["claim"]: c["verdict"] for c in entry["claims"]}
            for entry in result.keys}
    assert rows["numpy.exp"]["is_defined"] == "holds", rows["numpy.exp"]
    assert rows["numpy.exp"]["is_overflow_safe"] == "holds", rows["numpy.exp"]
    assert rows["math.exp"]["is_overflow_safe"] == "holds", rows["math.exp"]
    assert rows["math.exp"]["exp_overflow_raises"] == "holds", rows["math.exp"]
    assert rows["math.exp"]["exp_positive"] == "holds", rows["math.exp"]


def test_validation_accepts_the_overflow_safe_restriction_form():
    from mathema.spec import validate_claims_file
    data = {"compendium": "math", "versions": "*",
            "math.exp": {"claims": [
                {"name": "is_overflow_safe",
                 "statement": "x <= 709.782712893384"},
                {"name": "is_defined", "statement": "is_defined(f)"}]}}
    validate_claims_file(data, "math.claims.yaml")


def test_region_texts_read_both_region_families():
    from mathema.compendium import _region_texts
    entry = {"claims": [
        {"name": "is_defined", "statement": "x >= 0"},
        {"name": "is_overflow_safe", "statement": "-2 < x < 2"},
        {"name": "positive", "statement": "for x in [0, 1], f(x) > 0"}]}
    assert _region_texts(entry, ("is_defined",)) == [["x >= 0"]]
    assert _region_texts(entry, ("is_overflow_safe",)) == [["-2 < x", "x < 2"]]
    assert _region_texts(entry, ("is_defined", "is_overflow_safe")) == [
        ["x >= 0"], ["-2 < x", "x < 2"]]
