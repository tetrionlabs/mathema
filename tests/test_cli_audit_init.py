# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`mathema audit` / `mathema init`: population-level views over a real,
importable package. Real subprocess per invocation, same reasoning as
test_cli_verify.py's own docstring, inspect.getsource() resolves
against currently-loaded module state, so mutating fixture files and
reimporting in-process is unrepresentative of real usage.
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


def _field(header_line, data_line, col_name):
    """audit's row format is groups joined by " || ", columns within a
    group joined by " | ", find `col_name` by header position
    regardless of which group it's currently in, so a test doesn't
    break every time columns get regrouped. Every cell is now padded
    for column-width alignment, so both the header lookup and the
    extracted value are stripped; padding is a display concern, not
    part of the actual field value a test should compare against."""
    header_groups = [g.split(" | ") for g in header_line.split(" || ")]
    group_idx = next(i for i, g in enumerate(header_groups)
                     if col_name in (c.strip() for c in g))
    col_idx = [c.strip() for c in header_groups[group_idx]].index(col_name)
    return data_line.split(" || ")[group_idx].split(" | ")[col_idx].strip()


_COUNTED_DOCS_BODY = '''
def partially_documented(a: float, b: float, c: float) -> float:
    """Does a thing.

    Args:
        a: first
        b: second

    Raises:
        ValueError: on bad a.
    """
    if a < 0:
        raise ValueError("bad a")
    if b < 0:
        raise TypeError("bad b")
    return a + b + c
'''


_BODY = '''
def pure_fn(x: float) -> float:
    return x * 2


def branchy_fn(x: float) -> float:
    if x < 0:
        return -x
    return x


def claimed_fn(x: float) -> float:
    """
    Claims:
        nonneg: f(x) >= 0
    """
    return x ** 2


SOME_GLOBAL = 1.0


def uses_a_global(x: float) -> float:
    return x + SOME_GLOBAL
'''


def test_audit_reports_claimed_pure_and_unclaimed(tmp_path):
    root = _write_pkg(tmp_path, _BODY)
    r = _run(root, "audit", "trialpkg", "--one-line")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "trialpkg.mod.pure_fn" in r.stdout
    assert "trialpkg.mod.branchy_fn" in r.stdout
    assert "trialpkg.mod.claimed_fn" in r.stdout
    assert "1/4 claimed" in r.stdout
    # two questions now, reported separately: what the derive route can
    # do given the declared domain, and what lifts with nothing supplied
    assert "/4 derivable" in r.stdout
    assert "3/4 lift unconditionally" in r.stdout
    assert "a probe claim can still be written" in r.stdout
    assert "no coverage.json" in r.stdout


def test_audit_docsync_is_on_by_default_and_excludable(tmp_path):
    # the old opt-in --mathema-docs flag is gone: docsync is an
    # ordinary analysis, in the grid by default, excludable like any
    root = _write_pkg(tmp_path, _BODY)
    r = _run(root, "audit", "trialpkg", "--one-line")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "docsync" in r.stdout.splitlines()[1]
    assert "mean docsync" in r.stdout and "%" in r.stdout
    r = _run(root, "audit", "trialpkg", "--exclude", "docsync")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "docsync" not in r.stdout.splitlines()[1]


def test_audit_docs_shows_a_grid_not_the_wide_table(tmp_path):
    root = _write_pkg(tmp_path, _BODY)
    r = _run(root, "audit", "trialpkg", "--docs")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "trialpkg.mod.pure_fn" in r.stdout
    assert r.stdout.splitlines()[0] == "quality:"
    header = r.stdout.splitlines()[1]
    assert "has_docstring" in header
    assert "has_summary" in header
    assert "params" in header
    assert "raises" in header
    assert "quality_ratio" in header
    # the wide table's own columns must not appear; this is a
    # different report, not the same table with extra rows
    assert "underivable_reason" not in r.stdout
    assert "|| claimed ||" not in r.stdout
    assert "mathema_docs" not in header
    assert "docstring quality criteria met" in r.stdout


