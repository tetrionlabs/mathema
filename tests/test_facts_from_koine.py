# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`facts_from_koine` reads a KOINE document into the `Facts` the engine
derives from, with the same structure the Python function it was
written from has; a document whose structure line disagrees with its
body, or that is not valid KOINE, is declined. A `Facts` carrying a
document and no tree is hydrated from the document in one place,
`effective_facts`, and every entry reads it that way."""
import inspect
import warnings
from dataclasses import replace

import pytest

import mathema
from mathema.analysis import Facts, analyze_source, effective_facts
from mathema.conjecture import _effective_facts
from mathema.koine import Document, KoineDeclined, facts_from_koine, koine_hash
from mathema.koine.facts import guards, structure
from mathema._signatures import module_scope
from tests._koine_docs import (
    GROWTH_BODY,
    SEQUENCE,
    at,
    doc,
    golden,
    golden_index,
    golden_text,
    growth,
    koine_fixture,
)

koine_py = koine_fixture()

GOLDEN_FUNCTIONS = {"growth_py": "growth", "ema_first_py": "ema", "piecewise_py": "tax",
                    "dot_py": "dot", "mean_py": "mean", "quotient_py": "quotient",
                    "remainders_py": "remainders"}

SAME_AS_THE_ORIGINAL = ("params", "param_kinds", "returns_kind", "branch_count", "recursion",
                        "guards", "max_loop_depth", "call_groups", "is_pure")


def _original(name):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return analyze_source(getattr(koine_py, GOLDEN_FUNCTIONS[name]))


@pytest.mark.parametrize("name", sorted(GOLDEN_FUNCTIONS))
def test_a_document_has_the_structure_of_the_function_it_was_written_from(name):
    facts = facts_from_koine(golden(name))
    original = _original(name)
    for field in SAME_AS_THE_ORIGINAL:
        assert getattr(facts, field) == getattr(original, field), (name, field)
    assert [(lf.kind, lf.item, lf.iter_src, lf.acc, lf.op_source, lf.depth)
            for lf in facts.loops] == \
        [(lf.kind, lf.item, lf.iter_src, lf.acc, lf.op_source, lf.depth)
         for lf in original.loops]


@pytest.mark.parametrize("name", sorted(GOLDEN_FUNCTIONS))
def test_the_structure_counted_from_the_body_is_the_structure_line(name):
    d = golden(name)
    stated = {k: v.value for k, v in d.first("structure").named}
    counted = structure(d)
    assert (counted.loops, counted.branches, counted.recursion) == \
        (stated["loops"], stated["branches"], stated["recursion"])


def test_the_facts_carry_the_document_its_rendering_and_its_hash():
    d = golden("growth_py")
    facts = facts_from_koine(d)
    assert facts.koine is d
    assert facts.tree is not None and facts.tree.name == "growth"
    assert facts.source.startswith("def growth(x: float, r: float) -> float:")
    assert facts.form == koine_hash(d) == "koine-0.0.1:bd9102d9efb1342e"
    assert not facts.form_is_computed()
    assert facts.signature == "(x: float, r: float) -> float"
    assert facts.name == "growth"


def test_text_is_read_as_a_document():
    assert facts_from_koine(golden_text("growth_py")).form == "koine-0.0.1:bd9102d9efb1342e"


def test_guards_read_off_the_body():
    clamp = doc(f"statement::return(function::order::minimum(x, 1), {at()})")
    assert guards(clamp) == {"x": "clamp", "r": "none"}
    branch = doc(f"""
      statement::branch(operator::comparison::less(x, 0),
        [statement::fail(failure::raise("ValueError"), {at()})], [], {at()}),
      statement::return(function::order::maximum(x, r), {at()}),
    """)
    assert guards(branch) == {"x": "raise", "r": "clamp"}
    assert guards(growth()) == {"x": "none", "r": "raise"}


def test_recursion_is_a_call_to_the_document_s_own_key():
    d = doc(f'statement::return(call::function("py:src/f.py#f", x, r), {at()})')
    assert structure(d).recursion
    other = doc(f'statement::return(call::function("py:src/g.py#g", x, r), {at()})')
    assert not structure(other).recursion


def test_a_structure_line_that_disagrees_with_the_body_is_declined():
    text = golden_text("ema_first_py").replace(
        "structure(loops: 1, branches: 1, recursion: false)",
        "structure(loops: 0, branches: 1, recursion: false)")
    with pytest.raises(KoineDeclined) as caught:
        facts_from_koine(text)
    decline = caught.value.decline
    assert decline["category"] == "structure-conflict"
    assert "loops: 0 stated, 1 in the body" in decline["message"]
    assert set(decline) == {"line", "statement", "message", "category"}


@pytest.mark.parametrize("name", sorted(n for n, e in golden_index().items()
                                        if "problems" in e))
def test_an_invalid_document_is_declined(name):
    with pytest.raises(KoineDeclined) as caught:
        facts_from_koine(golden_text(name))
    decline = caught.value.decline
    assert decline["category"] == "invalid-koine"
    for needle in golden_index()[name]["problems"]:
        assert needle in decline["message"]


def test_a_body_with_no_rendering_is_declined():
    d = doc(f"""
      statement::bind(acc, 0, {at()}),
      statement::loop::each(v, xs, 1, [
        statement::update(acc, operator::binary::addition, i, {at()}),
      ], {at()}, index: i),
      statement::return(acc, {at()}),
    """, params=SEQUENCE)
    with pytest.raises(KoineDeclined) as caught:
        facts_from_koine(d)
    assert caught.value.decline["category"] == "unsupported-koine-feature"


def _bare(d: Document) -> Facts:
    """Facts that carry the document and nothing read off a body."""
    params = d.parameter_names
    return Facts(name=d.name, signature="(" + ", ".join(params) + ")", params=params,
                 param_kinds={p: "scalar" for p in params}, returns_kind="scalar",
                 docstring=None, source="", effects=[], is_pure=True, loops=[],
                 comprehensions=[], recursion=False, branch_count=0,
                 call_groups={"math": [], "builtin": [], "external": []},
                 max_loop_depth=0, lines=0, form=koine_hash(d), sigh="0" * 12, koine=d)


def _carrying(facts: Facts):
    def proxy(x, r):
        return None
    proxy.__mathema_facts__ = facts
    return proxy


def test_effective_facts_hydrates_a_document_without_a_tree():
    bare = _bare(golden("growth_py"))
    fn = _carrying(bare)
    facts = effective_facts(fn)
    assert facts is not bare and bare.tree is None
    assert facts.tree is not None and facts.tree.name == "growth"
    assert facts.branch_count == 1 and facts.guards == {"x": "none", "r": "raise"}
    assert facts.form == bare.form and facts.params == bare.params
    assert effective_facts(fn) is facts


def test_every_entry_reads_the_hydrated_facts():
    bare = _bare(golden("growth_py"))
    fn = _carrying(bare)
    assert mathema.analyze(fn) is effective_facts(fn)
    assert _effective_facts(fn) is effective_facts(fn)
    assert _effective_facts(fn, bare) is effective_facts(fn)


def test_facts_with_a_tree_or_without_a_document_are_kept_as_given():
    with_tree = facts_from_koine(golden("growth_py"))
    assert effective_facts(_carrying(with_tree)) is with_tree
    plain = replace(_original("growth_py"), tree=None)
    assert effective_facts(_carrying(plain)) is plain


def test_a_declined_document_hydrates_to_nothing():
    text = golden_text("ema_first_py").replace("loops: 1", "loops: 2")
    bare = _bare(Document.parse(text))
    assert effective_facts(_carrying(bare)) is bare


def test_a_stated_scope_is_the_scope():
    def fn(x):
        return x
    fn.__mathema_scope__ = {"k": 1}
    assert module_scope(fn) == {"k": 1}


def test_the_rendered_names_resolve_for_a_callable_carrying_a_document():
    d = doc(GROWTH_BODY.replace('"ValueError"', '"pkg.errors.RateError"'), name="growth")
    fn = _carrying(_bare(d))
    scope = module_scope(fn)
    assert scope["RateError"].__name__ == "pkg.errors.RateError"
    assert scope["math"].pi > 3 and callable(scope["div_trunc"])
    assert scope["inspect"] is inspect
    assert module_scope(fn)["RateError"] is scope["RateError"]
