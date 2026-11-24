# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The enforced domains family: `excluded_outside_domain(x)` for a
function behind `enforce_domain`, over pairs of an enforced domain and
a claimed one. The claim is true exactly when the guard refuses every
point outside the claimed domain, that is when the enforced domain lies
inside the claimed one."""
import random

from tests.families.functions.enforced import ENFORCED

F = "tests.families.functions.enforced"
ENFORCED_READING = "the enforced domain reading"
CLAIMED = ["[0, 1]", "(0, 1)", "[0, 1)", "(0, 1]", "[0, 100]", "{0, 1}", "[0, oo)", "Z", "R",
           "(-oo, oo)", "[-1, 2]"]

PINNED = {
    # the guard admits both closed ends, which an open claim leaves out
    ("closed", "(0, 1)"),
    # the guard admits [0, 100]; the claim says [0, 1]
    ("wide", "[0, 1]"),
    # the guard admits inf; [0, oo) does not hold it
    ("to_infinity", "[0, oo)"),
    # a bare Z enforced inside a claimed Z
    ("integers", "Z"),
    # a finite set enforced inside an interval holding it
    ("pair", "[0, 1]"),
    ("closed", "[0, 1]"),
}

CASES: list = []
_rng = random.Random(1129)
_grid = [(e, c) for e in ENFORCED for c in CLAIMED]
for e, c in sorted(set(_rng.sample(_grid, 30)) | PINNED):
    CASES.append(dict(
        name=f"{e}.{c}", function=f"{F}:e_{e}", claim=f"for x in {c}, excluded_outside_domain(x)",
        rule=ENFORCED_READING, rule_if_false=True, issue=129,
        shows=f"the guard enforces {ENFORCED[e]}; the claim names {c}"))
CASES.append(dict(name="unguarded.[0, 1]", function=f"{F}:unguarded",
                  claim="for x in [0, 1], excluded_outside_domain(x)", truth=False,
                  shows="no guard: every value outside is accepted"))
