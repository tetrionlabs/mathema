# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The KOINE text syntax: what parses to what, what is refused with
which line and column, and that both printers reparse to the same
terms."""
import pytest
from mathema.koine.syntax import (
    Bool,
    Int,
    KoineSyntaxError,
    List,
    Name,
    Real,
    Str,
    Term,
    compact,
    format_document,
    inline,
    parse,
    parse_node,
    pretty,
)


def test_atoms():
    assert parse_node("x") == Name("x")
    assert parse_node("-3") == Int(-3)
    assert parse_node("0.5") == Real("0.5")
    assert parse_node("1e-07") == Real("1e-07")
    assert parse_node("-2.5E+3") == Real("-2.5E+3")
    assert parse_node('"a \\"b\\"\\n"') == Str('a "b"\n')
    assert parse_node("true") == Bool(True)
    assert parse_node("false") == Bool(False)


def test_terms_paths_and_lists():
    assert parse_node("constant::pi") == Term("constant::pi")
    assert parse_node("f()") == Term("f")
    assert parse_node("operator::binary::addition(x, 1)") == \
        Term("operator::binary::addition", (Name("x"), Int(1)))
    t = parse_node('span(1, 2, "t", at: x, flag: true,)')
    assert t.args == (Int(1), Int(2), Str("t"))
    assert t.named == (("at", Name("x")), ("flag", Bool(True)))
    assert t.get("flag") == Bool(True) and t.get("nope") is None
    assert parse_node("[a, [1, 2.0], ]") == List((Name("a"), List((Int(1), Real("2.0")))))


def test_comments_and_documents():
    terms = parse("# a document\nkoine(1)  # the version\n\nbody()\n")
    assert terms == (Term("koine", (Int(1),)), Term("body"))


@pytest.mark.parametrize("text, where, what", [
    ("f(x", "1:4", "expected ')'"),
    ("f(a: 1, 2)", "1:9", "positional argument after a named one"),
    ("f(a: 1, a: 2)", "1:9", "given twice"),
    ("01", "1:1", "malformed number '01'"),
    ("1.5x", "1:1", "malformed number"),
    ("x ::y", "1:3", "expected a term, found ':'"),
    ('"tab\there"', "1:1", "unexpected"),
    ("\n\n  ?", "3:3", "unexpected '?'"),
])
def test_refusals_name_the_line_and_column(text, where, what):
    with pytest.raises(KoineSyntaxError) as caught:
        parse(text)
    assert str(caught.value).startswith(where) and what in str(caught.value)


def test_parse_node_wants_exactly_one():
    with pytest.raises(KoineSyntaxError, match="expected one term, found 2"):
        parse_node("a b")


SAMPLE = parse_node(
    'statement::bind(total, operator::binary::addition(operator::binary::multiplication('
    'alpha, value::index(xs, 0)), -1.5), at: span(3, 3, "total = alpha * xs[0] - 1.5"))')


def test_printers_reparse_to_the_same_terms():
    assert " " not in compact(SAMPLE).replace('"total = alpha * xs[0] - 1.5"', "")
    assert parse_node(compact(SAMPLE)) == SAMPLE
    assert parse_node(inline(SAMPLE)) == SAMPLE
    assert parse_node(pretty(SAMPLE, width=40)) == SAMPLE
    text = pretty(SAMPLE, width=40)
    assert text.splitlines()[0] == "statement::bind("
    assert all(len(line) <= 40 or '"' in line for line in text.splitlines())


def test_a_single_identifier_term_keeps_its_parentheses():
    assert compact(Term("f")) == "f()"
    assert compact(Term("constant::pi")) == "constant::pi"


def test_format_document_is_one_term_per_group():
    terms = (Term("koine", (Int(1),)), Term("body", (SAMPLE,)))
    text = format_document(terms)
    assert text.startswith("koine(1)\nbody(\n") and text.endswith(")\n")
    assert parse(text) == terms
