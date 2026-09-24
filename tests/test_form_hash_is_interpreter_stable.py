# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A function's form hash is the same on every supported Python. The
hash is over the alpha-normalized AST, and each interpreter version
adds its own empty fields to that tree (3.12 gives every function a
`type_params=[]`), so the text that is hashed carries only the fields
that hold content: an empty list, a missing field and a None value all
read the same. A record written on one Python then reads as fresh, not
as "form changed", on another. The pinned hash below was produced on
3.10, 3.12 and 3.13 alike."""
import ast

from mathema.identity import form_hash, form_text, normalized

_SOURCE = '''
def discount_factor(x: float) -> float:
    """A discount factor that divides by one minus the rate."""
    return 1 / (1 - x)
'''


def _fdef():
    return ast.parse(_SOURCE).body[0]


def test_the_hashed_text_carries_no_empty_fields():
    text = form_text(normalized(_fdef()))
    assert "=[]" not in text
    assert "=None" not in text
    assert "type_params" not in text


def test_a_field_an_interpreter_adds_empty_does_not_change_the_text():
    tree = normalized(_fdef())
    plain = form_text(tree)
    tree.type_params = []
    tree.type_comment = None
    assert form_text(tree) == plain


def test_the_hash_is_the_one_every_supported_python_produces():
    assert form_hash(_fdef()) == "ebb4c9b87847"


def test_content_still_tells_forms_apart():
    other = ast.parse(_SOURCE.replace("1 - x", "1 + x")).body[0]
    assert form_hash(_fdef()) != form_hash(other)
