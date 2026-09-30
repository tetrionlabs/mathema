# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""mathema/conjecture.py's EVIDENCE_LADDER/evidence_rank(): route
strength ordering, the routes tied on one rung, every route the engine
emits placed, and the routes that are not on the ladder at all."""
import os
import re

import pytest

from mathema.conjecture import EVIDENCE_LADDER, NotOnTheLadder, evidence_rank


def test_derive_outranks_derive_extensive():
    assert evidence_rank("derive") < evidence_rank("derive:extensive")


def test_derive_extensive_outranks_informed_probing():
    assert evidence_rank("derive:extensive") < evidence_rank("probe:semi_analytical")
    assert evidence_rank("derive:extensive") < evidence_rank("probe:algorithmic")


def test_semi_analytical_and_algorithmic_probing_tie():
    assert evidence_rank("probe:semi_analytical") == evidence_rank("probe:algorithmic")


def test_informed_probing_outranks_plain_probe():
    assert evidence_rank("probe:semi_analytical") < evidence_rank("probe")
    assert evidence_rank("probe:algorithmic") < evidence_rank("probe")


def test_plain_probe_outranks_intent_provenance_classes():
    assert evidence_rank("probe") < evidence_rank("documented")
    assert evidence_rank("documented") < evidence_rank("declared")


def test_an_unrecognized_suffix_falls_back_to_its_base_routes_rank():
    # probe:fallback isn't its own rung; it ties plain "probe", the
    # same as before this session's route generalization.
    assert evidence_rank("probe:fallback") == evidence_rank("probe")


def test_a_wholly_unrecognized_route_ranks_last():
    assert evidence_rank("some_third_party_route") > evidence_rank("declared")


# --- one evidence ladder -------------------------------------------------

_ROUTE_LITERAL = re.compile(r"""["']((?:derive|probe|examine|axiom)(?::[a-z_]+)?)["']""")

#: retired by the missing-values work, never placed on the ladder
_RETIRED = {"probe:classified"}


def _emitted_routes() -> set:
    # every route spelled as a literal anywhere in the engine's source
    import mathema
    root = os.path.dirname(mathema.__file__)
    found: set = set()
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            if name.endswith(".py"):
                with open(os.path.join(dirpath, name)) as fh:
                    found |= set(_ROUTE_LITERAL.findall(fh.read()))
    return found - _RETIRED


def test_every_route_the_engine_emits_is_on_the_ladder():
    listed = {route for rung in EVIDENCE_LADDER for route in rung}
    emitted = _emitted_routes()
    assert {"derive", "probe", "examine"} <= emitted
    assert sorted(emitted - listed - {"axiom"}) == []


def test_examine_ranks_with_derive():
    assert evidence_rank("examine") == evidence_rank("derive")


def test_the_informed_probing_rung_holds_four_techniques():
    rung = {evidence_rank(r) for r in ("probe:semi_analytical", "probe:algorithmic",
                                       "probe:minimal_example", "probe:counterfactual")}
    assert len(rung) == 1
    assert rung.pop() < evidence_rank("probe")


def test_lifted_numeric_is_level_with_probe():
    assert "probe:lifted_numeric" in {r for rung in EVIDENCE_LADDER for r in rung}
    assert evidence_rank("probe:lifted_numeric") == evidence_rank("probe")


def test_an_axiom_is_not_on_the_ladder():
    assert "axiom" not in {r for rung in EVIDENCE_LADDER for r in rung}
    with pytest.raises(NotOnTheLadder, match="trusted, not adjudicated"):
        evidence_rank("axiom")



def test_the_public_evidence_rank_raises_for_an_axiom():
    from mathema.interfaces.extension import evidence_rank as public
    with pytest.raises(NotOnTheLadder):
        public("axiom")


def test_a_language_strategy_route_ranks_as_the_default_path_would():
    # a strategy reports derive:<its mechanism>; the default path calls
    # a wider mechanism derive:extensive, and the plain one derive
    assert evidence_rank("derive:language") == evidence_rank("derive")
    assert evidence_rank("derive:sturm") == evidence_rank("derive:extensive")
