# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim that calls the function under test by its own name is the
same claim as one that calls it `f`: the derive route reads the call as
`f`, so a bundled parameter (a record whose fields are the symbols)
proves exactly as it does under `f`, and the statement keeps the name
the author wrote."""
from dataclasses import dataclass

from mathema.conjecture import check_conjectures, claim


@dataclass
class Config:
    a: float
    b: float


def sum_fields(cfg: Config) -> float:
    return cfg.a + cfg.b


def test_the_own_name_proves_what_f_proves():
    (by_f,) = check_conjectures(sum_fields, [claim("f(cfg) == cfg.a + cfg.b", route="derive")])
    (by_name,) = check_conjectures(sum_fields, [claim("sum_fields(cfg) == cfg.a + cfg.b",
                                                      route="derive")])
    assert by_f.verdict == "proven"
    assert by_name.verdict == "proven", by_name.note
    assert "sum_fields(cfg)" in by_name.statement


def test_the_own_name_disproves_what_f_disproves():
    (p,) = check_conjectures(sum_fields, [claim("sum_fields(cfg) == cfg.a - cfg.b",
                                                route="derive")])
    assert p.verdict != "proven", p.note
