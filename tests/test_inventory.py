# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Per-function classification primitives: purity, docstring quality,
derivability, scope dependencies, best-effort test-coverage piggybacking.
audit.py's own sweep functions (discover()/audit_rows()/write_stubs())
that these back are covered end to end (real subprocess, real installed
package) in test_cli_audit_init.py instead; this file sticks to the
parts that don't need dynamic module discovery."""
import json
import os
import warnings

import pytest

from mathema.inventory import (derivability_report, docstring_quality, is_pure_enough,
                               is_test_covered, mutated_globals,
                               read_test_coverage, scope_dependencies,
                               structural_complexity, suggest_coverage_command,
                               typing_info)


SOME_GLOBAL = 1.0


def pure_fn(x: float) -> float:
    return x * 2


def branchy_fn(x: float) -> float:
    if x < 0:
        return -x
    return x


def recursive_fn(n: int) -> int:
    if n <= 0:
        return 0
    return n + recursive_fn(n - 1)


def test_is_pure_enough_loop_free_branch_free():
    assert is_pure_enough(pure_fn) is True


def test_docstring_quality_requires_each_raised_exception_named():
    def partial_raises_doc(x: float) -> float:
        """Halves x.

        Raises:
            ValueError: if x is negative.
        """
        if x < 0:
            raise ValueError("x must be nonnegative")
        if x > 1e6:
            raise OverflowError("x too large")
        return x / 2

    q = docstring_quality(partial_raises_doc)
    assert q["raises_total"] == 2
    assert q["raises_documented"] == 1
    assert q["documents_raises"] is False

    def full_raises_doc(x: float) -> float:
        """Halves x.

        Raises:
            ValueError: if x is negative.
            OverflowError: if x is too large.
        """
        if x < 0:
            raise ValueError("x must be nonnegative")
        if x > 1e6:
            raise OverflowError("x too large")
        return x / 2

    q2 = docstring_quality(full_raises_doc)
    assert q2["raises_total"] == 2
    assert q2["raises_documented"] == 2
    assert q2["documents_raises"] is True


def test_docstring_quality_section_alone_is_not_enough():
    def section_only(x: float) -> float:
        """Halves x.

        Raises:
            Something goes wrong sometimes.
        """
        if x < 0:
            raise ValueError("x must be nonnegative")
        return x / 2

    q = docstring_quality(section_only)
    assert q["raises_total"] == 1
    assert q["raises_documented"] == 0
    assert q["documents_raises"] is False


def test_structural_complexity_counts_nested_loops():
    def flat(xs: list) -> float:
        t = 0.0
        for v in xs:
            t += v
        return t

    def nested_once(rows: list) -> float:
        t = 0.0
        for row in rows:
            for v in row:
                t += v
        return t

    def nested_twice(cube: list) -> float:
        t = 0.0
        for plane in cube:
            for row in plane:
                for v in row:
                    t += v
        return t

    flat_c = structural_complexity(flat)
    once_c = structural_complexity(nested_once)
    twice_c = structural_complexity(nested_twice)

    assert flat_c["loops"] == 1 and flat_c["nested_loops"] == 0
    assert once_c["loops"] == 2 and once_c["nested_loops"] == 1
    assert twice_c["loops"] == 3 and twice_c["nested_loops"] == 2

    # a loop nested two levels deep must cost more than one nested one
    # level deep, not the same flat amount each time
    assert once_c["cyclomatic"] > flat_c["cyclomatic"]
    assert twice_c["cyclomatic"] > once_c["cyclomatic"] + (
        once_c["cyclomatic"] - flat_c["cyclomatic"])


def test_is_pure_enough_false_for_branch():
    assert is_pure_enough(branchy_fn) is False


def test_is_pure_enough_true_for_numpy_qualified_and_float_cast():
    pytest.importorskip("numpy")
    import numpy as np

    def linfoot(mi: float) -> float:
        return float(np.sqrt(1.0 - np.exp(-2.0 * max(0.0, mi))))

    assert is_pure_enough(linfoot) is True


def test_is_pure_enough_does_not_print_the_underlying_scope_warning():
    # analyze_source() warns on global-scope capture on every call; a
    # population sweep over many functions must not let that leak
    # through as one interleaved warning per function
    def uses_a_global(x: float) -> float:
        return x + SOME_GLOBAL

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        is_pure_enough(uses_a_global)
    assert not caught


