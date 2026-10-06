# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A `str` annotation is a type fact core owns: the parameter holds
strings only, rendered `: str`, and a number is outside its domain. The
numeric families (representation, number set, pole, overflow, accuracy)
run on numbers and never on a string parameter, so a function over
strings carries no row for them; `is_language_defined` runs on strings.
`Optional[str]` admits absence like any other Optional parameter, and
`check` judges what f does at None by default."""
from typing import Optional

import pytest

import mathema
from mathema.conjecture import check_conjectures, claim, parameter_domains
from mathema.domain import domain_contains, parse_binding, render_domain
from mathema.suggest import suggest_claims


def label2(s: str) -> str:
    return s.upper()


def label(s: Optional[str]) -> str:
    return "none" if s is None else s.upper()


def scaled(s: str, x: float) -> float:
    return len(s) * x


def _names(rec):
    return {p.name for p in rec.probes}


def test_a_string_parameter_has_no_representation_row():
    names = _names(mathema.check(label2))
    assert "is_representation_safe[s]" not in names, names
    assert "is_language_defined[s]" in names
    assert not any(n.startswith("is_numerically_stable") for n in names), names


def test_a_stated_representation_claim_on_a_string_is_never_falsified():
    (p,) = check_conjectures(label2, [claim("is_representation_safe(s)")])
    assert p.verdict != "falsified", (p.verdict, p.counterexample)
    assert "0" not in (p.counterexample or "")


def test_the_numeric_families_run_on_the_number_only():
    names = _names(mathema.check(scaled))
    assert "is_representation_safe[x]" in names
    assert "is_representation_safe[s]" not in names
    suggested = {c.name for c in suggest_claims(scaled)}
    assert "is_representation_safe[s]" not in suggested
    assert "is_numerically_stable" in suggested


def test_the_type_fact_is_strings_only_and_renders_as_str():
    bound = parameter_domains(label2)["s"]
    assert render_domain(bound, ascii_mode=True) == ": str"
    assert render_domain(bound, ascii_mode=False) == ": str"
    assert domain_contains("x", bound)
    assert domain_contains("", bound)
    assert not domain_contains(0, bound)
    assert not domain_contains(0.0, bound)
    assert not domain_contains(None, bound)


def test_the_rendering_reads_back_as_the_same_domain():
    for text in (": str", ": str|absent"):
        name, bound = parse_binding(f"s in {text}")
        assert name == "s"
        assert render_domain(bound, ascii_mode=True) == text, text
        assert domain_contains("a", bound)
        assert not domain_contains(1, bound)
    assert domain_contains(None, parse_binding("s in : str|absent")[1])
    assert not domain_contains(None, parse_binding("s in : str")[1])


def test_an_optional_str_admits_absence_and_check_judges_it():
    bound = parameter_domains(label)["s"]
    assert render_domain(bound, ascii_mode=True) == ": str|absent"
    assert domain_contains(None, bound)
    rec = mathema.check(label)
    (row,) = [p for p in rec.probes if p.name == "absent[s]"]
    assert row.verdict in ("holds", "proven"), (row.verdict, row.note)
    assert row.n >= 1
    (p,) = check_conjectures(label, [claim("f(s) == f(s)")])
    assert "inferred s in : str|absent from its own Optional[str] annotation" \
        in (p.note or ""), p.note


@pytest.mark.parametrize("law", ["is_representation_safe(s)",
                                 "is_number_set_safe(s)", "is_pole_safe(s)",
                                 "is_overflow_safe(s)"])
def test_a_numeric_family_stated_on_a_string_says_why_it_does_not_run(law):
    (p,) = check_conjectures(label2, [claim(law)])
    assert p.verdict in ("unknown", "skipped"), (law, p.verdict, p.note)
    assert "string" in (p.note or ""), p.note
