# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Every law `claims/koine_record_soundness.claims.yaml` states holds at
every point of its domain: a record-language definition whose at_most
holds a value its at_least does not decides nothing on the KOINE route,
and the value it names is that one; and a witness holds no surrogate
pair where a member without one exists, while a witness that must hold
one says so."""
import importlib.util
import itertools
import pathlib
import re

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
CLAIMS = yaml.safe_load((ROOT / "claims" / "koine_record_soundness.claims.yaml")
                        .read_text(encoding="utf-8"))


def _support():
    spec = importlib.util.spec_from_file_location(
        "koine_record_soundness_support", ROOT / "claims" / "koine_record_soundness_support.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SUPPORT = _support()


def _points(statement: str) -> list:
    domains = [[int(x) for x in found.split(", ")]
               for found in re.findall(r"in \{([0-9, ]+)\}", statement)]
    return list(itertools.product(*domains))


def test_each_index_set_is_as_long_as_its_catalogue():
    assert len(CLAIMS) == 2
    sizes = {"an_inconsistent_definition_decides_nothing":
             len(SUPPORT.INCONSISTENT) * len(SUPPORT.DEFINITIONS) * len(SUPPORT.WORDS),
             "a_witness_holds_no_surrogate_pair_where_one_can_be_found":
             len(SUPPORT.TEXT_QUESTIONS)}
    for name, size in sizes.items():
        statement = CLAIMS[f"claims.koine_record_soundness_support.{name}"]["claims"][0][
            "statement"]
        assert len(_points(statement)) == size, name


@pytest.mark.parametrize("target", sorted(CLAIMS), ids=lambda t: t.rsplit(".", 1)[1])
def test_a_law_of_the_claims_file_holds_over_its_domain(target):
    pytest.importorskip("z3")
    law = getattr(SUPPORT, target.rsplit(".", 1)[1])
    for claim in CLAIMS[target]["claims"]:
        broken = [point for point in _points(claim["statement"]) if law(*point) is not True]
        assert broken[:3] == [], claim["name"]
