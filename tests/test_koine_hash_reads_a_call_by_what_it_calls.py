# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A call to another function of the program hashes by what the callee
computes, not by how it is addressed: the sibling, self, ancestor and
external respellings, and the nominal form that keeps the locator."""
from mathema.koine import (
    Document,
    canonical_text,
    gather_siblings,
    koine_hash,
    nominal_hash,
    nominal_text,
    unresolved_calls,
)

SHA = "0" * 64


def fn(key: str, body: str, params: str = "x") -> Document:
    names = [p.strip() for p in params.split(",")]
    decls = "\n".join(f"parameter({n}, kind::scalar, representation::f64)" for n in names)
    return Document.parse(f"""koine("0.0.1")
lifter(language: "py", name: "t", version: "0")
source(file: "f", line: 1, sha256: "{SHA}")
function(name: "{key.rpartition('#')[2].rpartition('.')[2]}", key: "{key}")
{decls}
returns(kind::scalar, representation::f64)
body({body})
""")


def caller(callee: str, key: str = "m.caller") -> Document:
    return fn(key, f'statement::return(call::function("{callee}", x))')


DOUBLE = "statement::return(operator::binary::multiplication(y, 2))"
TRIPLE = "statement::return(operator::binary::multiplication(y, 3))"


def test_a_renamed_helper_with_the_same_mathematics_hashes_alike():
    a = caller("m.twice")
    b = caller("py:src/f.py#doubled", key="py:src/f.py#caller")
    sa = {"m.twice": fn("m.twice", DOUBLE, "y")}
    sb = {"py:src/f.py#doubled": fn("py:src/f.py#doubled",
                                  "statement::return(operator::binary::multiplication(z, 2))", "z")}
    assert koine_hash(a, sa) == koine_hash(b, sb)
    assert "call::hashed(" in canonical_text(a, sa)


def test_a_different_helper_hashes_apart():
    a, b = caller("m.h"), caller("m.h")
    assert koine_hash(a, {"m.h": fn("m.h", DOUBLE, "y")}) != koine_hash(
        b, {"m.h": fn("m.h", TRIPLE, "y")})


def test_a_callee_the_siblings_do_not_reach_keeps_only_its_bare_name():
    for locator in ("pkg.mod.norm_cdf", "py:a/b.py#norm_cdf", "py:x.py#norm_cdf"):
        text = canonical_text(caller(locator))
        assert 'call::external("norm_cdf",_p0)' in text


def test_recursion_is_call_self():
    d = fn("m.f", 'statement::return(call::function("m.f", x))')
    assert "call::self(_p0)" in canonical_text(d)
    other = fn("other.name", 'statement::return(call::function("other.name", x))')
    assert koine_hash(d) == koine_hash(other)


def test_mutual_recursion_terminates_with_an_ancestor_call():
    a = fn("m.a", 'statement::return(call::function("m.b", x))')
    b = fn("m.b", 'statement::return(call::function("m.a", x))')
    siblings = {"m.a": a, "m.b": b}
    assert koine_hash(a, siblings).startswith("koine-0.0.1:")
    from mathema.koine.canonical import _Calls, _canonical_terms
    from mathema.koine.syntax import compact_document
    seen = compact_document(_canonical_terms(b, nominal=False, calls=_Calls(siblings),
                                             stack=("m.a",)))
    assert "call::ancestor(1,_p0)" in seen


def test_the_nominal_form_keeps_the_locator():
    d = caller("m.twice")
    assert 'call::function("m.twice",x)' in nominal_text(d)
    assert nominal_hash(d) != nominal_hash(caller("m.thrice"))
    assert nominal_hash(d) == nominal_hash(caller("m.twice"))


def test_gather_follows_calls_transitively_and_skips_self():
    a = caller("m.b", key="m.a")
    b = fn("m.b", 'statement::return(call::function("m.c", y))', "y")
    c = fn("m.c", 'statement::return(call::function("m.b", y))', "y")
    found = gather_siblings(a, {"m.b": b, "m.c": c}.get)
    assert set(found) == {"m.b", "m.c"}
    assert gather_siblings(caller("m.zzz"), lambda locator: None) == {}


def _diamond(depth: int):
    siblings = {}
    for level in range(depth):
        for side in "ab":
            key = f"m.{side}{level}"
            if level == depth - 1:
                body = "statement::return(x)"
            else:
                body = ("statement::return(operator::binary::addition("
                        f'call::function("m.a{level + 1}", x), call::function("m.b{level + 1}", x)))')
            siblings[key] = fn(key, body)
    top = fn("m.top", "statement::return(operator::binary::addition("
                      'call::function("m.a0", x), call::function("m.b0", x)))')
    return top, siblings


def _clique(size: int):
    siblings = {}
    for i in range(size):
        calls = ",".join(f'call::function("m.c{j}", x)' for j in range(size) if j != i)
        siblings[f"m.c{i}"] = fn(f"m.c{i}", f"statement::return(operator::binary::addition({calls}))")
    return siblings["m.c0"], siblings


def test_a_diamond_of_calls_hashes_in_linear_time():
    import time

    top, siblings = _diamond(30)
    started = time.perf_counter()
    koine_hash(top, siblings)
    assert time.perf_counter() - started < 1.0


def test_memoising_callees_leaves_the_hashes_unchanged():
    top, siblings = _diamond(16)
    assert koine_hash(top, siblings) == "koine-0.0.1:4747eebdf670bf04"
    top, siblings = _clique(6)
    assert koine_hash(top, siblings) == _reference_clique_hash(6)


def _reference_clique_hash(size: int) -> str:
    """The clique hash computed with every callee rehashed at each call site."""
    from mathema.koine import canonical
    from mathema.koine.syntax import compact_document

    top, siblings = _clique(size)

    class Unmemoised(canonical._Calls):
        def _hash(self, locator, sibling, stack):
            terms = canonical._canonical_terms(sibling, nominal=False, calls=self, stack=stack)
            return canonical._digest(compact_document(terms))

    terms = canonical._canonical_terms(top, nominal=False, calls=Unmemoised(siblings), stack=())
    return canonical._digest(compact_document(terms))


def test_unresolved_calls_lists_the_locators_a_hash_rests_on_by_name():
    a = caller("a.helper")
    b = caller("b.helper")
    assert koine_hash(a) == koine_hash(b)
    assert unresolved_calls(a) == ("a.helper",)
    assert unresolved_calls(b) == ("b.helper",)


def test_unresolved_calls_follows_siblings_and_skips_resolved_and_self():
    top = caller("m.mid", key="m.top")
    mid = fn("m.mid", 'statement::return(operator::binary::addition('
                      'call::function("m.mid", y), call::function("lib.erf", y)))', "y")
    assert unresolved_calls(top, {"m.mid": mid}) == ("lib.erf",)
    assert unresolved_calls(top, {"m.mid": mid, "lib.erf": fn("lib.erf", DOUBLE, "y")}) == ()
