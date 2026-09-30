# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim about a library function (a key of a `compendium:` file)
leaves the parameters it does not bind at their defaults: `for a in
R^n, ...` on `numpy.mean` samples only `a`, and `axis`, `dtype`, `out`,
`keepdims` and `where` are passed as numpy defines them. The values
passed are stated in the record (`mathema.defaults`) and the note, a
row may pin a parameter with `let p be v`, and a pinned name the
function does not have is a misspecified row. A project's own function
keeps sampling its defaulted parameters."""
import sys
import textwrap

import pytest

import mathema

np = pytest.importorskip("numpy")

_MEAN_DEFAULTS = {"axis", "dtype", "out", "keepdims", "where"}


def _declared(fn, statement, name=None):
    c = mathema.claim(statement, name=name) if name else statement
    (p,) = [p for p in mathema.check(fn, claims=[c]).probes
            if p.meta.get("mathema.surface") == "declared"]
    return p


def test_is_defined_on_mean_holds_with_its_defaults_stated():
    p = _declared(np.mean, "dim(a) >= 1", name="is_defined")
    assert p.verdict == "holds", p.note
    assert set(p.meta["mathema.defaults"]) == {"numpy.mean"}
    kept = p.meta["mathema.defaults"]["numpy.mean"]
    assert set(kept) == _MEAN_DEFAULTS
    assert kept["axis"] == "None"
    assert kept["keepdims"] == "<no value>"
    assert "held at their defaults: axis=None" in p.note


def test_a_bound_on_mean_samples_only_the_array():
    p = _declared(np.mean, "for a in R^n, min(a) <= f(a) <= max(a)")
    assert p.verdict == "holds", p.note
    assert set(p.meta["mathema.defaults"]["numpy.mean"]) == _MEAN_DEFAULTS


def test_a_pinned_axis_is_passed_and_shown_pinned():
    # the mean over axis 0 of an n by n matrix has n entries
    law = "for a in R^(n,n), dim(f(a)) == dim(a)"
    pinned = _declared(np.mean, f"let axis be 0, {law}")
    assert pinned.verdict == "holds", pinned.note
    assert pinned.meta["mathema.defaults"]["numpy.mean"]["axis"] == \
        "0 (pinned)"
    assert "let axis be" in pinned.statement
    assert _declared(np.mean, law).verdict != "holds"


def test_a_literal_pin_survives_the_canonical_text():
    p = _declared(np.mean, "let keepdims be True, for a in R^n, dim(f(a)) == 1")
    assert p.verdict == "holds", p.note
    assert p.meta["mathema.defaults"]["numpy.mean"]["keepdims"] == \
        "True (pinned)"
    again = mathema.claim(p.statement)
    assert again.param_pins == {"keepdims": True}


def test_a_pin_naming_no_parameter_is_misspecified():
    p = _declared(np.mean, "let bogus be None, for a in R^n, f(a) <= max(a)")
    assert p.verdict == "skipped:misspecified"
    assert "bogus is not a parameter of numpy.mean" in p.note


def test_a_project_function_still_samples_its_defaulted_parameters(
        tmp_path, monkeypatch):
    (tmp_path / "dflt.py").write_text(textwrap.dedent('''
        def f(x: float, alpha: float = 0.5) -> float:
            """x scaled by alpha, which must be one half."""
            if alpha != 0.5:
                raise ValueError("alpha")
            return alpha * x
    '''))
    monkeypatch.syspath_prepend(str(tmp_path))
    import importlib
    f = importlib.import_module("dflt").f
    from mathema.probing import _keeps_default
    import inspect
    alpha = inspect.signature(f).parameters["alpha"]
    assert not _keeps_default(f, alpha)
    rec = mathema.check(f, claims=["for x in [0, 1], f(x) >= 0"])
    # the battery samples alpha, and the raise it hits says so
    (callable_probe,) = [p for p in rec.probes if p.name == "callable"]
    assert callable_probe.verdict == "skipped", callable_probe.note
    assert "ValueError" in callable_probe.note
    (claim_probe,) = [p for p in rec.probes if p.name == "f_x_ge_0"]
    assert "mathema.defaults" not in (claim_probe.meta or {})


def test_verify_readjudicates_when_a_library_default_moves(
        tmp_path, monkeypatch):
    # a library outside the project, installed at version 1.0
    import mathema.compendium as comp
    from mathema.verify import verify_project
    real = comp._installed_version
    monkeypatch.setattr(comp, "_installed_version",
                        lambda lib, aliases=(): "1.0" if lib == "extlib" else real(lib, aliases))
    site = tmp_path / "site"
    (site / "extlib").mkdir(parents=True)
    source = site / "extlib" / "__init__.py"
    # the default is read from a module constant, so a release that
    # moves it leaves the function's own text, and its form, unchanged
    body = '''
        K = {k}


        def scaled(x: float, k: float = K) -> float:
            """x times k."""
            return x * k
    '''
    source.write_text(textwrap.dedent(body.format(k="2.0")))
    monkeypatch.syspath_prepend(str(site))
    proj = tmp_path / "proj"
    (proj / "claims").mkdir(parents=True)
    (proj / "claims" / "extlib.claims.yaml").write_text(textwrap.dedent("""
        compendium: extlib
        versions: ">=1.0"
        extlib.scaled:
          claims:
            - name: nonneg
              statement: 'for x in [0, 4], f(x) >= 0'
    """))
    (proj / "claims" / "use.claims.yaml").write_text(textwrap.dedent("""
        extlib.scaled:
          claims: []
    """))

    def sweep():
        sys.modules.pop("extlib", None)
        comp.uninstall()
        return verify_project(str(proj))

    first = sweep()
    assert any("extlib.scaled" in line for line in first.lines), first.lines
    import yaml
    rec = proj / ".mathema" / "verified" / "extlib.scaled.yaml"
    (row,) = [c for c in yaml.safe_load(rec.read_text())["extlib.scaled"]
              ["claims"] if c["name"] == "nonneg"]
    assert row["meta"]["mathema.defaults"] == {"extlib.scaled": {"k": "2.0"}}
    # unchanged: fresh
    again = sweep()
    assert any("extlib.scaled: fresh" in line for line in again.lines), \
        again.lines
    # the library's next release moves the default inside the range
    source.write_text(textwrap.dedent(body.format(k="-2.0")))
    moved = sweep()
    line = next(line for line in moved.lines if "extlib.scaled" in line)
    assert "fresh" not in line, moved.lines
    (row,) = [c for c in yaml.safe_load(rec.read_text())["extlib.scaled"]
              ["claims"] if c["name"] == "nonneg"]
    assert row["meta"]["mathema.defaults"] == \
        {"extlib.scaled": {"k": "-2.0"}}
    assert "defaults changed" in line, line
    # the claim held at the old default and fails at the new one
    assert row["verdict"] == "invalidated"


def test_a_numeric_pin_of_a_parameter_the_function_lacks_is_misspecified():
    # numpy.clip has no axis: the row's pin names nothing
    p = _declared(np.clip,
                  "let axis be 0, for a in [0, 1], f(a, 0, 1) >= 0")
    assert p.verdict == "skipped:misspecified", p.note
    assert "axis is not a parameter of numpy.clip" in p.note


def test_a_literal_pin_on_a_project_function_is_passed(tmp_path, monkeypatch):
    (tmp_path / "pinproj.py").write_text(textwrap.dedent('''
        def g(x: float, strict: bool = False) -> float:
            """x, or its magnitude when strict."""
            return abs(x) if strict else x
    '''))
    monkeypatch.syspath_prepend(str(tmp_path))
    import importlib
    g = importlib.import_module("pinproj").g
    pinned = _declared(g, "let strict be True, for x in [-1, 1], f(x) >= 0")
    assert pinned.verdict == "holds", pinned.note
    assert pinned.meta["mathema.defaults"] == \
        {"pinproj.g": {"strict": "True (pinned)"}}
    assert _declared(g, "for x in [-1, 1], f(x) >= 0").verdict == "falsified"


def test_a_library_function_is_known_after_its_module_is_imported_again():
    # the identity cache was built for an earlier import of the library;
    # the function object reached now is a fresh one with the same name
    from mathema import compendium
    compendium.ensure_bundled()

    def stale():
        pass

    compendium._INSTALLED["objects"] = {id(stale): (stale, "numpy.mean")}
    assert compendium.library_key_of(np.mean) == "numpy.mean"
    import inspect
    axis = inspect.signature(np.mean).parameters["axis"]
    from mathema.probing import _keeps_default
    assert _keeps_default(np.mean, axis)


def test_a_let_bound_library_function_states_the_defaults_it_kept():
    # one claim can call several library functions: each one's kept
    # values are stated under its own name
    p = _declared(np.mean,
                  "let g = numpy.sqrt, for a in R^n, g(f(a) * f(a)) >= 0")
    assert p.verdict == "holds", p.note
    stated = p.meta["mathema.defaults"]
    assert set(stated) == {"numpy.mean", "numpy.sqrt"}
    assert set(stated["numpy.mean"]) == _MEAN_DEFAULTS
    assert stated["numpy.sqrt"]["out"] == "None"
    assert "numpy.sqrt" in p.note


def test_a_project_function_calling_a_let_bound_library_function(
        tmp_path, monkeypatch):
    (tmp_path / "letproj.py").write_text(textwrap.dedent('''
        def sq(x: float) -> float:
            """x squared."""
            return x * x
    '''))
    monkeypatch.syspath_prepend(str(tmp_path))
    import importlib
    sq = importlib.import_module("letproj").sq
    p = _declared(sq, "let g = numpy.sqrt, for x in [0, 4], g(f(x)) >= 0")
    assert p.verdict in ("holds", "proven"), p.note
    stated = p.meta["mathema.defaults"]
    assert set(stated) == {"numpy.sqrt"}
    assert stated["numpy.sqrt"]["out"] == "None"


def test_freshness_compares_the_defaults_per_function():
    from mathema.verify import _defaults_moved
    entry = {"claims": [{"name": "is_defined", "statement": "dim(a) >= 1"}]}
    p = _declared(np.mean, "dim(a) >= 1", name="is_defined")
    recorded = {"claims": [{"name": "is_defined",
                            "meta": {"mathema.defaults":
                                     p.meta["mathema.defaults"]}}]}
    assert not _defaults_moved(np.mean, entry, recorded)
    flat = {"claims": [{"name": "is_defined",
                        "meta": {"mathema.defaults":
                                 p.meta["mathema.defaults"]["numpy.mean"]}}]}
    assert _defaults_moved(np.mean, entry, flat)


def test_a_library_key_with_a_policy_row_stays_fresh(tmp_path, monkeypatch):
    import mathema.compendium as comp
    from mathema.verify import verify_project
    real = comp._installed_version
    monkeypatch.setattr(comp, "_installed_version",
                        lambda lib, aliases=(): "1.0" if lib == "extlib" else real(lib, aliases))
    site = tmp_path / "site"
    (site / "extlib").mkdir(parents=True)
    (site / "extlib" / "__init__.py").write_text(textwrap.dedent('''
        def scaled(x: float, k: float = 2.0) -> float:
            """x times k."""
            return x * k
    '''))
    monkeypatch.syspath_prepend(str(site))
    proj = tmp_path / "proj"
    (proj / "claims").mkdir(parents=True)
    (proj / "claims" / "extlib.claims.yaml").write_text(textwrap.dedent("""
        compendium: extlib
        versions: ">=1.0"
        extlib.scaled:
          claims:
            - name: nonneg
              statement: 'for x in [0, 4], f(x) >= 0'
            - name: holes_through
              statement: 'missing(f, x) propagates'
    """))
    (proj / "claims" / "use.claims.yaml").write_text(textwrap.dedent("""
        extlib.scaled:
          claims: []
    """))

    def sweep():
        sys.modules.pop("extlib", None)
        comp.uninstall()
        return verify_project(str(proj))

    sweep()
    import yaml
    rec = proj / ".mathema" / "verified" / "extlib.scaled.yaml"
    (row,) = [c for c in yaml.safe_load(rec.read_text())["extlib.scaled"]
              ["claims"] if c["name"] == "holes_through"]
    assert row["meta"]["mathema.defaults"] == {"extlib.scaled": {"k": "2.0"}}
    again = sweep()
    assert any("extlib.scaled: fresh" in line for line in again.lines), again.lines
