# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Implementation coverage: which of a function's own lines are backed by
evidence.

A line counts as covered when it is exercised by ANY of three sources,
unioned:

- **test**: an external test run executed it, read from an existing
  `.coverage`/`coverage.json` report (`inventory.read_test_coverage`);
- **probe**: a mathema probe/examine trial executed it, captured by
  tracing `check(fn)` (its sampling calls the function across branches);
- **derive**: a derive-route proof modeled it: a symbolic proof never
  runs the code, so tracing cannot see it, but a body the lift closed is
  established more strongly than execution. v1 counts a function's whole
  body as derive-covered when any claim on it proved on the derive route;
  a per-branch refinement is future work.

A STALE external test report does NOT count toward the score: its lines
may not even map to the current code. A report stamped with its sources'
content hashes (`inventory.stamp_coverage_sources`) is stale for a file
exactly when that file's content changed since measurement; an unstamped
one falls back to file times (the source modified after the report). Those
lines are surfaced as RECLAIMABLE instead, so a re-run of the tests folds
them back in. The probe and derive sources are recomputed on every pass,
so they are always current and carry the score.

This is the data behind the implementation badge. It is a SEPARATE pass
(`mathema coverage`), never part of the fast `check` loop, and needs NO
third-party dependency: the probe source traces with the standard
library (`sys.settrace`) and the denominator comes from the `ast`
module. coverage.py is only involved in reading a native `.coverage`
external report (the TEST source's native format; a `coverage.json`
export needs nothing), exactly as `inventory.read_test_coverage` already
handled before this pass existed.
"""
from __future__ import annotations

import ast
import inspect
import os
import sys
from dataclasses import dataclass, field

from .inventory import (ReportFreshness, coverage_freshness,
                        read_test_coverage, stamp_coverage_sources)


@dataclass
class FunctionCoverage:
    """One function's implementation coverage: its executable statement
    lines (the denominator), the covered subset, and which source(s)
    covered each. `percent` is 0-100; `traced` is False when the probe
    source could not run (no `coverage` extra), so a reader knows the
    number omits probe evidence rather than treating its absence as
    uncovered."""
    key: str
    statements: set = field(default_factory=set)
    covered: set = field(default_factory=set)
    by_source: dict = field(default_factory=dict)   # "test"/"probe"/"derive" -> lines
    traced: bool = True
    test_stale: bool = False   # the source changed since the external report
                               # measured it, so its "test" lines are unreliable
    reclaimable: set = field(default_factory=set)   # stale-test lines the
                               # score excludes, re-runnable back into it
    derivable: "bool | None" = None   # the lift can model the body, so a
                               # claim would derive-cover it (None = unknown)
    freshness: "str | None" = None   # how test_stale was judged: "hash"
                               # (a stamped report), "mtime", or None (no report)

    @property
    def uncovered(self) -> set:
        return self.statements - self.covered

    @property
    def percent(self) -> int:
        """The trustworthy score: fresh evidence only (a stale test
        report is excluded, see `reclaimable`)."""
        if not self.statements:
            return 100
        return round(100 * len(self.covered & self.statements) / len(self.statements))

    @property
    def potential_percent(self) -> int:
        """The score a re-run of the tests could reach, folding the
        reclaimable stale-test lines back in."""
        if not self.statements:
            return 100
        reachable = (self.covered | self.reclaimable) & self.statements
        return round(100 * len(reachable) / len(self.statements))


def _line_range(fn) -> tuple[str, int, int] | None:
    """`(abspath, first_line, last_line)` of fn's source, or None when
    the source is unavailable (a builtin, a C extension, exec'd code)."""
    try:
        src_file = inspect.getsourcefile(fn)
        lines, start = inspect.getsourcelines(fn)
    except (TypeError, OSError):
        return None
    if src_file is None:
        return None
    return os.path.abspath(src_file), start, start + len(lines) - 1


def _external_lines(fn, coverage_data: dict | None) -> set:
    """The function's own lines an external test run executed, from a
    coverage report; empty when there is no report or the file is absent
    (an absent file is 'unknown', but for a per-line union it contributes
    nothing, and `traced`/the report's presence is surfaced elsewhere)."""
    rng = _line_range(fn)
    if rng is None or not coverage_data:
        return set()
    path, start, end = rng
    executed = coverage_data.get(path)
    if executed is None:
        return set()
    return {ln for ln in executed if start <= ln <= end}


def _trace_check(fn):
    """Run `check(fn)` under a standard-library `sys.settrace` line
    tracer and return `(statements, executed, record)` in fn's own line
    range: its executable statements (the denominator, from the AST), the
    lines the probing actually ran, and the check record (for the derive
    source). No third-party tracer is needed. Returns `(None, None,
    None)` only when the source cannot be located (a builtin/C
    function)."""
    rng = _line_range(fn)
    if rng is None:
        return None, None, None
    path, start, end = rng
    executed: set = set()

    def _local(frame, event, arg):
        if event == "line":
            ln = frame.f_lineno
            if start <= ln <= end:
                executed.add(ln)
        return _local

    def _global(frame, event, arg):
        # descend only into the target file's frames; mathema's own
        # machinery is left untraced, so the per-line overhead is scoped
        # to the function under measurement.
        return _local if frame.f_code.co_filename == path else None

    from . import check

    previous = sys.gettrace()
    sys.settrace(_global)
    record = None
    try:
        record = check(fn)
    except Exception:
        record = None
    finally:
        sys.settrace(previous)
    statements = _statement_lines(fn)
    return statements, executed & statements, record


def _plain_check(fn):
    """Run `check(fn)` WITHOUT tracing, for its record only. Used in the
    no-`coverage`-extra fallback so the derive source (read off the
    record) still works even though the probe source, which needs the
    line tracer, does not."""
    try:
        from . import check
        return check(fn)
    except Exception:
        return None


def _derive_covered_lines(record, statements: set) -> set:
    """Lines the derive route established on this function: a proof's own
    per-branch attribution (`mathema.derive_lines`, set by the prover for
    a domain-restricted proof) when it recorded one, else the whole body
    for a proven claim (a straight-line proof reasons about all of it).
    A proof never executes the code, so this is added on top of the
    traced probe/test lines."""
    covered: set = set()
    if record is None:
        return covered
    for p in getattr(record, "probes", []) or []:
        route = getattr(p, "route", None) or ""
        if (route.split(":", 1)[0] != "derive"
                or getattr(p, "verdict", None) != "proven"):
            continue
        lines = (getattr(p, "meta", None) or {}).get("mathema.derive_lines")
        covered |= set(lines) if lines is not None else set(statements)
    return covered & statements


def function_coverage(fn, key: str | None = None, root: str = ".",
                      coverage_data: dict | None = None,
                      report_mtime: float | None = None,
                      freshness: ReportFreshness | None = None
                      ) -> FunctionCoverage:
    """The merged implementation coverage of one function: test-executed
    ∪ probe-executed ∪ derive-modeled lines, over its executable
    statements. `coverage_data` (an already-read external report) is
    reused when given, else read once from `root`. `freshness` decides
    whether the report's lines for this function's file still describe
    its code (`inventory.coverage_freshness`, by content hash when the
    report is stamped, else by file time); read from `root` when not
    given, and `report_mtime` alone forces the file-time check."""
    from .authoring import _fn_key

    key = key or _fn_key(fn)
    if coverage_data is None:
        coverage_data = read_test_coverage(root)
    if freshness is None:
        freshness = (ReportFreshness(method="mtime", report_mtime=report_mtime)
                     if report_mtime is not None else coverage_freshness(root))

    statements, probe_executed, record = _trace_check(fn)
    traced = statements is not None
    if statements is None:
        # no coverage extra (or no traceable source): the PROBE source
        # needs the line tracer, so it drops out (and the row is marked
        # untraced). The DERIVE source only needs the record, so still
        # run check(fn) plain to get it, and fall back to a static
        # statement-line denominator.
        statements = _statement_lines(fn)
        probe_executed = set()
        record = _plain_check(fn)

    test_stale = False
    rng = _line_range(fn)
    if rng is not None and os.path.exists(rng[0]):
        test_stale = freshness.is_stale(rng[0])

    by_source: dict = {}
    if probe_executed and not _is_mathema_own(fn):
        by_source["probe"] = probe_executed & statements
    derive_lines = _derive_covered_lines(record, statements)
    if derive_lines:
        by_source["derive"] = derive_lines
    test_lines = _external_lines(fn, coverage_data) & statements
    # a stale external report does NOT count toward the score: its lines
    # may not even map to the current source. A fresh one does.
    if test_lines and not test_stale:
        by_source["test"] = test_lines

    covered: set = set()
    for lines in by_source.values():
        covered |= lines
    covered &= statements

    # the stale-test lines nothing fresh already covers are RECLAIMABLE:
    # re-running the tests would fold them back into the score.
    reclaimable = (test_lines - covered) if test_stale else set()

    try:
        from .inventory import is_pure_enough
        derivable = is_pure_enough(fn)
    except Exception:
        derivable = None

    return FunctionCoverage(key=key, statements=set(statements),
                            covered=covered, by_source=by_source,
                            traced=traced, test_stale=test_stale,
                            reclaimable=reclaimable, derivable=derivable,
                            freshness=freshness.method)


def _is_mathema_own(fn) -> bool:
    """Whether `fn` is defined inside the mathema package itself. Checking
    such a function runs mathema's own machinery, which may call the same
    function while parsing or adjudicating the claim, so its traced lines
    cannot be told apart from probe execution and earn no probe credit.
    Derive and test lines are unaffected."""
    try:
        path = os.path.abspath(inspect.getsourcefile(fn) or "")
    except TypeError:
        return False
    package = os.path.dirname(os.path.abspath(__file__))
    return path.startswith(package + os.sep)


def _statement_lines(fn) -> set:
    """The executable statement lines of fn's BODY, from its AST: every
    statement's own line (recursively), the `def`/signature and a leading
    docstring excluded, mapped to absolute file lines. The denominator
    the probe/derive/test sources are scored against, computed with no
    third-party dependency."""
    import textwrap

    rng = _line_range(fn)
    if rng is None:
        return set()
    _, start, _ = rng
    try:
        source = textwrap.dedent("".join(inspect.getsourcelines(fn)[0]))
        tree = ast.parse(source)
    except (OSError, TypeError, SyntaxError):
        return set()
    fdef = tree.body[0]
    body = list(getattr(fdef, "body", []))
    if (body and isinstance(body[0], ast.Expr)
            and isinstance(getattr(body[0], "value", None), ast.Constant)
            and isinstance(body[0].value.value, str)):
        body = body[1:]                       # drop the docstring
    rel: set = set()
    for stmt in body:
        for node in ast.walk(stmt):
            if isinstance(node, ast.stmt):
                rel.add(node.lineno)
    # ast line numbers are 1-based within the (dedented) source block,
    # whose first line is file line `start`.
    return {start - 1 + ln for ln in rel}


@dataclass
class ProjectCoverage:
    """Implementation coverage across a set of functions: the per-function
    rows and the line-weighted aggregate percentage."""
    functions: list = field(default_factory=list)   # list[FunctionCoverage]

    @property
    def percent(self) -> int:
        total = sum(len(f.statements) for f in self.functions)
        covered = sum(len(f.covered & f.statements) for f in self.functions)
        return round(100 * covered / total) if total else 100

    @property
    def potential_percent(self) -> int:
        """The aggregate a test re-run could reach (reclaimable folded in)."""
        total = sum(len(f.statements) for f in self.functions)
        reach = sum(len((f.covered | f.reclaimable) & f.statements)
                    for f in self.functions)
        return round(100 * reach / total) if total else 100


def regenerate_test_coverage(root: str, test_command: str | None = None) -> bool:
    """Run the project's tests UNDER coverage to produce a fresh report,
    the reclaim path: afterwards the test source is current and counts
    toward the score. Needs coverage.py installed (to run `coverage
    run`), so returns False when it is absent, when no test command is
    known, or when no fresh report results. The command defaults to
    `inventory.suggest_coverage_command` (a pytest project), else a
    plain `coverage run -m pytest` + `coverage json`.

    Success is a `coverage.json` newer than the run's start, not the
    command's exit status: a failing test still leaves the lines every
    other test executed. When the command leaves only a `.coverage` data
    file, it is exported to `coverage.json` here, and per-process
    `.coverage.<suffix>` files (a parallel-mode run, or subprocess
    measurement) are combined into it first."""
    import importlib.util
    import subprocess
    import time

    if importlib.util.find_spec("coverage") is None:
        return False
    cmd = test_command
    if cmd is None:
        from .inventory import suggest_coverage_command
        cmd = suggest_coverage_command(root)
        if cmd and cmd.startswith("pip install"):
            # coverage is present (checked above); drop any install prefix
            cmd = cmd.split("&&", 1)[-1].strip()
    if not cmd:
        cmd = "python -m coverage run -m pytest; python -m coverage json"
    json_path = os.path.join(root, "coverage.json")
    data_path = os.path.join(root, ".coverage")
    started = time.time()

    def _fresh(path: str) -> bool:
        return os.path.exists(path) and os.path.getmtime(path) >= started - 1

    def _coverage(*args: str) -> None:
        subprocess.run([sys.executable, "-m", "coverage", *args], cwd=root,
                       capture_output=True, text=True)

    try:
        subprocess.run(cmd, shell=True, cwd=root,
                       capture_output=True, text=True)
        parallel = [name for name in os.listdir(root)
                    if name.startswith(".coverage.")
                    and _fresh(os.path.join(root, name))]
        if parallel:
            # per-process data files (parallel mode, subprocess measurement)
            # merge into `.coverage`, keeping what the main process wrote
            _coverage("combine", "--append")
            _coverage("json", "-o", json_path)
        elif not _fresh(json_path) and _fresh(data_path):
            _coverage("json", "-o", json_path)
    except Exception:
        return False
    if not _fresh(json_path):
        return False
    stamp_coverage_sources(root)
    return True


def project_coverage(targets, root: str = ".", run_tests: bool = False,
                     test_command: str | None = None) -> ProjectCoverage:
    """Implementation coverage over the resolved `targets`, or rootwide
    (every function the declared/verified stores know) when `targets` is
    empty, the same discovery `verify`/`docsync` use. `run_tests` first
    re-runs the suite under coverage (`regenerate_test_coverage`) so the
    test source is fresh, the reclaim path. The external report is read
    once and shared."""
    from .targets import resolve

    if run_tests:
        regenerate_test_coverage(root, test_command)
    coverage_data = read_test_coverage(root)
    freshness = coverage_freshness(root)
    funcs: dict = {}
    if targets:
        for t in targets:
            funcs.update(resolve(t, root).functions)
    else:
        from .conjecture import _resolve_func_ref
        from .spec import load_declared, load_verified
        for key in sorted(set(load_declared(root)) | set(load_verified(root))):
            fn = _resolve_func_ref(key)
            if fn is not None:
                funcs[key] = fn
    rows = [function_coverage(fn, key=key, root=root,
                              coverage_data=coverage_data,
                              freshness=freshness)
            for key, fn in sorted(funcs.items())]
    return ProjectCoverage(functions=rows)


def _compact(lines) -> str:
    """A sorted line-number set as compact ranges: {4,5,6,9} -> '4-6, 9'."""
    out, ordered = [], sorted(lines)
    i = 0
    while i < len(ordered):
        j = i
        while j + 1 < len(ordered) and ordered[j + 1] == ordered[j] + 1:
            j += 1
        out.append(str(ordered[i]) if i == j
                   else f"{ordered[i]}-{ordered[j]}")
        i = j + 1
    return ", ".join(out)


def remedy(fc: FunctionCoverage) -> str:
    """The single most useful action to RAISE this function's score, or
    "" when it is already fully covered. A stale test report is the
    cheapest gain (re-run the tests); a derivable body with no proof is
    next (declare a claim); otherwise the uncovered lines need a claim or
    a test that exercises them."""
    if fc.percent >= 100 or not fc.statements:
        return ""
    reclaim = fc.potential_percent - fc.percent
    if reclaim > 0:
        return f"re-run tests: reclaims +{reclaim}% (stale coverage report)"
    if fc.derivable and "derive" not in fc.by_source:
        return "declare a claim: the derive route would prove and cover the body"
    return f"add a claim or test exercising line(s) {_compact(fc.uncovered)}"