def test_scope_dependencies_reports_globals_as_data_not_a_warning():
    def uses_a_global(x: float) -> float:
        return x + SOME_GLOBAL

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        global_vars, global_funcs, unresolved = scope_dependencies(uses_a_global)
    assert not caught
    assert global_vars == ["SOME_GLOBAL"]
    assert global_funcs == []
    assert unresolved == []


def test_scope_dependencies_separates_sibling_function_refs_from_globals():
    # the actual point of the split: calling another module-level
    # function by name is ordinary code structure, not a hidden-state
    # dependency the way a global *variable* is; these are different
    # error surfaces and shouldn't be conflated under one signal.
    def calls_a_sibling(x: float) -> float:
        return pure_fn(x) + SOME_GLOBAL

    global_vars, global_funcs, unresolved = scope_dependencies(calls_a_sibling)
    assert global_vars == ["SOME_GLOBAL"]
    assert global_funcs == ["pure_fn"]
    assert unresolved == []


def test_global_capture_warning_names_only_the_variable_not_the_sibling_call():
    # scope_dependencies() always suppresses this warning (it's meant to
    # be a data accessor, not a warning-producer, see its own
    # docstring); analyze_source() is the real, unsuppressed path.
    from mathema.analysis import analyze_source

    def calls_a_sibling(x: float) -> float:
        return pure_fn(x) + SOME_GLOBAL

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        analyze_source(calls_a_sibling)
    assert len(caught) == 1
    assert "SOME_GLOBAL" in str(caught[0].message)
    assert "pure_fn" not in str(caught[0].message)


def test_scope_dependencies_sibling_function_alone_triggers_no_warning():
    def calls_only_a_sibling(x: float) -> float:
        return pure_fn(x)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        global_vars, global_funcs, unresolved = scope_dependencies(calls_only_a_sibling)
    assert not caught
    assert global_vars == []
    assert global_funcs == ["pure_fn"]


def test_scope_dependencies_ignores_names_used_only_in_type_annotations():
    # a real bug this fixes: analyze_source()'s global-capture scan used
    # to walk the *entire* FunctionDef, including parameter/return
    # annotations, a name referenced only in a Literal[...]/Annotated[...]
    # type hint (never executed as part of the function's actual logic)
    # was wrongly reported as a behavioral dependency on global scope.
    from typing import Literal

    def scaled(scale: Literal["info", "linear"], x: float) -> float:
        return x

    global_vars, global_funcs, unresolved = scope_dependencies(scaled)
    assert global_vars == []
    assert global_funcs == []
    assert unresolved == []


def test_scope_dependencies_binds_except_handler_name():
    # a real bug this fixes: except X as name binds `name` for the
    # duration of the block (Python deletes it implicitly afterward, but
    # it's genuinely bound *inside*), yet identity.local_names() never
    # tracked ast.ExceptHandler at all, any reference to a normal
    # exception variable inside its own except block was wrongly reported
    # as an unresolved free name.
    def reraises(x: float) -> float:
        try:
            return 1 / x
        except ZeroDivisionError as exc:
            raise ValueError("x must be nonzero") from exc

    global_vars, global_funcs, unresolved = scope_dependencies(reraises)
    assert global_vars == []
    assert global_funcs == []
    assert unresolved == []


def test_is_pure_enough_false_for_recursion():
    assert is_pure_enough(recursive_fn) is False


def test_read_test_coverage_none_when_no_report(tmp_path):
    assert read_test_coverage(str(tmp_path)) is None


def test_read_test_coverage_json_report(tmp_path):
    src_file = os.path.abspath(__file__)
    (tmp_path / "coverage.json").write_text(json.dumps(
        {"files": {src_file: {"executed_lines": [1, 2, 3]}}}))
    data = read_test_coverage(str(tmp_path))
    assert data is not None
    assert data[os.path.abspath(src_file)] == {1, 2, 3}


