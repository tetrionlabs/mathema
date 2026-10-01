# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A `let` binding calls the function it names, as importing that
library and calling the function in your own code would. A binding into
mathema itself or the author's own project carries nothing extra. A
binding into third-party code whose purity mathema cannot establish
runs, and the claim's result says so, naming the binding: in the
record's note, in `check` output and in the MCP result. Purity is
established for math, cmath, statistics and numpy's numeric functions;
numpy's random generators are not pure."""
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


_WORDS = "calls third-party code whose purity mathema cannot establish"


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
