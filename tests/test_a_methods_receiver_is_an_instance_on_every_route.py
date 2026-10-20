# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""An unbound method's unannotated receiver (`self`) is drawn as an
instance of its class on every route: the probe, the `is_defined`
region probe and the computation companion of a proof, never as a
number. A dataclass is built from its fields, its generated methods
included; any other class from the fields the body reads, each inside
the claim's binding of it. A receiver whose fields the body does not
show is not drawn: the claim is skipped with the reason."""
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
    def __init__(self):
        self.v = 2.0

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