def test_read_test_coverage_native_dotcoverage(tmp_path):
    # the native `.coverage` path reads coverage.py's analysis2(), a
    # 5-tuple; executed lines are statements minus missing. A run
    # function's body is covered, an un-run function's body is not.
    # (A four-value unpack of analysis2() silently emptied this once.)
    pytest.importorskip("coverage")
    import importlib.util

    import coverage

    mod = tmp_path / "sample.py"
    mod.write_text("def ran(x):\n    return x + 1\n\n"
                   "def never(y):\n    return y - 1\n")
    # config_file=False: this run stands alone, whatever coverage settings
    # the surrounding project declares (parallel data files, subprocesses)
    cov = coverage.Coverage(data_file=str(tmp_path / ".coverage"),
                            source=[str(tmp_path)], config_file=False)
    cov.start()
    spec = importlib.util.spec_from_file_location("cov_sample", str(mod))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.ran(5)
    cov.stop()
    cov.save()

    data = read_test_coverage(str(tmp_path))
    assert data is not None and data != {}
    executed = data[os.path.realpath(str(mod))]
    assert 2 in executed       # ran()'s body ran
    assert 5 not in executed   # never()'s body did not


def test_is_test_covered_unknown_without_report():
    assert is_test_covered(pure_fn, None) is None


def test_is_test_covered_true_when_lines_executed(tmp_path):
    src_file = os.path.abspath(__file__)
    import inspect
    lines, start = inspect.getsourcelines(pure_fn)
    coverage_data = {os.path.abspath(src_file): set(range(start, start + len(lines)))}
    assert is_test_covered(pure_fn, coverage_data) is True


def test_is_test_covered_false_when_lines_not_executed():
    src_file = os.path.abspath(__file__)
    coverage_data = {os.path.abspath(src_file): {99999}}
    assert is_test_covered(pure_fn, coverage_data) is False


def test_suggest_coverage_command_none_when_nothing_pytest_shaped(tmp_path):
    assert suggest_coverage_command(str(tmp_path)) is None


def test_suggest_coverage_command_uses_module_invocation_not_bare_script(tmp_path):
    # the actual arbital-trial bug this fixes: a bare `coverage` console
    # script isn't guaranteed to be on PATH even when the package is
    # installed, "coverage: command not found". `python -m coverage`
    # only needs the package importable, not a linked script.
    (tmp_path / "tests").mkdir()
    cmd = suggest_coverage_command(str(tmp_path))
    assert cmd is not None
    assert "python -m coverage run -m pytest" in cmd
    assert "python -m coverage json" in cmd
    assert cmd.split()[0] != "coverage"   # never a bare, possibly-missing script


def test_suggest_coverage_command_prepends_install_when_coverage_not_importable(tmp_path, monkeypatch):
    (tmp_path / "tests").mkdir()
    import importlib.util
    monkeypatch.setattr(importlib.util, "find_spec",
                        lambda name: None if name == "coverage" else object())
    cmd = suggest_coverage_command(str(tmp_path))
    assert cmd.startswith("pip install coverage && ")


def test_suggest_coverage_command_no_install_prefix_when_already_importable(tmp_path, monkeypatch):
    (tmp_path / "tests").mkdir()
    import importlib.util
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: object())
    cmd = suggest_coverage_command(str(tmp_path))
    assert not cmd.startswith("pip install")


def test_suggest_coverage_command_exports_the_report_even_when_a_test_fails(tmp_path):
    # `coverage json` must not be chained on the test run's success: one
    # red test would otherwise leave no report at all, and the lines every
    # passing test executed would be lost.
    (tmp_path / "tests").mkdir()
    cmd = suggest_coverage_command(str(tmp_path))
    run_part, _, json_part = cmd.partition("python -m coverage run -m pytest")
    assert "python -m coverage json" in json_part
    assert "&&" not in json_part


def fully_typed_fn(x: float, y: int) -> float:
    return x + y


def untyped_fn(x, y):
    return x + y


def partially_typed_fn(x: float, y) -> float:
    return x + y


def test_typing_info_fully_typed():
    info = typing_info(fully_typed_fn)
    assert info == {"params_typed": 2, "params_total": 2,
                    "return_typed": True, "finite_domains": {}}


def test_typing_info_untyped():
    info = typing_info(untyped_fn)
    assert info == {"params_typed": 0, "params_total": 2,
                    "return_typed": False, "finite_domains": {}}


def test_typing_info_partial():
    info = typing_info(partially_typed_fn)
    assert info["params_typed"] == 1 and info["params_total"] == 2


def test_typing_info_literal_yields_finite_domain():
    from typing import Literal

    def scaled(scale: Literal["info", "linear"], x: float) -> float:
        return x

    assert typing_info(scaled)["finite_domains"] == {"scale": ["info", "linear"]}