def test_audit_docs_shows_two_separate_tables(tmp_path):
    root = _write_pkg(tmp_path, _BODY)
    r = _run(root, "audit", "trialpkg", "--docs")
    assert r.returncode == 0, r.stdout + r.stderr
    lines = r.stdout.splitlines()
    docs_header = lines[1]
    assert "quality_ratio" in docs_header
    # the sync table is NOT appended to the docs table's own header row;
    # it's a second, independent table further down, under its own label
    assert "intent" not in docs_header
    assert "\ndocsync:" in r.stdout
    sync_header = next(ln for ln in lines if "intent" in ln and "declared" in ln)
    assert "intent" in sync_header
    assert "declared" in sync_header
    assert "params_typed" in sync_header
    assert "sync_score" in sync_header
    assert "callees_typed" not in sync_header
    assert "docstring quality criteria met" in r.stdout
    assert "mean docsync" in r.stdout


def test_audit_docs_reports_per_param_and_per_exception_counts(tmp_path):
    root = _write_pkg(tmp_path, _COUNTED_DOCS_BODY)
    r = _run(root, "audit", "trialpkg", "--docs")
    assert r.returncode == 0, r.stdout + r.stderr
    header = r.stdout.splitlines()[1]
    line = next(ln for ln in r.stdout.splitlines() if "partially_documented" in ln)
    assert _field(header, line, "params") == "2/3"
    assert _field(header, line, "raises") == "1/2"


def test_audit_surfaces_global_deps_as_data_not_interleaved_warnings(tmp_path):
    # the actual arbital-trial feedback this fixes: analyze_source()
    # warns once per function with global-scope dependencies, which used
    # to print raw and unfiltered, drowning out the audit table on any
    # real package. Must now show up as a clean per-row annotation
    # instead, with zero raw UserWarning text on either stream.
    root = _write_pkg(tmp_path, _BODY)
    r = _run(root, "audit", "trialpkg", "--one-line")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "UserWarning" not in r.stdout
    assert "UserWarning" not in r.stderr
    assert "trialpkg.mod.uses_a_global" in r.stdout
    header = r.stdout.splitlines()[1]
    line = next(ln for ln in r.stdout.splitlines() if "uses_a_global" in ln)
    assert _field(header, line, "vars") == "SOME_GLOBAL"
    assert "1/4 depend on state outside their own parameters" in r.stdout


_SIBLING_CALL_BODY = '''
def helper(x: float) -> float:
    return x * 2


def calls_a_sibling(x: float) -> float:
    return helper(x)
'''


def test_audit_separates_sibling_function_refs_from_global_vars(tmp_path):
    root = _write_pkg(tmp_path, _SIBLING_CALL_BODY)
    r = _run(root, "audit", "trialpkg", "--one-line")
    assert r.returncode == 0, r.stdout + r.stderr
    header = r.stdout.splitlines()[1]
    line = next(ln for ln in r.stdout.splitlines() if "calls_a_sibling" in ln)
    assert _field(header, line, "vars") == "-"
    assert _field(header, line, "funcs") == "helper"
    # calling a sibling function alone is not a "depends on state" risk
    assert "depend on state outside their own parameters" not in r.stdout


def test_audit_module_qualname_scopes_to_a_single_function(tmp_path):
    root = _write_pkg(tmp_path, _BODY)
    r = _run(root, "audit", "trialpkg.mod:pure_fn", "--one-line")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "trialpkg.mod.pure_fn" in r.stdout
    assert "trialpkg.mod.branchy_fn" not in r.stdout
    assert "trialpkg.mod.claimed_fn" not in r.stdout
    assert "0/1 claimed" in r.stdout


_MANY_GLOBALS_BODY = '''
A = 1.0
B = 2.0
C = 3.0
D = 4.0
E = 5.0


def uses_many_globals(x: float) -> float:
    return x + A + B + C + D + E
'''


