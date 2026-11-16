# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`operator::truth::ambiguous(x)` stands for the truth value of `x`
where a frontend cannot say yet what makes `x` true: its kind is not
known, or its class defines its own truth and that definition was not
read. It is a leaf with no evaluation rule. A document holding it
validates and hashes, so the rest of the function is still read; the
interpreter and the renderer both stop at the leaf and name it, so
nothing is decided through it. A frontend that knows the operand's kind
writes the check itself (`x != 0`, a length above zero) and never this
term."""
import pytest

from mathema.koine import canonical_text, interpret, koine_hash, validate
from mathema.koine._render import RenderError, render
from mathema.koine.interpret import InterpretError, Value
from mathema.koine.vocabulary import EXPRESSIONS
from tests._koine_docs import at, doc

AMBIGUOUS = "operator::truth::ambiguous"


def _choice(test: str):
    """`return x if <test> else 1.0`."""
    return doc(f"statement::return(value::conditional({test}, x, 1.0), {at()})")


def test_the_term_is_in_the_vocabulary_with_one_operand():
    sig = EXPRESSIONS[AMBIGUOUS]
    assert len(sig.positional) == 1 and sig.rest is None and sig.feature is None


def test_a_document_holding_it_validates():
    assert validate(_choice(f"{AMBIGUOUS}(x)")) == []


def test_it_takes_exactly_one_operand():
    assert validate(_choice(f"{AMBIGUOUS}()")) != []
    assert validate(_choice(f"{AMBIGUOUS}(x, r)")) != []


def test_it_hashes_and_is_not_the_explicit_check():
    undecided = _choice(f"{AMBIGUOUS}(x)")
    decided = _choice("operator::comparison::not_equal(x, 0)")
    assert AMBIGUOUS in canonical_text(undecided)
    assert koine_hash(undecided) == koine_hash(_choice(f"{AMBIGUOUS}(x)"))
    assert koine_hash(undecided) != koine_hash(decided)


def test_the_interpreter_stops_at_the_leaf_and_names_it():
    with pytest.raises(InterpretError, match="truth of x is ambiguous"):
        interpret(_choice(f"{AMBIGUOUS}(x)"), {"x": 2.0, "r": 0.5})
    assert interpret(_choice("operator::comparison::not_equal(x, 0)"),
                     {"x": 2.0, "r": 0.5}) == Value(2.0)
    assert interpret(_choice("operator::comparison::not_equal(x, 0)"),
                     {"x": 0.0, "r": 0.5}) == Value(1.0)


def test_the_renderer_stops_at_the_leaf_and_names_it():
    with pytest.raises(RenderError, match="truth of x is ambiguous"):
        render(_choice(f"{AMBIGUOUS}(x)"))
    assert render(_choice("operator::comparison::not_equal(x, 0)")) is not None
