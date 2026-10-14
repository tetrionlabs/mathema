# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`sibling_scope(fn, siblings)` on the extension surface: a callable
whose injected facts carry a lifted body that calls another function of
its program is derived through that callee once the callee is supplied,
as its document or as a callable, keyed by the locator the body calls
it by."""
import inspect
from dataclasses import replace

import mathema
from mathema.analysis import Facts
from mathema.interfaces.extension import sibling_scope
from mathema.koine import Document, koine_hash

SHA = "0" * 64

HELPER_KEY = "py:src/shapes#scaled"


def document(key: str, statements: str) -> str:
    name = key.rpartition("#")[2]
    return f"""koine("0.0.1")
lifter(language: "py", name: "t", version: "0")
source(file: "src/shapes", line: 1, sha256: "{SHA}")
function(name: "{name}", key: "{key}")
parameter(x, kind::scalar, representation::f64)
returns(kind::scalar, representation::f64)
body({statements})
"""


AT = 'at: span(1, 1, "")'

HELPER = document(HELPER_KEY,
                  f"statement::return(operator::binary::multiplication(3, x), {AT})")
CALLER = document("py:src/shapes#shifted", f"""statement::return(operator::binary::addition(
    call::function("{HELPER_KEY}", x), 1), {AT})""")

CLAIM = "for x in [-4, 4], f(x) == 3 * x + 1"


def _facts(text: str) -> Facts:
    """Facts stating the function only through its document: no tree,
    no body read."""
    d = Document.parse(text)
    return Facts(name=d.name, signature="(x)", params=["x"], param_kinds={"x": "scalar"},
                 returns_kind="scalar", docstring=None, source="", effects=[],
                 is_pure=True, loops=[], comprehensions=[], recursion=False,
                 branch_count=0, call_groups={"math": [], "builtin": [], "external": []},
                 max_loop_depth=0, lines=0, form=koine_hash(d), sigh="0" * 12, koine=d)


def _proxy(text: str, impl):
    """A callable standing for a lifted function as a runtime adaptor
    serves it: an opaque forwarding body and facts carrying only the
    document."""
    def proxy(x):
        return impl(x)
    proxy.__name__ = Document.parse(text).name
    proxy.__signature__ = inspect.signature(lambda x: None)
    proxy.__mathema_facts__ = _facts(text)
    return proxy


def _shifted():
    return _proxy(CALLER, lambda x: 3 * x + 1)


def _verdict(fn):
    (probe,) = [p for p in mathema.check(fn, claims=[CLAIM]).probes
                if p.name == "f_x_eq_3_x_1"]
    return probe.verdict, probe.route


def test_without_its_sibling_the_body_is_not_proven_through_derive():
    assert _verdict(_shifted()) != ("proven", "derive")


def test_with_its_sibling_document_the_body_is_proven_through_derive():
    fn = _shifted()
    fn.__mathema_scope__ = sibling_scope(fn, {HELPER_KEY: HELPER})
    assert _verdict(fn) == ("proven", "derive")


def test_a_sibling_may_be_supplied_as_a_callable_carrying_its_own_document():
    fn = _shifted()
    helper = _proxy(HELPER, lambda x: 3 * x)
    fn.__mathema_scope__ = sibling_scope(fn, {HELPER_KEY: helper})
    assert _verdict(fn) == ("proven", "derive")


def test_the_scope_holds_what_the_rendered_body_reads():
    fn = _shifted()
    scope = sibling_scope(fn, {HELPER_KEY: HELPER})
    assert "math" in scope
    assert callable(scope["scaled"])
    assert scope["scaled"](2.0) == 6.0


def test_a_sibling_the_body_does_not_call_is_not_bound():
    fn = _shifted()
    other = document("py:src/shapes#unused", f"statement::return(x, {AT})")
    scope = sibling_scope(fn, {HELPER_KEY: HELPER, "py:src/shapes#unused": other})
    assert "unused" not in scope


def test_a_sibling_calling_a_sibling_is_bound_through_the_same_mapping():
    inner_key = "py:src/shapes#tripled"
    inner = document(inner_key,
                     f"statement::return(operator::binary::multiplication(3, x), {AT})")
    middle = document(HELPER_KEY, f'statement::return(call::function("{inner_key}", x), {AT})')
    fn = _shifted()
    fn.__mathema_scope__ = sibling_scope(fn, {HELPER_KEY: middle, inner_key: inner})
    assert _verdict(fn) == ("proven", "derive")


def test_facts_without_a_document_give_an_empty_scope():
    def plain(x):
        return x
    assert sibling_scope(plain, {HELPER_KEY: HELPER}) == {}


def test_a_facts_object_may_stand_for_the_callable():
    facts = replace(_facts(CALLER))
    scope = sibling_scope(facts, {HELPER_KEY: HELPER})
    assert scope["scaled"](1.0) == 3.0
