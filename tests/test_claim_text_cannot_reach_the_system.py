# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim's text names functions by dotted path (`let g = numpy.mean`)
and by bare call name, and mathema refuses every name that reaches the
system: a module on the denylist (os, subprocess, builtins and the
like), a function that evaluates text as code, and anything reached
through an allowed module's attribute. The refusal comes at parse with
the module named, and nothing runs, whether the claim arrives in
Python, a claims file, a library's compendium file or over MCP. A
legitimate binding keeps working."""
import os
import subprocess
import sys
import textwrap

import pytest

import mathema
from mathema.conjecture import InvalidConjecture, claim


def _f(x: float) -> float:
    return x


_DENIED = [
    ("os.system", "os"),
    ("os.path.join", "os"),
    ("sys.exit", "sys"),
    ("subprocess.run", "subprocess"),
    ("builtins.exec", "builtins"),
    ("builtins.eval", "builtins"),
    ("builtins.open", "builtins"),
    ("shutil.rmtree", "shutil"),
    ("socket.socket", "socket"),
    ("importlib.import_module", "importlib"),
    ("pathlib.Path", "pathlib"),
    ("io.open", "io"),
    ("ctypes.CDLL", "ctypes"),
    ("multiprocessing.Process", "multiprocessing"),
    ("threading.Thread", "threading"),
    ("signal.signal", "signal"),
    ("pickle.loads", "pickle"),
    ("marshal.loads", "marshal"),
    ("runpy.run_path", "runpy"),
    ("code.interact", "code"),
    ("pty.spawn", "pty"),
    ("tempfile.mkdtemp", "tempfile"),
    ("glob.glob", "glob"),
    ("webbrowser.open", "webbrowser"),
    ("urllib.request.urlopen", "urllib"),
    ("http.client.HTTPConnection", "http"),
    ("ftplib.FTP", "ftplib"),
    ("smtplib.SMTP", "smtplib"),
    ("asyncio.run", "asyncio"),
]


@pytest.mark.parametrize("path,module", _DENIED)
def test_a_let_binding_to_a_system_module_is_refused_at_parse(path, module):
    with pytest.raises(InvalidConjecture) as caught:
        claim(f"let g = {path}, g(1) == 0")
    said = str(caught.value)
    assert repr(module) in said or f"`{module}`" in said, said
    assert path in said, said


@pytest.mark.parametrize("path", ["math.__builtins__.exec",
                                  "numpy.__builtins__.open"])
def test_a_dunder_on_the_path_is_refused_at_parse(path):
    with pytest.raises(InvalidConjecture, match="__builtins__"):
        claim(f"let g = {path}, g(1) == 0")


@pytest.mark.parametrize("path", ["sympy.sympify", "sympy.parse_expr",
                                  "sympy.lambdify", "sympy.simplify",
                                  "pandas.eval", "pydoc.locate",
                                  "operator.attrgetter",
                                  "operator.methodcaller", "numpy.load",
                                  "numpy.savetxt", "pandas.read_csv",
                                  "pandas.DataFrame.to_parquet",
                                  "polars.read_csv",
                                  "polars.DataFrame.write_csv"])
def test_a_function_that_runs_text_or_reflects_is_refused(path):
    with pytest.raises(InvalidConjecture, match="reaches the system"):
        claim(f"let g = {path}, g('1') == 1")


def test_the_reported_claims_run_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    texts = [
        "let g = os.system, g('touch PWNED3') == 0",
        "let g = os.system, f(x) == f(x) + 0*g('touch PWNED4')",
        "let g = builtins.exec, f(x) == f(x) + 0*g('open(\"PWNED5\",\"w\")')",
    ]
    for text in texts:
        with pytest.raises(InvalidConjecture):
            mathema.check(_f, claims=[text])
    assert not [p for p in os.listdir(tmp_path) if p.startswith("PWNED")]


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))


_REACH = '''
    import os as osmod
    from os import system
    from shutil import rmtree
    try:
        from pandas import read_csv
    except ImportError:
        read_csv = None

    exec_alias = exec


    def f(x: float) -> float:
        return x
'''


@pytest.fixture
def reach_module(tmp_path, monkeypatch):
    _write(tmp_path / "reachmod.py", _REACH)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.chdir(tmp_path)
    sys.modules.pop("reachmod", None)
    import reachmod
    yield reachmod
    sys.modules.pop("reachmod", None)


@pytest.mark.parametrize("path,module", [
    ("reachmod.system", "os"),
    ("reachmod.exec_alias", "builtins"),
    ("reachmod.rmtree", "shutil"),
    ("reachmod.osmod.system", "os"),
    ("reachmod.read_csv", "read_csv"),
    ("random._os.system", "os"),
])
def test_a_system_function_reached_through_an_allowed_module_is_refused(
        reach_module, tmp_path, path, module):
    if module == "read_csv":
        pytest.importorskip("pandas")
    stmt = (f"let g = {path}, f(x) == f(x) + 0*g('touch PWNED_REACH')")
    rec = mathema.check(reach_module.f, claims=[claim(stmt, name="c")])
    row = next(p for p in rec.probes if p.name == "c")
    assert row.verdict.startswith("skipped"), (row.verdict, row.note)
    assert "reaches the system" in (row.note or ""), row.note
    assert module in (row.note or ""), row.note
    assert not (tmp_path / "PWNED_REACH").exists()


def test_a_bare_call_name_bound_from_scope_to_a_system_function_runs_nothing(
        reach_module, tmp_path):
    os.makedirs(tmp_path / "victim")
    rec = mathema.check(reach_module.f, claims=[claim(
        "f(x) == f(x) + 0*rmtree('victim')", name="c")])
    row = next(p for p in rec.probes if p.name == "c")
    assert row.verdict.startswith("skipped"), (row.verdict, row.note)
    assert "reaches the system" in (row.note or ""), row.note
    assert (tmp_path / "victim").is_dir()


@pytest.mark.parametrize("stmt", [
    "let g = math.sqrt, for x in (0, 100], g(x) >= 0",
    "let g = numpy.mean, for x in [0, 1], f(x) == g(x)",
    "let g = numpy.linalg.norm, for x in [0, 1], g(x) >= 0",
    "let g = pandas.isna, for x in [0, 1], g(x) == 0",
])
def test_a_legitimate_binding_keeps_working(stmt):
    pytest.importorskip("numpy")
    pytest.importorskip("pandas")
    rec = mathema.check(_f, claims=[claim(stmt, name="c")])
    row = next(p for p in rec.probes if p.name == "c")
    assert row.verdict in ("proven", "holds"), (row.verdict, row.note)


def _cli(root, *args):
    env = dict(os.environ, PYTHONPATH=str(root))
    env.pop("VIRTUAL_ENV", None)
    script = ("import sys; from mathema.cli import main; "
              f"sys.exit(main({list(args)!r}))")
    return subprocess.run([sys.executable, "-c", script], cwd=str(root),
                          capture_output=True, text=True, env=env)


def test_a_claims_file_and_a_compendium_file_run_nothing(tmp_path):
    _write(tmp_path / "proj.py", '''
        import math


        def f(x: float) -> float:
            return math.sqrt(abs(x))
    ''')
    _write(tmp_path / "claims" / "proj.claims.yaml", """
        proj.f:
          claims:
            - name: pwn
              statement: "let g = os.system, g('touch PWNED_FILE') == 0"
    """)
    _write(tmp_path / "claims" / "math.claims.yaml", """
        compendium: math
        math.sqrt:
          claims:
            - name: pwn
              statement: "let g = builtins.exec, g('open(\\"PWNED_DEP\\", \\"w\\")') == 0"
    """)
    r = _cli(tmp_path, "verify", "--root", str(tmp_path))
    out = r.stdout + r.stderr
    assert not (tmp_path / "PWNED_FILE").exists(), out
    assert not (tmp_path / "PWNED_DEP").exists(), out
    assert "os" in out and "reaches the system" in out, out


def test_mcp_adjudicate_target_runs_nothing(tmp_path, monkeypatch):
    from mathema.interfaces.mcp import tools
    _write(tmp_path / "fx.py", '''
        def f(x: float) -> float:
            return x
    ''')
    monkeypatch.chdir(tmp_path)
    out = tools.adjudicate_target(
        "fx:f", claims=["let g = os.system, g('touch PWNED_MCP') == 0"],
        root=str(tmp_path))
    assert not (tmp_path / "PWNED_MCP").exists(), out
    assert out.get("passed") is not True, out
    assert "reaches the system" in str(out), out


def test_a_language_or_exception_named_inside_a_system_module_is_refused():
    from mathema.conjecture import _resolve_exception_type
    from mathema.languages import UnknownLanguage, resolve
    from mathema.domain import LanguageRef
    with pytest.raises(UnknownLanguage, match="reaches the system"):
        resolve(LanguageRef("os.path"))
    assert _resolve_exception_type("subprocess.CalledProcessError",
                                   _f) is None


@pytest.mark.parametrize("stmt", [
    "let g = operator.add, for x in [0, 1], g(x, x) == 2*x",
    "let g = operator.mul, for x in [0, 1], g(x, x) == x^2",
    "let g = operator.neg, for x in [0, 1], g(x) == -x",
    "let g = operator.truediv, for x in [1, 2], g(x, 2) == x/2",
    "let g = operator.abs, for x in [-1, 1], g(x) >= 0",
])
def test_a_plain_operator_function_keeps_working(stmt):
    rec = mathema.check(_f, claims=[claim(stmt, name="c")])
    row = next(p for p in rec.probes if p.name == "c")
    assert row.verdict in ("proven", "holds"), (row.verdict, row.note)


def test_itemgetter_on_its_own_is_allowed():
    assert claim("let g = operator.itemgetter, g(0)([1.0]) == 1").funcs


@pytest.mark.parametrize("path", ["operator.call", "_operator.attrgetter",
                                  "_operator.methodcaller", "_operator.call"])
def test_the_operator_callables_that_reach_code_are_refused(path):
    with pytest.raises(InvalidConjecture, match="reaches the system"):
        claim(f"let g = {path}, g(1) == 1")
