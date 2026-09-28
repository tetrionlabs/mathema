# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A record writes a missing value in a domain as the word the grammar
uses, `{"sentinel": "None"}`, `{"sentinel": "missing"}`,
`{"sentinel": "nan"}`, and reads it back; a stored `null` reads as
absence, and the `__mathema_missing__` an earlier release wrote reads as
the hole class. A path through an absent field reaches `None`."""
import json

import pytest

import mathema
from mathema.domain import (ABSENT, MISSING, Domain, domain_bound_from_json,
                            domain_bound_to_json, member, parse_binding,
                            path_values, render_domain)


def bound(text: str):
    return parse_binding(f"x in {text}")[1]


@pytest.mark.parametrize("text", ["{0.25, None}", "{missing}", "(R | {nan})^n",
                                  "[0, 1] : float|None|missing"])
def test_a_domain_round_trips_through_its_record(text):
    b = bound(text)
    stored = json.loads(json.dumps(domain_bound_to_json(b)))
    back = domain_bound_from_json(stored)
    assert back == b
    assert render_domain(back, ascii_mode=True) == render_domain(b, ascii_mode=True)
    assert "__mathema_missing__" not in json.dumps(stored)


def test_the_record_names_each_sentinel_by_its_word():
    stored = domain_bound_to_json(bound("{0.25, None, missing, nan}"))
    assert stored == {"set": [0.25, {"sentinel": "None"}, {"sentinel": "missing"},
                              {"sentinel": "nan"}]}


def test_the_older_token_and_null_read_back():
    assert domain_bound_from_json({"set": [0.25, "__mathema_missing__"]}) == \
        frozenset({0.25, MISSING})
    assert domain_bound_from_json({"set": [0.25, None]}) == frozenset({0.25, ABSENT})
    old = domain_bound_from_json({"base_type": "R", "pieces": [],
                                  "excluded": ["__mathema_missing__"],
                                  "explicit_type": False})
    assert old == Domain(excluded=frozenset({MISSING}))


def test_a_completed_domain_records_its_members_and_absence():
    def f(xs: list) -> float:
        return 1.0
    report = mathema.check(f, claims=[mathema.claim("for xs in [0, 1]^n, f(xs) >= 0",
                                                    name="c")])
    probe = next(p for p in report.probes if p.name == "c")
    stored = probe.domain["xs"]
    assert stored["members"] == ["null", "nan"]
    assert {"sentinel": "None"} in stored["excluded"]
    assert {"set": [{"sentinel": "missing"}]} in stored["pieces"]


def test_a_member_sentinel_reads_back_as_that_member():
    assert domain_bound_from_json({"set": [{"sentinel": "NA"}]}) == \
        frozenset({member("NA")})


def test_a_path_through_an_absent_field_reaches_none():
    assert path_values({"a": None}, ["a", "b"]) == [None]
    assert path_values({}, ["a"]) == [None]
    assert path_values({"a": [1, 2]}, ["a", 5]) == [None]
