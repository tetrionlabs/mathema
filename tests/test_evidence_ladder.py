# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""mathema/conjecture.py's EVIDENCE_LADDER/evidence_rank(): route
strength ordering, including the tie between probe:semi_analytical and
probe:algorithmic, no test coverage existed for either before this."""
from mathema.conjecture import evidence_rank


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
