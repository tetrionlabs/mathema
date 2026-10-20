# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Derive reads a project function called through its module as it
reads one imported by name: `helpers.g(x)`, `h.g(x)` after `import
helpers as h`, and `pkg.sub.g(x)` all lift into the callee's own body,
so a claim about the caller is proven from the callee's mathematics
rather than left to running the code. The callee must be a plain Python
function of the project reached through modules alone: a function of an
installed library (`statistics.fmean`) and a method of an object a
module holds are not inlined.

An inlined callee brings its raise regions with it, however it is
called: `inv(x) * x` simplifies to 1, yet the call raises at x = 0, so
`f(x) == 1` over [-1, 1] is falsified there, and proven over [1, 2].
"""
import sys
import textwrap

import pytest

from mathema.conjecture import check_conjectures, claim

HELPERS = '''
    import math


    def g(x):
        return x * x + 1


    def inv(x):
        return 1 / x


    def root(x):
        return math.sqrt(x)


    def checked(x):
        if x < 0:
            raise ValueError("negative")
        return x
'''

SUB = '''
    def g(x):
        return x * x + 1
'''

CALLERS = '''
    import statistics

    import attr_inline_helpers
    import attr_inline_helpers as h
    import attr_inline_pkg.sub
    from attr_inline_pkg import sub
    from attr_inline_helpers import checked, inv, root


    class _Scale:
        def g(self, x):
            return x * x + 1


    scale = _Scale()


    def via_module(x):
        return attr_inline_helpers.g(x)


    def via_alias(x):
        return h.g(x)


    def via_package_path(x):
        return attr_inline_pkg.sub.g(x)


    def via_submodule(x):
        return sub.g(x)


    def via_library(x):
        return statistics.fmean([x * x + 1])


    def via_object(x):
        return scale.g(x)


    def bare_inv(x):
        return inv(x) * x


    def module_inv(x):
        return attr_inline_helpers.inv(x) * x


    def bare_root(x):
        return root(x) * root(x)


    def module_root(x):
        return h.root(x) * h.root(x)


    def bare_checked(x):
        return checked(x) + 1


    def module_checked(x):
        return h.checked(x) + 1


    from dataclasses import dataclass


    @dataclass
    class Account:
        rate: float

        def per_unit(self) -> float:
            return 1 / self.rate

        def scaled(self, x: float) -> float:
            return self.per_unit() * self.rate * x
'''

_MODULES = ("attr_inline_helpers", "attr_inline_pkg", "attr_inline_pkg.sub",
            "attr_inline_callers")


@pytest.fixture
def callers(tmp_path, monkeypatch):
    (tmp_path / "attr_inline_helpers.py").write_text(textwrap.dedent(HELPERS))
    pkg = tmp_path / "attr_inline_pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "sub.py").write_text(textwrap.dedent(SUB))
    (tmp_path / "attr_inline_callers.py").write_text(textwrap.dedent(CALLERS))
    monkeypatch.syspath_prepend(str(tmp_path))
    for name in _MODULES:
        sys.modules.pop(name, None)
    import attr_inline_callers
    yield attr_inline_callers
    for name in _MODULES:
        sys.modules.pop(name, None)


def _row(fn, law):
    (p,) = check_conjectures(fn, [claim(law)])
    return p


@pytest.mark.needs_full_proof_budget
@pytest.mark.parametrize("name", ["via_module", "via_alias",
                                  "via_package_path", "via_submodule"])
def test_a_module_attribute_call_is_inlined(callers, name):
    p = _row(getattr(callers, name), "for x in [-3, 3], f(x) >= 1")
    assert p.verdict == "proven", (p.verdict, p.route, p.note)
    assert p.route.startswith("derive"), p.route


@pytest.mark.parametrize("name", ["via_module", "via_package_path"])
def test_a_false_claim_through_a_module_call_is_not_proven(callers, name):
    p = _row(getattr(callers, name), "for x in [-3, 3], f(x) >= 2")
    assert p.verdict == "falsified", (p.verdict, p.route, p.note)


@pytest.mark.parametrize("name", ["via_library", "via_object"])
def test_a_library_function_or_an_object_method_is_not_inlined(callers, name):
    p = _row(getattr(callers, name), "for x in [-3, 3], f(x) >= 1")
    assert not p.route.startswith("derive"), (p.verdict, p.route, p.note)


@pytest.mark.parametrize("name, law", [
    ("bare_inv", "for x in [-1, 1], f(x) == 1"),
    ("module_inv", "for x in [-1, 1], f(x) == 1"),
    ("bare_root", "for x in [-1, 1], f(x) == x"),
    ("module_root", "for x in [-1, 1], f(x) == x"),
    ("bare_checked", "for x in [-1, 1], f(x) >= 1"),
    ("module_checked", "for x in [-1, 1], f(x) >= 1"),
])
def test_an_inlined_callee_raising_in_the_domain_falsifies(callers, name, law):
    p = _row(getattr(callers, name), law)
    assert p.verdict == "falsified", (p.verdict, p.route, p.sketch, p.note)


@pytest.mark.needs_full_proof_budget
@pytest.mark.parametrize("name, law", [
    ("bare_inv", "for x in [1, 2], f(x) == 1"),
    ("module_inv", "for x in [1, 2], f(x) == 1"),
    ("module_root", "for x in [1, 2], f(x) ~= x"),
    ("module_checked", "for x in [0, 1], f(x) >= 1"),
])
def test_an_inlined_callee_that_returns_on_the_domain_is_proven(callers, name, law):
    p = _row(getattr(callers, name), law)
    assert p.verdict == "proven", (p.verdict, p.route, p.sketch, p.note)


def test_a_sibling_method_raising_in_the_domain_is_not_proven(callers):
    p = _row(callers.Account.scaled,
             "for self.rate in [-1, 1], x in [0, 1], f(self, x) == x")
    assert p.verdict != "proven", (p.verdict, p.route, p.sketch, p.note)


@pytest.mark.needs_full_proof_budget
def test_a_sibling_method_that_returns_on_the_domain_is_proven(callers):
    p = _row(callers.Account.scaled,
             "for self.rate in [1, 2], x in [0, 1], f(self, x) == x")
    assert p.verdict == "proven", (p.verdict, p.route, p.sketch, p.note)
