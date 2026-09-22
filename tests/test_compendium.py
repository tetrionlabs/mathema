# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The compendium: curated facts about well-known libraries, the
typing-stubs model, renamed for what it is. Bundled starters load version-gated, a project
file shadows them per function, raise regions reach the partiality
registry, nan regions become hazard boundaries for callers, and a
compendium-backed premise is NAMED in the missing-prerequisite note without
its verdict ever entering the evidence chain."""
import textwrap

from mathema.compendium import (_version_in_range, compendium_functions,
                                install, load_compendium_packs,
                                premise_names)


def test_bundled_starters_load_for_installed_packages():
    packs = {p.package: p for p in load_compendium_packs(".")}
    assert "math" in packs                    # stdlib: always applicable
    assert "numpy" in packs                   # installed in the test venv
    assert "numpy.clip" in compendium_functions(".")


def test_version_gating_is_the_light_range_spelling():
    assert _version_in_range("2.2.1", ">=1.24,<3")
    assert not _version_in_range("3.0.0", ">=1.24,<3")
    assert not _version_in_range("1.20.0", ">=1.24,<3")
    assert _version_in_range("0.1", "*")
    # an unsupported spelling matches nothing rather than everything
    assert not _version_in_range("2.0", "~=2.0")


def test_a_project_file_shadows_the_bundled_one(tmp_path):
    stub_dir = tmp_path / ".mathema" / "compendium"
    stub_dir.mkdir(parents=True)
    (stub_dir / "numpy.yaml").write_text(textwrap.dedent("""
        package: numpy
        versions: "*"
        functions:
          numpy.clip:
            params: [x, lo, hi]
            claims:
              - name: clip_lower
                statement: 'assuming lo <= hi, for x in [-9, 9], lo <= f(x, lo, hi)'
    """))
    sf = compendium_functions(str(tmp_path))["numpy.clip"]
    assert "[-9, 9]" in sf.claims[0]["statement"]


def test_a_stale_entry_contributes_nothing(tmp_path):
    stub_dir = tmp_path / ".mathema" / "compendium"
    stub_dir.mkdir(parents=True)
    (stub_dir / "old.yaml").write_text(textwrap.dedent("""
        package: numpy
        versions: ">=99"
        functions:
          numpy.stale_only_fn:
            params: [x]
            claims:
              - name: stale_only_claim
                statement: 'for x in [-9, 9], f(x) <= 1'
    """))
    # a name the bundled compendium does not cover, so this asserts the
    # version gate (>=99 excludes the installed numpy), not shadowing
    assert "numpy.stale_only_fn" not in compendium_functions(str(tmp_path))
    assert "stale_only_claim" not in premise_names(str(tmp_path))


def test_a_compendium_premise_is_named_but_never_trusted(tmp_path):
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


def test_compendium_raise_regions_reach_the_partiality_registry(tmp_path):
    stub_dir = tmp_path / ".mathema" / "compendium"
    stub_dir.mkdir(parents=True)
    (stub_dir / "kernellib.yaml").write_text(textwrap.dedent("""
        package: math
        versions: "*"
        functions:
          kernellib.stable_kernel:
            params: [u, tol]
            raises_when:
              - condition: 'u <= tol'
                exception: ValueError
    """))
    install(str(tmp_path))
    from mathema.symbolic._partiality import _PARTIALITY_LEMMAS
    assert "kernellib.stable_kernel" in _PARTIALITY_LEMMAS
    import sympy
    builder, exc = _PARTIALITY_LEMMAS["kernellib.stable_kernel"][-1]
    u, tol = sympy.symbols("a b", real=True)
    assert builder(u, tol) == sympy.Le(u, tol)
    assert exc == "ValueError"


def test_nan_regions_become_hazard_boundaries_for_callers():
    import numpy

    def root_gap(x: float, y: float) -> float:
        """Gap between the roots."""
        return numpy.sqrt(x) - numpy.sqrt(y)

    install(".")
    from mathema.analysis import analyze_source
    from mathema.hazards import hazard_points
    points = [h for h in hazard_points(root_gap, analyze_source(root_gap))
              if h.kind == "compendium"]
    assert any(h.value == 0.0 and "numpy.sqrt" in h.at for h in points)
    assert {h.source for h in points} == {
        s for s in {h.source for h in points} if s.startswith("compendium:numpy")}
