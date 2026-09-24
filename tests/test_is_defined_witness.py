# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""An `is_defined` claim is falsified only by an executed witness.

Both readings are covered: the bare `is_defined(f)` (f returns
everywhere in the domain) and the restriction, a claim named
`is_defined` whose statement is a region R (f returns exactly where R
holds). A falsification names a concrete point,
and calling the real function there disagrees with the claim: it
raises where the claim says defined, or returns where the claim says it
raises. When no such point is found, the verdict is `unknown` with the
corroboration flags, never `falsified`.
"""
import re

import mathema


def reciprocal_pole(x):
    return 1 / (1 - x)


def guarded_root(x):
    if x < 0:
        raise ValueError("negative")
    return x ** 0.5


def total(x):
    return x + 1


def _restriction(region):
    return mathema.claim(region, name="is_defined")


def _only(fn, statement):
    (probe,) = [p for p in mathema.check(fn, claims=[statement]).probes
                if p.meta.get("mathema.surface") == "declared"]
    return probe


def _witness_x(probe) -> float:
    m = re.search(r"\bx=([-+0-9.e]+)", probe.counterexample or "")
    assert m, probe.counterexample
    return float(m.group(1))


def _raises(fn, x) -> bool:
    try:
        fn(x)
    except Exception:
        return True
    return False


def test_bare_is_defined_on_a_pole_names_a_point_that_raises():
    probe = _only(reciprocal_pole, "is_defined(f)")
    assert probe.verdict == "falsified"
    assert _raises(reciprocal_pole, _witness_x(probe))
    assert probe.meta.get("mathema.corroboration") == "reproduced"


def test_bare_is_defined_on_a_raise_guard_names_a_point_that_raises():
    probe = _only(guarded_root, "is_defined(f)")
    assert probe.verdict == "falsified"
    assert _raises(guarded_root, _witness_x(probe))


def test_a_restriction_too_narrow_names_a_point_where_f_returns():
    probe = _only(guarded_root, _restriction("x >= 1"))
    assert probe.verdict == "falsified"
    x = _witness_x(probe)
    assert not x >= 1 and not _raises(guarded_root, x)


def test_a_restriction_on_a_total_function_names_a_point_where_f_returns():
    probe = _only(total, _restriction("x >= 0"))
    assert probe.verdict == "falsified"
    x = _witness_x(probe)
    assert not x >= 0 and not _raises(total, x)


def test_a_restriction_naming_the_wrong_pole_is_falsified_at_an_executed_point():
    probe = _only(reciprocal_pole, _restriction("x != 2"))
    assert probe.verdict == "falsified"
    x = _witness_x(probe)
    assert (x != 2) == _raises(reciprocal_pole, x)


def test_a_domain_that_excludes_the_pole_is_never_falsified():
    probe = _only(reciprocal_pole, "for x in [2, 5], is_defined(f)")
    assert probe.verdict != "falsified"
    assert probe.counterexample is None


def test_a_premise_that_excludes_the_pole_is_never_falsified():
    probe = _only(reciprocal_pole, "assuming x > 2, is_defined(f)")
    assert probe.verdict != "falsified"
    assert probe.counterexample is None


def test_a_disproof_with_no_reproducing_point_is_unknown_and_flagged():
    probe = _only(reciprocal_pole, "for x in [2, 5], is_defined(f)")
    assert probe.verdict == "unknown"
    assert probe.meta.get("mathema.corroboration") == "uncorroborated"


def test_the_correct_claims_still_prove():
    assert _only(reciprocal_pole, _restriction("x != 1")).verdict == "proven"
    assert _only(guarded_root, _restriction("x >= 0")).verdict == "proven"
    assert _only(total, "is_defined(f)").verdict == "proven"
