# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Every law `claims/koine_record_ported.claims.yaml` states holds over
its stated domain, on the KOINE route: a record language is a subset of
itself, of its union with another and around their intersection, and
disjoint from its complement; inclusion is transitive; a term and its
canonical form hold the same values; a text of any character is found;
a value the solver gives that the interpreter does not place, and no
answer from the solver, are both no answer; and numbers are told from
truth values.

Each statement is run over every point of its domain where there are at
most `SWEEP` of them, else `SWEEP` points spread evenly across it."""
import importlib.util
import itertools
import pathlib
import re

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
CLAIMS = yaml.safe_load((ROOT / "claims" / "koine_record_ported.claims.yaml")
                        .read_text(encoding="utf-8"))
SWEEP = 1000


def _support():
    spec = importlib.util.spec_from_file_location(
        "koine_record_ported_support", ROOT / "claims" / "koine_record_ported_support.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SUPPORT = _support()


def _points(statement: str) -> list:
    domains = [[int(x) for x in found.split(", ")]
               for found in re.findall(r"in \{([0-9, ]+)\}", statement)]
    points = list(itertools.product(*domains))
    return points[::max(1, len(points) // SWEEP)]


def test_each_index_set_is_as_long_as_its_catalogue():
    assert len(CLAIMS) == 8
    sizes = {"a_term_equals_its_canonical_form": len(SUPPORT.TERMS),
             "a_text_of_any_character_is_found": len(SUPPORT.TEXTS),
             "the_solver_tells_numbers_from_booleans": len(SUPPORT.SCALARS) ** 2}
    for name, size in sizes.items():
        statement = CLAIMS[f"claims.koine_record_ported_support.{name}"]["claims"][0]["statement"]
        assert len(_points(statement)) == size, name


@pytest.mark.parametrize("target", sorted(CLAIMS), ids=lambda t: t.rsplit(".", 1)[1])
def test_a_law_of_the_claims_file_holds_over_its_domain(target):
    pytest.importorskip("z3")
    law = getattr(SUPPORT, target.rsplit(".", 1)[1])
    for claim in CLAIMS[target]["claims"]:
        broken = [point for point in _points(claim["statement"]) if law(*point) is not True]
        assert broken[:3] == [], claim["name"]