def test_audit_condenses_global_vars_over_the_limit(tmp_path):
    root = _write_pkg(tmp_path, _MANY_GLOBALS_BODY)
    r = _run(root, "audit", "trialpkg")
    assert r.returncode == 0, r.stdout + r.stderr
    header = r.stdout.splitlines()[1]
    line = next(ln for ln in r.stdout.splitlines() if "uses_many_globals" in ln)
    field = _field(header, line, "vars")
    assert field.count(",") == 3   # 3 shown names + a bare "+2"
    assert field.endswith("+2")
    # --one-line is the fully expanded table: every name, no +N
    r = _run(root, "audit", "trialpkg", "--one-line")
    header = r.stdout.splitlines()[1]
    line = next(ln for ln in r.stdout.splitlines() if "uses_many_globals" in ln)
    field = _field(header, line, "vars")
    assert "+2" not in field and field.count(",") == 4


def test_audit_suggests_coverage_command_when_pytest_detected(tmp_path):
    root = _write_pkg(tmp_path, _BODY)
    (root / "tests").mkdir()
    (root / "tests" / "test_mod.py").write_text("def test_nothing(): pass\n")
    r = _run(root, "audit", "trialpkg")
    assert r.returncode == 0, r.stdout + r.stderr
    # core command text only, whether a "pip install coverage &&" prefix
    # is added depends on whether coverage happens to be importable in
    # *this* environment, which the test shouldn't be sensitive to
    assert "python -m coverage run -m pytest" in r.stdout
    assert "python -m coverage json" in r.stdout


def test_audit_does_not_suggest_coverage_command_when_no_tests_dir(tmp_path):
    root = _write_pkg(tmp_path, _BODY)
    r = _run(root, "audit", "trialpkg")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "coverage run -m pytest" not in r.stdout


def test_init_writes_stubs_only_for_unclaimed_functions(tmp_path):
    root = _write_pkg(tmp_path, _BODY)
    r = _run(root, "init", "trialpkg")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "claims/trialpkg.mod.claims.yaml" in r.stdout

    stub_file = root / "claims" / "trialpkg.mod.claims.yaml"
    content = stub_file.read_text()
    assert "trialpkg.mod.pure_fn" in content
    assert "trialpkg.mod.branchy_fn" in content
    assert "trialpkg.mod.claimed_fn" not in content   # already claimed, skipped

    import yaml
    parsed = yaml.safe_load(content)
    assert parsed["trialpkg.mod.pure_fn"]["claims"] == []   # real empty list, not "[]"


def test_init_is_idempotent_and_preserves_hand_written_claims(tmp_path):
    root = _write_pkg(tmp_path, _BODY)
    r1 = _run(root, "init", "trialpkg")
    assert r1.returncode == 0, r1.stdout

    stub_file = root / "claims" / "trialpkg.mod.claims.yaml"
    stub_file.write_text(stub_file.read_text().replace(
        "trialpkg.mod.branchy_fn:\n  claims: []",
        'trialpkg.mod.branchy_fn:\n  claims:\n    - name: nonneg\n'
        '      statement: "f(x) >= 0"\n      route: probe'))

    r2 = _run(root, "init", "trialpkg")
    assert r2.returncode == 0, r2.stdout
    assert "nothing to do" in r2.stdout   # branchy_fn now claimed, pure_fn still stubbed... but
    # pure_fn was already stubbed from r1, so init has nothing new to add either way

    # the hand-written claim must have survived the second init run untouched
    content = stub_file.read_text()
    assert "nonneg" in content and 'statement: "f(x) >= 0"' in content


