# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Every law `claims/koine_record_robustness.claims.yaml` states holds
over its stated domain: the KOINE route reads a text holding a
surrogate on its own as the record-language oracle does, refuses one
holding a high surrogate followed by a low one as it does, and can
hash and ask about what it reads; and a number no float holds, tested
by kind and value, never makes the solver question raise or answer
wrongly."""
import importlib.util
import itertools
import pathlib
import re

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
CLAIMS = yaml.safe_load((ROOT / "claims" / "koine_record_robustness.claims.yaml")
                        .read_text(encoding="utf-8"))


def _support():
    spec = importlib.util.spec_from_file_location(
        "koine_record_robustness_support",
        ROOT / "claims" / "koine_record_robustness_support.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SUPPORT = _support()


def _points(statement: str) -> list:
    domains = [[int(x) for x in found.split(", ")]
               for found in re.findall(r"in \{([0-9, ]+)\}", statement)]
    return list(itertools.product(*domains))


def test_the_claims_file_holds_what_it_is_expected_to():
    assert len(CLAIMS) == 2
    sizes = {"a_text_with_surrogates_is_read_as_the_oracle_reads_it":
             len(SUPPORT.SURROGATE_DOCUMENTS),
             "a_number_no_float_holds_is_never_a_wrong_answer": SUPPORT.NUMBER_EXPRESSIONS}
    for name, size in sizes.items():
        statement = CLAIMS[f"claims.koine_record_robustness_support.{name}"]["claims"][0][
            "statement"]
        assert len(_points(statement)) == size, name
    assert len(SUPPORT._number_expressions()) == SUPPORT.NUMBER_EXPRESSIONS


@pytest.mark.parametrize("target", sorted(CLAIMS), ids=lambda t: t.rsplit(".", 1)[1])
def test_a_law_of_the_claims_file_holds_over_its_domain(target):
    pytest.importorskip("z3")
    law = getattr(SUPPORT, target.rsplit(".", 1)[1])
    for claim in CLAIMS[target]["claims"]:
        broken = [point for point in _points(claim["statement"]) if law(*point) is not True]
        assert broken[:3] == [], claim["name"]
