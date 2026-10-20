# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Derive reads a statement `sys.exit(c)` (and `exit(c)`, `quit(c)`, any
import spelling of `sys.exit`) as `raise SystemExit(c)`, the raise it
is: a guard that exits gives the same derive verdicts and raise regions
as the same guard written as a raise, with the exit code kept. The
function's form hash and source are those of the code as written, and
the probe side records the exit as it always has."""
import ast
import sys
import sys as system
from sys import exit as leave_now

import pytest

from mathema.analysis import analyze_source, get_tree
from mathema.conjecture import _definedness_region, check_conjectures, claim
from mathema.identity import form_hash
from mathema.symbolic._conditioned import lift_piecewise


def via_sys_exit(x: float) -> float:
    if x < 0:
        sys.exit(2)
    return x + 1


def via_raise(x: float) -> float:
    if x < 0:
        raise SystemExit(2)
    return x + 1


def via_builtin_exit(x: float) -> float:
    if x < 0:
        exit(2)
    return x + 1


def via_builtin_quit(x: float) -> float:
    if x < 0:
        quit(2)
    return x + 1


def via_imported_exit(x: float) -> float:
    if x < 0:
        leave_now(2)
    return x + 1


def via_aliased_module(x: float) -> float:
    if x < 0:
        system.exit(2)
    return x + 1


def via_local_import(x: float) -> float:
    import sys as here
    if x < 0:
        here.exit(2)
    return x + 1


def via_bare_exit(x: float) -> float:
    if x < 0:
        sys.exit()
    return x + 1


def via_bare_raise(x: float) -> float:
    if x < 0:
        raise SystemExit()
    return x + 1


class _NotSys:
    @staticmethod
    def exit(code=None):
        return code


def via_shadowed(x: float, sys=_NotSys) -> float:
    if x < 0:
        sys.exit(2)
    return x + 1


def via_exit_in_expression(x: float) -> float:
    if x < 0:
        return sys.exit(2)
    return x + 1


_EXITING = [via_sys_exit, via_builtin_exit, via_builtin_quit,
            via_imported_exit, via_aliased_module, via_local_import]


def _raises_in(fn) -> list:
    return [ast.unparse(n) for n in ast.walk(analyze_source(fn).tree)
            if isinstance(n, ast.Raise)]


def _one(fn, text, route="derive"):
    (p,) = check_conjectures(fn, [claim(text, route=route)])
    return p


@pytest.mark.parametrize("fn", _EXITING, ids=lambda f: f.__name__)
def test_every_spelling_of_an_exit_statement_reads_as_the_raise(fn):
    assert _raises_in(fn) == ["raise SystemExit(2)"]


def test_an_exit_with_no_code_reads_as_systemexit_with_code_none():
    assert _raises_in(via_bare_exit) == ["raise SystemExit()"]
    assert SystemExit().code is None


def test_a_name_that_is_not_sys_is_not_read_as_an_exit():
    assert _raises_in(via_shadowed) == []


def test_an_exit_inside_an_expression_is_left_as_the_call():
    assert _raises_in(via_exit_in_expression) == []


@pytest.mark.parametrize("fn", _EXITING + [via_raise],
                         ids=lambda f: f.__name__)
def test_form_hash_and_source_are_the_code_as_written(fn):
    src, fdef = get_tree(fn)
    facts = analyze_source(fn)
    assert facts.source == src
    assert facts.form == form_hash(fdef)
    assert facts.form_is_computed()


def test_an_exit_and_a_raise_keep_distinct_forms():
    assert analyze_source(via_sys_exit).form != analyze_source(via_raise).form


@pytest.mark.parametrize("fn", _EXITING, ids=lambda f: f.__name__)
def test_the_raise_region_matches_the_raise_spelling(fn):
    exiting = lift_piecewise(fn, analyze_source(fn))
    raising = lift_piecewise(via_raise, analyze_source(via_raise))
    assert exiting is not None and raising is not None
    assert [(str(c), e) for c, e in exiting.raise_guards] == \
        [(str(c), e) for c, e in raising.raise_guards] == [("x < 0", "SystemExit")]
    assert _definedness_region(fn, analyze_source(fn)) == \
        _definedness_region(via_raise, analyze_source(via_raise)) == ["x >= 0"]
    assert analyze_source(fn).guards == {"x": "raise"}


@pytest.mark.parametrize("text, verdict", [
    ("for x in [-5, -1], raises(f(x), SystemExit)", "proven"),
    ("for x in [0, 10], f(x) >= 1", "proven"),
    ("for x in [-10, 10], f(x) >= 1", "falsified"),
])
def test_derive_verdicts_match_the_raise_spelling(text, verdict):
    exiting = _one(via_sys_exit, text)
    raising = _one(via_raise, text)
    assert (exiting.verdict, exiting.route) == (raising.verdict, raising.route) \
        == (verdict, "derive"), (exiting, raising)
    assert exiting.sketch == raising.sketch


def test_is_defined_over_the_working_domain_matches_the_raise_spelling():
    exiting, raising = (
        check_conjectures(fn, [claim("x >= 0", name="is_defined",
                                     route="derive")])[0]
        for fn in (via_sys_exit, via_raise))
    assert exiting.verdict == raising.verdict == "proven", (exiting, raising)
    assert exiting.sketch == raising.sketch


def test_an_exit_with_no_code_is_proven_to_raise_systemexit():
    for fn in (via_bare_exit, via_bare_raise):
        p = _one(fn, "for x in [-5, -1], raises(f(x), SystemExit)")
        assert (p.verdict, p.route) == ("proven", "derive"), p


def test_the_probe_side_still_records_the_exit_with_its_code():
    held = _one(via_sys_exit, "for x in [-5, -1], raises(f(x), SystemExit)",
                route="probe")
    assert held.verdict == "holds", held
    falsified = _one(via_sys_exit, "for x in [-5, 5], f(x) >= 1",
                     route="probe")
    assert falsified.verdict == "falsified", falsified
    assert "SystemExit (exit code 2)" in falsified.counterexample


def test_a_derive_falsification_over_an_exit_names_its_exit_code():
    p = _one(via_sys_exit, "for x in [-5, 5], f(x) >= 1")
    assert (p.verdict, p.route) == ("falsified", "derive"), p
    assert "raised SystemExit (exit code 2)" in p.counterexample, p
    bare = _one(via_bare_exit, "for x in [-5, 5], f(x) >= 1")
    assert (bare.verdict, bare.route) == ("falsified", "derive"), bare
    assert "raised SystemExit (exit code None)" in bare.counterexample, bare
