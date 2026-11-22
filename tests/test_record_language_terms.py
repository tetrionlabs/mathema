# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A record-language definition has the canonical text and hash its
vectors state, a document outside the schema is refused, every law the
claims file states of the module holds on the catalogues it is stated
over, and the question the term is for is answered: a nested record
is inside a wider one, and the child with one flag widened
is not, by a value `member` places.

The vectors are literals in `tests/data/record_language_vectors.json`.
The laws are the statements of `tests/claims/record_language_oracle.claims.yaml`,
each run here over its stated domain: every point where there are at
most `SWEEP` of them, else `SWEEP` points spread evenly across it. The
claims file is where a law is run over all of its domain."""
import importlib.util
import itertools
import json
import pathlib
import re

import pytest
import yaml

from tests import _record_language_oracle as record_language

ROOT = pathlib.Path(__file__).resolve().parent.parent
VECTORS = json.loads((ROOT / "tests" / "data" / "record_language_vectors.json")
                     .read_text(encoding="utf-8"))["vectors"]
VALID = [v for v in VECTORS if not v.get("invalid")]
INVALID = [v for v in VECTORS if v.get("invalid")]
CLAIMS = yaml.safe_load((ROOT / "tests" / "claims" / "record_language_oracle.claims.yaml").read_text(encoding="utf-8"))
SWEEP = 1000


def _support():
    spec = importlib.util.spec_from_file_location(
        "record_language_oracle_support",
        ROOT / "tests" / "claims" / "record_language_oracle_support.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SUPPORT = _support()
def test_the_vector_file_holds_what_it_is_expected_to():
    assert (len(VALID), len(INVALID)) == (79, 36)
    assert len(CLAIMS) == 49


@pytest.mark.parametrize("vector", VALID, ids=[v["name"] for v in VALID])
def test_a_valid_document_has_the_stated_canonical_text_and_hash(vector):
    assert record_language.canonical_text(vector["document"]) == vector["canonical"]
    assert record_language.term_hash(vector["document"]) == vector["hash"]
    record_language.validate(vector["document"])


@pytest.mark.parametrize("vector", INVALID, ids=[v["name"] for v in INVALID])
def test_a_document_outside_the_schema_is_refused(vector):
    for read in (record_language.validate, record_language.canonical_text, record_language.term_hash):
        with pytest.raises(record_language.InvalidTerm):
            read(vector["document"])


def test_a_value_that_json_cannot_carry_is_refused_in_a_choice():
    for values in ((1, 2), [float("nan")], [float("inf")]):
        with pytest.raises(record_language.InvalidTerm):
            record_language.canonical({"op": "choice", "values": values})


def _points(statement: str) -> list:
    domains = [[int(x) for x in found.split(", ")]
               for found in re.findall(r"in \{([0-9, ]+)\}", statement)]
    points = list(itertools.product(*domains))
    return points[::max(1, len(points) // SWEEP)]


@pytest.mark.parametrize("target", sorted(CLAIMS), ids=lambda t: t.rsplit(".", 1)[1])
def test_a_law_of_the_claims_file_holds_over_its_domain(target):
    name = target.rsplit(".", 1)[1]
    law = getattr(SUPPORT, name)
    for claim in CLAIMS[target]["claims"]:
        broken = [point for point in _points(claim["statement"]) if law(*point) is not True]
        assert broken[:3] == [], claim["name"]


def test_a_nested_record_is_inside_a_wider_one():
    pytest.importorskip("z3")
    from mathema.koine import record_relations
    child, parent, widened = SUPPORT.CHILD, SUPPORT.PARENT, SUPPORT.WIDENED
    exact = SUPPORT._exact
    assert record_relations.decide("subset", exact(child), exact(parent)).verdict == "proven"
    decided = record_relations.decide("subset", exact(widened), exact(child))
    assert decided.verdict == "falsified"
    found = decided.witness["value"]
    assert record_language.member(widened, found)
    assert not record_language.member(child, found)
    assert found["publish"] is True
