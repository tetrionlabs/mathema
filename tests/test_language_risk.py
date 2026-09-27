# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A language domain is a risk factor like a wide interval: the hazards
a parameter's language brings are cases a fixed trial count must cover,
so `_structural_risk` names a `language` factor sized to them (one unit
per `language_hazards_per_unit` hazards, capped at `max_language_risk`),
the starting budget grows with it up front, and the confidence score is
penalised for it. When a language's lap of hazards is still longer than
the budget, the budget is raised to the lap and the sampling line says
so. A written language and an inferred one count alike; a claim with no
language has no `language` factor at all."""
import math
import textwrap
from dataclasses import dataclass

import pytest

import mathema.languages as languages
from mathema.analysis import analyze_source
from mathema.conjecture import check_conjectures, claim
from mathema.domain import parse_binding
from mathema.languages import (HazardValue, StringLanguage, register_language,
                               unregister_language)
from mathema.probing import (_N_BASE, _N_MAX, _RISK, _probe_density, _starting_budget,
                             _structural_risk)


@dataclass(frozen=True)
class _Extra(StringLanguage):
    """Every string, with `extra` more hazards."""

    extra: int = 0

    def hazards(self):
        more = tuple(HazardValue("text", f"w{i}", "a word") for i in range(self.extra))
        return super().hazards() + more


PLAIN = _Extra("plain", char_ok=lambda c: True, pool="abc")
CROWDED = _Extra("crowded", char_ok=lambda c: True, pool="abc", extra=40)
HUGE = _Extra("huge", char_ok=lambda c: True, pool="abc", extra=400)


@pytest.fixture
def langs():
    for lang in (PLAIN, CROWDED, HUGE):
        register_language(lang.name, lang)
    try:
        yield
    finally:
        for lang in (PLAIN, CROWDED, HUGE):
            unregister_language(lang.name)


def flag(s):
    """Whether s is the needle."""
    return 1 if s == "needle" else 0


def nonlinear(x):
    """A square."""
    return x * x


def _bound(text):
    return parse_binding(f"s in {text}")[1]


def _units(language):
    return math.ceil(len(language.hazards()) / _RISK.language_hazards_per_unit)


def test_a_language_is_a_risk_factor_sized_to_its_hazards(langs):
    facts = analyze_source(flag)
    plain = _structural_risk(facts, {"s": _bound("L[plain]")})
    crowded = _structural_risk(facts, {"s": _bound("L[crowded]")})
    assert plain["language"] == _units(PLAIN) >= 1
    assert crowded["language"] == min(_units(CROWDED), _RISK.max_language_risk)
    assert crowded["language"] > plain["language"]


def test_the_factor_is_capped(langs):
    huge = _structural_risk(analyze_source(flag), {"s": _bound("L[huge]")})
    assert huge["language"] == _RISK.max_language_risk


def test_excluded_hazards_do_not_count(langs):
    words = {f'"w{i}"' for i in range(40)}
    text = "L[crowded] \\ {" + ", ".join(sorted(words)) + "}"
    risk = _structural_risk(analyze_source(flag), {"s": _bound(text)})
    assert risk["language"] == _units(PLAIN)


def test_a_claim_with_no_language_has_no_language_factor():
    risk = _structural_risk(analyze_source(nonlinear), {"x": (0.0, 1.0)})
    assert "language" not in risk


def test_the_budget_grows_with_the_language_up_front():
    risk = {"branches": 0, "loops": 0, "params": 0, "wide_domain": 0,
            "float_extremes": 0, "language": 2}
    assert _starting_budget(risk, affine=False) == \
        min(_N_MAX, _N_BASE + 2 * _RISK.budget_step_per_unit)
    assert _starting_budget(risk, affine=True) > _RISK.affine_budget


def test_the_confidence_score_is_penalised_for_a_language():
    base = {"branches": 1, "loops": 0, "params": 0, "wide_domain": 0, "float_extremes": 0}
    with_language = {**base, "language": 2}
    assert _probe_density(with_language, _N_BASE)["score"] == pytest.approx(
        _probe_density(base, _N_BASE)["score"] - 2 * _RISK.language_penalty)
    assert _probe_density(with_language, _N_BASE)["factors"]["language"] == 2


def test_a_written_language_sets_the_budget_and_the_confidence(langs):
    (p,) = check_conjectures(flag, [claim('for s in L[crowded], f(s) == 0', route="probe")])
    assert p.verdict == "holds", (p.verdict, p.note)
    units = min(_units(CROWDED), _RISK.max_language_risk)
    assert p.meta["mathema.confidence"]["factors"]["language"] == units
    assert p.n == _starting_budget({"branches": 0, "loops": 0, "params": 0,
                                    "wide_domain": 0, "float_extremes": 0,
                                    "language": units}, affine=False)
    assert "every hazard" not in p.meta["mathema.sampling"]


def test_a_lap_longer_than_the_budget_raises_it_and_says_so(langs):
    (p,) = check_conjectures(flag, [claim('for s in L[huge], f(s) == 0', route="probe")])
    assert p.verdict == "holds", (p.verdict, p.note)
    lap = len(HUGE.hazards())
    budget = _starting_budget({"branches": 0, "loops": 0, "params": 0, "wide_domain": 0,
                               "float_extremes": 0, "language": _RISK.max_language_risk},
                              affine=False)
    assert p.n == lap > budget
    assert f"n raised to {lap} to visit every hazard (budget {budget})" \
        in p.meta["mathema.sampling"], p.meta["mathema.sampling"]


class _Entry:
    def __init__(self, name, value, obj):
        self.name, self.value, self._obj = name, value, obj

    def load(self):
        return self._obj


def test_an_inferred_language_counts_alike(tmp_path, monkeypatch, langs):
    def adapt(obj):
        return CROWDED if obj is str else None

    monkeypatch.setattr(languages, "_discovered_adaptors",
                        lambda: (_Entry("text", "pkg.mod:adapt", adapt),))
    languages._loaded_adaptors.cache_clear()
    try:
        import importlib.util
        path = tmp_path / "risk_infer.py"
        path.write_text(textwrap.dedent('''
            def flag(s: str) -> int:
                """Whether s is the needle."""
                return 1 if s == "needle" else 0
        '''))
        spec = importlib.util.spec_from_file_location("risk_infer", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        (p,) = check_conjectures(mod.flag, [claim("f(s) <= 1", route="probe")])
    finally:
        languages._loaded_adaptors.cache_clear()
    assert p.verdict == "holds", (p.verdict, p.note)
    assert p.meta["mathema.confidence"]["factors"]["language"] == \
        min(_units(CROWDED), _RISK.max_language_risk)
