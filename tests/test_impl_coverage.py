# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Implementation coverage: a line is covered when a test, a mathema
probe, or a derive-route proof exercised/modeled it. The `mathema
coverage` pass merges the three, per function and repo-wide."""
import os
import textwrap

from mathema.impl_coverage import (FunctionCoverage, function_coverage,
                                   project_coverage)


def _load(tmp_path, body: str, name: str = "m"):
    import importlib.util

    p = tmp_path / f"{name}.py"
    p.write_text(textwrap.dedent(body))
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_percent_is_line_weighted():
    fc = FunctionCoverage(key="f", statements={1, 2, 3, 4},
                          covered={1, 2, 3})
    assert fc.percent == 75
    assert FunctionCoverage(key="g", statements=set()).percent == 100


def test_derivable_function_is_derive_covered(tmp_path):
    mod = _load(tmp_path, '''
        def clamp01(x: float) -> float:
            """Clamp to the unit interval."""
            if x < 0.0:
                return 0.0
            if x > 1.0:
                return 1.0
            return x
    ''')
    fc = function_coverage(mod.clamp01, root=str(tmp_path))
    assert fc.traced is True
    assert fc.statements                       # a non-empty denominator
    # probing runs the branches; a derive proof models the whole body
    assert "probe" in fc.by_source
    assert "derive" in fc.by_source
    assert fc.percent == 100


def test_external_test_coverage_is_a_source(tmp_path):
    mod = _load(tmp_path, '''
        def add(a: float, b: float) -> float:
            """Sum."""
            return a + b
    ''')
    # a coverage report that marks the function's own lines executed
    import inspect
    src = os.path.abspath(inspect.getsourcefile(mod.add))
    lines, start = inspect.getsourcelines(mod.add)
    report = {src: set(range(start, start + len(lines)))}
    fc = function_coverage(mod.add, root=str(tmp_path), coverage_data=report)
    assert "test" in fc.by_source
    assert fc.by_source["test"]                # the test source contributed lines


def test_project_coverage_aggregates(tmp_path):
    _load(tmp_path, '''
        def a(x: float) -> float:
            """Twice."""
            return 2.0 * x

        def b(x: float) -> float:
            """Thrice."""
            return 3.0 * x
    ''', name="proj")
    import sys
    sys.path.insert(0, str(tmp_path))
    try:
        pc = project_coverage(["proj"], root=str(tmp_path))
    finally:
        sys.path.remove(str(tmp_path))
    assert len(pc.functions) == 2
    assert 0 <= pc.percent <= 100


def test_untraceable_source_degrades_without_probe(tmp_path, monkeypatch):
    # when a function's source cannot be traced (a builtin/C function),
    # the pass still reports test/derive and marks the row untraced
    # rather than crashing.
    import mathema.impl_coverage as ic

    monkeypatch.setattr(ic, "_trace_check", lambda fn: (None, None, None))
    mod = _load(tmp_path, '''
        def add(a: float, b: float) -> float:
            """Sum."""
            return a + b
    ''', name="notrace")
    fc = ic.function_coverage(mod.add, root=str(tmp_path))
    assert fc.traced is False
    assert fc.statements                       # static denominator still found
    assert "probe" not in fc.by_source


def test_coverage_command_reports_and_exits_zero(tmp_path, capsys):
    (tmp_path / "cproj").mkdir()
    (tmp_path / "cproj" / "__init__.py").write_text("")
    (tmp_path / "cproj" / "mod.py").write_text(textwrap.dedent('''
        def clamp01(x: float) -> float:
            """Clamp to the unit interval."""
            if x < 0.0:
                return 0.0
            return x
    '''))
    import sys

    from mathema.cli import main
    sys.path.insert(0, str(tmp_path))
    try:
        rc = main(["coverage", "cproj.mod", "--root", str(tmp_path)])
    finally:
        sys.path.remove(str(tmp_path))
    out = capsys.readouterr().out
    assert rc == 0
    assert "cproj.mod.clamp01" in out
    assert "implementation coverage:" in out


def test_stale_test_is_excluded_but_reclaimable(tmp_path):
    import inspect
    import json
    import os
    import time

    from mathema.impl_coverage import remedy

    mod = _load(tmp_path, '''
        def route(n: int) -> int:
            if n == 999999:
                return -1
            if n <= 0:
                return 0
            return route(n - 1)
    ''')
    src = os.path.abspath(inspect.getsourcefile(mod.route))
    lines, start = inspect.getsourcelines(mod.route)
    # a report covering every line, made OLDER than the (touched) source
    (tmp_path / "coverage.json").write_text(json.dumps(
        {"files": {src: {"executed_lines": list(range(start, start + len(lines)))}}}))
    time.sleep(0.01)
    os.utime(src, None)

    fc = function_coverage(mod.route, root=str(tmp_path))
    assert fc.test_stale is True
    assert "test" not in fc.by_source                 # stale test not in the score
    assert fc.percent < 100                           # a real gap remains
    assert fc.potential_percent > fc.percent          # reclaimable by re-running
    assert fc.reclaimable                             # the reclaimable lines
    assert "re-run tests" in remedy(fc)


def test_run_tests_refreshes_and_reclaims_the_test_source(tmp_path):
    # `--run-tests` re-runs the suite under coverage to produce a FRESH
    # report; here a custom command stands in for the suite. After it,
    # the test source is current and counts toward the score.
    import os

    from mathema.impl_coverage import project_coverage

    root = os.path.realpath(str(tmp_path))    # sidestep the macOS /private symlink
    modp = os.path.join(root, "m.py")
    with open(modp, "w") as f:
        f.write(textwrap.dedent('''
            def route(n: int) -> int:
                if n == 999999:
                    return -1
                if n <= 0:
                    return 0
                return route(n - 1)
        '''))
    # a "test command" that writes a fresh coverage.json for m.py
    cmd = ("python -c \"import json,os;"
           "p=os.path.realpath('m.py');"
           "json.dump({'files':{p:{'executed_lines':[2,3,4,5,6,7]}}},"
           "open('coverage.json','w'))\"")
    import sys
    sys.path.insert(0, root)
    try:
        pc = project_coverage(["m"], root=root, run_tests=True,
                              test_command=cmd)
    finally:
        sys.path.remove(str(root))
    (fc,) = pc.functions
    assert fc.test_stale is False                 # the report is fresh now
    assert "test" in fc.by_source                 # and counts toward the score
    assert 3 in fc.by_source["test"]


def test_regenerate_reports_failure_without_coverage(monkeypatch):
    # regenerate needs coverage.py to run `coverage run`; report False
    # (not crash) when it is absent.
    import importlib

    import mathema.impl_coverage as ic
    monkeypatch.setattr(importlib.util, "find_spec",
                        lambda name: None if name == "coverage" else True)
    assert ic.regenerate_test_coverage(".") is False


def test_derive_coverage_uses_per_branch_attribution(tmp_path):
    # a domain-restricted proof records the lines it covers (excluding
    # the branch its domain prunes) in the probe meta; the coverage pass
    # counts those, not the whole body.
    import types

    from mathema.impl_coverage import _derive_covered_lines

    # a proven derive probe carrying per-branch lines {2, 3, 5}
    probe = types.SimpleNamespace(route="derive", verdict="proven",
                                  meta={"mathema.derive_lines": [2, 3, 5]})
    record = types.SimpleNamespace(probes=[probe])
    got = _derive_covered_lines(record, statements={2, 3, 4, 5})
    assert got == {2, 3, 5}            # line 4 (pruned branch) not covered

    # a proven probe WITHOUT per-branch lines counts the whole body
    plain = types.SimpleNamespace(route="derive", verdict="proven", meta={})
    whole = _derive_covered_lines(types.SimpleNamespace(probes=[plain]),
                                  statements={2, 3, 4, 5})
    assert whole == {2, 3, 4, 5}
