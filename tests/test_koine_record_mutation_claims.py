# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Every law `claims/koine_record_mutation.claims.yaml` states holds
over its stated domain: the mutation sites of a membership document are
stable and addressed; a document with one site changed is valid KOINE
and another document; a change with an inverse is undone by it; and a
change moves the language the way its site says, against
`record_language.member` on the conformance vectors.

Each statement is run over every point of its domain where there are at
most `SWEEP` of them, else `SWEEP` points spread evenly across it."""
import importlib.util
import itertools
import pathlib
import re

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
CLAIMS = yaml.safe_load((ROOT / "claims" / "koine_record_mutation.claims.yaml")
                        .read_text(encoding="utf-8"))
SWEEP = 3000
#: the laws that ask the solver
SOLVER = ("a_changed_document_has_a_solver_reading",
          "only_a_dropped_part_can_lose_the_value")


def _support():
    spec = importlib.util.spec_from_file_location(
        "koine_record_mutation_support", ROOT / "claims" / "koine_record_mutation_support.py")
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
    assert len(CLAIMS) == 8


@pytest.mark.parametrize("target", sorted(CLAIMS), ids=lambda t: t.rsplit(".", 1)[1])
def test_a_law_of_the_claims_file_holds_over_its_domain(target):
    name = target.rsplit(".", 1)[1]
    if name in SOLVER:
        pytest.importorskip("z3")
    law = getattr(SUPPORT, name)
    for claim in CLAIMS[target]["claims"]:
        broken = [point for point in _points(claim["statement"]) if law(*point) is not True]
        assert broken[:3] == [], claim["name"]


def test_every_site_of_every_vector_is_within_the_index_set():
    from mathema.koine import record_mutation_sites
    counts = [len(record_mutation_sites.sites(SUPPORT._document(i)))
              for i in range(len(SUPPORT.VECTORS)) if SUPPORT._document(i) is not None]
    assert counts and max(counts) <= SUPPORT.MOST_SITES
    assert sum(counts) > 0


def test_every_change_of_every_vector_keeps_to_its_direction_at_every_value():
    law = SUPPORT.a_change_moves_the_language_the_way_its_site_says
    from mathema.koine import record_mutation_sites
    broken = []
    for i in range(len(SUPPORT.VECTORS)):
        document = SUPPORT._document(i)
        if document is None:
            continue
        for s in range(len(record_mutation_sites.sites(document))):
            broken += [(i, s, v) for v in range(len(SUPPORT.VALUES)) if law(i, s, v) is not True]
    assert broken[:3] == []
