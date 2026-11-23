# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Every spelling Python gives a string literal stores and reads back.

Adjacent literals are one value (`'a' 'b'` is `"ab"`, `'it''s'` is
`"its"`), a triple-quoted literal is the value between its quotes, and
a raw literal keeps its backslashes (`r'\\x41'` is a backslash, an x,
a 4 and a 1). The stored text writes that one value in its stored
spelling, and reading the stored text back gives the same value.
"""
import ast

import pytest

from mathema.conjecture import claim
from mathema.spec import canonical_claim_text


@pytest.mark.parametrize("written, value, stored", [
    ("f(x) = 'a' 'b'", "ab", 'f(x) = "ab"'),
    ("f(s) = 'it''s'", "its", 'f(s) = "its"'),
    ("f(x) = '''a'''", "a", 'f(x) = "a"'),
    ('f(x) = """a "b" c"""', 'a "b" c', "f(x) = 'a \"b\" c'"),
    ("f(x) = r'\\x41'", "\\x41", 'f(x) = "\\\\x41"'),
    ("f(x) = r'a\\'b'", "a\\'b", 'f(x) = "a\\\\\'b"'),
    ("f(x) = u'a'", "a", None),
    ("f(x, 'a' \"b\") = 1", "ab", 'f(x, "ab") = 1'),
])
def test_a_literal_stores_as_its_one_value_and_reads_back(written, value, stored):
    text = canonical_claim_text(claim(written))
    assert stored is None or text == stored
    back = claim(text)
    literals = [n.value for side in (back.lhs, back.rhs)
                for n in ast.walk(ast.parse(side, mode="eval"))
                if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    assert literals == [value], (text, literals)
    assert canonical_claim_text(back) == text