def test_audit_picks_up_existing_coverage_json(tmp_path):
    root = _write_pkg(tmp_path, _BODY)
    # a minimal, real coverage.json shape (coverage.py's own `coverage json`
    # export) covering only pure_fn's lines
    (root / "coverage.json").write_text(
        '{"files": {"trialpkg/mod.py": {"executed_lines": [2, 3]}}}')
    r = _run(root, "audit", "trialpkg", "--one-line")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "no coverage.json" not in r.stdout
    header = r.stdout.splitlines()[1]
    line = next(ln for ln in r.stdout.splitlines() if "trialpkg.mod.pure_fn" in ln)
    assert _field(header, line, "tested") == "yes"


_CLASS_BODY = '''
class Calculator:
    def __init__(self, offset: float):
        self.offset = offset

    def stateless_double(self, x: float) -> float:
        return x * 2

    def read_offset(self, x: float) -> float:
        return x + self.offset

    def stateful_bump(self, amount: float) -> None:
        self.offset = self.offset + amount

    @staticmethod
    def static_square(x: float) -> float:
        return x * x

    @classmethod
    def from_zero(cls):
        return cls(0.0)
'''


def test_audit_discovers_class_methods_static_and_stateless_and_stateful(tmp_path):
    root = _write_pkg(tmp_path, _CLASS_BODY)
    r = _run(root, "audit", "trialpkg", "--one-line")
    assert r.returncode == 0, r.stdout + r.stderr
    # __init__ (dunder) and from_zero (classmethod) must not appear at all
    assert "__init__" not in r.stdout
    assert "from_zero" not in r.stdout

    def line_for(key):
        return next(ln for ln in r.stdout.splitlines() if key in ln)

    # no yes/no column any more: an empty (dash) reason IS derivable,
    # and only an underivable function carries reason text
    header = r.stdout.splitlines()[1]
    assert _field(header, line_for("trialpkg.mod.Calculator.stateless_double"),
                  "reason") == "-"
    assert _field(header, line_for("trialpkg.mod.Calculator.static_square"),
                  "reason") == "-"
    # a read-only field method is derivable now; stateful means a
    # genuine write to instance state
    assert _field(header, line_for("trialpkg.mod.Calculator.read_offset"),
                  "reason") == "-"
    stateful_line = line_for("trialpkg.mod.Calculator.stateful_bump")
    assert "stateful" in _field(header, stateful_line, "reason")


_PRIVATE_HELPER_BODY = '''
def _core(x: float) -> float:
    return x * 2


def public_wrapper(x: float) -> float:
    return _core(x) + 1


class Widget:
    def __init__(self, x: float):
        self.x = x

    def _private_method(self, y: float) -> float:
        return y * 2
'''


def test_audit_discovers_single_underscore_helpers_not_just_dunders(tmp_path):
    # a "private by convention" module-level function or method is a
    # real, defined function, often the more claimable one (a public
    # function frequently just dispatches to a private numeric core).
    # Only dunders (__init__, ...) are excluded, not single-underscore
    # names.
    root = _write_pkg(tmp_path, _PRIVATE_HELPER_BODY)
    r = _run(root, "audit", "trialpkg", "--one-line")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "trialpkg.mod._core" in r.stdout
    assert "trialpkg.mod.Widget._private_method" in r.stdout
    # dunders still excluded
    assert "__init__" not in r.stdout


_WRAPPER_BODY = '''
import math


def real_sqrt_impl(x: float) -> float:
    return math.sqrt(x)


def wrapper_fn(x: float) -> float:
    """Just forwards to the real implementation."""
    return real_sqrt_impl(x)


def not_a_wrapper(x: float) -> float:
    return math.sqrt(x) + 1
'''


def test_audit_grid_has_no_wraps_column_diagnostic_report_carries_it(tmp_path):
    # wraps moved out of the grid into diagnostic_report, the grid
    # stays identity + analyses, and the wrapper fact travels with the
    # issue payload instead
    root = _write_pkg(tmp_path, _WRAPPER_BODY)
    r = _run(root, "audit", "trialpkg", "--one-line")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "wraps" not in r.stdout.splitlines()[1]


