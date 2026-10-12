# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A hazard gate's raise is the hazard input's only when the same call,
that parameter at an ordinary value and every other argument held, does
not raise. When it raises there too, other draws of the other arguments
are tried; where none lets f run with the ordinary value, the row is
unknown, naming the other argument, never falsified. A falsified row
shows the raising call and the call with the ordinary value returning on its
first line, the gate's own words on the next. A function with one
parameter has nothing else to blame, and is read as before."""
import importlib.util
import math
from typing import Any

import pytest

from mathema.conjecture import check_conjectures, claim


def label(language: Any, name: str | None = None) -> str:
    kind = language.kind
    return name if name is not None else kind


def ascii_bytes(language: Any, name: str) -> bytes:
    return name.encode("ascii")


def only_ascii_bytes(name: str) -> bytes:
    return name.encode("ascii")


def only_kind(name: str) -> str:
    return name.kind


def logged(language: Any, x: float) -> float:
    k = language.kind
    return math.log(x) + k


def logged_alone(language: Any, x: float) -> float:
    return math.log(x)


def summed(language: Any, xs: list) -> float:
    k = language.kind
    return sum(xs) + k


def first(language: Any, xs: list) -> float:
    return xs[0]


# is_encoding_safe and is_length_safe come from the mathema-language package
_PACKAGE = pytest.mark.skipif(importlib.util.find_spec("mathema_language") is None,
                              reason="needs mathema-language")


def _gate(*args):
    """A parametrize entry, skipped without the package when its law names
    one of the package's gates."""
    law = next(a for a in args if isinstance(a, str) and "(" in a)
    marks = [_PACKAGE] if law.startswith(("is_encoding_safe", "is_length_safe")) else []
    return pytest.param(*args, marks=marks)


def _row(fn, law):
    (p,) = check_conjectures(fn, [claim(law)])
    return p


TEXT_GATES = [_gate("is_encoding_safe(name)"), _gate("is_length_safe(name)"),
              _gate("is_language_defined(name)")]


@pytest.mark.parametrize("law", TEXT_GATES)
def test_a_raise_another_argument_causes_leaves_a_text_gate_unknown(law):
    row = _row(label, law)
    assert row.verdict == "unknown", (row.verdict, row.counterexample, row.note)
    assert "on every draw of language tried" in row.note, row.note
    assert "the raise is not name's" in row.note, row.note


@pytest.mark.parametrize("law", [_gate("is_encoding_safe(name)"),
                                 _gate("is_language_defined(name)")])
def test_a_raise_the_hazard_causes_is_falsified_with_the_ordinary_call_shown(law):
    row = _row(ascii_bytes, law)
    assert row.verdict == "falsified", (row.verdict, row.note)
    assert "raised UnicodeEncodeError" in row.counterexample, row.counterexample
    calls, said = row.counterexample.split("\n")
    assert calls.startswith("f(language="), calls
    assert ") raises UnicodeEncodeError; with name=" in calls, calls
    assert " it returns b'" in calls, calls
    assert "raised UnicodeEncodeError" in said, said


@pytest.mark.parametrize("fn, law, raised", [
    _gate(only_ascii_bytes, "is_encoding_safe(name)", "UnicodeEncodeError"),
    _gate(only_ascii_bytes, "is_language_defined(name)", "UnicodeEncodeError"),
    _gate(only_kind, "is_encoding_safe(name)", "AttributeError"),
    _gate(only_kind, "is_length_safe(name)", "AttributeError"),
    _gate(only_kind, "is_language_defined(name)", "AttributeError"),
])
def test_a_one_parameter_function_is_read_as_before(fn, law, raised):
    row = _row(fn, law)
    assert row.verdict == "falsified", (row.verdict, row.note)
    assert f"raised {raised}" in row.counterexample, row.counterexample
    assert "; f(" not in row.counterexample, row.counterexample
    assert "; with " not in row.counterexample, row.counterexample


@pytest.mark.parametrize("fn, law", [
    (logged, "is_number_set_safe(x)"),
    (logged, "is_representation_safe(x)"),
    (summed, "is_empty_safe(xs)"),
])
def test_a_raise_another_argument_causes_leaves_a_numeric_gate_unknown(fn, law):
    row = _row(fn, law)
    assert row.verdict == "unknown", (row.verdict, row.counterexample, row.note)
    assert "on every draw of language tried" in row.note, row.note


@pytest.mark.parametrize("fn, law, raised", [
    (logged_alone, "is_number_set_safe(x)", "ValueError"),
    (first, "is_empty_safe(xs)", "IndexError"),
])
def test_a_raise_the_numeric_hazard_causes_is_falsified(fn, law, raised):
    row = _row(fn, law)
    assert row.verdict == "falsified", (row.verdict, row.note)
    assert raised in row.counterexample, row.counterexample
    calls, said = row.counterexample.split("\n")
    assert calls.startswith("f(language="), calls
    assert f") raises {raised}; with " in calls, calls
    assert " it returns " in calls, calls
    assert raised in said, said
