# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Field names and texts the record-language term reads exactly: a
field's name never makes it the same solver variable as another value,
a text is never changed by the canonical form, and a node that is not
of the schema is refused as one."""
import pytest

from mathema import record_language as rl
from mathema.regular import InvalidTerm


#: an astral character written as the two surrogates that encode it in UTF-16
PAIR = chr(0xD83D) + chr(0xDE00)


def choice(*values):
    return {"op": "choice", "values": list(values)}


def record(*fields):
    return {"op": "record", "fields": [list(f) for f in fields], "rest": {"op": "empty"}}


def exact(node):
    return {"kind": rl.KIND, "version": rl.VERSION, "exact": True, "language": node}


@pytest.mark.parametrize("node, value", [
    (record(["a.b", choice(1), True], ["a", record(["b", choice(2), True]), True]),
     {"a.b": 1, "a": {"b": 2}}),
    (record(["x[0]", choice(4), True],
            ["x", {"op": "list", "item": choice(3), "min": 1, "max": 1}, True]),
     {"x[0]": 4, "x": [3]}),
    (record(["\x00", choice(1), True]), {"\x00": 1}),
    (record(["", choice(1), True], ["\x00", choice(2), True]), {"": 1, "\x00": 2}),
    (record(["a", choice(1), True], ["a\x00zzz", choice(2), True]), {"a": 1, "a\x00zzz": 2}),
    (record(["a kind", choice(True), True], ["a", choice(1), True]), {"a kind": True, "a": 1}),
    (record(["'a'", choice(1), True], ["a", record(["'", choice(2), True]), True]),
     {"'a'": 1, "a": {"'": 2}}),
])
def test_a_record_whose_field_names_look_like_paths_has_its_member_found(node, value):
    pytest.importorskip("z3")
    assert rl.member(node, value)
    found = rl.find_member([node], [])
    assert found.status == "member", found
    assert rl.member(node, found.member)


def test_a_found_member_is_told_from_a_value_with_a_dotted_name():
    pytest.importorskip("z3")
    node = record(["a.b", choice(1), True], ["a", record(["b", choice(2), True]), True])
    other = record(["a.b", choice(7), True], ["a", record(["b", choice(2), True]), True])
    found = rl.find_member([node], [other])
    assert found.status == "member", found
    assert rl.member(node, found.member) and not rl.member(other, found.member)


@pytest.mark.parametrize("text", [PAIR, "\ud800", "a\udfffb"])
def test_a_text_holding_a_surrogate_is_refused_where_json_cannot_keep_it(text):
    with pytest.raises(InvalidTerm, match="surrogate"):
        rl.canonical(choice(text))
    with pytest.raises(InvalidTerm, match="surrogate"):
        rl.canonical(record([text, choice(1), True]))
    with pytest.raises(InvalidTerm, match="surrogate"):
        rl.term_hash(exact(choice(text)))


def test_an_astral_character_is_kept_by_the_canonical_form():
    node = choice("\U0001F600", "a")
    assert sorted(rl.canonical(node)["values"]) == ["a", "\U0001F600"]
    assert rl.member(node, "\U0001F600") and not rl.member(node, PAIR)
    assert rl.canonical(rl.canonical(node)) == rl.canonical(node)


@pytest.mark.parametrize("node", [
    choice(10 ** 5000),
    {"op": "list", "item": {"op": "any"}, "min": 0, "max": 10 ** 5000},
    {"op": ["choice"], "values": [1]},
    {"op": {"choice": 1}},
    {"op": None},
])
def test_a_node_out_of_the_schema_is_refused_as_an_invalid_term(node):
    with pytest.raises(InvalidTerm):
        rl.canonical_text(exact(node))
