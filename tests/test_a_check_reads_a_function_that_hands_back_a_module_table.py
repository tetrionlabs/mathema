# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Examining a function follows where each value it hands back comes
from, and a value read from module state is that object itself, whatever
it holds: a dict, a list, an array. Two such origins are the same only
when they are the same object, so a function that may hand back one of
several module tables, or one of several arrays, is examined like any
other, and the claim about it gets a verdict."""
import numpy as np

import mathema
from mathema import check
from mathema._examine import examine
from mathema.conjecture import claim

TABLE = {"a": 1}
OTHER = {"b": 2}
ROW = [1.0, 2.0]
LEFT = np.array([1.0, 2.0])
RIGHT = np.array([1.0, 3.0])


def either_table(flag: bool) -> dict:
    return TABLE if flag else OTHER


def any_table(flag: bool) -> dict:
    return flag and TABLE or OTHER


def tables_and_more(flag: bool) -> list:
    rest = [flag]
    return [*rest, TABLE, OTHER, ROW]


def either_array(flag: bool):
    return LEFT if flag else RIGHT


def same_table_twice(flag: bool) -> dict:
    return TABLE if flag else TABLE


def test_a_function_handing_back_one_of_two_module_dicts_is_examined():
    (origin,) = examine(either_table).returns
    assert origin[0] == "may", origin
    assert [o[1] for o in origin[1]] == [TABLE, OTHER], origin
    assert origin[1][0][1] is TABLE and origin[1][1][1] is OTHER


def test_an_and_or_choice_between_module_dicts_is_examined():
    (origin,) = examine(any_table).returns
    assert origin[0] == "may", origin
    assert origin[1][-1][1] is OTHER, origin


def test_module_lists_and_dicts_held_in_a_starred_list_are_examined():
    found = examine(tables_and_more)
    assert found.returns, found.returns


def test_two_arrays_with_equal_elements_are_still_two_origins():
    found = examine(either_array)
    (origin,) = found.returns
    assert origin[0] == "may" and len(origin[1]) == 2, origin
    assert origin[1][0][1] is LEFT and origin[1][1][1] is RIGHT


def test_the_same_module_table_on_both_paths_is_one_origin():
    found = examine(same_table_twice)
    (origin,) = found.returns
    assert origin[0] == "value" and origin[1] is TABLE, origin


def test_a_ground_claim_on_select_codes_gets_a_verdict():
    rows = {p.name: p for p in check(mathema.reason_codes.select_codes,
                                     claims=[claim('f("no-such") == {}', name="g")]).probes}
    assert rows["g"].verdict == "proven", (rows["g"].verdict, rows["g"].note)


def test_a_ground_claim_on_to_latex_gets_a_verdict():
    text = r'f("f(x) <= 1") == r"f{\left(x \right)} \leq 1"'
    rows = {p.name: p for p in check(mathema.grammar.to_latex,
                                     claims=[claim(text, name="g")]).probes}
    assert rows["g"].verdict == "holds", (rows["g"].verdict, rows["g"].note)


def test_an_examination_that_stops_leaves_no_empty_reading_behind(monkeypatch):
    from mathema import _examine

    def written(flag: bool) -> None:
        TABLE["a"] = 2

    def stops(self):
        raise RuntimeError("stopped")
    monkeypatch.setattr(_examine._Examiner, "run", stops)
    try:
        examine(written)
    except RuntimeError:
        pass
    monkeypatch.undo()
    assert examine(written).writes, "the second reading must see the write"


def table_chosen_in_a_loop(flag: bool) -> int:
    t = TABLE
    for _ in range(2):
        t = OTHER if flag else t
    t["z"] = 1
    return 0


def test_an_object_that_may_be_one_of_two_tables_names_each_once():
    (write,) = examine(table_chosen_in_a_loop).unknown_writes
    assert write.text == ("table_chosen_in_a_loop changes an object that may "
                          "be the module-level TABLE or the module-level OTHER "
                          "(t['z'] = ...)"), write.text
