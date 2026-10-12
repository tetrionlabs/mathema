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


@pytest.mark.parametrize("sid", S.FULLY_PROVEN)
def test_every_source_settled_by_proof_scores_exactly_100(sid, scores):
    assert scores[sid] == 100


@pytest.mark.parametrize("sid", _IDS)
def test_only_proof_of_every_source_scores_100(sid, scores):
    if scores[sid] == 100:
        assert all(row["verdict"] == "proven" for row in _rows(sid)), sid


@pytest.mark.parametrize("sid", S.FULLY_PROVEN)
def test_any_holds_or_scoped_claim_keeps_a_proven_function_below_100(sid):
    rows = _rows(sid)
    for i, row in enumerate(rows):
        held = rows[:i] + [dict(row, route="derive", verdict="holds")] + \
            rows[i + 1:]
        assert S.clarity_of(sid, held) < 100, row["name"]
    first = rows[0]
    param = first["statement"].split("f(", 1)[1].split(")")[0].split(",")[0]
    if not first["statement"].startswith("for "):
        scoped = [dict(first, statement=f"for {param} in {{{_point(sid)}}}, "
                       + first["statement"])] + rows[1:]
        assert S.clarity_of(sid, scoped) < 100


def _point(sid):
    return '"1m"' if sid.startswith(("E5", "E6")) else "1.0"


@pytest.mark.parametrize("seed", range(6))
def test_no_combination_of_claims_leaves_the_bounds(seed):
    import random

    from mathema.badges import (_clarity_profile, _reductions,
                                clarity_bits)
    rng = random.Random(seed)
    pool = [row for sid in _IDS for row in _rows(sid)]
    verdicts = [("proven", "derive"), ("holds", "probe"),
                ("holds", "probe:semi_analytical"), ("falsified", "probe"),
                ("holds", "derive:brute_force"), ("unknown", "probe")]
    for sid in rng.sample(_IDS, 5):
        fn = getattr(S, next(s[1] for s in S.SCENARIOS if s[0] == sid))
        profile = _clarity_profile(fn, library_keys=frozenset())
        for _ in range(4):
            rows = []
            for row in rng.choices(pool, k=rng.randint(1, 25)):
                verdict, route = rng.choice(verdicts)
                rows.append(dict(row, verdict=verdict, route=route,
                                 n=rng.choice([None, 1, 3, 13, 400])))
            for value in _reductions(rows, profile.pure, profile).values():
                assert 0.0 <= value <= 1.0
            h0, h_rem = clarity_bits(fn, verified_claims=rows,
                                     library_keys=frozenset())
            assert 0.0 <= h_rem <= h0
            assert 0 <= S.clarity_of(sid, rows) <= 100