def test_audit_grid_lines_column_is_sed_style(tmp_path):
    root = _write_pkg(tmp_path, _WRAPPER_BODY)
    r = _run(root, "audit", "trialpkg", "--one-line")
    assert r.returncode == 0, r.stdout + r.stderr
    header = r.stdout.splitlines()[1]
    line = next(ln for ln in r.stdout.splitlines()
                if "trialpkg.mod.not_a_wrapper" in ln)
    import re
    assert re.fullmatch(r"\d+:\d+p", _field(header, line, "span"))


def test_audit_exclude_skips_column_and_updates_summary(tmp_path):
    root = _write_pkg(tmp_path, _BODY)
    r = _run(root, "audit", "trialpkg", "--exclude", "docs,scope")
    assert r.returncode == 0, r.stdout + r.stderr
    header = r.stdout.splitlines()[1]
    assert " docs " not in header          # the loose checklist column
    assert "docsync" in header             # its own analysis, still on
    assert "global_vars" not in r.stdout.splitlines()[0]
    assert "docstring best-practice" not in r.stdout


def test_audit_exclude_rejects_unknown_analysis_name(tmp_path):
    root = _write_pkg(tmp_path, _BODY)
    r = _run(root, "audit", "trialpkg", "--exclude", "bogus")
    assert r.returncode != 0
    assert "unknown --exclude" in r.stdout + r.stderr


def test_audit_rolls_up_by_module(tmp_path):
    pkg = tmp_path / "trialpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "geometry.py").write_text(
        "def area(r: float) -> float:\n    return 3.14159 * r * r\n")
    (pkg / "measures.py").write_text(
        "def pearson(x, y):\n    return 0.0\n")
    r = _run(tmp_path, "audit", "trialpkg")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "by module:" in r.stdout
    assert "trialpkg.geometry:" in r.stdout
    assert "trialpkg.measures:" in r.stdout
    # a single target given, no separate "by package" breakdown needed
    # when it would just duplicate the grand total
    assert "by package:" not in r.stdout


def test_audit_deriv_report_is_the_opt_in_detail(tmp_path):
    # the coded per-function detail moved behind --deriv-report (off
    # by default, the grid alone answers the population question)
    root = _write_pkg(tmp_path, _BODY)
    r = _run(root, "audit", "trialpkg")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "underivable functions:" not in r.stdout
    r = _run(root, "audit", "trialpkg", "--deriv-report")
    assert "underivable functions:" in r.stdout
    assert "trialpkg.mod.branchy_fn:" in r.stdout
    assert "branch:needs-domain(x)" in r.stdout
    assert "codes explained" in r.stdout
    # pure_fn/claimed_fn are derivable, no detail block for them
    section = r.stdout.split("underivable functions:", 1)[1]
    assert "trialpkg.mod.pure_fn:" not in section
    # the full module-state view rides the same report, with the file
    # line each name is used at
    r = _run(root, "audit", "trialpkg", "--deriv-report")
    assert "uses module state: SOME_GLOBAL (line" in r.stdout


def test_audit_blocked_column_carries_the_compact_code(tmp_path):
    root = _write_pkg(tmp_path, _BODY)
    r = _run(root, "audit", "trialpkg", "--one-line")
    header = r.stdout.splitlines()[1]
    line = next(ln for ln in r.stdout.splitlines()
                if "trialpkg.mod.branchy_fn " in ln)
    assert _field(header, line, "code") == "branch:needs-domain(x)"


_TERNARY_BODY = '''
def ternary_fn(flag: bool, x: float) -> float:
    y = 0.0 if flag else 1.0 / x
    return y
'''


