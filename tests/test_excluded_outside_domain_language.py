# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`excluded_outside_domain[s]` over a language: the function must
reject what lies outside the language. The near non-members come from
the language's own `outside` draws; a clean return on one falsifies
with that value as the witness, naming the language; every raise holds;
a language with no outside skips and says so; and a function wrapped by
`@enforce_domain` still proves rejection by construction."""
import textwrap

import mathema
from mathema.conjecture import check_conjectures, claim
from mathema.languages import Problem, StringLanguage, register_language, unregister_language

LETTERS = StringLanguage("letters", char_ok=str.isalpha, pool="abcXYZ",
                         outside_pool="1 -.")


class _Everything:
    name = "everything"
    kind = "string"
    level = "alphabet"

    def contains(self, value):
        return isinstance(value, str)

    def explain(self, value):
        return None if self.contains(value) else [Problem("", "str", value)]

    def sample(self, rng):
        return rng.choice(["a", "bc", ""])

    def members(self, limit):
        return None

    def hazards(self):
        return ()

    def outside(self, rng):
        return None

    def shrink(self, value):
        return ()

    def fields(self):
        return None

    def render(self, ascii_mode=True):
        return "L[everything]"

    def to_json(self):
        return {"type": "string"}


def _load(tmp_path, body, name="excl_fns"):
    import importlib.util
    p = tmp_path / f"{name}.py"
    p.write_text(textwrap.dedent(body))
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _one(fn, law):
    (p,) = check_conjectures(fn, [claim(law, route="best")])
    return p


def setup_module(module):
    register_language("letters", LETTERS)
    register_language("everything", _Everything())


def teardown_module(module):
    unregister_language("letters")
    unregister_language("everything")


def test_a_non_member_returning_cleanly_falsifies_with_the_outside_witness(tmp_path):
    mod = _load(tmp_path, '''
        def shout(s: str) -> str:
            """Upper case, whatever comes in."""
            return s.upper()
    ''')
    p = _one(mod.shout, "for s in L[letters], excluded_outside_domain(s)")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "outside L[letters]" in p.counterexample
    assert "accepted" in p.counterexample


def test_the_witness_says_why_the_value_is_outside(tmp_path):
    import re
    mod = _load(tmp_path, '''
        def shout(s: str) -> str:
            """Upper case, whatever comes in."""
            return s.upper()
    ''')
    p = _one(mod.shout, "for s in L[letters], excluded_outside_domain(s)")
    m = re.search(r"= ('.*?') \(outside L\[letters\] at (\[\d+\]): (.+?)\)", p.counterexample)
    assert m, p.counterexample
    (problem, *_) = LETTERS.explain(eval(m.group(1)))
    assert (m.group(2), m.group(3)) == (problem.path, problem.predicate)


def test_a_function_rejecting_every_non_member_holds(tmp_path):
    mod = _load(tmp_path, '''
        def shout(s: str) -> str:
            """Upper case of a word of letters."""
            if not s.isalpha() and s != "":
                raise ValueError("letters only")
            return s.upper()
    ''')
    p = _one(mod.shout, "for s in L[letters], excluded_outside_domain(s)")
    assert p.verdict == "holds", (p.verdict, p.note, p.counterexample)


def test_a_language_with_no_outside_skips_and_says_so(tmp_path):
    mod = _load(tmp_path, '''
        def shout(s: str) -> str:
            """Upper case, whatever comes in."""
            return s.upper()
    ''')
    p = _one(mod.shout, "for s in L[everything], excluded_outside_domain(s)")
    # the structural half is undecided and the trials have nothing to
    # draw, so the claim is unknown, with the reason on the note
    assert p.verdict in ("skipped", "unknown"), (p.verdict, p.note)
    assert "no outside" in p.note


def test_enforce_domain_still_proves_rejection_by_construction():
    @mathema.enforce_domain()
    @mathema.claims_decorator("for s in L[letters], excluded_outside_domain(s)")
    def shout(s: str) -> str:
        """Upper case of a word of letters."""
        return s.upper()

    p = _one(shout, "for s in L[letters], excluded_outside_domain(s)")
    assert p.verdict == "proven", (p.verdict, p.note)
    assert "rejection by construction" in (p.sketch or "")


class _Row:
    """A record whose repr is Python's default."""

    def __init__(self, name):
        self.name = name


class _Rows(_Everything):
    """Records whose name is letters; any other record is outside."""

    name = "rows"
    kind = "row"

    def contains(self, value):
        return isinstance(value, _Row) and value.name.isalpha()

    def explain(self, value):
        return None if self.contains(value) else [Problem(".name", "letters", value)]

    def sample(self, rng):
        return _Row("abc")

    def outside(self, rng):
        return _Row("1")

    def render(self, ascii_mode=True):
        return "L[rows]"


def greet(row) -> str:
    """A greeting for the record."""
    return "hello " + row.name


def test_a_record_witness_is_shown_by_its_fields():
    register_language("rows", _Rows())
    try:
        p = _one(greet, "for row in L[rows], excluded_outside_domain(row)")
    finally:
        unregister_language("rows")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "row = _Row(name='1') (outside L[rows] at .name: letters)" in p.counterexample, \
        p.counterexample