def test_scope_dependencies_ignores_a_nested_functions_own_parameters():
    # a real bug this fixes: a helper defined *inside* the function being
    # analyzed has its own separate scope; its own parameters aren't
    # free variables of the outer function at all, but a flat AST walk
    # can't tell the difference. Found via arbital's real
    # measures.profile(), which has exactly this shape.
    def outer(x: float) -> float:
        def _helper(v, flag):
            return v if flag else -v

        return _helper(x, True)

    global_vars, global_funcs, unresolved = scope_dependencies(outer)
    assert unresolved == []
    assert global_vars == []
    assert global_funcs == []


def test_typing_info_enum_yields_finite_domain():
    import enum

    class Scale(enum.Enum):
        INFO = "info"
        LINEAR = "linear"

    def scaled(scale: Scale, x: float) -> float:
        return x

    assert typing_info(scaled)["finite_domains"] == {"scale": ["info", "linear"]}


# --- derivability_report(): real, confirmed fixtures for each
# blocker shape, not synthetic guesses, each one mirrors a real function
# this exact diagnosis was verified against in arbital.geometry/measures.

def test_derivability_report_liftable_function_says_so():
    assert derivability_report(pure_fn) == {"liftable": True}


def test_derivability_report_ternary_with_a_comparison_condition_now_lifts():
    # a ternary whose condition is a single comparison (or and/or/not of
    # comparisons) lifts to a sympy Piecewise directly; see
    # tests/test_symbolic.py's ternary-specific tests for the derive-
    # route proof behavior; this only confirms the audit-level status.
    def ternary_fn(x: float) -> float:
        y = 0.0 if x == 0.0 else 1.0 / x
        return y

    assert derivability_report(ternary_fn) == {"liftable": True}


def test_derivability_report_ternary_with_a_bare_name_condition_names_the_category():
    def ternary_fn(flag: bool, x: float) -> float:
        y = 0.0 if flag else 1.0 / x
        return y

    report = derivability_report(ternary_fn)
    assert report["liftable"] is False
    assert report["blocker"] == "unsupported-construct"
    assert report["category"] == "ternary"
    assert report["line"] == 2
    assert "0.0 if flag else" in report["statement"]


def test_derivability_report_unsupported_call_names_the_category():
    import math

    def calls_unmapped(x: float) -> float:
        return math.hypot(x, x)   # a real math function, just not whitelisted

    report = derivability_report(calls_unmapped)
    assert report["blocker"] == "unsupported-construct"
    assert report["category"] == "unsupported-call"


def test_derivability_report_unsupported_call_message_names_the_specific_culprit():
    import numpy as np

    def calls_unresolvable_wrapper(x: float) -> float:
        # np.minimum lifts fine on its own; undefined_helper doesn't
        # (it isn't defined anywhere, so callee inlining can't resolve
        # it either); the message must name undefined_helper as the
        # actual culprit, not just print the whole nested expression
        # and leave a reader to guess which part of it is the problem.
        return undefined_helper(np.minimum(x, 1.0))  # noqa: F821 (deliberately unresolved, see comment above)

    report = derivability_report(calls_unresolvable_wrapper)
    assert report["category"] == "unsupported-call"
    assert "undefined_helper(np.minimum(x, 1.0))" in report["message"]
    assert "unresolved: 'undefined_helper'" in report["message"]


def test_derivability_report_recognized_fold_loop_is_liftable():
    # a running sum is exactly the one loop shape lift_fold() recognizes
    # (external_init mode, AugAssign normalized the same as `=`); this
    # loop is genuinely liftable, not a mathema-limitation.
    def looped(xs) -> float:
        total = 0.0
        for x in xs:
            total += x
        return total

    report = derivability_report(looped)
    assert report == {"liftable": True}


def test_derivability_report_bare_range_fold_is_liftable():
    # compound interest, a genuine fold (coeff_acc = 1+r != 1), no
    # sequence parameter at all (lift_fold()'s no-sequence shape).
    def compound_balance(P: float, r: float, n: float) -> float:
        balance = P
        for _ in range(n):
            balance = balance * (1 + r)
        return balance

    report = derivability_report(compound_balance)
    assert report == {"liftable": True}


def test_derivability_report_bare_range_non_affine_update_is_a_mathema_limitation():
    def compound_balance(P: float, r: float, n: float) -> float:
        balance = P
        for i in range(n):
            balance = balance * i
        return balance

    report = derivability_report(compound_balance)
    assert report["liftable"] is False
    assert report["blocker"] == "loop"
    assert report["reason"] == "non-affine-update"
    assert report["line"] == 3


