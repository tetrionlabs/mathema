# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Every law `claims/koine_record_question.claims.yaml` states holds
over its stated domain: the formula a KOINE function of one JSON value
is read as has the function's own truth at each value; the question
asked of membership documents has the answer `record_language` gives
the terms they were written from; and the relations between two record
languages follow from it. A nested closed record is a subset of a wider
one, and the same record with one flag widened is not, by a value both
statements of membership place.

Each statement is run over every point of its domain where there are at
most `SWEEP` of them, else `SWEEP` points spread evenly across it."""
import importlib.util
import itertools
import pathlib
import re

import pytest
import yaml

from mathema.koine import record_membership, record_relations, solver_question

ROOT = pathlib.Path(__file__).resolve().parent.parent
CLAIMS = yaml.safe_load((ROOT / "claims" / "koine_record_question.claims.yaml")
                        .read_text(encoding="utf-8"))
SWEEP = 1000


def _support():
    spec = importlib.util.spec_from_file_location(
        "koine_record_question_support", ROOT / "claims" / "koine_record_question_support.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SUPPORT = _support()


def _points(statement: str) -> list:
    domains = [[int(x) for x in found.split(", ")]
               for found in re.findall(r"in \{([0-9, ]+)\}", statement)]
    points = list(itertools.product(*domains))
    return points[::max(1, len(points) // SWEEP)]


def test_the_claims_file_holds_what_it_is_expected_to():
    assert len(CLAIMS) == 22
    assert len(SUPPORT._expressions()) == SUPPORT.EXPRESSIONS
    assert len(SUPPORT._outside_the_reading()) == SUPPORT.OUTSIDE_THE_READING


@pytest.mark.parametrize("target", sorted(CLAIMS), ids=lambda t: t.rsplit(".", 1)[1])
def test_a_law_of_the_claims_file_holds_over_its_domain(target):
    pytest.importorskip("z3")
    law = getattr(SUPPORT, target.rsplit(".", 1)[1])
    for claim in CLAIMS[target]["claims"]:
        broken = [point for point in _points(claim["statement"]) if law(*point) is not True]
        assert broken[:3] == [], claim["name"]


def test_a_nested_closed_record_is_a_subset_of_a_wider_one():
    pytest.importorskip("z3")
    record_language = SUPPORT.REF._load()
    child, parent, widened = SUPPORT.CHILD, SUPPORT.PARENT, SUPPORT.WIDENED
    inside = solver_question.find_member([record_membership.membership_document(child)],
                                         [record_membership.membership_document(parent)])
    assert inside.status == "none"
    found = solver_question.find_member([record_membership.membership_document(widened)],
                                        [record_membership.membership_document(child)])
    assert found.status == "member"
    assert found.member["publish"] is True
    assert record_language.member(widened, found.member)
    assert not record_language.member(child, found.member)
    exact = SUPPORT.REF._exact
    assert record_relations.decide("subset", exact(child), exact(parent)).verdict == "proven"
    decided = record_relations.decide("subset", exact(widened), exact(child))
    assert decided.verdict == "falsified" and decided.witness["value"]["publish"] is True


def test_without_a_solver_the_answer_is_unknown(monkeypatch):
    import builtins
    real = builtins.__import__

    def no_z3(name, *args, **kwargs):
        if name == "z3":
            raise ImportError("no z3")
        return real(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", no_z3)
    document = record_membership.membership_document({"op": "any"})
    found = solver_question.find_member([document], [])
    assert found.status == "unknown" and "z3" in found.reason
    exact = SUPPORT.REF._exact
    decided = record_relations.decide("subset", exact({"op": "any"}), exact({"op": "any"}))
    assert decided.verdict == "unknown" and "z3" in decided.reason