def test_audit_deep_dive_names_the_category_for_an_unsupported_ternary_condition(tmp_path):
    # a ternary with a *comparison* condition now lifts (see
    # test_tuple_returns.py-adjacent symbolic tests); this exercises
    # the narrower remaining gap, a bare boolean-name condition, which
    # _cond_to_sympy still doesn't recognize.
    root = _write_pkg(tmp_path, _TERNARY_BODY)
    r = _run(root, "audit", "trialpkg")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "unsupported:ternary" in r.stdout


def test_audit_rolls_up_by_package_when_multiple_targets_given(tmp_path):
    pkg = tmp_path / "trialpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "geometry.py").write_text(
        "def area(r: float) -> float:\n    return 3.14159 * r * r\n")
    (pkg / "measures.py").write_text(
        "def pearson(x, y):\n    return 0.0\n")
    r = _run(tmp_path, "audit", "trialpkg.geometry", "trialpkg.measures")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "by package:" in r.stdout
    assert "trialpkg.geometry:" in r.stdout
    assert "trialpkg.measures:" in r.stdout


def test_audit_rejects_a_path_target_with_a_clear_message(tmp_path):
    root = _write_pkg(tmp_path, _BODY)
    r = _run(root, "audit", "./trialpkg")
    assert r.returncode == 2, r.stdout + r.stderr
    assert "filesystem path" in r.stderr
    assert "dotted name" in r.stderr
    # never a raw traceback
    assert "Traceback" not in r.stderr


def test_audit_unimportable_target_reports_cleanly_not_a_traceback(tmp_path):
    root = _write_pkg(tmp_path, _BODY)
    r = _run(root, "audit", "no_such_package_xyz")
    assert r.returncode == 2, r.stdout + r.stderr
    assert "could not import" in r.stderr
    assert "Traceback" not in r.stderr


def _write_pkg_with_broken_submodule(tmp_path, *, keep_good):
    pkg = tmp_path / "trialpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "broken.py").write_text(
        "import a_module_that_is_not_installed_xyz\n"
        "def useful(x: float) -> float:\n    return x + 1\n")
    if keep_good:
        (pkg / "good.py").write_text(
            "def square(x: float) -> float:\n    return x * x\n")
    return tmp_path


def test_audit_warns_which_submodule_it_skipped_on_partial_success(tmp_path):
    root = _write_pkg_with_broken_submodule(tmp_path, keep_good=True)
    r = _run(root, "audit", "trialpkg", "--one-line")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "trialpkg.good.square" in r.stdout          # the good one is found
    assert "skipped submodule trialpkg.broken" in r.stderr
    assert "a_module_that_is_not_installed_xyz" in r.stderr


def test_audit_empty_result_names_the_skipped_submodule_as_the_cause(tmp_path):
    root = _write_pkg_with_broken_submodule(tmp_path, keep_good=False)
    r = _run(root, "audit", "trialpkg")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "no functions found" in r.stdout
    assert "skipped submodule trialpkg.broken" in r.stderr
    assert "failed to import" in r.stdout


def test_audit_empty_clean_package_gives_actionable_hints(tmp_path):
    pkg = tmp_path / "trialpkg"
    pkg.mkdir()
    # a module that only re-exports: nothing is DEFINED here
    (pkg / "__init__.py").write_text("")
    (pkg / "facade.py").write_text("from trialpkg import facade as _f\n")
    r = _run(tmp_path, "audit", "trialpkg.facade")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "no functions found" in r.stdout
    assert "importable dotted name" in r.stdout
    assert "re-exported" in r.stdout


def test_audit_grid_group_title_row(tmp_path):
    # a title row above the columns names each group once, so the
    # columns underneath stay short (struct/code under derivable,
    # vars/funcs under globals)
    root = _write_pkg(tmp_path, _BODY)
    r = _run(root, "audit", "trialpkg")
    assert r.returncode == 0, r.stdout + r.stderr
    titles, header = r.stdout.splitlines()[0], r.stdout.splitlines()[1]
    for title in ("derive route", "typing", "globals", "docs"):
        assert title in titles
    # `derives` answers provability given the declared domain; `reason`/
    # `code` describe the unconditional lift, and the two disagree often
    for col in ("derives", "reason", "code", "finite_domain", "vars",
                "mutates", "funcs", "quality"):
        assert col in header
    for gone in ("structure", "blocked", "finite_domain_hint",
                 "global_vars", "struct", "concepts/tags"):
        assert gone not in header
    # a clean population drops the unresolved column in the tree
    # layout ( --one-line always keeps it)
    assert "unresolved" not in header


