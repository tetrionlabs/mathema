# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Text inside quotes in a domain is data: a bar, a backslash before a
brace and a raw-string prefix inside or before a quoted member are
never read as a union, an exclusion or a derivative prime."""
from mathema._scan import _split_commas, mask_strings, unmask_strings
from mathema.domain import parse_binding


def test_a_bar_inside_a_quoted_member_is_not_a_union():
    assert parse_binding('s in {"a|b"}') == ("s", frozenset({"a|b"}))
    assert parse_binding('s in {"a|b"} | {"c ∪ d"}') == ("s", frozenset({"a|b", "c ∪ d"}))


def test_a_backslash_brace_inside_a_quoted_member_is_not_an_exclusion():
    assert parse_binding(r's in {"a\{b}"}') == ("s", frozenset({r"a\{b}"}))
    assert parse_binding(r's in {"x", "\{y}"}') == ("s", frozenset({"x", r"\{y}"}))


def test_an_exclusion_after_a_quoted_member_still_reads():
    name, bound = parse_binding(r's in {"a", "b"} \ {"b"}')
    assert bound.excluded == frozenset({"b"})


def test_a_raw_single_quoted_string_is_a_string_not_a_prime():
    masked, literals = mask_strings("re(r'[a-z]+', x)")
    assert literals == ["r'[a-z]+'"]
    assert "'" not in masked
    assert unmask_strings(masked, literals) == "re(r'[a-z]+', x)"
    assert _split_commas("r'a,b', c") == ["r'a,b'", " c"]


def test_a_raw_string_opening_with_a_bracket_is_still_a_string():
    assert mask_strings("re(r'(a|b)+')")[1] == ["r'(a|b)+'"]


def test_a_prime_after_a_function_named_r_is_still_a_derivative():
    assert mask_strings("r'(x) + r'(y)")[1] == []
    assert mask_strings("r'(x) >= 0")[1] == []
    assert mask_strings("f'(x) + bar'(y)")[1] == []
