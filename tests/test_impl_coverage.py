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


def test_coverage_stamp_command_writes_the_sidecar(tmp_path, capsys):
    import json

    from mathema.cli import main
    (tmp_path / "m.py").write_text("def f(x):\n    return x + 1\n")
    (tmp_path / "coverage.json").write_text(json.dumps(
        {"files": {"m.py": {"executed_lines": [2]}}}))
    rc = main(["coverage", "--stamp", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert (tmp_path / "coverage.sources.json").exists()
    assert "coverage.sources.json" in out


def test_coverage_command_states_how_freshness_was_judged(tmp_path, capsys):
    import json
    import sys

    from mathema.cli import main
    (tmp_path / "cproj").mkdir()
    (tmp_path / "cproj" / "__init__.py").write_text("")
    (tmp_path / "cproj" / "mod.py").write_text(
        "def g(x: float) -> float:\n    return x\n")
    (tmp_path / "coverage.json").write_text(json.dumps(
        {"files": {"cproj/mod.py": {"executed_lines": [2]}}}))
    sys.path.insert(0, str(tmp_path))
    try:
        main(["coverage", "cproj.mod", "--root", str(tmp_path)])
        unstamped = capsys.readouterr().out
        main(["coverage", "--stamp", "--root", str(tmp_path)])
        capsys.readouterr()
        main(["coverage", "cproj.mod", "--root", str(tmp_path)])
        stamped = capsys.readouterr().out
    finally:
        sys.path.remove(str(tmp_path))
    assert "file modification time" in unstamped
    assert "content hash" in stamped


def test_stale_test_is_excluded_but_reclaimable(tmp_path):
    import inspect
    import json
    import os
    import time

    from mathema.impl_coverage import remedy

    # the first guard is a string comparison: no guard solution the
    # probe pins reaches it, so only a test covers that line
    mod = _load(tmp_path, '''
        def route(n: int) -> int:
            if str(n) == "999999":
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


def test_regenerate_keeps_the_report_when_a_test_fails(tmp_path):
    # a failing test still leaves executed-line data behind; the report is
    # exported from it and counts as regenerated, whatever the exit status.
    import sys

    import mathema.impl_coverage as ic
    (tmp_path / "m.py").write_text("def f(x):\n    return x + 1\n")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_m.py").write_text(
        "import sys, os\n"
        "sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))\n"
        "from m import f\n"
        "def test_passes():\n    assert f(1) == 2\n"
        "def test_fails():\n    assert f(1) == 3\n")
    cmd = (f"{sys.executable} -m coverage run -m pytest -q "
           "-p no:cacheprovider -p no:xdist tests")
    assert ic.regenerate_test_coverage(str(tmp_path), cmd) is True
    assert (tmp_path / "coverage.json").exists()


def test_regenerate_combines_parallel_data_files(tmp_path):
    # a parallel-mode run (one data file per process, as subprocess
    # measurement writes) leaves only `.coverage.<suffix>` files; they are
    # combined before the export, or every line they hold is lost.
    import json
    import sys

    import mathema.impl_coverage as ic
    (tmp_path / "m.py").write_text("def f(x):\n    return x + 1\n")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_m.py").write_text(
        "import sys, os\n"
        "sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))\n"
        "from m import f\n"
        "def test_passes():\n    assert f(1) == 2\n")
    cmd = (f"{sys.executable} -m coverage run --parallel-mode -m pytest -q "
           "-p no:cacheprovider -p no:xdist tests")
    assert ic.regenerate_test_coverage(str(tmp_path), cmd) is True
    report = json.loads((tmp_path / "coverage.json").read_text())
    assert any(name.endswith("m.py") for name in report["files"])


def _fully_reported(tmp_path):
    """A module whose one function the coverage report fully covers, and
    the absolute path of its source file."""
    import inspect
    import json

    mod = _load(tmp_path, '''
        def route(n: int) -> int:
            if n <= 0:
                return 0
            return n - 1
    ''')
    src = os.path.abspath(inspect.getsourcefile(mod.route))
    lines, start = inspect.getsourcelines(mod.route)
    (tmp_path / "coverage.json").write_text(json.dumps(
        {"files": {src: {"executed_lines":
                         list(range(start, start + len(lines)))}}}))
    return mod, src


def _age(path, seconds: float = 100.0) -> None:
    import time
    old = time.time() - seconds
    os.utime(path, (old, old))


def test_stamp_records_a_content_hash_per_measured_file(tmp_path):
    import hashlib
    import json

    from mathema.inventory import stamp_coverage_sources
    mod, src = _fully_reported(tmp_path)
    path = stamp_coverage_sources(str(tmp_path))
    data = json.loads(open(path).read())
    with open(src, "rb") as fh:
        expected = hashlib.sha256(fh.read()).hexdigest()
    assert data["files"][os.path.relpath(src, str(tmp_path))] == expected


def test_a_touched_but_unchanged_source_stays_fresh_under_a_stamp(tmp_path):
    # a checkout rewrites file times without changing content; the hash
    # sees the same code the report measured, so its lines still count
    from mathema.inventory import stamp_coverage_sources
    mod, src = _fully_reported(tmp_path)
    stamp_coverage_sources(str(tmp_path))
    _age(tmp_path / "coverage.json")
    fc = function_coverage(mod.route, root=str(tmp_path))
    assert fc.freshness == "hash"
    assert fc.test_stale is False
    assert "test" in fc.by_source


def test_an_edited_source_is_stale_under_a_stamp_whatever_its_time(tmp_path):
    from mathema.inventory import stamp_coverage_sources
    mod, src = _fully_reported(tmp_path)
    stamp_coverage_sources(str(tmp_path))
    with open(src, "a") as fh:
        fh.write("\n# edited\n")
    _age(src, 1000.0)                   # older than the report, yet changed
    fc = function_coverage(mod.route, root=str(tmp_path))
    assert fc.freshness == "hash"
    assert fc.test_stale is True
    assert "test" not in fc.by_source


def test_a_stamp_for_a_different_report_is_not_trusted(tmp_path):
    # the report was regenerated after the stamp: the stamp describes other
    # source, so freshness falls back to file times rather than trust it
    from mathema.inventory import stamp_coverage_sources
    mod, src = _fully_reported(tmp_path)
    stamp_coverage_sources(str(tmp_path))
    report = tmp_path / "coverage.json"
    report.write_text(report.read_text().replace("executed_lines",
                                                 "executed_lines", 1) + " ")
    fc = function_coverage(mod.route, root=str(tmp_path))
    assert fc.freshness == "mtime"


def test_without_a_stamp_freshness_is_judged_by_file_time(tmp_path):
    mod, src = _fully_reported(tmp_path)
    fc = function_coverage(mod.route, root=str(tmp_path))
    assert fc.freshness == "mtime"


def test_regenerate_stamps_the_measured_sources(tmp_path):
    import sys

    import mathema.impl_coverage as ic
    (tmp_path / "m.py").write_text("def f(x):\n    return x + 1\n")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_m.py").write_text(
        "import sys, os\n"
        "sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))\n"
        "from m import f\n"
        "def test_passes():\n    assert f(1) == 2\n")
    cmd = (f"{sys.executable} -m coverage run -m pytest -q "
           "-p no:cacheprovider -p no:xdist tests")
    assert ic.regenerate_test_coverage(str(tmp_path), cmd) is True
    assert (tmp_path / "coverage.sources.json").exists()


def test_mathema_own_functions_get_no_probe_credit():
    # checking one of mathema's own functions runs mathema's machinery,
    # which calls that same function while parsing the claim; those lines
    # are indistinguishable from probe execution, so they are not credited.
    from mathema.grammar import normalize
    fc = function_coverage(normalize, coverage_data={})
    assert "probe" not in fc.by_source


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