def test_audit_tested_outdated_when_source_newer_than_report(tmp_path):
    import os
    root = _write_pkg(tmp_path, _BODY)
    (root / "coverage.json").write_text(
        '{"files": {"trialpkg/mod.py": {"executed_lines": [2, 3]}}}')
    # the source changed AFTER the report: neither yes nor no is
    # trustworthy, so the cell says so instead of either
    stale = os.path.getmtime(root / "coverage.json") - 100
    os.utime(root / "coverage.json", (stale, stale))
    r = _run(root, "audit", "trialpkg", "--one-line")
    assert r.returncode == 0, r.stdout + r.stderr
    header = r.stdout.splitlines()[1]
    line = next(ln for ln in r.stdout.splitlines()
                if "trialpkg.mod.pure_fn" in ln)
    assert _field(header, line, "tested") == "outdated"
    assert "outdated, source changed after the coverage report" in r.stdout


def test_audit_index_prints_the_table_it_wrote(tmp_path):
    root = _write_pkg(tmp_path, _BODY)
    r = _run(root, "audit", "trialpkg", "--index")
    assert r.returncode == 0, r.stdout + r.stderr
    assert (root / ".mathema" / "index.yaml").exists()
    # overwriting a generated view is by design: nothing reads the
    # index back into the declared or verified layers
    assert "trialpkg.mod" in r.stdout
    assert "verified" in r.stdout
    line = next(ln for ln in r.stdout.splitlines()
                if "trialpkg.mod.pure_fn" in ln)
    assert "no" in line
    r2 = _run(root, "audit", "trialpkg", "--index")
    assert r2.returncode == 0, r2.stdout + r2.stderr


def test_audit_tree_layout_nests_module_class_function(tmp_path):
    # the default layout: one line for the module, one per enclosing
    # class, functions indented under their own scope, the key
    # column carries only the leaf name, so the dotted prefix's width
    # is paid once, not per row
    root = _write_pkg(tmp_path, _CLASS_BODY)
    r = _run(root, "audit", "trialpkg")
    assert r.returncode == 0, r.stdout + r.stderr
    lines = r.stdout.splitlines()
    assert "trialpkg.mod" in lines            # the module section line
    assert " .Calculator" in lines            # the class, one space in, dotted
    fn_line = next(ln for ln in lines if ln.startswith("  .stateless_double"))
    assert "||" in fn_line                    # a real grid row
    # the full dotted key never appears as a row
    assert not any(ln.startswith("trialpkg.mod.Calculator.stateless_double")
                   for ln in lines)


def test_claims_triplet_floor_flag_colors_red_and_amber():
    # the claim floor left the docsync score and became a flag on the
    # triplet cell: red under the floor, amber at or above it, and
    # deliberately never green; without a corpus nobody can say the
    # count is ENOUGH
    from mathema.cli import _ANSI_AMBER, _ANSI_GREEN, _ANSI_RED, _colorize_token
    red = _colorize_token("{4 | 0 | -}", "{4 | 0 | -}", True, col="claims")
    assert _ANSI_RED in red
    amber = _colorize_token("{2 | 3 | -}", "{2 | 3 | -}", True, col="claims")
    assert _ANSI_AMBER in amber and _ANSI_GREEN not in amber
    plain = _colorize_token("{- | 0 | -}", "{- | 0 | -}", True, col="claims")
    assert _ANSI_RED not in plain and _ANSI_AMBER not in plain
