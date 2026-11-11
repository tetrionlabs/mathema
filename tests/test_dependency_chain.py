# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The dependency chain: what a function's claims rest on, transitively
through the functions it calls and the classes it reads. A change
anywhere along it re-adjudicates every function above the change; a
broken chain names its root, the deepest function that changed; a
function with no record reads as not checked; and a callee whose claim
regressed while its code did not change leaves its callers' chains
intact, the regression showing on the callee alone."""
import subprocess
import sys

import yaml

from mathema.inventory import dependency_reach


def _verify(root):
    script = ("import sys; from mathema.cli import main; "
              "sys.exit(main(['verify', '--root', '.', '--lenient']))")
    return subprocess.run([sys.executable, "-c", script], cwd=str(root),
                          capture_output=True, text=True)


_CHAIN = '''\
def leaf(x: float) -> float:
    return x + 1.0


def middle(x: float) -> float:
    return leaf(x) * 2.0


def top(x: float) -> float:
    return middle(x) - 1.0
'''


def _claims_for(root, *names):
    claims = root / "claims"
    claims.mkdir(exist_ok=True)
    for name in names:
        (claims / f"chain.{name}.claims.yaml").write_text(
            f"chain.{name}:\n  claims:\n"
            "    - name: grows\n"
            '      statement: "for x in [0, 100], f(x) >= x"\n'
            "      route: probe\n")


def _claims(root, key):
    doc = yaml.safe_load((root / ".mathema" / "verified" / f"{key}.yaml").read_text())
    return {c["name"]: c for c in doc[key]["claims"]}


def _settle(root, gate_passes=True):
    for _ in range(3):
        r = _verify(root)
        assert (r.returncode == 0) == gate_passes, r.stdout + r.stderr
    return r


def test_a_function_reaches_what_its_callees_call(tmp_path):
    import importlib.util
    (tmp_path / "chain_reach.py").write_text(_CHAIN)
    spec = importlib.util.spec_from_file_location("chain_reach", tmp_path / "chain_reach.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["chain_reach"] = mod
    try:
        spec.loader.exec_module(mod)
        assert [r["key"] for r in dependency_reach(mod.top)] == \
            ["chain_reach.leaf", "chain_reach.middle"]
    finally:
        sys.modules.pop("chain_reach", None)


def test_a_change_two_levels_down_re_adjudicates_the_top(tmp_path):
    (tmp_path / "chain.py").write_text(_CHAIN)
    _claims_for(tmp_path, "leaf", "middle", "top")
    _settle(tmp_path)
    assert _claims(tmp_path, "chain.top")["dependencies_current"]["verdict"] == "proven"

    (tmp_path / "chain.py").write_text(_CHAIN.replace("x + 1.0", "x + 3.0"))
    r = _verify(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    rerun = [line for line in r.stdout.splitlines() if "chain.top" in line]
    assert rerun and "dependency changed" in r.stdout, r.stdout


def test_a_broken_chain_names_the_deepest_function_that_changed(tmp_path):
    (tmp_path / "chain.py").write_text(_CHAIN)
    _claims_for(tmp_path, "middle", "top")
    _claims_for(tmp_path, "leaf")
    _settle(tmp_path)
    from mathema.spec import dependencies_current_probe
    from mathema.inventory import function_dependencies
    import importlib.util
    (tmp_path / "chain.py").write_text(_CHAIN.replace("x + 1.0", "x + 3.0")
                                       .replace("* 2.0", "* 4.0"))
    spec = importlib.util.spec_from_file_location("chain", tmp_path / "chain.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["chain"] = mod
    try:
        spec.loader.exec_module(mod)
        p = dependencies_current_probe(function_dependencies(mod.top), root=str(tmp_path))
    finally:
        sys.modules.pop("chain", None)
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert p.meta["mathema.chain_roots"] == ["chain.leaf"]
    assert "chain.leaf" in p.counterexample


def test_a_function_with_no_record_reads_as_not_checked(tmp_path):
    (tmp_path / "chain.py").write_text(_CHAIN)
    _claims_for(tmp_path, "middle", "top")
    r = _settle(tmp_path, gate_passes=False)
    assert "not checked, no record: chain.leaf" in r.stdout
    # a direct callee with no record leaves the rung open
    dc = _claims(tmp_path, "chain.middle")["dependencies_current"]
    assert dc["verdict"] == "unknown"
    assert "not checked, no record" in dc["note"] and "chain.leaf" in dc["note"]
    # reached only further down, it is listed and the verdict stands
    dc = _claims(tmp_path, "chain.top")["dependencies_current"]
    assert dc["verdict"] == "proven"
    assert dc["meta"]["mathema.chain_unrecorded"] == ["chain.leaf"]


def test_a_callee_regression_without_a_change_leaves_the_caller_chain_intact(tmp_path):
    import importlib.util

    import mathema
    from mathema.inventory import function_dependencies
    from mathema.records import Probe
    from mathema.spec import dependencies_current_probe, record

    (tmp_path / "chain_regress.py").write_text(_CHAIN)
    spec = importlib.util.spec_from_file_location("chain_regress", tmp_path / "chain_regress.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["chain_regress"] = mod
    try:
        spec.loader.exec_module(mod)
        root = str(tmp_path)
        for fn in (mod.leaf, mod.middle):
            facts = mathema.analyze(fn)
            key = f"chain_regress.{fn.__name__}"
            record(mathema.Record(facts=facts, probes=[
                Probe("nonneg", "f(x) >= 0", "proven", route="derive")],
                dependencies=function_dependencies(fn, facts)), key=key, root=root)
        facts = mathema.analyze(mod.middle)
        record(mathema.Record(facts=facts, probes=[
            Probe("nonneg", "f(x) >= 0", "unknown", route="derive")],
            dependencies=function_dependencies(mod.middle, facts)),
            key="chain_regress.middle", root=root)
        p = dependencies_current_probe(function_dependencies(mod.top), root=root)
    finally:
        sys.modules.pop("chain_regress", None)
    assert p.verdict == "proven", (p.verdict, p.note, p.counterexample)


def test_settling_rewrites_the_dependency_stamps_with_the_chain_verdict(tmp_path):
    # callers sort before their callees, so the first sweep adjudicates
    # each caller before the record it rests on exists
    source = (_CHAIN.replace("leaf", "c_leaf").replace("middle", "b_middle")
              .replace("def top", "def a_top"))
    (tmp_path / "chain.py").write_text(source)
    _claims_for(tmp_path, "c_leaf", "b_middle", "a_top")
    r = _verify(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    for key in ("chain.b_middle", "chain.a_top"):
        doc = yaml.safe_load((tmp_path / ".mathema" / "verified" / f"{key}.yaml").read_text())
        dc = {c["name"]: c for c in doc[key]["claims"]}["dependencies_current"]
        stamps = {d["key"]: d.get("freshness") for d in doc[key]["dependencies"]
                  if d.get("kind") == "function"}
        assert dc["verdict"] == "proven", (key, dc)
        assert set(stamps.values()) == {"current"}, (key, stamps)