def test_derivability_report_non_fold_loop_names_the_reason():
    def builds_a_list(xs) -> list:
        out = []
        for x in xs:
            out.append(x * 2)
        return out

    report = derivability_report(builds_a_list)
    assert report["liftable"] is False
    assert report["blocker"] == "loop"
    assert "not-a-fold" in report["reason"]


def test_derivability_report_recursion_names_the_call_count():
    # branch-free recursion specifically, recursive_fn (module-level,
    # used by test_is_pure_enough_false_for_recursion) also has a branch,
    # which correctly takes priority over "recursion" in the gate order
    # (matches purity_reason()'s own precedence: recursive_fn reports
    # "1 branch", not "recursive")
    def unconditionally_recurses(n: int) -> int:
        return n + unconditionally_recurses(n - 1)

    report = derivability_report(unconditionally_recurses)
    assert report["blocker"] == "recursion"
    assert report["recursive_calls"] == 1
    assert report["line"] == 2   # facts.tree is parsed from the function's own
    # dedented source snippet, so line numbers are relative to it, not the file


def test_derivability_report_stateful_method_names_the_param():
    # stateful now means WRITES to (or escapes of) self; a read-only
    # field method derives instead
    class Calculator:
        def __init__(self, offset: float):
            self.offset = offset

        def bump(self, amount: float) -> None:
            self.offset = self.offset + amount

        def add_offset(self, x: float) -> float:
            return x + self.offset

    report = derivability_report(Calculator.bump)
    assert report["blocker"] == "stateful"
    assert report["param"] == "self"
    assert report["line"] == 1
    read_only = derivability_report(Calculator.add_offset)
    assert read_only["liftable"] is True


def test_derivability_report_no_parameters_names_the_blocker():
    def constant_fn() -> float:
        return 42.0

    report = derivability_report(constant_fn)
    assert report["blocker"] == "no-parameters"
    assert report["line"] == 1


def test_derivability_report_non_scalar_parameter_names_the_params():
    def takes_a_list(xs: list) -> float:
        return xs[0]

    report = derivability_report(takes_a_list)
    assert report["blocker"] == "non-scalar-parameters"
    assert report["params"] == ["xs"]
    assert report["line"] == 1


def test_derivability_report_branch_over_a_parameter_is_resolvable():
    # single-condition case, mirrors arbital.geometry.strength_to_distance
    def scaled(scale: str, x: float) -> float:
        if scale == "info":
            return x * 2
        return x

    report = derivability_report(scaled)
    assert report["blocker"] == "branch"
    assert len(report["branches"]) == 1
    b = report["branches"][0]
    assert b["kind"] == "resolvable"
    assert b["needs_domain_for"] == ["scale"]


def test_derivability_report_branch_over_an_affine_local_is_resolvable():
    # denom is affine in x, y (both unmodified parameters), so this is
    # resolvable (see symbolic._affine_locals), naming the *parameters*
    # a claim would need to declare a domain for, not the local itself
    # (a claim can't declare a domain for `denom` directly).
    def divides(x: float, y: float) -> float:
        denom = x + y
        if denom == 0.0:
            return 0.0
        return x / denom

    report = derivability_report(divides)
    assert report["blocker"] == "branch"
    b = report["branches"][0]
    assert b["kind"] == "resolvable"
    assert b["needs_domain_for"] == ["x", "y"]


def test_derivability_report_branch_over_a_non_affine_local_is_blocked():
    # x * y is not affine, corner-evaluation isn't a valid decision
    # procedure for it, so this must stay blocked, not be misreported as
    # resolvable just because the local traces back to unmodified params.
    def divides(x: float, y: float) -> float:
        denom = x * y
        if denom == 0.0:
            return 0.0
        return x / denom

    report = derivability_report(divides)
    b = report["branches"][0]
    assert b["kind"] == "blocked"
    assert "denom" in b["reason"]
    assert "isn't affine" in b["reason"]
    assert "Reparameterizing" in b["reason"]
    assert "essential" not in b["reason"]


