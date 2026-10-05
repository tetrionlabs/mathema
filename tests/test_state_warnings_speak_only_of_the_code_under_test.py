# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A function whose behaviour depends on state outside it is warned
about when it is the project's own code. A library function mathema
reads on the way (one a claim binds, or a compendium key it accepts)
is not the reader's code to change, and says nothing."""
import json
import warnings

import pytest

from mathema import analyze
from mathema.analysis import StateDependenceWarning

_TOTAL = 0.0


def adds_to_the_total(x: float) -> float:
    return x + _TOTAL


def test_a_library_function_reads_its_globals_in_silence():
    with warnings.catch_warnings():
        warnings.simplefilter("error", StateDependenceWarning)
        analyze(json.dumps)


def test_the_projects_own_function_is_still_warned_about():
    with pytest.warns(StateDependenceWarning, match="_TOTAL"):
        analyze(adds_to_the_total)
