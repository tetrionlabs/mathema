# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Every case of every verdict family, checked on this tree and judged
against what calling the function does: no `proven` verdict is
contradicted by a call, no `falsified` verdict's witness passes when
called, and no row shows a value the function wrote.

A case whose rule this tree lacks is skipped, with the rule named. A
verdict weaker than the one recorded in `tests/families/expected.json`
is reported as a warning, not a failure."""
import json
import warnings
from pathlib import Path

import pytest

from mathema._devtools import verdict_families as V

CASES = V.cases_of(V.FAMILIES)
EXPECTED = json.loads((Path(__file__).parent / "families" / "expected.json").read_text())


def _weaker(found: V.Judgement, recorded: dict) -> bool:
    if recorded["status"] != V.RIGHT:
        return False
    return found.status != V.RIGHT or V.weaker(recorded["verdict"], found.verdict)


@pytest.mark.parametrize("case", CASES, ids=[c.name for c in CASES])
def test_no_family_verdict_is_contradicted_by_a_call(case, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", str(V.REPO_ROOT))
    outcome = V.check_case(case)
    if outcome.verdict == V.NOT_RUN:
        pytest.skip(f"{case.name}: {outcome.skipped_for}")
    found = V.judge(case, outcome, V.ground_truth(case, V._witness_points(case, [outcome])))
    recorded = EXPECTED.get(case.name)
    if recorded is not None and _weaker(found, recorded):
        warnings.warn(f"{case.name} is weaker than recorded: {recorded['verdict']} "
                      f"({recorded['status']}) then, {found.verdict} ({found.status}) now")
    assert found.status not in (V.WRONG, V.LEAK, V.CRASH), f"{case.name}: {found.reason}"


def test_every_case_has_a_recorded_expectation():
    assert sorted(set(c.name for c in CASES) - set(EXPECTED)) == []


def test_every_case_says_what_it_shows():
    assert [c.name for c in CASES if not c.shows] == []
