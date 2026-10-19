# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A function with no retrievable source (defined through `exec` or
`python -c`) is still checked: every built-in claim either runs against
the live function or says it cannot be read, and none of them ends the
check with an error. is_language_defined reads the body only to tell a
validating guard from an unguarded crash; without a body, a run with no
accidental raise holds as it would on a sourced function, and an
accidental raise is unknown with the reason, never falsified."""
import pytest

import mathema
from mathema.conjecture import InvalidConjecture
from mathema.families import families

SOURCE = '''
def first_char(s: str) -> str:
    return s[0] if s else ""


def head(s: str) -> str:
    return s[0]


def mixed(s: str, x: float, xs: list[float]) -> float:
    return float(len(s)) + x + sum(xs)
'''


def head(s: str) -> str:
    return s[0]


def _sourceless(name):
    ns: dict = {"__name__": "sourceless_module"}
    exec(compile(SOURCE, "<sourceless>", "exec"), ns)
    return ns[name]


def _row(fn, text):
    rows = mathema.check(fn, claims=[text]).probes
    (row,) = [p for p in rows if p.name.startswith("is_language_defined")]
    return row


def test_a_sourceless_function_with_no_accidental_raise_holds():
    row = _row(_sourceless("first_char"), "is_language_defined(s)")
    assert row.verdict == "holds", (row.verdict, row.note, row.counterexample)


def test_a_sourceless_accidental_raise_is_unknown_with_the_reason():
    row = _row(_sourceless("head"), "is_language_defined(s)")
    assert row.verdict == "unknown", (row.verdict, row.note, row.counterexample)
    assert row.counterexample is None
    assert "IndexError" in row.note, row.note
    assert "no Python source" in row.note, row.note


def test_the_same_raise_on_a_sourced_function_is_falsified():
    row = _row(head, "is_language_defined(s)")
    assert row.verdict == "falsified", (row.verdict, row.note)
    assert "IndexError" in row.counterexample


@pytest.mark.parametrize("name", sorted(families()))
def test_every_family_runs_on_a_sourceless_function(name):
    fn = _sourceless("mixed")
    texts = []
    for target in ("s", "x", "xs", "f"):
        try:
            mathema.claim(f"{name}({target})")
        except InvalidConjecture:
            continue
        texts.append(f"{name}({target})")
    if not texts:
        pytest.skip(f"{name} has no bare `{name}(p)` spelling")
    rows = mathema.check(fn, claims=texts).probes
    assert rows
