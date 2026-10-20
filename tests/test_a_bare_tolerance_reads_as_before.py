# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A bare-number tolerance, and no tolerance at all, keep their meaning
now that a `~=` claim may name a tolerance kind: a sample of claims
over every relation that reads a tolerance, on each route, gives the
same rows as it did before kinds reached `~=`, compared byte for byte
on every field a tolerance can move (verdict, route, the tolerance as
written, the note with its reading and its gaps, the witness, the
trial count and every meta key). The expected rows are
`tests/data/bare_tolerance_records.json` (the sample is
tests/_bare_tolerance_sample.py), written by the code before
the change."""
import json
import os

from tests._bare_tolerance_sample import records

_EXPECTED = os.path.join(os.path.dirname(__file__), "data",
                         "bare_tolerance_records.json")


def test_bare_and_default_tolerances_give_the_rows_they_gave_before():
    with open(_EXPECTED) as fh:
        expected = json.load(fh)
    found = json.loads(json.dumps(records()))
    assert len(found) == len(expected)
    for want, got in zip(expected, found):
        assert json.dumps(got, sort_keys=True) == json.dumps(
            want, sort_keys=True), want["law"]
