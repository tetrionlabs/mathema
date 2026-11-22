# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The law `claims/koine_record_catalogue.claims.yaml` states holds at
every point of its domain: the KOINE claims leave out of the oracle's
catalogue exactly the terms holding a list node, each of which the route
declines by name, and no term for any other reason."""
import importlib.util
import itertools
import pathlib
import re

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
CLAIMS = yaml.safe_load((ROOT / "claims" / "koine_record_catalogue.claims.yaml")
                        .read_text(encoding="utf-8"))


def _support():
    spec = importlib.util.spec_from_file_location(
        "koine_record_catalogue_support", ROOT / "claims" / "koine_record_catalogue_support.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SUPPORT = _support()


def _points(statement: str) -> list:
    domains = [[int(x) for x in found.split(", ")]
               for found in re.findall(r"in \{([0-9, ]+)\}", statement)]
    return list(itertools.product(*domains))


def test_the_claim_ranges_over_the_whole_catalogue():
    (target,) = CLAIMS
    statement = CLAIMS[target]["claims"][0]["statement"]
    assert len(_points(statement)) == len(SUPPORT.ALL_TERMS)


def test_the_law_holds_at_every_term_of_the_catalogue():
    (target,) = CLAIMS
    law = getattr(SUPPORT, target.rsplit(".", 1)[1])
    statement = CLAIMS[target]["claims"][0]["statement"]
    assert [p for p in _points(statement) if law(*p) is not True][:3] == []
