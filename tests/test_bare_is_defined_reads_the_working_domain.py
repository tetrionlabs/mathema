# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Decision A: `is_defined(f)` asks for a value or a deliberate error
inside the working domain. A conditional raise, `@enforce_domain` and
an entry `@enforce_dimensions` check are the function's own guards: they
cut the working domain, so a guarded function is defined over what is
left. A bare `assert` is not a guard, and a failure inside the working
domain still falsifies. The record names a guard by its condition,
never by a line number."""
import math
import re

from mathema import enforce_domain
from mathema.conjecture import check_conjectures, claim


def guarded_root(x: float) -> float:
    if x < 0:
        raise ValueError("x must be nonnegative")
    return math.sqrt(x)


def asserted_root(x: float) -> float:
    assert x >= 0
    return math.sqrt(x)


def guarded_pole(x: float) -> float:
    if x < 0:
        raise ValueError("x must be nonnegative")
    return 1.0 / (x - 1.0)


@enforce_domain(domain={"x": (0.0, 10.0)})
def enforced_root(x: float) -> float:
    return math.sqrt(x)


def _bare(fn, text="for x in [-4, 4], is_defined(f)", route="best"):
    (p,) = check_conjectures(fn, [claim(text, route=route)])
    return p


def test_a_guarded_function_is_defined_over_its_working_domain():
    for route in ("derive", "best"):
        p = _bare(guarded_root, route=route)
        assert p.verdict == "proven", (route, p.verdict, p.sketch, p.note)
    note = " ".join(filter(None, (p.sketch, p.note)))
    assert "x < 0" in note
    assert not re.search(r"\bline \d+", note)


def test_the_executed_half_skips_the_calls_a_guard_rejects():
    import random

    from mathema.analysis import analyze_source
    from mathema.claim_families import _is_defined_probe, split_probe_result
    result = _is_defined_probe(
        guarded_root, analyze_source(guarded_root),
        claim("for x in [-4, 4], is_defined(f)"), {"x": (-4.0, 4.0)},
        random.Random(0), 40)
    verdict, checked, _cx, _est, meta = split_probe_result(result)
    assert verdict == "holds" and checked > 0, result
    assert "x < 0" in meta["mathema.sampled"]


def test_an_assert_is_not_a_guard():
    p = _bare(asserted_root)
    assert p.verdict == "falsified", (p.verdict, p.note)


def test_a_failure_inside_the_working_domain_still_falsifies():
    p = _bare(guarded_pole)
    assert p.verdict == "falsified", (p.verdict, p.note)
    found = re.search(r"\bx\s*=\s*([-0-9.e]+)", p.counterexample)
    assert found and float(found.group(1)) >= 0, p.counterexample


def test_an_enforced_domain_cuts_the_working_domain():
    p = _bare(enforced_root)
    assert p.verdict in ("proven", "holds"), (p.verdict, p.note,
                                              p.counterexample)
