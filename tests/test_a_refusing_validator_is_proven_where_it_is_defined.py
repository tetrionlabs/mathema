# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`assuming f is defined, f(x) == x` about a refusing validator is
decided on the solver route. The reader shows the function raises
outside the language its match accepts and returns its argument inside
it, so it is defined exactly on that language, and under the premise a
breaking text would be one in the domain and in that language that the
definition does not place there; the solver is asked for one.

Only this premise is read, only on `f(x) == x`, and only for a
function read as a refusing validator: any other premise, a predicate,
a `raises` claim or a premise joined to another one is left to the
other routes."""
import pytest

import _text_validators as T

pytest.importorskip("z3")

_CLAIM = "for text in L[anytext], assuming f is defined, f(text) == text"


@pytest.fixture(autouse=True)
def served():
    T.serve()
    try:
        yield
    finally:
        T.unserve()


@pytest.mark.parametrize("fn", [T.check_slug, T.check_slug_dollar])
def test_a_refusing_validator_returns_its_argument_wherever_it_is_defined(fn):
    row = T.row(fn, _CLAIM)
    assert row.verdict == "proven", (row.verdict, row.note, row.sketch)
    assert T.on_smt(row)
    statuses = {a["statement"]: a["status"]
                for a in row.meta["mathema.assumptions"]["definitions"]}
    assert set(statuses.values()) == {"assumed"}, statuses
    assert all(a["corroboration"]["disagreed"] == 0
               for a in row.meta["mathema.assumptions"]["definitions"])
    assert f"{fn.__name__} accepts a text exactly when it is in" in " ".join(statuses)


def test_the_premise_is_said_in_the_sketch():
    row = T.row(T.check_slug, _CLAIM)
    assert "where f is defined" in row.sketch, row.sketch


def test_without_the_premise_the_same_claim_is_falsified():
    row = T.row(T.check_slug, "for text in L[anytext], f(text) == text")
    assert row.verdict == "falsified", (row.verdict, row.note)


@pytest.mark.parametrize("fn,text", [
    (T.is_person, "for actor in L[anytext], assuming f is defined, f(actor) == True"),
    (T.is_person, "for actor in L[anytext], assuming f is defined, f(actor) == False"),
    (T.check_slug, "for text in L[anytext], assuming f is defined, "
                   "raises(f(text + \"\\n\"), ValueError)"),
    (T.check_slug, "for text in L[anytext], assuming len(text) >= 1, f(text) == text"),
    (T.check_slug, "for text in L[anytext], assuming f is defined and len(text) >= 1, "
                   "f(text) == text"),
    (T.check_slug, 'for text in L[slugs], assuming f is defined, f(text + "a") == text + "a"'),
])
def test_every_other_premise_or_claim_form_is_not_decided_on_this_route(fn, text):
    row = T.row(fn, text, route="best")
    assert not T.on_smt(row), (row.verdict, row.sketch)


def test_the_route_reads_the_premise_only_for_a_refusing_validator():
    from mathema.conjecture import _validator_proof, claim
    plain = claim(_CLAIM, route="derive")
    assert _validator_proof(plain, T.check_slug, plain.domain).status == "proven"
    predicate = claim("for actor in L[anytext], assuming f is defined, f(actor) == True",
                      route="derive")
    found = _validator_proof(predicate, T.is_person, predicate.domain)
    assert found.status == "undecided"
    assert "premise" in found.sketch
