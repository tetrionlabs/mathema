# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""One-deep dependency records in the verified spec: every callee with
key, file, line, and form; freshness annotated at record time
(current / stale / invalidated / unverified), composing so a caller
never needs a deeper walk; an unchanged callee form means the
callee's own claims still stand."""
import importlib.util
import sys
import textwrap

import yaml

import pytest

import mathema
from mathema.inventory import function_dependencies


def _load_module(tmp_path, name, source):
    path = tmp_path / f"{name}.py"
    path.write_text(textwrap.dedent(source))
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    _LOADED_FIXTURE_MODULES.append(name)
    spec.loader.exec_module(mod)
    return mod


_LOADED_FIXTURE_MODULES: list = []


@pytest.fixture(autouse=True)
def _unload_fixture_modules():
    # fixture modules registered in sys.modules must not outlive their
    # test: inspect.getsource resolves against currently-loaded module
    # state, so a leaked name is cross-test contamination waiting to
    # collide
    yield
    while _LOADED_FIXTURE_MODULES:
        sys.modules.pop(_LOADED_FIXTURE_MODULES.pop(), None)


_SOURCE = '''\
import math


def helper(x: float) -> float:
    return x + 1.0


def caller(x: float) -> float:
    return helper(x) * math.pi
'''


def test_function_dependencies_carry_key_file_line_and_form(tmp_path):
    mod = _load_module(tmp_path, "deps_fixture", _SOURCE)
    deps = {d["name"]: d for d in function_dependencies(mod.caller)}
    # `math` is deliberately absent: analysis classifies math-module
    # references as their own group, not a callee dependency, stdlib
    # math is not a freshness concern.
    assert set(deps) == {"helper"}
    h = deps["helper"]
    assert h["kind"] == "function"
    assert h["key"] == "deps_fixture.helper"
    assert h["file"].endswith("deps_fixture.py")
    assert h["line"] == 4
    assert h["form"]   # a real hash, compared by the freshness check


def test_signature_callable_is_listed_without_a_form(tmp_path):
    mod = _load_module(tmp_path, "sig_dep_fixture", '''\
    from typing import Callable


    def apply_twice(f: Callable[[float], float], x: float) -> float:
        return f(f(x))
    ''')
    deps = function_dependencies(mod.apply_twice)
    sig_deps = [d for d in deps if d["kind"] == "signature-callable"]
    assert [d["name"] for d in sig_deps] == ["f"]
    assert "form" not in sig_deps[0]


def _record_claims_free(fn, key, root):
    facts = mathema.analyze(fn)
    rec = mathema.Record(facts=facts, probes=[],
                         dependencies=function_dependencies(fn, facts))
    from mathema.spec import record
    return record(rec, key=key, root=root)


def _read_deps(tmp_path, key):
    doc = yaml.safe_load((tmp_path / ".mathema" / "verified" / f"{key}.yaml").read_text())
    return {d["name"]: d for d in doc[key].get("dependencies") or []}


def test_freshness_unverified_then_current_then_stale(tmp_path):
    root = str(tmp_path)
    mod = _load_module(tmp_path, "fresh_fixture", _SOURCE)

    _record_claims_free(mod.caller, "fresh_fixture.caller", root)
    assert _read_deps(tmp_path, "fresh_fixture.caller")["helper"]["freshness"] == "unverified"

    _record_claims_free(mod.helper, "fresh_fixture.helper", root)
    _record_claims_free(mod.caller, "fresh_fixture.caller", root)
    assert _read_deps(tmp_path, "fresh_fixture.caller")["helper"]["freshness"] == "current"

    # the callee's body changes: its recorded form no longer matches the
    # live one, so the caller's next record marks the dependency stale.
    mod2 = _load_module(tmp_path, "fresh_fixture",
                        _SOURCE.replace("return x + 1.0", "return x + 2.0"))
    _record_claims_free(mod2.caller, "fresh_fixture.caller", root)
    assert _read_deps(tmp_path, "fresh_fixture.caller")["helper"]["freshness"] == "stale"


