# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""An unbound method's unannotated receiver (`self`) is drawn as an
instance of its class on every route: the probe, the `is_defined`
region probe and the computation companion of a proof, never as a
number. It is built as the class builds one: a dataclass from its
fields (an int field as an int, its `__post_init__` run), a class with
a constructor of its own through that constructor, any other class
from the fields the body reads, each inside the claim's binding of it.
A draw the constructor refuses is outside the class, never f's raise.
A receiver mathema cannot build is not drawn: the claim is skipped
with the reason."""
from dataclasses import dataclass

import pytest

from mathema.conjecture import check_conjectures, claim
from mathema.domain import domain_contains
from mathema.probing import Instances

pytestmark = pytest.mark.filterwarnings(
    "ignore::mathema.analysis.StateDependenceWarning")


@dataclass(order=True)
class Point:
    x: float
    y: float


@dataclass
class Bond:
    face: float
    rate: float

    def simple_interest(self, n: int) -> float:
        return self.face * self.rate * n


class Scale:
    def __init__(self, k: float = 1.0):
        self.k = k

    def scaled(self, x: float) -> float:
        return self.k * x

    def shifted(self, x: float) -> float:
        return x + 1.0


class Relay:
    def __init__(self, source: list):
        self.v = float(len(source))

    def value(self) -> float:
        return self.v

    def twice(self, x: float) -> float:
        return self.value() * x


def _no_number_receiver(rows):
    for p in rows:
        shown = (p.counterexample or "").split(",")[0]
        assert not shown.startswith("self = ") or not shown[7:8].lstrip("-")[:1].isdigit(), \
            (p.name, p.counterexample)


def test_a_generated_dataclass_method_is_defined_on_its_instances():
    rows = check_conjectures(Point.__lt__, [claim("is_defined(f)")])
    _no_number_receiver(rows)
    assert rows[0].verdict == "holds", (rows[0].verdict, rows[0].counterexample)


def test_a_value_claim_on_a_generated_method_holds_on_its_instances():
    rows = check_conjectures(Point.__lt__,
                             [claim("f(self, other) == f(self, other)")])
    _no_number_receiver(rows)
    assert rows[0].verdict == "holds", (rows[0].verdict, rows[0].counterexample)


def test_the_companion_of_a_plain_class_method_runs_on_instances():
    rows = check_conjectures(Scale.scaled, [claim("f(self, x) == f(self, x)")],
                             float_companions=True)
    _no_number_receiver(rows)
    proof, companion = rows
    assert proof.verdict == "proven", (proof.verdict, proof.note)
    assert companion.verdict == "holds", (companion.verdict,
                                          companion.counterexample)
    assert companion.n > 0
    assert "self drawn as an instance of Scale" in proof.note, proof.note


def test_the_companion_draws_each_field_inside_its_binding():
    rows = check_conjectures(Bond.simple_interest, [claim(
        "for self.rate in [0.01, 0.2], self.face in [50, 100], "
        "n in [1, 10] subset Z, f(self, n) == self.face * self.rate * n")],
        float_companions=True)
    proof, companion = rows
    assert proof.verdict == "proven", (proof.verdict, proof.note)
    assert companion.verdict == "holds", (companion.verdict, companion.note)
    assert companion.n > 0


def test_a_receiver_the_body_never_reads_is_still_an_instance():
    rows = check_conjectures(Scale.shifted, [claim("f(self, x) == x + 1")],
                             float_companions=True)
    _no_number_receiver(rows)
    assert [p.verdict for p in rows] == ["proven", "holds"], \
        [(p.verdict, p.counterexample) for p in rows]


def test_a_falsified_method_names_its_receiver_as_an_instance():
    (p, *_rest) = check_conjectures(Bond.simple_interest,
                                    [claim("f(self, n) >= 0")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert p.counterexample.startswith("self = Bond("), p.counterexample


def test_a_receiver_whose_fields_are_not_shown_is_skipped_with_the_reason():
    (p,) = check_conjectures(Relay.twice, [claim("f(self, x) == f(self, x)")])
    assert p.verdict == "skipped", (p.verdict, p.counterexample)
    assert "self is the receiver, an instance of Relay" in p.note, p.note


def test_the_receivers_domain_holds_only_instances():
    instances = Instances(Scale, (("k", "float"),))
    assert not domain_contains(2.0, instances)
    assert domain_contains(Scale(), instances)


class Positive:
    def __init__(self, k: float):
        if k <= 0:
            raise ValueError("k must be positive")
        self.k = k

    def root(self) -> float:
        import math
        return math.sqrt(self.k)


@dataclass
class PositiveRecord:
    k: float

    def __post_init__(self):
        if self.k <= 0:
            raise ValueError("k must be positive")

    def root(self) -> float:
        import math
        return math.sqrt(self.k)


@dataclass
class Width:
    w: float

    def log_w(self) -> float:
        import math
        return math.log(self.w)


@dataclass
class Counter:
    n: int

    def bumped(self, k: int) -> int:
        return self.n + k


@pytest.mark.parametrize("route", ["best", "probe", "derive"])
@pytest.mark.parametrize("fn", [Positive.root, PositiveRecord.root],
                         ids=["constructor", "post_init"])
def test_a_receiver_is_built_through_its_constructor(fn, route):
    (p,) = check_conjectures(fn, [claim("is_defined(f)", route=route)])
    assert p.verdict in ("holds", "proven"), (p.verdict, p.counterexample)


@pytest.mark.parametrize("fn", [Positive.root, PositiveRecord.root],
                         ids=["constructor", "post_init"])
def test_a_constructor_refusal_is_a_draw_outside_the_class(fn):
    (p,) = check_conjectures(fn, [claim("f(self) >= 0", route="probe")])
    assert p.verdict == "holds", (p.verdict, p.counterexample)


def test_a_dataclass_receiver_witness_names_its_fields():
    (p,) = check_conjectures(Width.log_w, [claim("is_defined(f)")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert p.counterexample.startswith("self = Width(w="), p.counterexample


def test_an_int_field_of_a_receiver_is_drawn_as_an_int():
    (p,) = check_conjectures(Counter.bumped, [claim(
        "f(self, k) >= self.n - 100", route="probe")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    field = p.counterexample.split("Counter(n=", 1)[1].split(")", 1)[0]
    assert float(field).is_integer() and "." not in field and "e" not in field, \
        p.counterexample


class Doubler:
    def __init__(self):
        self.v = 2.0

    def value(self) -> float:
        return self.v

    def twice(self, x: float) -> float:
        return self.value() * x


def test_a_receiver_built_by_its_own_constructor_is_drawn():
    rows = check_conjectures(Doubler.twice, [claim(
        "for x in [-10, 10], f(self, x) == 2 * x")],
                             float_companions=True)
    _no_number_receiver(rows)
    assert rows[0].verdict in ("proven", "holds"), (rows[0].verdict,
                                                    rows[0].note)
