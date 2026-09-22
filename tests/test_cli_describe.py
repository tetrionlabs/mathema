# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`mathema describe`: list every function key found under a target,
with its own signature. Real subprocess per invocation, same reasoning
as test_cli_audit_init.py's own docstring, inspect.getsource()
resolves against currently-loaded module state, so mutating fixture
files and reimporting in-process is unrepresentative of real usage.
"""
import subprocess
import sys


def _repo_root():
    import os
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _env_with_repo_on_path(pkg_root):
    import os
    env = dict(os.environ)
    parts = [_repo_root(), str(pkg_root)]
    if env.get("PYTHONPATH"):
        parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(parts)
    return env


def _write_pkg(tmp_path, body):
    pkg = tmp_path / "trialpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(body)
    return tmp_path


def _run(root, *args):
    script = ("import sys; from mathema.cli import main; "
             f"sys.exit(main({list(args)!r} + ['--root', {str(root)!r}]))")
    return subprocess.run([sys.executable, "-c", script], cwd=str(root),
                          capture_output=True, text=True,
                          env=_env_with_repo_on_path(root))


_BODY = '''
def typed_fn(a: float, b: float) -> float:
    return a + b


def untyped_seq_fn(signal, k=3):
    total = 0.0
    for x in signal:
        total += x
    return total / len(signal)


def _private_helper(x):
    return x * 2


class Widget:
    def method(self, x: int) -> int:
        return x + 1

    def __repr__(self):
        return "Widget()"
'''


def test_describe_lists_every_key_with_its_signature(tmp_path):
    root = _write_pkg(tmp_path, _BODY)
    r = _run(root, "describe", "trialpkg")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "trialpkg.mod.typed_fn(a: float, b: float) -> float" in r.stdout
    assert "trialpkg.mod._private_helper(x)" in r.stdout
    assert "trialpkg.mod.Widget.method(self, x: int) -> int" in r.stdout
    # dunders are excluded, same convention discover() already documents
    assert "__repr__" not in r.stdout
    assert "4 functions found" in r.stdout


def test_describe_infers_sequence_kind_for_an_untyped_parameter(tmp_path):
    root = _write_pkg(tmp_path, _BODY)
    r = _run(root, "describe", "trialpkg")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "signal: sequence (inferred)" in r.stdout
    # the default value is still rendered even for an enriched parameter
    assert "k = 3" in r.stdout


def test_describe_module_qualname_scopes_to_a_single_function(tmp_path):
    # a colon target whose bare name is unique now resolves to the
    # single-function *detail* view (mathema describe <key>, see
    # test_cli_describe_detail.py), not the old list-mode line; this
    # is the deliberate behavior change that feature adds.
    root = _write_pkg(tmp_path, _BODY)
    r = _run(root, "describe", "trialpkg.mod:typed_fn")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "trialpkg.mod.typed_fn(a: float, b: float) -> float" in r.stdout
    assert "untyped_seq_fn" not in r.stdout
    assert "form_hash:" in r.stdout


_GLOBAL_BODY = '''
SCALE = 2.0


def uses_global(x: float) -> float:
    return x * SCALE
'''


def test_describe_suppresses_the_global_scope_warning(tmp_path):
    # analyze_source() warns on global-scope capture (real, useful
    # signal on a single function), a sweep over every function in a
    # package must suppress it, same as every population-sweep function
    # in inventory.py already does around its own analyze_source() call,
    # or the listing gets drowned out by one UserWarning per affected
    # function.
    root = _write_pkg(tmp_path, _GLOBAL_BODY)
    r = _run(root, "describe", "trialpkg")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "trialpkg.mod.uses_global(x: float) -> float" in r.stdout
    assert "UserWarning" not in r.stderr
    assert "inherits from global scope" not in r.stderr


def test_describe_reports_no_functions_found_cleanly(tmp_path):
    pkg = tmp_path / "emptypkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    r = _run(tmp_path, "describe", "emptypkg")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "no functions found under emptypkg" in r.stdout
