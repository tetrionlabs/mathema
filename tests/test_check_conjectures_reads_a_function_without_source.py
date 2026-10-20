# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`check_conjectures` reads a function with no retrievable source (a
function defined through `exec` or `python -c`, a method a dataclass
generates) from its signature, as `mathema.check` does, so the two
entries give the same verdict for the same claim."""
import dataclasses

import pytest

import mathema
from mathema.conjecture import check_conjectures, claim

SOURCE = '''
def double(x: float) -> float:
    return 2.0 * x


def head(s: str) -> str:
    return s[0]
'''


@dataclasses.dataclass(order=True)
class Point:
    x: float


def _sourceless(name):
    ns: dict = {"__name__": "sourceless_module"}
    exec(compile(SOURCE, "<sourceless>", "exec"), ns)
    return ns[name]


CASES = [
    ("double", "for x in [0, 1], f(x) >= 0"),
    ("double", "for x in [0, 1], f(x) <= 1"),
    ("head", "is_language_defined(s)"),
]


def _verdicts(rows, name):
    return [p.verdict for p in rows if p.name == name]


@pytest.mark.parametrize("fn_name, text", CASES)
def test_both_entries_agree_on_a_sourceless_function(fn_name, text):
    fn = _sourceless(fn_name)
    cj = claim(text)
    via_check = _verdicts(mathema.check(fn, claims=[text]).probes, cj.name)
    via_conjectures = _verdicts(check_conjectures(fn, [claim(text)]), cj.name)
    assert via_check and via_check == via_conjectures, (via_check, via_conjectures)


def test_a_sourceless_function_reads_its_kinds_from_the_signature():
    (row,) = check_conjectures(_sourceless("double"),
                               [claim("for x in [0, 1], f(x) <= 1")])
    assert row.verdict == "falsified", (row.verdict, row.note)


def test_a_method_a_dataclass_generates_is_read_from_its_signature():
    text = "f(self, other) == f(self, other)"
    cj = claim(text)
    via_check = _verdicts(mathema.check(Point.__lt__, claims=[text]).probes, cj.name)
    via_conjectures = _verdicts(check_conjectures(Point.__lt__, [claim(text)]), cj.name)
    assert via_check and via_check == via_conjectures, (via_check, via_conjectures)
