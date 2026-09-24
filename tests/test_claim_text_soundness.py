# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The claim grammar either reads a claim as exactly what was written or
refuses it. Every accepted spelling here is held to four checks: its
canonical text is a fixed point, both display renderings reparse to the
same canonical claim, the declared layer (`declare` then
`entry_claims`) rebuilds the same canonical claim, and a real function
gets the same verdict from the claim before and after the round trip.
Every refused spelling raises `InvalidConjecture` with a message that
says what to write instead."""
import pytest

from mathema.conjecture import InvalidConjecture, check_conjectures, claim
from mathema.spec import (canonical_claim_text, declare, entry_claims,
                          fingerprint_text, render_claim_text)


def _verdict(fn, cj):
    (probe,) = check_conjectures(fn, [cj], extensive=False)
    return probe.verdict


def assert_round_trips(law, fn=None):
    """The four round-trip checks, returning the canonical text."""
    cj = claim(law)
    canon = canonical_claim_text(cj)
    assert canonical_claim_text(claim(canon)) == canon, "canonical drifts"
    for unicode in (True, False):
        shown = render_claim_text(cj, unicode=unicode)
        assert canonical_claim_text(claim(shown)) == canon, (
            f"display {shown!r} reparses to a different claim")
    (declared,) = entry_claims({"claims": [declare(cj)]})
    assert canonical_claim_text(declared) == canon, "declared layer drifts"
    if fn is not None:
        before = _verdict(fn, claim(law))
        assert _verdict(fn, claim(canon)) == before
        for unicode in (True, False):
            assert _verdict(fn, claim(render_claim_text(cj, unicode=unicode))) \
                == before
        assert _verdict(fn, declared) == before
    return canon


def five(x: float) -> float:
    return 5.0


def pick(r: float, mode: str) -> float:
    if mode == "alpha":
        return r
    raise ValueError(mode)


def labelled(m1: float, label: str) -> float:
    if label == "m":
        return m1
    raise ValueError(label)


# -- boolean connectives -------------------------------------------------

@pytest.mark.parametrize("law", [
    "for x in [0, 1], f(x) >= 1 and f(x) <= 2",
    "for x in [0, 1], f(x) >= 1 or f(x) <= 2",
    "for x in [0, 1], f(x) >= 0 and 1 > 2",
    "f(x) >= not x",
    "f(x) >= x and 1",
])
def test_a_boolean_connective_between_relations_is_refused(law):
    with pytest.raises(InvalidConjecture, match="its own claim"):
        claim(law)


def test_the_false_conjunction_no_longer_holds():
    # read with Python precedence this was f(x) >= (1 and f(x) <= 2),
    # which a constant 5 satisfies
    with pytest.raises(InvalidConjecture):
        claim("for x in [0, 1], f(x) >= 1 and f(x) <= 2")
    assert _verdict(five, claim("for x in [0, 1], 1 <= f(x) <= 2")) \
        == "falsified"


def test_a_parenthesised_boolean_value_is_still_a_value():
    canon = assert_round_trips("f(a, b) == (a <= b and b <= 1)")
    assert "and" in canon


# -- string literals ------------------------------------------------------

def test_a_greek_word_inside_quotes_is_not_a_parameter():
    law = 'for r in [0, 1], f(r, "alpha") >= 0'
    canon = assert_round_trips(law, pick)
    assert '"alpha"' in canon or "'alpha'" in canon
    shown = render_claim_text(claim(law), unicode=True)
    assert "α" not in shown
    assert _verdict(pick, claim(law)) in ("proven", "holds")


def test_a_let_alias_never_substitutes_inside_quotes():
    law = 'let m = m1, for m1 in [0, 1], f(m, "m") >= 0'
    canon = assert_round_trips(law, labelled)
    assert "'m'" in canon or '"m"' in canon
    assert "(m1)'" not in canon


@pytest.mark.parametrize("law, literal", [
    ('f(x, "a^b") == 1', "a^b"),
    ('f(x, "≤") == 1', "≤"),
    ('f(x, "x!") == 1', "x!"),
    ('f(x, "|a|") == 1', "|a|"),
    ('f(x) == "a, b"', "a, b"),
    ('"a<=b" == f(x)', "a<=b"),
])
def test_grammar_sugar_never_rewrites_a_string_value(law, literal):
    canon = assert_round_trips(law)
    assert f"'{literal}'" in canon


def test_an_ascii_greek_name_and_its_letter_stay_two_parameters():
    law = "for theta in [0, 1], θ in [2, 3], f(theta, θ) >= 0"
    canon = assert_round_trips(law)
    shown = render_claim_text(claim(law), unicode=True)
    assert "let θ = theta" not in shown
    assert set(claim(shown).domain) == {"theta", "θ"}
    assert "theta" in canon and "θ" in canon


# -- comment marks ---------------------------------------------------------

@pytest.mark.parametrize("law", [
    "for x in [0, 1], f(x) >= 1 # and f(x) <= 2",
    "# only a comment",
])
def test_a_hash_is_refused_rather_than_truncating_the_claim(law):
    with pytest.raises(InvalidConjecture, match="`#`"):
        claim(law)


def test_a_hash_inside_a_string_value_is_data():
    assert_round_trips('f(x, "a # b") >= 0')


# -- bindings ---------------------------------------------------------------

def negated(x: float) -> float:
    return -1.0 - x


@pytest.mark.parametrize("law", [
    "let f = math.sqrt, for x in [0, 1], f(x) >= 0",
    "let f = 2*x, for x in [0, 1], f >= 0",
    "let f be [0, 1], f(x) >= 0",
    "for f in [0, 1], f(f) >= 0",
])
def test_the_function_under_test_cannot_be_rebound(law):
    with pytest.raises(InvalidConjecture, match="`f` always names"):
        claim(law)


def test_a_false_claim_cannot_be_made_to_hold_by_rebinding_f():
    assert _verdict(negated, claim("for x in [0, 1], f(x) >= 0")) \
        == "falsified"
    with pytest.raises(InvalidConjecture):
        claim("let f = math.sqrt, for x in [0, 1], f(x) >= 0")


@pytest.mark.parametrize("law", [
    "for x in [0, 1], x in [2, 3], f(x) >= 0",
    "for x in [0, 1], for x in [2, 3], f(x) >= 0",
])
def test_one_name_bound_twice_is_a_conflict(law):
    from mathema.conjecture import ConflictingDomainBinding
    with pytest.raises(ConflictingDomainBinding, match="'x'"):
        claim(law)


@pytest.mark.parametrize("law, message", [
    ("let = 3, f(x) >= 0", "cannot read the binding"),
    ("let x = , f(x) >= 0", "binds 'x' to nothing"),
    ("let g = , f(x) >= g(x)", "binds 'g' to nothing"),
])
def test_a_malformed_let_binding_is_refused(law, message):
    with pytest.raises(InvalidConjecture, match=message):
        claim(law)


def test_a_well_formed_let_run_still_reads():
    assert_round_trips("let g = math.sqrt, for x in [0, 1], g(x) >= 0")
    assert_round_trips("let c be [-1, 1], for x in [0, 1], f(x + c) >= -9")


# -- radicals ---------------------------------------------------------------

def square(x: float) -> float:
    return x * x


@pytest.mark.parametrize("law, rhs", [
    ("for x in [1, 4], f(x) >= √x", "sqrt(x)"),
    ("for x in [1, 4], f(x) >= √ x", "sqrt(x)"),
    ("for x in [1, 4], f(x) >= √2", "sqrt(2)"),
    ("for x in [1, 4], f(x) >= √f(x) - 9", "sqrt(f(x)) - 9"),
    ("for x in [1, 4], f(x) >= √√x", "sqrt(sqrt(x))"),
])
def test_a_radical_takes_the_root_of_the_atom_after_it(law, rhs):
    assert claim(law).rhs == rhs
    assert_round_trips(law, square)
    assert canonical_claim_text(claim(law)) == canonical_claim_text(
        claim(law.replace(law.split(">= ")[1], rhs)))


def test_a_bare_radical_no_longer_reads_as_a_free_variable():
    assert _verdict(square, claim("for x in [1, 4], f(x) >= √x")) \
        == _verdict(square, claim("for x in [1, 4], f(x) >= √(x)"))


@pytest.mark.parametrize("law", [
    "f(x) >= √x^2",
    "f(x) >= √x²",
    "f(x) >= √",
])
def test_a_radical_with_an_unclear_reach_is_refused(law):
    with pytest.raises(InvalidConjecture, match="√"):
        claim(law)


# -- reserved call shapes -----------------------------------------------------

@pytest.mark.parametrize("law, form", [
    ("d(f(x), 1) >= 0", "`d`"),
    ("d(f(x), x, -1) >= 0", "`d`"),
    ("d(f(x), x+1) >= 0", "`d`"),
    ("d() >= 0", "`d`"),
    ("d(f(x), x) @ {x = 1, x = 2} == 2", "two values"),
    ("integrate(f(x), 1, 0, 1) == 1", "`integrate`"),
    ("integrate(f(x)) == 1", "`integrate`"),
    ("integrate(f(x), x, 0) == 1", "`integrate`"),
    ("Sum(f(i), 1, 1, n) == 1", "`Sum`"),
    ("lim(f(x), x) == 0", "`lim`"),
    ("f(x) >= lambda: 1", "lambda"),
])
def test_a_reserved_form_with_the_wrong_shape_is_refused(law, form):
    with pytest.raises(InvalidConjecture, match=form):
        claim(law)


@pytest.mark.parametrize("law", [
    "for x in [0, 1], d(f(x), x, 2) >= -99",
    "for x in [0, 1], d(f(x), x) @ {x = 1} >= -99",
    "integrate(f(x), x, 0, 1) >= -99",
    "Sum(f(i), i, 1, 3) >= -99",
    "lim(f(x), x, 0) >= -99",
])
def test_a_reserved_form_with_its_shape_still_reads(law):
    assert_round_trips(law)


@pytest.mark.parametrize("law", [
    "f(x) >= f(x=1)",
    "f(x) >= f(**x)",
    "f(x) =~ 1",
    "f(x) >= ~x",
    "f(x) >= x << 1",
    "f(x) >= (yield 1)",
    "f(x) >= [i for i in x]",
    "f(x) >= x if x else 1",
    "f(x) >= {1}",
    'f(x) >= b"abc"',
    'f(x) >= f"{x}"',
    "f(x) >= ...",
    "f(x) >= __import__('os').__dict__",
])
def test_python_syntax_with_no_claim_reading_is_refused(law):
    with pytest.raises(InvalidConjecture, match="claim syntax"):
        claim(law)


# -- identity: limits ---------------------------------------------------------

def shifted_up(x: float) -> float:
    return x + 1.0


def test_a_one_sided_limit_keeps_its_side_in_its_identity():
    right = claim("lim(f(x), x -> 0+) == 1")
    left = claim("lim(f(x), x -> 0-) == 1")
    both = claim("lim(f(x), x -> 0) == 1")
    prints = {fingerprint_text(right), fingerprint_text(left),
              fingerprint_text(both)}
    assert len(prints) == 3
    assert assert_round_trips("lim(f(x), x -> 0+) == 1", shifted_up) \
        == "lim(f(x), x, 0+) = 1"
    assert assert_round_trips("lim(f(x), x -> 0-) == 1") \
        == "lim(f(x), x, 0-) = 1"
    assert assert_round_trips("lim(f(x), x -> 0) == 1") \
        == "lim(f(x), x, 0) = 1"
    assert assert_round_trips("lim(f(x), x -> oo) == 0") \
        == "lim(f(x), x, oo) = 0"


# -- identity: the missing-value policy ---------------------------------------

def total(x: float) -> float:
    return x + 1.0


@pytest.mark.parametrize("law, ascii_domain", [
    (r"for x in [0, 1] \ {missing}, f(x) >= 0", r"[0.0, 1.0] \ {missing}:float"),
    (r"for x in [0, 1] \ {3, missing}, f(x) >= 0",
     r"[0.0, 1.0] \ {3, missing}:float"),
    (r"for x in [0, 1] \ {3}, f(x) >= 0", r"[0.0, 1.0] \ {3}:float|missing"),
    (r"for n in [0, 5] subset Z \ {missing}, f(n) >= 0", r"[0, 5] \ {missing}:int"),
    (r"for x in R \ {missing}, f(x) >= 0", r"R \ {missing}"),
])
def test_an_excluded_missing_value_is_stated_and_survives_reparse(
        law, ascii_domain):
    canon = assert_round_trips(law, total)
    assert ascii_domain in canon


def test_excluding_missing_is_a_different_claim_from_allowing_it():
    assert fingerprint_text(claim(r"for x in [0, 1] \ {missing}, f(x) >= 0")) \
        != fingerprint_text(claim("for x in [0, 1], f(x) >= 0"))


# -- identity: norm and absolute value ----------------------------------------

def magnitude(x: float) -> float:
    return abs(x)


def test_a_norm_and_an_absolute_value_are_different_claims():
    norm_law = "for x in [-1, 1], ||f(x)|| >= 0"
    abs_law = "for x in [-1, 1], |f(x)| >= 0"
    assert fingerprint_text(claim(norm_law)) != fingerprint_text(claim(abs_law))
    assert "norm(f(x))" in assert_round_trips(norm_law, magnitude)
    assert "|f(x)|" in assert_round_trips(abs_law, magnitude)


# -- identity: a bare-name equation after a let run ----------------------------

@pytest.mark.parametrize("law", [
    "r == 1 - alpha*q",
    "let c be [0, 1], r == c",
    "let g = math.sqrt, r == g(q)",
])
def test_a_bare_name_equation_is_not_read_as_another_binding(law):
    assert_round_trips(law)
    for unicode in (True, False):
        reparsed = claim(render_claim_text(claim(law), unicode=unicode))
        assert (reparsed.lhs, reparsed.relation) == ("r", "==")


# -- identity: function aliases -------------------------------------------------

def test_the_display_of_a_long_function_alias_is_the_same_claim():
    law = ("let compute_square_root = numpy.sqrt, for x in [0, 100], "
           "compute_square_root(x) >= 0")
    canon = assert_round_trips(law, square)
    assert "compute_square_root(x)" in canon


# -- the assuming section --------------------------------------------------------

def test_an_empty_assuming_premise_is_refused():
    with pytest.raises(InvalidConjecture, match="no premise"):
        claim("assuming , f(x) >= 0")


def test_an_assuming_premise_round_trips():
    assert_round_trips("assuming x > 0, for x in [-1, 1], f(x) >= 0", total)


# -- domains that denote no set --------------------------------------------------

@pytest.mark.parametrize("law", [
    "for x in [nan, 1], f(x) >= 0",
    "for x in [0, nan), f(x) >= 0",
    "for x in [0, 1] | [nan, 2], f(x) >= 0",
    "let c be [nan, 1], f(x) + c >= 0",
])
def test_a_nan_domain_endpoint_is_refused(law):
    with pytest.raises(InvalidConjecture, match="not a number"):
        claim(law)


def test_a_single_point_domain_still_reads():
    assert_round_trips("for x in [1, 1], f(x) >= 0", total)


def test_an_unreadable_let_bound_says_what_is_wrong():
    with pytest.raises(InvalidConjecture, match="'banana' isn't a recognized"):
        claim("let c be banana, f(c) >= 0")
