# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A `let` binding calls the function it names, in the same way as
importing it and calling it directly would. A binding into mathema
itself, into the author's own project (its declared packages, or the
top-level package of the function under test), or into a function a
trusted compendium covers carries nothing extra. A binding into any
other third-party code whose effects mathema cannot establish runs, and
the claim's result says so, naming the binding: in the record's note,
in `check` output and in the MCP result. Effects are established for
math, cmath, statistics and a named table of numpy's numeric functions;
a numpy function that writes its argument or process-wide state, and
numpy's random generators, are not on it. A trusted compendium is a
bundled one, or a project or dependency compendium whose rows for the
key the project accepted as trusted."""
import os
import subprocess
import sys
import textwrap

import pytest

import mathema
from mathema.conjecture import claim

np = pytest.importorskip("numpy")
pd = pytest.importorskip("pandas")


def _f(x: float) -> float:
    return x


_WORDS = "calls third-party code whose effects mathema cannot establish"


def _row(stmt, fn=_f):
    rec = mathema.check(fn, claims=[claim(stmt, name="c")])
    return rec, next(p for p in rec.probes if p.name == "c")


@pytest.mark.parametrize("stmt,binding", [
    ("let g = json.dumps, for x in [0, 1], g(x) == g(x)",
     "let g = json.dumps"),
    ("let g = pandas.isna, for x in [0, 1], g(x) == 0",
     "let g = pandas.isna"),
    ("let r = numpy.random.random, for x in [0, 1], r() >= 0",
     "let r = numpy.random.random"),
    ("let g = numpy.copyto, for x in [0, 1], f(x) == x",
     "let g = numpy.copyto"),
    ("let g = numpy.put, for x in [0, 1], f(x) == x",
     "let g = numpy.put"),
    ("let g = numpy.seterr, for x in [0, 1], f(x) == x",
     "let g = numpy.seterr"),
    ("let g = numpy.set_printoptions, for x in [0, 1], f(x) == x",
     "let g = numpy.set_printoptions"),
    ("let g = numpy.ndarray.fill, for x in [0, 1], f(x) == x",
     "let g = numpy.ndarray.fill"),
])
def test_a_third_party_binding_carries_the_warning(stmt, binding):
    rec, row = _row(stmt)
    said = f"{binding} {_WORDS}, in the same way as importing it and calling it directly would"
    assert said in (row.note or ""), row.note
    assert said in (row.meta or {}).get("mathema.let_warning", []), row.meta
    assert said in repr(rec), repr(rec)


@pytest.mark.parametrize("stmt", [
    "let g = math.sqrt, for x in (0, 100], g(x) >= 0",
    "let g = cmath.sqrt, for x in (0, 100], g(x) == g(x)",
    "let g = statistics.fmean, for x in [0, 1], f(x) == x",
    "let g = numpy.mean, for x in [0, 1], f(x) == g(x)",
    "let g = numpy.linalg.norm, for x in [0, 1], g(x) >= 0",
    "let g = numpy.sqrt, for x in [0, 1], g(x) >= 0",
    "let g = mathema.f.finite_no_error, for x in [0, 1], f(x) == x",
    "let g = pandas.Series.mean, for x in [0, 1], f(x) == x",
])
def test_an_established_or_mathema_binding_carries_none(stmt):
    rec, row = _row(stmt)
    assert _WORDS not in (row.note or ""), row.note
    assert "mathema.let_warning" not in (row.meta or {}), row.meta
    assert _WORDS not in repr(rec)


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))


@pytest.fixture
def project(tmp_path, monkeypatch):
    _write(tmp_path / "projmod.py", '''
        def double(x: float) -> float:
            return 2 * x


        def f(x: float) -> float:
            return double(x)
    ''')
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.chdir(tmp_path)
    sys.modules.pop("projmod", None)
    import projmod
    yield projmod
    sys.modules.pop("projmod", None)


def test_a_binding_into_the_authors_own_project_carries_none(project):
    for stmt in ("let g = projmod.double, for x in [0, 1], f(x) == g(x)",
                 "for x in [0, 1], f(x) == double(x)"):
        _rec, row = _row(stmt, project.f)
        assert row.verdict in ("proven", "holds"), (row.verdict, row.note)
        assert _WORDS not in (row.note or ""), row.note


def _cli(root, *args):
    env = dict(os.environ, PYTHONPATH=str(root))
    env.pop("VIRTUAL_ENV", None)
    script = ("import sys; from mathema.cli import main; "
              f"sys.exit(main({list(args)!r}))")
    return subprocess.run([sys.executable, "-c", script], cwd=str(root),
                          capture_output=True, text=True, env=env)


def test_check_output_and_mcp_show_the_warning(tmp_path, monkeypatch):
    _write(tmp_path / "fx.py", '''
        def f(x: float) -> float:
            return x
    ''')
    stmt = "let g = json.dumps, for x in [0, 1], g(x) == g(x)"
    r = _cli(tmp_path, "check", "fx:f", "--root", str(tmp_path),
             "--claim", stmt)
    assert f"warning: let g = json.dumps {_WORDS}" in r.stdout, \
        r.stdout + r.stderr
    from mathema.interfaces.mcp import tools
    monkeypatch.chdir(tmp_path)
    out = tools.adjudicate_target("fx:f", claims=[stmt], root=str(tmp_path))
    rows = [c for c in out["claims"] if c.get("warnings")]
    assert rows, out
    assert any(f"let g = json.dumps {_WORDS}" in w
               for c in rows for w in c["warnings"]), rows


def test_third_party_code_vendored_in_the_tree_carries_the_warning(
        project, monkeypatch):
    import pathlib
    vendor = pathlib.Path(project.__file__).parent / "vendor"
    _write(vendor / "thirdlib.py", '''
        SEEN = []


        def remember(x):
            SEEN.append(x)
            return x
    ''')
    monkeypatch.syspath_prepend(str(vendor))
    sys.modules.pop("thirdlib", None)
    stmt = "let g = thirdlib.remember, for x in [0, 1], f(x) == 2 * g(x)"
    _rec, row = _row(stmt, project.f)
    assert f"let g = thirdlib.remember {_WORDS}" in (row.note or ""), row.note
    sys.modules.pop("thirdlib", None)


def test_a_package_the_pyproject_declares_is_the_projects_own(project):
    import pathlib
    root = pathlib.Path(project.__file__).parent
    _write(root / "pyproject.toml", '''
        [project]
        name = "projmod"

        [tool.setuptools]
        packages = ["helpers"]
    ''')
    _write(root / "helpers" / "__init__.py", '''
        def triple(x: float) -> float:
            return 3 * x
    ''')
    sys.modules.pop("helpers", None)
    stmt = "let g = helpers.triple, for x in [0, 1], 3 * f(x) == 2 * g(x)"
    _rec, row = _row(stmt, project.f)
    assert _WORDS not in (row.note or ""), row.note
    sys.modules.pop("helpers", None)


def test_a_dependency_compendium_key_warns_until_accepted_as_trusted(
        tmp_path, monkeypatch):
    _write(tmp_path / "dep.py", '''
        def f(x: float) -> float:
            return -x
    ''')
    _write(tmp_path / "claims" / "operator.claims.yaml", """
        compendium: operator
        versions: "*"
        operator.neg:
          claims:
            - name: decreasing
              statement: 'for x in (0, 100], d(f(x), x) < 0'
              meta: {mathema.compendium_claimed: proven}
    """)
    _write(tmp_path / "claims" / "dep.claims.yaml", """
        dep.f:
          claims:
            - name: same
              statement: 'let g = operator.neg, for x in [0, 1], f(x) == g(x)'
    """)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.chdir(tmp_path)
    _cli(tmp_path, "verify", "--root", str(tmp_path))
    sys.modules.pop("dep", None)
    import dep
    stmt = "let g = operator.neg, for x in [0, 1], f(x) == g(x)"
    _rec, row = _row(stmt, dep.f)
    assert f"let g = operator.neg {_WORDS}" in (row.note or ""), row.note
    from mathema.acceptance import apply_acceptance, plan_acceptance
    apply_acceptance(plan_acceptance(str(tmp_path), "operator.neg",
                                     "decreasing", "trusted", by="test"))
    _rec, row = _row(stmt, dep.f)
    assert _WORDS not in (row.note or ""), row.note
    sys.modules.pop("dep", None)


def test_an_established_function_called_with_out_carries_the_warning():
    _rec, row = _row("let g = numpy.add, for x in [0, 1], "
                     "g(x, x, out=x) == 2 * x")
    assert f"let g = numpy.add {_WORDS}" in (row.note or ""), row.note


@pytest.mark.parametrize("stmt,binding", [
    ("let g = numpy.add, let y be 0.0, for x in [0, 1], "
     "g(x, 1.0, y) == x + 1", "let g = numpy.add"),
    ("let g = numpy.clip, let y be 0.0, for x in [0, 1], "
     "g(x, 0, 1, y) == x", "let g = numpy.clip"),
    ("let g = numpy.cumsum, let y be 0.0, for x in [0, 1], "
     "g(x, 0, None, y) == x", "let g = numpy.cumsum"),
])
def test_out_passed_by_position_carries_the_warning(stmt, binding):
    _rec, row = _row(stmt)
    assert f"{binding} {_WORDS}" in (row.note or ""), row.note


@pytest.mark.parametrize("stmt", [
    "let g = numpy.add, for x in [0, 1], g(x, 1.0) == x + 1",
    "let g = numpy.clip, for x in [0, 1], g(x, 0, 1) == x",
    "let g = numpy.cumsum, for x in [0, 1], g(x, 0) == x",
])
def test_an_established_call_without_out_carries_none(stmt):
    _rec, row = _row(stmt)
    assert _WORDS not in (row.note or ""), row.note


def test_a_declared_package_is_found_from_a_subdirectory(project,
                                                         monkeypatch):
    import pathlib
    root = pathlib.Path(project.__file__).parent
    _write(root / "pyproject.toml", '''
        [project]
        name = "projmod"

        [tool.setuptools]
        packages = ["helpers"]
    ''')
    _write(root / "helpers" / "__init__.py", '''
        def triple(x: float) -> float:
            return 3 * x
    ''')
    (root / "sub").mkdir()
    monkeypatch.chdir(root / "sub")
    sys.modules.pop("helpers", None)
    stmt = "let g = helpers.triple, for x in [0, 1], 3 * f(x) == 2 * g(x)"
    _rec, row = _row(stmt, project.f)
    assert row.verdict in ("proven", "holds"), (row.verdict, row.note)
    assert _WORDS not in (row.note or ""), row.note
    sys.modules.pop("helpers", None)


def test_an_installed_dependency_key_accepted_as_trusted_is_silent(
        tmp_path, monkeypatch):
    import yaml
    _write(tmp_path / "dep2.py", '''
        def f(x: float) -> float:
            return x
    ''')
    # a compendium for an installed dependency (PyYAML), in the project
    _write(tmp_path / "claims" / "yaml.claims.yaml", f"""
        compendium: yaml
        versions: ">={yaml.__version__.split('.')[0]}"
        yaml.safe_dump:
          claims:
            - name: grows
              statement: 'for x in (0, 100], d(f(x), x) > 0'
              meta: {{mathema.compendium_claimed: holds}}
    """)
    _write(tmp_path / "claims" / "dep2.claims.yaml", """
        dep2.f:
          claims:
            - name: same
              statement: 'let g = yaml.safe_dump, for x in [0, 1], f(x) == x'
    """)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.chdir(tmp_path)
    from mathema.compendium import load_library_claims
    assert "yaml.safe_dump" in load_library_claims(str(tmp_path))
    _cli(tmp_path, "verify", "--root", str(tmp_path))
    sys.modules.pop("dep2", None)
    import dep2
    stmt = "let g = yaml.safe_dump, for x in [0, 1], f(x) == x"
    said = f"let g = yaml.safe_dump {_WORDS}"
    _rec, row = _row(stmt, dep2.f)
    assert said in (row.note or ""), row.note
    from mathema.acceptance import apply_acceptance, plan_acceptance
    apply_acceptance(plan_acceptance(str(tmp_path), "yaml.safe_dump",
                                     "grows", "trusted", by="test"))
    _rec, row = _row(stmt, dep2.f)
    assert said not in (row.note or ""), row.note
    # a trust gone stale (the form it was given for has changed) warns
    path = tmp_path / ".mathema" / "verified" / "yaml.safe_dump.yaml"
    data = yaml.safe_load(path.read_text())
    for c in data["yaml.safe_dump"]["claims"]:
        if c.get("name") == "grows":
            c["accepted"]["stale"] = True
    path.write_text(yaml.safe_dump(data))
    _rec, row = _row(stmt, dep2.f)
    assert said in (row.note or ""), row.note
    sys.modules.pop("dep2", None)
