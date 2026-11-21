# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A relation between number domains is decided only on the numbers as
they are written. Where the domain holds an endpoint as a nearby
double (a whole number past 2**53, a decimal a double cannot hold, a
magnitude that underflows or overflows), where an endpoint is an
expression, or where an infinity is a member of one side by the
domain's own membership test and the set comparison cannot see it, the
relation reads unknown and says why. It is never decided on the rounded
number."""
import pytest

from mathema import claim
from mathema.conjecture import check_conjectures


def _f(x):
    return x


def _row(text):
    (row,) = check_conjectures(_f, [claim(text, route="derive")])
    return row


@pytest.mark.parametrize("text,token", [
    ("[0, 9007199254740993] : int subset [0, 9007199254740992] : int", "9007199254740993"),
    ("[9007199254740993, 9007199254740993] : int = {9007199254740992}", "9007199254740993"),
    ("(0, 1e-400) : real = {}", "1e-400"),
    ("[1e-400, 1] subset (0, 1]", "1e-400"),
    ("{0.1000000000000000055511151231257827} disjoint (0.1, 1)",
     "0.1000000000000000055511151231257827"),
    ("[0, 1e400) : real = [0, inf) : real", "1e400"),
    ("[0, 0.1] subset [0, 1]", "0.1"),
])
def test_a_number_the_domain_does_not_hold_exactly_is_not_compared(text, token):
    row = _row(text)
    assert row.verdict == "unknown", (row.verdict, row.sketch or row.counterexample)
    assert row.note == (f"`{token}` is not held exactly by the domain (it is kept as the "
                        f"nearest double), so the relation is not decided on it")


def test_a_finite_set_keeps_its_whole_numbers_exactly():
    row = _row("{9007199254740993} = {9007199254740992}")
    assert row.verdict == "falsified"
    assert "9007199254740993" in row.counterexample


@pytest.mark.parametrize("text", [
    "[0, 1/3] subset [0, 1]",
    "[0, pi] subset [0, 4]",
    "[0, 2**0.5] subset [0, 2]",
])
def test_an_endpoint_written_as_an_expression_is_not_compared(text):
    row = _row(text)
    assert row.verdict == "unknown"
    assert "is written as an expression" in row.note


@pytest.mark.parametrize("text", [
    "[0, inf] : real = [0, inf) : real",
    "[0, inf] subset [0, inf)",
    "[-inf, 0] subset (-inf, 0]",
])
def test_an_infinity_one_side_admits_and_the_other_does_not_is_not_decided(text):
    row = _row(text)
    assert row.verdict == "unknown", (row.verdict, row.sketch)
    assert "infinity" in row.note


def test_a_relation_the_set_arithmetic_cannot_carry_returns_a_verdict():
    row = _row("(-inf, 3) : int = [0, 0) : int")
    assert row.verdict in ("proven", "falsified", "unknown")


@pytest.mark.parametrize("text,verdict", [
    ("[0, 1] subset [0, 2]", "proven"),
    ("[0, 0.5] subset [0, 1]", "proven"),
    ("[0.25, 1e3] subset [0, 1000]", "proven"),
    ("Z subset R", "proven"),
    ("[0, 10] : int subset N", "proven"),
    ("[0, inf) subset R", "proven"),
    ("(-inf, 0] disjoint (0, inf)", "proven"),
    ("[0, 2] subset [0, 1]", "falsified"),
    ("[0, 9007199254740992] : int subset [0, 9007199254740992] : int", "proven"),
])
def test_numbers_a_double_holds_exactly_are_compared_as_before(text, verdict):
    assert _row(text).verdict == verdict
