# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A compendium is a claims file about a library's functions: the
file-level `compendium:` and `versions:` fields name the library and
the version range. Bundled files load version-gated, a project file
shadows them per function, the rows carry the compendium surface, and
a compendium-backed premise is NAMED in the missing-prerequisite note
without its verdict ever entering the evidence chain."""
import textwrap

import pytest

from mathema.compendium import (_version_in_range, compendium_functions,
                                load_library_claims, premise_names)
from mathema.spec import ClaimsFileError, load_declared, validate_claims_file


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))


def install_throwaway_library(tmp_path, monkeypatch) -> str:
    """Intent:
        A made-up library `ramp_kit`, importable and installed at 1.0,
        whose `ramp(x)` raises ValueError below 1: a key the compendium
        tests can state true rows about without naming a real function.
    """
    import sys
    site = tmp_path / "site"
    _write(site / "ramp_kit.py", """
        def ramp(x):
            if x < 1:
                raise ValueError("below one")
            return x - 1
    """)
    _write(site / "ramp_kit-1.0.dist-info" / "METADATA",
           "Metadata-Version: 2.1\nName: ramp_kit\nVersion: 1.0\n")
    monkeypatch.syspath_prepend(str(site))
    monkeypatch.delitem(sys.modules, "ramp_kit", raising=False)
    return "ramp_kit.ramp"


def test_bundled_files_load_for_installed_libraries():
    lib = load_library_claims(".")
    assert lib["math.sqrt"]["compendium"] == "math"          # stdlib: always
    assert lib["numpy.clip"]["compendium"] == "numpy"         # in the test venv
    assert lib["numpy.sqrt"]["versions"] == ">=1.24,<3"
    assert lib["numpy.sqrt"]["source"] == \
        "mathema/compendium/numpy/scalars.claims.yaml"
    rows = {r["name"]: r for r in lib["numpy.sqrt"]["entry"]["claims"]}
    assert set(rows) == {"is_defined", "is_defined_over_complex"}
    row = rows["is_defined"]
    assert row["name"] == "is_defined" and row["statement"] == "x >= 0"
    assert row["source"] == "compendium"
    assert row["meta"]["mathema.compendium"].startswith("compendium:numpy-")
    assert "numpy.clip" in compendium_functions(".")


def test_version_gating_is_the_light_range_spelling():
    assert _version_in_range("2.2.1", ">=1.24,<3")
    assert not _version_in_range("3.0.0", ">=1.24,<3")
    assert not _version_in_range("1.20.0", ">=1.24,<3")
    assert _version_in_range("0.1", "*")
    # an unsupported spelling matches nothing rather than everything
    assert not _version_in_range("2.0", "~=2.0")


def test_a_claims_file_may_name_its_library_and_version_range():
    validate_claims_file({"compendium": "numpy", "versions": ">=1.24,<3",
                          "numpy.sqrt": {"claims": [
                              {"name": "is_defined",
                               "statement": "x >= 0"}]}}, "c.claims.yaml")
    validate_claims_file({"compendium": "math", "versions": "*"}, "m.yaml")
    validate_claims_file({"compendium": "numpy", "versions": ">=2"}, "n.yaml")


@pytest.mark.parametrize("data, field", [
    ({"compendium": ""}, "compendium"),
    ({"compendium": 3}, "compendium"),
    ({"compendium": "num py"}, "compendium"),
    ({"compendium": "numpy", "versions": "~=2.0"}, "versions"),
    ({"compendium": "numpy", "versions": 2}, "versions"),
    ({"compendium": "numpy", "versions": ">=1,<2,<3"}, "versions"),
    ({"versions": ">=1"}, "versions"),
])
def test_a_malformed_library_field_is_refused_naming_the_field(data, field):
    with pytest.raises(ClaimsFileError) as info:
        validate_claims_file(data, "lib.claims.yaml")
    assert str(info.value).startswith(f"lib.claims.yaml: {field}:")


def test_a_project_row_replaces_its_bundled_namesake(tmp_path):
    _write(tmp_path / "claims" / "numpy.claims.yaml", """
        compendium: numpy
        versions: "*"
        numpy.clip:
          claims:
            - name: clip_lower
              statement: 'assuming a_min <= a_max, for a in [-9, 9], a_min <= f(a, a_min, a_max)'
    """)
    info = load_library_claims(str(tmp_path))["numpy.clip"]
    assert info["source"] == "claims/numpy.claims.yaml"
    rows = {r["name"]: r for r in info["entry"]["claims"]}
    # the project's clip_lower replaces the bundled one; the bundled
    # rows it does not restate stay
    assert "[-9, 9]" in rows["clip_lower"]["statement"]
    assert {"clip_upper", "definition"} <= set(rows)
    assert [r["name"] for r in info["entry"]["claims"]].count(
        "clip_lower") == 1
    # every other bundled key is untouched
    assert load_library_claims(str(tmp_path))["numpy.sqrt"]["source"] \
        .startswith("mathema/compendium/")


def test_a_stale_entry_contributes_nothing(tmp_path):
    _write(tmp_path / "claims" / "old.claims.yaml", """
        compendium: numpy
        versions: ">=99"
        numpy.stale_only_fn:
          claims:
            - name: stale_only_claim
              statement: 'for x in [-9, 9], f(x) <= 1'
    """)
    # a name the bundled compendium does not cover, so this asserts the
    # version gate (>=99 excludes the installed numpy), not shadowing
    assert "numpy.stale_only_fn" not in compendium_functions(str(tmp_path))
    assert "stale_only_claim" not in premise_names(str(tmp_path))
    assert "numpy.stale_only_fn" not in load_declared(str(tmp_path))


def test_a_library_that_is_not_importable_contributes_nothing(tmp_path):
    _write(tmp_path / "claims" / "ghost.claims.yaml", """
        compendium: no_such_library_here
        no_such_library_here.f:
          claims:
            - name: bounded
              statement: 'for x in [0, 1], f(x) <= 1'
    """)
    assert "no_such_library_here.f" not in load_library_claims(str(tmp_path))
    assert "no_such_library_here.f" not in load_declared(str(tmp_path))


def test_rows_of_a_project_compendium_file_carry_the_compendium_surface(
        tmp_path):
    _write(tmp_path / "claims" / "numpy.claims.yaml", """
        compendium: numpy
        numpy.tanh:
          claims:
            - name: tanh_bounded
              statement: 'for x in [-1, 1], -1 <= f(x) <= 1'
              meta: {mathema.compendium_claimed: proven}
    """)
    entry = load_declared(str(tmp_path))["numpy.tanh"]["entry"]
    (row,) = entry["claims"]
    assert row["source"] == "compendium"
    assert row["meta"]["mathema.compendium_claimed"] == "proven"
    assert row["meta"]["mathema.compendium"].startswith("compendium:numpy-")
    from mathema.spec import authored_block, entry_claims
    (cj,) = entry_claims(entry)
    assert cj.source == "compendium"
    assert authored_block({"mathema.surface": cj.source}) == \
        {"surface": "compendium"}


def test_the_bundled_directory_is_not_a_project_claims_file():
    # the bundled files are read by the library loader, never as the
    # declared layer of a project tree that happens to contain them
    import os

    import mathema
    root = os.path.dirname(os.path.dirname(os.path.abspath(mathema.__file__)))
    assert not any(k.startswith("numpy.") for k in load_declared(root))


def test_a_compendium_premise_is_named_but_never_trusted():
    import mathema

    def widened(x: float) -> float:
        """x, widened a little."""
        return 1.1 * x

    rec = mathema.check(
        widened,
        claims=["assuming clip_lower holds, for x in [0, 4], f(x) <= 5"],
        known_premises=premise_names("."))
    (row,) = [p for p in rec.probes if "clip_lower" in (p.statement or "")]
    assert row.verdict == "unknown"
    assert row.meta.get("mathema.premise") == "missing-prerequisite"
    assert "compendium:numpy" in (row.note or "")
    assert "never trusted silently" in (row.note or "")


def test_is_defined_regions_become_hazard_boundaries_for_callers():
    import numpy

    def root_gap(x: float, y: float) -> float:
        """Gap between the roots."""
        return numpy.sqrt(x) - numpy.sqrt(y)

    from mathema.compendium import install
    install(".")
    from mathema.analysis import analyze_source
    from mathema.hazards import hazard_points
    points = [h for h in hazard_points(root_gap, analyze_source(root_gap))
              if h.kind == "compendium"]
    assert any(h.value == 0.0 and "numpy.sqrt" in h.at for h in points)
    assert points and all(h.source.startswith("compendium:numpy")
                          for h in points)


def test_region_boundaries_are_solved_over_the_reals():
    from mathema.compendium import _boundaries
    assert _boundaries("abs(x) > 1") == [-1.0, 1.0]
    assert _boundaries("x >= 0") == [0.0]
    assert _boundaries("-1 < x") == [-1.0]
    assert _boundaries("x + y > 1") == []


@pytest.mark.parametrize("spelling", ["np.arcsin(x)", "numpy.arcsin(x)",
                                      "arcsin(x)"])
def test_every_import_spelling_of_a_call_gets_the_hazard(tmp_path, spelling):
    import importlib.util
    (tmp_path / "hz.py").write_text(textwrap.dedent(f'''
        import numpy
        import numpy as np
        from numpy import arcsin

        def to_angle(x: float) -> float:
            """Angle whose sine is x."""
            return float({spelling})
    '''))
    spec = importlib.util.spec_from_file_location("hz", tmp_path / "hz.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    from mathema.analysis import analyze_source
    from mathema.compendium import install
    from mathema.hazards import hazard_points
    install(".")
    values = sorted(h.value for h in hazard_points(
        mod.to_angle, analyze_source(mod.to_angle), kinds=["compendium"]))
    assert values == [-1.0, 1.0]


def test_an_empty_reduction_is_a_hazard_on_sequence_parameters():
    import numpy as np

    def average_of(xs: list) -> float:
        """Mean of the values."""
        return float(np.mean(xs))

    from mathema.analysis import analyze_source
    from mathema.compendium import install
    from mathema.hazards import hazard_points
    install(".")
    (point,) = hazard_points(average_of, analyze_source(average_of),
                             kinds=["compendium"])
    assert point.param == "xs" and point.value is None
    assert point.at == "numpy.mean: empty sequence, outside (dim(a) >= 1)"


def test_library_rows_reach_the_partiality_registry_with_their_labels(
        tmp_path, monkeypatch):
    import sympy

    from mathema.compendium import install, register_library_claims
    from mathema.partiality import NO_VALUE
    from mathema.symbolic._partiality import _PARTIALITY_LEMMAS
    key = install_throwaway_library(tmp_path, monkeypatch)
    _write(tmp_path / "claims" / "ramp_kit.claims.yaml", """
        compendium: ramp_kit
        ramp_kit.ramp:
          claims:
            - name: is_defined
              statement: 'x >= 1'
            - name: below_one_raises
              statement: 'for x in [-10, 10], assuming x < 1, raises(f(x), ValueError)'
    """)
    names = register_library_claims(str(tmp_path))
    assert (key, "is_defined") in names
    assert (key, "below_one_raises") in names
    rows = _PARTIALITY_LEMMAS[key]
    assert [label for _b, label in rows] == [NO_VALUE, "ValueError"]
    u = sympy.Symbol("u", real=True)
    assert rows[0][0](u) == sympy.Lt(u, 1)
    raises_region = rows[1][0](u)
    assert raises_region.subs(u, 0) == sympy.true
    assert raises_region.subs(u, 2) == sympy.false
    assert raises_region.subs(u, -11) == sympy.false
    # the same root again is a no-op; another root replaces these rows
    install(str(tmp_path))
    assert len(_PARTIALITY_LEMMAS[key]) == 2
    install(".")
    assert key not in _PARTIALITY_LEMMAS


def test_a_row_whose_region_does_not_build_is_reported_once(tmp_path):
    from mathema.compendium import register_library_claims, uninstall
    _write(tmp_path / "claims" / "math.claims.yaml", """
        compendium: math
        math.acosh:
          claims:
            - name: is_defined
              statement: 'y >= 1'
    """)
    with pytest.warns(UserWarning, match=r"'is_defined' of math\.acosh"):
        register_library_claims(str(tmp_path))
    uninstall()
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        register_library_claims(str(tmp_path))



def test_a_compendium_file_naming_the_projects_own_package_is_ignored(
        tmp_path, monkeypatch):
    # the export of a project's own library, inside its own tree: the
    # package is installed (editable), so the file would apply
    import mathema.compendium as comp
    from mathema.verify import verify_project
    real = comp._installed_version
    monkeypatch.setattr(comp, "_installed_version",
                        lambda lib, aliases=(): "1.0" if lib == "mylib" else real(lib, aliases))
    monkeypatch.syspath_prepend(str(tmp_path))
    _write(tmp_path / "mylib" / "__init__.py", '''
        def f(x: float) -> float:
            """One more than x."""
            return x + 1.0
    ''')
    _write(tmp_path / "claims" / "c.claims.yaml", """
        mylib.f:
          claims:
            - name: grows
              statement: 'for x in [0, 1], f(x) >= x'
    """)
    _write(tmp_path / "claims" / "mylib.claims.yaml", """
        compendium: mylib
        versions: ">=1.0"
        mylib.f:
          claims:
            - name: grows
              statement: 'for x in [0, 1], f(x) >= x'
              meta: {mathema.compendium_claimed: holds}
            - name: bounded
              statement: 'for x in [0, 1], f(x) <= 2'
    """)
    declared = load_declared(str(tmp_path))
    assert declared["mylib.f"]["source"] == "claims/c.claims.yaml"
    rows = declared["mylib.f"]["entry"]["claims"]
    assert [r["name"] for r in rows] == ["grows"]
    assert (rows[0].get("meta") or {}).get("mathema.surface") != "compendium"
    assert "mylib.f" not in load_library_claims(str(tmp_path))
    result = verify_project(str(tmp_path))
    notes = [line for line in result.lines if "mylib.claims.yaml" in line]
    assert len(notes) == 1, result.lines
    assert notes[0].startswith("note ")
    assert "own package" in notes[0]
    assert not any("library claims from" in line for line in result.lines)


def test_a_bundled_entry_states_its_prose_as_row_notes_not_intent():
    # intent is a function's own statement of purpose; what a claims
    # file says about a library's behaviour rides the row it explains
    import glob
    import os

    import yaml

    from mathema.compendium import _bundled_dir
    paths = glob.glob(os.path.join(_bundled_dir(), "**", "*.claims.yaml"),
                      recursive=True)
    assert paths
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        for key, entry in data.items():
            if isinstance(entry, dict):
                assert "intent" not in entry, (path, key)
    lib = load_library_claims(None)
    (sqrt_row,) = [r for r in lib["numpy.sqrt"]["entry"]["claims"]
                   if r["name"] == "is_defined"]
    assert "never raises" in sqrt_row["note"]
    exp_rows = {r["name"]: r for r in lib["numpy.exp"]["entry"]["claims"]}
    assert "709.78" in exp_rows["is_overflow_safe"]["note"]
    assert "note" not in exp_rows["is_defined"]
