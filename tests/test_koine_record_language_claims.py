# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Every law `claims/koine_record_language.claims.yaml` states holds
over its stated domain: of a regular language written as `language::`
terms, of the terms a function of one JSON value is written in, and of
the membership function of a record-language node as a KOINE document,
which means what `record_language.member` means.

Each statement is run over every point of its domain where there are at
most `SWEEP` of them, else `SWEEP` points spread evenly across it."""
import importlib.util
import itertools
import pathlib
import re

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
CLAIMS = yaml.safe_load((ROOT / "claims" / "koine_record_language.claims.yaml")
                        .read_text(encoding="utf-8"))
SWEEP = 2000


def _support():
    spec = importlib.util.spec_from_file_location(
        "koine_record_language_support", ROOT / "claims" / "koine_record_language_support.py")
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
    assert len(CLAIMS) == 16


@pytest.mark.parametrize("target", sorted(CLAIMS), ids=lambda t: t.rsplit(".", 1)[1])
def test_a_law_of_the_claims_file_holds_over_its_domain(target):
    law = getattr(SUPPORT, target.rsplit(".", 1)[1])
    for claim in CLAIMS[target]["claims"]:
        broken = [point for point in _points(claim["statement"]) if law(*point) is not True]
        assert broken[:3] == [], claim["name"]


def test_each_catalogue_is_as_long_as_its_index_set():
    sizes = {"a_malformed_language_term_is_refused": len(SUPPORT._malformed_language_terms()),
             "a_malformed_term_is_refused": len(SUPPORT._malformed_expressions()),
             "a_wellformed_term_is_accepted": len(SUPPORT._wellformed_expressions()),
             "a_list_is_declined_by_name": len(SUPPORT._list_terms()),
             "a_language_term_reads_back": len(SUPPORT.REGULAR),
             "a_value_is_of_one_tested_kind_or_none": len(SUPPORT.VALUES),
             "a_membership_document_is_valid": len(SUPPORT.TERMS)}
    for name, size in sizes.items():
        statement = CLAIMS[f"claims.koine_record_language_support.{name}"]["claims"][0]["statement"]
        assert len(_points(statement)) == size, name
