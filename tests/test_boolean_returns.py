# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Truth-valued functions are first-class on both routes: a body like
`return mi <= chance` lifts as the 0/1 indicator of its condition
(Python's bool IS an int), a law may claim the boolean it computes
(`f(mi, chance) == (mi <= chance)`), and a falsification of a wrong
boolean claim carries its executed witness like any other."""
import textwrap

import pytest


@pytest.fixture(scope="module")
def rules(tmp_path_factory):
    p = tmp_path_factory.mktemp("boolrules") / "rules.py"
    p.write_text(textwrap.dedent('''
        def beats_chance(mi, chance):
            """Whether mutual information beats the chance floor."""
            return mi <= chance


        def in_band(x, lo, hi):
            """Whether x sits inside the closed band."""
            return lo <= x and x <= hi


        def outside(x, lo, hi):
            """Whether x sits outside the open band."""
            return not (lo < x and x < hi)
    '''))
    import importlib.util

    spec = importlib.util.spec_from_file_location("boolrules", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _one(fn, law, route):
    from mathema.conjecture import check_conjectures, claim
    (p,) = check_conjectures(fn, [claim(law, route=route)])
    return p


def test_a_boolean_body_proves_the_boolean_it_computes(rules):
    p = _one(rules.beats_chance,
             "for mi in [0,1], chance in [0,1], "
             "f(mi, chance) == (mi <= chance)", "derive")
    assert p.verdict == "proven", (p.verdict, p.note)


def test_boolean_connectives_and_negation_lift(rules):
    p = _one(rules.in_band,
             "for x in [0,10], lo in [0,3], hi in [7,10], "
             "f(x, lo, hi) == (lo <= x and x <= hi)", "derive")
    assert p.verdict == "proven", (p.verdict, p.note)
    q = _one(rules.outside,
             "for x in [0,10], lo in [0,3], hi in [7,10], "
             "f(x, lo, hi) == (not (lo < x and x < hi))", "derive")
    assert q.verdict == "proven", (q.verdict, q.note)


def test_a_wrong_boolean_claim_falsifies_with_an_executed_witness(rules):
    p = _one(rules.beats_chance,
             "for mi in [0,1], chance in [0,1], "
             "f(mi, chance) == (chance < mi)", "derive")
    assert p.verdict == "falsified"
    assert p.counterexample, "falsified requires an executed witness"


def test_the_indicator_reading_gives_boolean_values_numeric_claims(rules):
    p = _one(rules.beats_chance,
             "for mi in [0,1], chance in [0,1], f(mi, chance) >= 0",
             "derive")
    assert p.verdict == "proven", (p.verdict, p.note)


def test_the_probe_route_evaluates_the_boolean_law_directly(rules):
    p = _one(rules.beats_chance,
             "for mi in [0,1], chance in [0,1], "
             "f(mi, chance) == (mi <= chance)", "probe")
    assert p.verdict == "holds", (p.verdict, p.note)