def test_derivability_report_branch_over_a_transcendental_expression_names_the_domain_workaround():
    # cos(x) isn't even a polynomial in x (PolynomialError, not just a
    # high total_degree()), no reparameterization linearizes a
    # transcendental function, so the message must say so distinctly
    # from the bilinear/multilinear case above, and point at the real
    # workaround (restrict the domain to avoid the guard).
    import math

    def trig_guard(x: float) -> float:
        if math.cos(x) == 0:
            return 0.0
        return 1.0 / math.cos(x)

    report = derivability_report(trig_guard)
    b = report["branches"][0]
    assert b["kind"] == "blocked"
    assert "isn't affine" in b["reason"]
    assert "essential" in b["reason"]
    assert "interval evaluation settles the guard" in b["reason"]
    assert "reparameterizing" not in b["reason"]


def test_derivability_report_branch_over_an_inline_expression_is_resolvable():
    # the same computation as the affine-local test above (x + y), but
    # written directly in the condition rather than bound to a name
    # first, must resolve identically, not be misreported as blocked
    # purely because of where it was written (finding #7).
    def voltage_divider(vin: float, r1: float, r2: float) -> float:
        if r1 + r2 <= 0:
            raise ValueError("invalid resistances")
        return vin * r2 / (r1 + r2)

    report = derivability_report(voltage_divider)
    assert report["blocker"] == "branch"
    b = report["branches"][0]
    assert b["kind"] == "resolvable"
    assert b["needs_domain_for"] == ["r1", "r2"]


def test_derivability_report_branch_over_two_bare_parameters_is_resolvable():
    # x1 == x2 is algebraically x1 - x2 == 0, degree 1, the same
    # affine shape an inline expression vs a literal already resolves.
    # This used to be unconditionally "blocked" regardless of domain;
    # the diagnostic must agree with what the real decision path
    # (_compare_truth) now does.
    def withdraw(balance: float, amount: float) -> float:
        if amount > balance:
            raise ValueError("insufficient funds")
        return balance - amount

    report = derivability_report(withdraw)
    assert report["blocker"] == "branch"
    b = report["branches"][0]
    assert b["kind"] == "resolvable"
    assert b["needs_domain_for"] == ["amount", "balance"]


def test_derivability_report_mixed_branches_report_each_independently():
    # a function can have both a resolvable and a blocked branch, both
    # must be reported, not just the first one found. `local` is affine
    # in x, so it's resolvable too (unlike the earlier non-affine-local
    # test); the still-blocked branch here is the unrecognized
    # condition shape instead.
    def mixed(flag: str, x: float) -> float:
        local = x + 1
        if flag == "a":
            return 1.0
        if local == 0.0:
            return 2.0
        if len(flag) > 0:
            return 4.0
        return 3.0

    report = derivability_report(mixed)
    kinds = {b["condition"]: b["kind"] for b in report["branches"]}
    assert kinds["flag == 'a'"] == "resolvable"
    assert kinds["local == 0.0"] == "resolvable"
    assert kinds["len(flag) > 0"] == "blocked"


# --- mutated globals: writing module state, not merely reading it ------

_CACHE: dict = {}
_COUNTER = {"n": 0}
_TOTAL = 3


class _Cfg:
    level = 0


_CFG = _Cfg()


def _put(k, v):
    _CACHE[k] = v
    return _CACHE[k]


def _bump(x):
    _COUNTER["n"] += x
    return _COUNTER["n"]


def _set_level(n):
    _CFG.level = n
    return _CFG.level


def _reads(x):
    return x + _TOTAL


def _local_dict(xs):
    seen = {}
    for x in xs:
        seen[x] = True
    return seen


def _through_param(store, k, v):
    store[k] = v
    return store


def test_mutated_globals_sees_a_subscript_write():
    """`local_names` counts the name as bound for `CACHE[k] = v`, because
    it drives alpha-renaming. The capture scan must not rely on it."""
    assert mutated_globals(_put) == ["_CACHE"]


def test_mutated_globals_sees_an_augmented_write():
    assert mutated_globals(_bump) == ["_COUNTER"]


def test_mutated_globals_sees_an_attribute_write():
    assert mutated_globals(_set_level) == ["_CFG"]


def test_a_read_is_not_a_mutation():
    """Different relationships, different fields: reading reports through
    global_vars, writing through this one."""
    assert mutated_globals(_reads) == []
    assert scope_dependencies(_reads)[0] == ["_TOTAL"]


def test_writing_a_local_is_not_a_mutation():
    assert mutated_globals(_local_dict) == []


def test_writing_through_a_parameter_is_not_a_mutation():
    assert mutated_globals(_through_param) == []


def test_mutated_globals_is_none_without_source():
    assert mutated_globals(len) is None
