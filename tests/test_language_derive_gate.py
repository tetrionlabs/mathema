# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""What the derive route does with a parameter quantified over a
language: it declines the symbolic lift (a real symbol standing in for
a string would prove real-only facts it does not have) and states why,
so the probe decides; a FINITE language is the one exception, swept
point by point by the brute-force mechanism and proven or falsified
with a witness. A language whose members are not what the parameter
takes is flagged, an unknown language skips with the vocabulary on
every route, and the record states what every name resolved to. Core
ships no language, so these tests register an alphabet and a finite
language of their own."""
import textwrap

import pytest

from mathema.conjecture import check_conjectures, claim
from mathema.languages import (Problem, StringLanguage, register_language,
                               unregister_language)

LETTERS = StringLanguage("letters", char_ok=str.isalpha,
                         pool="abcXYZéΩ", outside_pool="1 -.")


def _load(tmp_path, body, name="lang_fns"):
    import importlib.util
    p = tmp_path / f"{name}.py"
    p.write_text(textwrap.dedent(body))
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _one(fn, law, route="best"):
    (p,) = check_conjectures(fn, [claim(law, route=route)])
    return p


class _Colours:
    name = "colours"
    kind = "string"
    level = "finite"
    WORDS = ("red", "green", "blue")

    def contains(self, value):
        return value in self.WORDS

    def explain(self, value):
        return None if self.contains(value) else [Problem("", "colours", value)]

    def sample(self, rng):
        return rng.choice(self.WORDS)

    def members(self, limit):
        return self.WORDS if len(self.WORDS) <= limit else None

    def hazards(self):
        return ()

    def outside(self, rng):
        return "purple"

    def shrink(self, value):
        return ()

    def fields(self):
        return None

    def render(self, ascii_mode=True):
        return "L[colours]"

    def to_json(self):
        return {"type": "string", "enum": list(self.WORDS)}


@pytest.fixture(autouse=True, scope="module")
def _languages():
    register_language("letters", LETTERS)
    register_language("colours", _Colours())
    try:
        yield
    finally:
        unregister_language("letters")
        unregister_language("colours")


@pytest.mark.parametrize("route", ["derive", "best"])
def test_derive_declines_a_language_bound_parameter_unless_finite(tmp_path, route):
    mod = _load(tmp_path, '''
        def size(s: str) -> float:
            """How long the text is, as a magnitude."""
            return abs(len(s))
    ''')
    p = _one(mod.size, "for s in L[letters], f(s) >= 0", route=route)
    # never proven: the only positive evidence is sampled
    assert p.verdict == "holds" and p.route == "probe"
    assert p.meta["mathema.derive_status"] == "unliftable"
    assert "language domain" in p.note


def test_a_branch_on_a_language_parameter_is_never_proven_by_the_real_lift(tmp_path):
    mod = _load(tmp_path, '''
        def short(s: str) -> int:
            """One for a short text, zero otherwise."""
            if len(s) < 3:
                return 1
            return 0
    ''')
    p = _one(mod.short, "for s in L[letters], f(s) >= 0", route="derive")
    assert p.verdict != "proven"
    assert p.meta["mathema.derive_status"] == "unliftable"


@pytest.mark.needs_full_proof_budget
def test_a_finite_language_is_proven_by_brute_force(tmp_path):
    mod = _load(tmp_path, '''
        def code(c: str) -> int:
            """A colour's code."""
            return len(c) + 1
    ''')
    p = _one(mod.code, "for c in L[colours], f(c) >= 4", route="derive")
    assert p.verdict == "proven", (p.verdict, p.note, p.sketch)
    assert p.route == "derive:brute_force"


@pytest.mark.needs_full_proof_budget
def test_a_finite_language_disproof_carries_the_member(tmp_path):
    mod = _load(tmp_path, '''
        def code(c: str) -> int:
            """A colour's code."""
            return len(c) + 1
    ''')
    p = _one(mod.code, "for c in L[colours], f(c) <= 5", route="derive")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert p.route == "derive:brute_force"
    assert "green" in str(p.counterexample)


def test_a_language_whose_members_are_not_what_the_parameter_takes_is_flagged(tmp_path):
    mod = _load(tmp_path, '''
        def successor(n: int) -> int:
            """One more than n."""
            return n + 1
    ''')
    p = _one(mod.successor, "for n in L[letters], f(n) == f(n)")
    assert "whose members are string values" in p.note
    assert p.verdict == "falsified"      # a str reaches n + 1 and raises
    assert "TypeError" in p.counterexample


@pytest.mark.parametrize("route", ["probe", "derive", "best"])
def test_an_unknown_language_skips_with_the_vocabulary_on_every_route(tmp_path, route):
    mod = _load(tmp_path, '''
        def same(s: str) -> str:
            """The text, unchanged."""
            return s
    ''')
    p = _one(mod.same, "for s in L[nope], f(s) == s", route=route)
    assert p.verdict == "skipped" and p.route is None
    assert "unknown language L[nope]" in p.note and "letters" in p.note
    assert "mathema[language]" in p.note
    assert p.meta["mathema.probe_gap"] == "language-unresolved"


def test_without_the_package_a_common_name_skips_and_names_it(tmp_path):
    mod = _load(tmp_path, '''
        def same(s: str) -> str:
            """The text, unchanged."""
            return s
    ''')
    p = _one(mod.same, "for s in L[unicode], f(s) == s")
    assert p.verdict == "skipped"
    assert "unknown language L[unicode]" in p.note
    assert "mathema[language]" in p.note


def test_the_record_states_what_the_language_resolved_to(tmp_path):
    mod = _load(tmp_path, '''
        def same(s: str) -> str:
            """The text, unchanged."""
            return s
    ''')
    p = _one(mod.same, "for s in L[letters] | L[colours], f(s) == s")
    assert p.verdict == "holds"
    (described,) = [p.meta["mathema.language"]["s"]]
    assert [d["name"] for d in described] == ["letters", "colours"]
    assert all(d["source"] == "registered" and d["kind"] == "string"
               for d in described)
    assert "s in L[letters] (registered)" in p.note
    assert p.domain == {"s": {"base_type": "L", "explicit_type": True,
                              "excluded": [],
                              "pieces": [{"language": "letters"},
                                         {"language": "colours"}]}}
    assert p.condition == "for s in L[letters] ∪ L[colours]|missing"


def test_every_sample_is_a_member_of_the_declared_language(tmp_path):
    mod = _load(tmp_path, '''
        def ascii_only(s: str) -> str:
            """The text, if ascii."""
            return s.encode("ascii").decode("ascii")
    ''')
    p = _one(mod.ascii_only, "for s in L[colours], f(s) == s")
    # a finite language is swept, so this can reach proven outright
    assert p.verdict in ("holds", "proven"), p.counterexample
    # the alphabet's pool holds non-ascii letters, so it reaches the raise
    q = _one(mod.ascii_only, "for s in L[letters], f(s) == s")
    assert q.verdict == "falsified" and "UnicodeEncodeError" in q.counterexample


def test_a_raise_inside_the_language_falsifies_with_the_member(tmp_path):
    mod = _load(tmp_path, '''
        def first(s: str) -> str:
            """The first character."""
            return s[0]
    ''')
    p = _one(mod.first, "for s in L[letters], len(f(s)) == 1")
    assert p.verdict == "falsified"
    assert p.counterexample.startswith("s='':") and "IndexError" in p.counterexample
    q = _one(mod.first, 'for s in L[letters] \\ {""}, len(f(s)) == 1')
    assert q.verdict == "holds"


def test_a_language_binding_is_the_parameter_s_own_domain_whatever_the_body_suggests(tmp_path):
    mod = _load(tmp_path, '''
        def count_commas(text) -> int:
            """How many commas the text holds."""
            n = 0
            for ch in text:
                if ch == ",":
                    n += 1
            return n
    ''')
    # the body iterates `text`, which reads as a sequence; the binding
    # says it is a string, and the samples are strings
    p = _one(mod.count_commas, "for text in L[letters], f(text) >= 0")
    assert p.verdict == "holds", (p.verdict, p.note)
    assert "members are string values" in p.note
