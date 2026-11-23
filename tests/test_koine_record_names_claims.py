# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Every law `claims/koine_record_names.claims.yaml` states holds at
every point of its domain: on the KOINE route, field names that look
like paths, quotes or nothing at all are told apart, at one place and
nested, and a question drawn from a seed over records named so has the
answer the oracle's enumerator gives.

The seeded law runs over the seeds its claim states. With the
environment variable `MATHEMA_FUZZ_FULL` set, it also runs over every
seed below `FULL_SEEDS`, the size the fuzz was first run at, and a seed
that breaks it is reported with the smallest question it shrinks to."""
import importlib.util
import itertools
import os
import pathlib
import re

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
CLAIMS = yaml.safe_load((ROOT / "claims" / "koine_record_names.claims.yaml")
                        .read_text(encoding="utf-8"))
FULL_SEEDS = 3000
SEEDED = "a_question_over_weird_names_agrees_with_the_enumerator"


def _support():
    spec = importlib.util.spec_from_file_location(
        "koine_record_names_support", ROOT / "claims" / "koine_record_names_support.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SUPPORT = _support()


def _points(statement: str) -> list:
    domains = [[int(x) for x in found.split(", ")]
               for found in re.findall(r"in \{([0-9, ]+)\}", statement)]
    return list(itertools.product(*domains))


def test_each_index_set_is_as_long_as_its_catalogue():
    assert len(CLAIMS) == 4
    statement = CLAIMS[f"claims.koine_record_names_support.{SEEDED}"]["claims"][0]["statement"]
    assert len(_points(statement)) == 300
    statement = CLAIMS["claims.koine_record_names_support.a_text_field_of_any_name_is_found"][
        "claims"][0]["statement"]
    assert len(_points(statement)) == len(SUPPORT.NAMES)


def _failures(law, points) -> list:
    broken = [point for point in points if law(*point) is not True]
    if law.__name__ == SEEDED:
        return [(point, SUPPORT.shrunk(*point)) for point in broken[:1]] + broken[1:3]
    return broken[:3]


@pytest.mark.parametrize("target", sorted(CLAIMS), ids=lambda t: t.rsplit(".", 1)[1])
def test_a_law_of_the_claims_file_holds_over_its_domain(target):
    pytest.importorskip("z3")
    law = getattr(SUPPORT, target.rsplit(".", 1)[1])
    for claim in CLAIMS[target]["claims"]:
        assert _failures(law, _points(claim["statement"])) == [], claim["name"]


@pytest.mark.skipif(not os.environ.get("MATHEMA_FUZZ_FULL"),
                    reason="the full fuzz runs only with MATHEMA_FUZZ_FULL set")
def test_the_seeded_question_holds_at_its_full_size():
    pytest.importorskip("z3")
    law = getattr(SUPPORT, SEEDED)
    assert _failures(law, [(seed,) for seed in range(FULL_SEEDS)]) == []
