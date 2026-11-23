# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Every law `claims/koine_record_reading.claims.yaml` states holds over
its stated domain: the KOINE route refuses with `InvalidTerm` exactly
the record-language definitions `record_language` refuses, reads the
rest with the same members under each bound (or declines a list node
by name), and writes each node's membership in the shape the claims
file states.

Each statement is run over every point of its domain."""
import importlib.util
import itertools
import pathlib
import re

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
CLAIMS = yaml.safe_load((ROOT / "claims" / "koine_record_reading.claims.yaml")
                        .read_text(encoding="utf-8"))
#: the laws that ask the solver
SOLVER = ("a_relation_refuses_what_the_route_refuses",)


def _support():
    spec = importlib.util.spec_from_file_location(
        "koine_record_reading_support", ROOT / "claims" / "koine_record_reading_support.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SUPPORT = _support()


def _points(statement: str) -> list:
    domains = [[int(x) for x in found.split(", ")]
               for found in re.findall(r"in \{([0-9, ]+)\}", statement)]
    return list(itertools.product(*domains))


def test_the_claims_file_holds_what_it_is_expected_to():
    assert len(CLAIMS) == 4
    sizes = {"a_definition_is_refused_as_the_reference_refuses_it": len(SUPPORT.DOCUMENTS),
             "each_node_is_written_in_its_stated_shape": len(SUPPORT.SHAPED)}
    for name, size in sizes.items():
        statement = CLAIMS[f"claims.koine_record_reading_support.{name}"]["claims"][0]["statement"]
        assert len(_points(statement)) == size, name


@pytest.mark.parametrize("target", sorted(CLAIMS), ids=lambda t: t.rsplit(".", 1)[1])
def test_a_law_of_the_claims_file_holds_over_its_domain(target):
    name = target.rsplit(".", 1)[1]
    if name in SOLVER:
        pytest.importorskip("z3")
    law = getattr(SUPPORT, name)
    for claim in CLAIMS[target]["claims"]:
        broken = [point for point in _points(claim["statement"]) if law(*point) is not True]
        assert broken[:3] == [], claim["name"]
