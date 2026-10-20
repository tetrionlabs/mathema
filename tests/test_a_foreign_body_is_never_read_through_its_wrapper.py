# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A callable standing for a function written in another language
carries that function's facts (`__mathema_facts__`, written by a
frontend other than Python). Its own Python source is a wrapper's: a
global it writes, a raise, an assert, its lines and its file describe
the wrapper, not the function. Every reading that would take them from
the wrapper answers from the facts or says it does not know: no effect,
raise line, assert, coverage, span, line, project or exact reading is
taken from the wrapper, and writing a docstring into it is refused. A
Python function is read from its own source as before.
"""
import importlib.util
import os
import sys
import textwrap

import pytest

from mathema import audit, authoring, diagnostics, docstring, impl_coverage, inventory
from mathema._exact_body import exact_twin
from mathema.analysis import Facts, foreign_body
from mathema.koine import koine_hash
from tests._koine_docs import golden

WRAPPER = '''
    _CACHE = {}


    def growth(x, r):
        """Wrapper text.

        Claims:
            wrapper_claim: f(1, 1) == 99
        """
        assert x >= 0
        _CACHE[x] = r
        if r < -100:
            raise ValueError("raised by the wrapper")
        y = x * (1 + r)
        assert y >= 0
        return y


    def plain(x, r):
        assert x >= 0
        _CACHE[x] = r
        y = x * (1 + r)
        assert y >= 0
        return y


    def caller(x, r):
        return growth(x, r) + 1
'''


def _foreign_facts():
    d = golden("growth_py")
    params = d.parameter_names
    return Facts(name=d.name, signature="(" + ", ".join(params) + ")", params=params,
                 param_kinds={p: "scalar" for p in params}, returns_kind="scalar",
                 docstring="Growth of x at rate r.\n\nClaims:\n"
                           "    nonneg: for x in [0, 10], r in [0, 1], f(x, r) >= 0\n",
                 source="", effects=[], is_pure=True, loops=[],
                 comprehensions=[], recursion=False, branch_count=0,
                 call_groups={"math": [], "builtin": [], "external": []},
                 max_loop_depth=0, lines=0, form=koine_hash(d), sigh="0" * 12,
                 koine=d, provenance={"frontend": {"name": "cpp"}})


@pytest.fixture
def wrapper(tmp_path):
    path = tmp_path / "foreign_wrapper_mod.py"
    path.write_text(textwrap.dedent(WRAPPER))
    spec = importlib.util.spec_from_file_location("foreign_wrapper_mod", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["foreign_wrapper_mod"] = mod
    spec.loader.exec_module(mod)
    mod.growth.__mathema_facts__ = _foreign_facts()
    yield mod
    sys.modules.pop("foreign_wrapper_mod", None)


def _wrapper_lines(mod) -> set:
    first = mod.growth.__code__.co_firstlineno
    return set(range(first, first + 12))


def test_the_proxy_is_read_as_foreign_and_a_python_function_is_not(wrapper):
    assert foreign_body(wrapper.growth)
    assert not foreign_body(wrapper.plain)


def test_no_effect_is_read_from_the_wrapper(wrapper):
    from mathema._examine import _project_source
    assert _project_source(wrapper.growth) is None
    assert _project_source(wrapper.plain) is not None


def test_no_raise_line_is_read_from_the_wrapper(wrapper):
    from mathema.conjecture import _raise_lines, deliberate_raise
    assert _raise_lines(wrapper.growth) == frozenset()
    try:
        wrapper.growth(1.0, -200.0)
    except ValueError as exc:
        assert deliberate_raise(exc, wrapper.growth) is False


def test_coverage_of_a_foreign_body_is_unknown(wrapper):
    path = os.path.abspath(wrapper.__file__)
    data = {path: _wrapper_lines(wrapper)}
    assert inventory.is_test_covered(wrapper.growth, data) is None
    assert inventory.is_test_covered(wrapper.plain, {path: {wrapper.plain.__code__.co_firstlineno + 1}}) is True
    assert impl_coverage._line_range(wrapper.growth) is None
    assert impl_coverage._statement_lines(wrapper.growth) == set()


def test_no_span_line_or_file_is_read_from_the_wrapper(wrapper):
    assert audit._source_span(wrapper.growth) is None
    assert audit._source_span(wrapper.plain) is not None
    assert diagnostics._source_file(wrapper.growth) == "<unknown>"
    from mathema.cli import _name_use_lines
    assert _name_use_lines({"_fn": wrapper.growth}, ["_CACHE"]) == {}
    from mathema.conjecture import _derive_line_coverage, _project_root
    assert os.path.abspath(_project_root(wrapper.growth)) == os.getcwd()
    assert _derive_line_coverage(wrapper.growth, _foreign_facts(), {}) is None


def test_no_assert_is_read_from_the_wrapper(wrapper):
    assert authoring._domain_from_entry_asserts(wrapper.growth) == {}
    assert authoring._range_from_exit_asserts(wrapper.growth) == ([], set())
    assert authoring._domain_from_entry_asserts(wrapper.plain) != {}


def test_the_exact_reading_refuses_the_wrapper(wrapper):
    assert exact_twin(wrapper.growth) is None


def test_a_docstring_is_not_written_into_the_wrapper(wrapper):
    before = open(wrapper.__file__).read()
    with pytest.raises(ValueError):
        docstring.write_docstring(wrapper.growth, "Growth.")
    assert open(wrapper.__file__).read() == before


def test_a_foreign_callee_is_recorded_without_the_wrappers_file_and_line(wrapper):
    deps = inventory.function_dependencies(wrapper.caller)
    (dep,) = [d for d in deps if d["name"] == "growth"]
    assert "file" not in dep and "line" not in dep, dep


def test_the_project_compendium_note_reads_no_wrapper_file(wrapper):
    from mathema.compendium import uninstalled_project_note
    assert uninstalled_project_note(wrapper.growth) is None


def test_the_claims_come_from_the_injected_docstring(wrapper):
    import mathema
    names = {p.name for p in mathema.check(wrapper.growth).probes
             if (p.meta or {}).get("mathema.surface") != "mathema"}
    assert "nonneg" in names, names
    assert "wrapper_claim" not in names, names


def test_the_authored_reference_names_no_wrapper_line(wrapper):
    from mathema.authoring import declared_from_function
    (row,) = declared_from_function(wrapper.growth)
    assert row["name"] == "nonneg"
    assert ":L" not in row["authored"]["ref"], row["authored"]