def test_freshness_propagates_a_callee_invalidation(tmp_path):
    from mathema.records import Probe
    from mathema.spec import record

    root = str(tmp_path)
    mod = _load_module(tmp_path, "invfresh_fixture", _SOURCE)

    # the callee regresses: proven once, then no longer establishable
    facts = mathema.analyze(mod.helper)
    record(mathema.Record(facts=facts, probes=[
        Probe("nonneg", "f(x) >= 0", "proven", route="derive")]),
        key="invfresh_fixture.helper", root=root)
    record(mathema.Record(facts=facts, probes=[
        Probe("nonneg", "f(x) >= 0", "unknown", route="derive")]),
        key="invfresh_fixture.helper", root=root)

    _record_claims_free(mod.caller, "invfresh_fixture.caller", root)
    assert _read_deps(tmp_path, "invfresh_fixture.caller")["helper"]["freshness"] == "invalidated"


def test_check_populates_dependencies_end_to_end(tmp_path):
    mod = _load_module(tmp_path, "e2e_dep_fixture", _SOURCE)
    rec = mathema.check(mod.caller, claims=[])
    names = {d["name"] for d in rec.dependencies}
    assert "helper" in names
    spec = rec.to_spec()
    assert {d["name"] for d in spec["dependencies"]} == names


# --- verify: the memoization rung and the staleness gate --------------------

def _run_verify(tmp_path):
    import subprocess
    script = ("import sys; from mathema.cli import main; "
             "sys.exit(main(['verify', '--root', '.', '--lenient']))")
    return subprocess.run([sys.executable, "-c", script], cwd=str(tmp_path),
                          capture_output=True, text=True)


def test_verify_writes_dependencies_current_and_reacts_to_callee_change(tmp_path):
    (tmp_path / "funcs.py").write_text(
        "def helper(x: float) -> float:\n"
        "    return x + 1.0\n\n\n"
        "def caller(x: float) -> float:\n"
        "    return helper(x) * 2.0\n")
    claims_dir = tmp_path / "claims"
    claims_dir.mkdir()
    (claims_dir / "funcs.caller.claims.yaml").write_text(
        "funcs.caller:\n  claims:\n"
        "    - name: grows\n"
        '      statement: "for x in [0, 100], f(x) >= x"\n'
        "      route: probe\n")
    (claims_dir / "funcs.helper.claims.yaml").write_text(
        "funcs.helper:\n  claims:\n"
        "    - name: increments\n"
        '      statement: "for x in [0, 100], f(x) >= x"\n'
        "      route: derive\n")

    r = _run_verify(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    caller_claims = _read_claims(tmp_path, "funcs.caller")
    dc = caller_claims["dependencies_current"]
    # first sweep order isn't guaranteed, so the callee's record may or
    # may not exist yet when the caller adjudicates, either honest
    # outcome is fine; a second sweep must settle it to proven.
    assert dc["verdict"] in ("proven", "unknown")
    r = _run_verify(tmp_path)
    # everything fresh now except what the dependency rung re-checks;
    # run once more so the caller re-records against the settled store.
    # After that the store is deterministic, so the rung MUST prove;
    # accepting "unknown" here would let the rung silently never settle
    if _read_claims(tmp_path, "funcs.caller")["dependencies_current"]["verdict"] != "proven":
        _run_verify(tmp_path)
    assert _read_claims(tmp_path, "funcs.caller")["dependencies_current"]["verdict"] \
        == "proven"

    # the callee changes; the caller's own body did not. verify must
    # still re-adjudicate the caller ("dependency changed"), and its
    # dependency record must show the drift was seen.
    (tmp_path / "funcs.py").write_text(
        "def helper(x: float) -> float:\n"
        "    return x + 2.0\n\n\n"
        "def caller(x: float) -> float:\n"
        "    return helper(x) * 2.0\n")
    r = _run_verify(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "dependency changed" in r.stdout


def _read_claims(tmp_path, key):
    doc = yaml.safe_load((tmp_path / ".mathema" / "verified" / f"{key}.yaml").read_text())
    return {c["name"]: c for c in doc[key]["claims"]}
