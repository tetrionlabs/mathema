# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Clarity orders realistic functions the way a developer expects.

The scenarios in `tests/fixtures/clarity_scenarios.py` are grouped in
families whose order is clear before any score is computed: more stated
knowledge scores higher, a proof above a holds above nothing, a claim
over a few points below one over a range below one over everything.
These tests pin each family's order and the properties the score keeps,
never an exact score.
"""
import importlib.util
import pathlib
import sys

import pytest

_PATH = pathlib.Path(__file__).parent / "fixtures" / "clarity_scenarios.py"


def _load():
    spec = importlib.util.spec_from_file_location("clarity_scenarios", _PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["clarity_scenarios"] = module
    spec.loader.exec_module(module)
    return module


S = _load()
_IDS = [s[0] for s in S.SCENARIOS]


@pytest.fixture(scope="module")
def scores():
    return {sid: S.clarity_of(sid) for sid in _IDS}


@pytest.mark.parametrize("family", sorted(S.FAMILIES))
def test_each_family_scores_in_the_expected_order(family, scores):
    order = S.FAMILIES[family]
    assert S.order_holds(order, scores), {
        sid: scores[sid] for group in order if group not in ("<", "<=")
        for sid in (group if isinstance(group, tuple) else (group,))}


def _rows(sid):
    return next(s[2] for s in S.SCENARIOS if s[0] == sid)


@pytest.mark.parametrize("sid", [sid for sid in _IDS if _rows(sid)])
def test_adding_a_verified_claim_never_lowers_clarity(sid, scores):
    rows = _rows(sid)
    for i in range(len(rows)):
        assert S.clarity_of(sid, rows[:i] + rows[i + 1:]) <= scores[sid], i


@pytest.mark.parametrize("sid", [sid for sid in _IDS if _rows(sid)])
def test_proven_scores_at_least_holds_and_holds_at_least_unknown(sid):
    def graded(verdict, route):
        return S.clarity_of(sid, [dict(row, verdict=verdict, route=route)
                                  for row in _rows(sid)])
    proven = graded("proven", "derive")
    held = graded("holds", "probe")
    unknown = graded("unknown", "probe")
    assert proven >= held >= unknown


@pytest.mark.parametrize("bare, stated", S.STATED_PAIRS)
def test_a_domain_stated_on_the_function_never_scores_lower(bare, stated,
                                                            scores):
    assert scores[stated] >= scores[bare]


def test_a_pure_total_helper_fully_claimed_reads_near_full(scores):
    assert scores["H2 lerp, fully claimed"] >= 90


def test_only_an_unverified_callee_keeps_the_caller_below_full(scores):
    assert scores["V1 callee unverified"] < 100
    assert scores["V2 callee defined, proven"] == 100
    assert scores["V3 callee identity, proven"] == 100


def test_the_scores_are_deterministic(scores):
    assert {sid: S.clarity_of(sid) for sid in _IDS} == scores
