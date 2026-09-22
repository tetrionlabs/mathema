# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The audit blocked-detail block's color and line logic: pure
functions of a `derivability_report()` dict, no source-analysis
involved, unlike test_cli_audit_init.py's own subprocess-per-test
convention (needed there because inspect.getsource() requires real
files), these are tested in-process directly against hand-built report
dicts."""
from mathema.cli import (_ANSI_AMBER, _ANSI_GREEN, _ANSI_RED, _ANSI_RESET,
                         _fmt_blocked_detail)


def _branch_report(*kinds):
    return {"blocker": "branch",
           "branches": [{"line": i + 1, "condition": f"c{i}", "kind": k,
                        "code": "non-affine-refinable" if k == "blocked" else "needs-domain",
                        "reason": "not affine", "needs_domain_for": ["x"]}
                       for i, k in enumerate(kinds)]}


def _single_cause_report():
    return {"blocker": "unsupported-construct", "line": 3, "statement": "f(x)",
           "message": "some message text", "category": "unsupported-call"}


def test_all_resolvable_branches_key_is_green():
    lines = _fmt_blocked_detail("pkg.fn", _branch_report("resolvable", "resolvable"), color=True)
    assert lines[0] == f"  {_ANSI_GREEN}pkg.fn:{_ANSI_RESET}"


def test_mixed_resolvable_and_blocked_branches_key_is_amber():
    lines = _fmt_blocked_detail("pkg.fn", _branch_report("resolvable", "blocked"), color=True)
    assert lines[0] == f"  {_ANSI_AMBER}pkg.fn:{_ANSI_RESET}"


def test_all_blocked_branches_key_is_red():
    lines = _fmt_blocked_detail("pkg.fn", _branch_report("blocked", "blocked"), color=True)
    assert lines[0] == f"  {_ANSI_RED}pkg.fn:{_ANSI_RESET}"


def test_single_cause_key_is_always_red():
    # a single-cause blocker (as opposed to a branch report, which has
    # a real resolvable/blocked mechanical signal) is uniformly red
    lines = _fmt_blocked_detail("pkg.fn", _single_cause_report(), color=True)
    assert lines[0] == f"  {_ANSI_RED}pkg.fn:{_ANSI_RESET}"


def test_single_cause_line_carries_the_compact_code_only():
    lines = _fmt_blocked_detail("pkg.fn", _single_cause_report(), color=True)
    assert any("unsupported:unsupported-call" in line for line in lines)
    # the human hint text lives in diagnostic_report and the docs
    # lookup, never in the audit detail block
    assert not any("some message text" in line for line in lines)


def test_branch_lines_carry_codes_with_parameters():
    lines = _fmt_blocked_detail("pkg.fn", _branch_report("resolvable", "blocked"),
                                color=False)
    assert any("branch:needs-domain(x)" in line for line in lines)
    assert any("branch:non-affine-refinable" in line for line in lines)
    assert all("not affine" not in line for line in lines)


def test_no_color_means_no_ansi_codes_at_all():
    lines = _fmt_blocked_detail("pkg.fn", _branch_report("blocked"), color=False)
    assert not any("\x1b[" in line for line in lines)
    assert lines[0] == "  pkg.fn:"
