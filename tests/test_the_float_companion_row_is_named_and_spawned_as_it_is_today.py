# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The `<name>[float]` companion row: how it is named, when a claim
spawns it, and the record fields that tie it to its claim.

Named: `<claim name>[float]`, `[complex]` for a claim over C, and a
runtime type after the descriptor. Spawned: by a claim the derive route
proves (route `derive` or `best`), not by a probe claim, a claim that
derive falsifies, or `derive:math_only`. Tied by the row's
`mathema.companion_of` and `mathema.family`, and the claim's
`mathema.float_companion`.
"""
import pytest

import mathema
from mathema.gates import (FLOAT_FAMILY, FLOAT_SUFFIX, companion_descriptor,
                           companion_name, computation_line_of)
from mathema.spec import to_spec


def doubled(x: float) -> float:
    return 2.0 * x


def conj(z: complex) -> complex:
    return 2 * z


def _rows(fn, law, route, name="law"):
    rec = mathema.check(fn, claims=[mathema.claim(law, name=name, route=route)])
    return {p.name: p for p in rec.probes}, rec


def test_the_companion_is_named_by_its_claim_and_a_bracketed_descriptor():
    assert FLOAT_SUFFIX == "[float]"
    assert FLOAT_FAMILY == "is_numerically_stable"
    assert companion_name("law") == "law[float]"
    assert companion_name("law", "complex") == "law[complex]"
    assert companion_name("law", "float, pandas.Series") == "law[float, pandas.Series]"
    assert companion_name("c0[link1]") == "c0[link1][float]"


@pytest.mark.parametrize("name,parts", [
    ("law[float]", ("float",)),
    ("law[complex]", ("complex",)),
    ("law[float, cpython3.12]", ("float", "cpython3.12")),
    ("law", ()),
    ("c0[link1][float]", ("float",)),
])
def test_a_companions_descriptor_is_read_from_its_last_bracket(name, parts):
    assert companion_descriptor(name) == parts


def test_a_row_is_a_computation_line_by_its_meta_not_its_name():
    assert computation_line_of({"mathema.companion_of": "law",
                                "mathema.family": FLOAT_FAMILY}) == "law"
    assert computation_line_of({"mathema.companion_of": "law"}) == "law"
    assert computation_line_of({"mathema.companion_of": "law",
                                "mathema.family": "is_empty_safe"}) is None
    assert computation_line_of({}) is None
    assert computation_line_of(None) is None


@pytest.mark.parametrize("route", ["derive", "best"])
def test_a_claim_the_derive_route_proves_spawns_a_float_companion(route):
    rows, _ = _rows(doubled, "for x in [-10, 10], f(x) == 2*x", route)
    assert rows["law"].verdict == "proven"
    assert rows["law"].meta["mathema.float_companion"] == "law[float]"
    comp = rows["law[float]"]
    assert comp.route == "probe"
    assert comp.meta["mathema.companion_of"] == "law"
    assert comp.meta["mathema.family"] == FLOAT_FAMILY
    assert comp.statement == rows["law"].statement


def test_a_claim_over_the_complex_numbers_spawns_a_complex_companion():
    rows, _ = _rows(conj, "for z in C, f(z) == 2*z", "derive")
    assert rows["law"].meta["mathema.float_companion"] == "law[complex]"
    assert rows["law[complex]"].meta["mathema.companion_of"] == "law"


def test_a_probe_claim_spawns_no_companion():
    rows, _ = _rows(doubled, "for x in [-10, 10], f(x) == 2*x", "probe")
    assert not [n for n in rows if n.endswith("[float]")]
    assert "mathema.float_companion" not in rows["law"].meta


def test_a_claim_derive_falsifies_spawns_no_companion():
    rows, _ = _rows(doubled, "for x in [-10, 10], f(x) == 3*x", "derive")
    assert rows["law"].verdict == "falsified"
    assert not [n for n in rows if n.endswith("[float]")]


def test_the_mathematics_only_route_states_why_it_spawns_none():
    rows, _ = _rows(doubled, "for x in [-10, 10], f(x) == 2*x", "derive:math_only")
    assert rows["law"].meta["mathema.float_companion"] == "none (derive:math_only)"
    assert "law[float]" not in rows


def test_the_record_writes_the_companion_after_its_claim_with_its_fields():
    _, rec = _rows(doubled, "for x in [-10, 10], f(x) == 2*x", "derive")
    names = [c["name"] for c in to_spec(rec)["claims"]]
    assert names.index("law[float]") == names.index("law") + 1
    row = next(c for c in to_spec(rec)["claims"] if c["name"] == "law[float]")
    assert row["route"] == "probe"
    assert row["meta"]["mathema.companion_of"] == "law"
    assert row["meta"]["mathema.family"] == FLOAT_FAMILY
