# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The `in` / `not in` relation: membership in a language or a set on
the right, value containment otherwise, a numeric interval reduced to
the chain it means, both decided by execution with a witness, the
canonical text a fixed point, and `sin(x)` never split at its `in`."""
import textwrap

import pytest

from mathema.conjecture import check_conjectures, claim
from mathema.domain import Interval, InvalidDomain
from mathema.languages import StringLanguage, register_language, unregister_language
from mathema.spec import render_claim_text

LETTERS = StringLanguage("letters", char_ok=str.isalpha, pool="abcXYZ")


@pytest.fixture
def letters():
    register_language("letters", LETTERS)
    try:
        yield
    finally:
        unregister_language("letters")


def _load(tmp_path, body, name="membership_fns"):
    import importlib.util
    p = tmp_path / f"{name}.py"
    p.write_text(textwrap.dedent(body))
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _one(fn, law, **kw):
    (p,) = check_conjectures(fn, [claim(law, **kw)])
    return p


def test_the_parse_reads_a_domain_on_the_right_and_a_value_otherwise():
    cj = claim("for s in L[letters], f(s) in L[letters]")
    assert cj.relation == "in" and cj.lhs == "f(s)" and cj.rhs == "L[letters]"
    assert getattr(cj.rhs_bound, "base_type", None) == "L"
    cj = claim('for s in L[letters], "<" not in f(s)')
    assert cj.relation == "not in" and cj.rhs == "f(s)" and cj.rhs_bound is None
    cj = claim("for x in [0, 1], f(x) in {1, 2, 3}")
    assert cj.relation == "in" and isinstance(cj.rhs_bound, frozenset)
    cj = claim("for x in [0, 1], f(x) not in [2, 3]")
    assert cj.relation == "not in" and isinstance(cj.rhs_bound, Interval)


def test_a_numeric_interval_on_the_right_is_the_chain_it_means():
    cj = claim("for x in [0, 1], f(x) in [0, 1]")
    assert cj.relation == "<=" and cj.links and cj.rhs_bound is None
    assert render_claim_text(cj, unicode=False).endswith("0 <= f(x) <= 1")
    cj = claim("for x in [0, 1], f(x) in (0, 1]")
    assert render_claim_text(cj, unicode=False).endswith("0 < f(x) <= 1")


def test_sin_is_never_split_at_its_in():
    cj = claim("for x in [0, 1], sin(x) >= 0")
    assert cj.relation == ">=" and cj.lhs == "sin(x)"


def test_the_symbols_render_and_the_text_is_a_fixed_point(letters):
    for law, unicode_text in (
            ("for s in L[letters], f(s) in L[letters]", "f(s) ∈ L[letters]"),
            ('for s in L[letters], "<" not in f(s)', '"<" ∉ f(s)'),
            ("for s ∈ L[letters], f(s) ∉ L[letters]", "f(s) ∉ L[letters]")):
        cj = claim(law)
        assert render_claim_text(cj, unicode=True).endswith(unicode_text)
        ascii_text = render_claim_text(cj, unicode=False)
        assert render_claim_text(claim(ascii_text), unicode=False) == ascii_text
        assert claim(render_claim_text(cj, unicode=True)).relation == cj.relation


def test_closure_holds_and_leaving_the_language_falsifies_with_a_witness(tmp_path, letters):
    mod = _load(tmp_path, '''
        def shout(s: str) -> str:
            """Upper case."""
            return s.upper()

        def tagged(s: str) -> str:
            """The text with a digit appended."""
            return s + "1"
    ''')
    p = _one(mod.shout, "for s in L[letters], f(s) in L[letters]", route="best")
    assert p.verdict == "holds", (p.verdict, p.note, p.counterexample)
    assert p.route == "probe"
    q = _one(mod.tagged, "for s in L[letters], f(s) in L[letters]", route="best")
    assert q.verdict == "falsified", (q.verdict, q.note)
    assert "is not in L[letters]" in q.counterexample


def test_containment_holds_and_falsifies_with_a_witness(tmp_path, letters):
    mod = _load(tmp_path, '''
        def escape(s: str) -> str:
            """Angle brackets escaped."""
            return s.replace("<", "&lt;")

        def same(s: str) -> str:
            """Unchanged."""
            return s
    ''')
    p = _one(mod.escape, 'for s in L[letters] | {"a<b"}, "<" not in f(s)')
    assert p.verdict == "holds", (p.verdict, p.note, p.counterexample)
    q = _one(mod.same, 'for s in L[letters] | {"a<b"}, "<" not in f(s)')
    assert q.verdict == "falsified", (q.verdict, q.note)
    assert "'a<b' is in" in q.counterexample or "is in f(s)" in q.counterexample


def test_a_missing_output_is_a_member_of_nothing(tmp_path, letters):
    mod = _load(tmp_path, '''
        def maybe(s: str):
            """None for an empty string."""
            return s or None
    ''')
    p = _one(mod.maybe, 'for s in L[letters] | {""}, f(s) in L[letters]')
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "None is not in L[letters]" in p.counterexample


def test_the_derive_route_declines_with_the_reason(tmp_path, letters):
    mod = _load(tmp_path, '''
        def shout(s: str) -> str:
            """Upper case."""
            return s.upper()
    ''')
    p = _one(mod.shout, "for s in L[letters], f(s) in L[letters]", route="derive")
    assert p.verdict != "proven", (p.verdict, p.note)
    assert "decided by running the code" in (p.note or "") + str(p.sketch or "")


def test_an_unknown_language_on_the_right_is_a_gap_not_a_crash(tmp_path, letters):
    mod = _load(tmp_path, '''
        def shout(s: str) -> str:
            """Upper case."""
            return s.upper()
    ''')
    p = _one(mod.shout, "for s in L[letters], f(s) in L[no_such_language]")
    assert p.verdict == "unknown"
    assert p.meta.get("mathema.probe_gap") == "language-unresolved"


def test_a_number_set_on_the_right_is_membership_too(tmp_path):
    mod = _load(tmp_path, '''
        def half(x: float) -> float:
            """Half."""
            return x / 2

        def whole(x: float) -> float:
            """Rounded."""
            return int(round(x))
    ''')
    p = _one(mod.whole, "for x in [0, 10], f(x) in Z")
    assert p.verdict == "holds", (p.verdict, p.note, p.counterexample)
    q = _one(mod.half, "for x in [0, 10], f(x) in Z")
    assert q.verdict == "falsified", (q.verdict, q.note)


def test_a_bare_name_on_the_left_is_still_a_binding_not_a_law():
    with pytest.raises((InvalidDomain, Exception)):
        claim("for s in L[letters], s in L[letters]")


def test_a_union_on_the_right_is_a_domain_not_an_unpaired_bar(letters):
    cj = claim('for s in L[letters], f(s) in L[letters] | {""}')
    assert cj.relation == "in" and cj.rhs_bound is not None
    ascii_text = render_claim_text(cj, unicode=False)
    assert render_claim_text(claim(ascii_text), unicode=False) == ascii_text
