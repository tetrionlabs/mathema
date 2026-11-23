# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Every law `claims/record_term.claims.yaml` states holds over its
stated domain: the record-term document format gives each valid
conformance vector the canonical text and hash it states, refuses each
invalid one, and its canonical form and built definitions keep the
written meaning of the record-language oracle."""
import importlib.util
import itertools
import pathlib
import re

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
CLAIMS = yaml.safe_load((ROOT / "claims" / "record_term.claims.yaml").read_text(encoding="utf-8"))


def _support():
    spec = importlib.util.spec_from_file_location(
        "record_term_support", ROOT / "claims" / "record_term_support.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SUPPORT = _support()


def _points(statement: str) -> list:
    domains = [[int(x) for x in found.split(", ")]
               for found in re.findall(r"in \{([0-9, ]+)\}", statement)]
    return list(itertools.product(*domains))


def test_each_index_set_is_as_long_as_its_catalogue():
    assert len(CLAIMS) == 5
    sizes = {"a_valid_vector_has_its_canonical_text_and_hash": len(SUPPORT.VALID),
             "an_invalid_vector_is_refused": len(SUPPORT.INVALID),
             "canonical_is_idempotent": len(SUPPORT.TERMS),
             "canonical_keeps_the_written_meaning": len(SUPPORT.TERMS) * len(SUPPORT.VALUES),
             "built_definitions_keep_the_written_meaning":
                 len(SUPPORT.DEFINITIONS) ** 2 * len(SUPPORT.VALUES)}
    for name, size in sizes.items():
        statement = CLAIMS[f"claims.record_term_support.{name}"]["claims"][0]["statement"]
        assert len(_points(statement)) == size, name


@pytest.mark.parametrize("target", sorted(CLAIMS), ids=lambda t: t.rsplit(".", 1)[1])
def test_a_law_of_the_claims_file_holds_over_its_domain(target):
    law = getattr(SUPPORT, target.rsplit(".", 1)[1])
    for claim in CLAIMS[target]["claims"]:
        broken = [point for point in _points(claim["statement"]) if law(*point) is not True]
        assert broken[:3] == [], claim["name"]


def test_the_format_module_reads_no_solver():
    source = (ROOT / "mathema" / "record_term.py").read_text(encoding="utf-8")
    assert "z3" not in source and "find_member" not in source
