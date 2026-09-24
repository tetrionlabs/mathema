# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`@enforce_domain()` guards with the domain a declared claim states,
whatever its shape: a plain interval, an interval with the missing
value excluded, and an interval typed onto the integers. The guard read
off the claim is the same guard as passing that claim's own Domain
explicitly."""
import pytest

import mathema
from mathema import claim


def _guarded_from_claim(text):
    @mathema.enforce_domain()
    @mathema.claims_decorator(text)
    def f(x):
        return x
    return f


def _guarded_explicitly(text):
    def f(x):
        return x
    return mathema.enforce_domain({"x": claim(text).domain["x"]})(f)


PLAIN = "for x in [0, 100], f(x) >= 0"
NO_MISSING = "for x in [0, 100] \\ {∅}, f(x) >= 0"
INTEGERS = "for x in [0, 100] ⊂ Z, f(x) >= 0"


@pytest.mark.parametrize("build", [_guarded_from_claim, _guarded_explicitly])
@pytest.mark.parametrize("text", [PLAIN, NO_MISSING, INTEGERS])
def test_an_out_of_range_value_is_rejected(build, text):
    f = build(text)
    assert f(50) == 50
    with pytest.raises(ValueError, match="x=200"):
        f(200)


@pytest.mark.parametrize("build", [_guarded_from_claim, _guarded_explicitly])
def test_excluding_missing_rejects_a_missing_value(build):
    f = build(NO_MISSING)
    with pytest.raises(ValueError, match="x=None"):
        f(None)
    with pytest.raises(ValueError, match="element 1"):
        f([1, None])


@pytest.mark.parametrize("build", [_guarded_from_claim, _guarded_explicitly])
@pytest.mark.parametrize("text", [PLAIN, INTEGERS])
def test_missing_is_allowed_unless_excluded(build, text):
    assert build(text)(None) is None


@pytest.mark.parametrize("build", [_guarded_from_claim, _guarded_explicitly])
def test_the_integer_type_rejects_a_fraction(build):
    f = build(INTEGERS)
    with pytest.raises(ValueError, match="x=3.5"):
        f(3.5)


def test_the_guard_read_off_the_claim_is_the_claims_own_domain():
    f = _guarded_from_claim(NO_MISSING)
    assert f.__mathema_enforced_domain__ == {"x": claim(NO_MISSING).domain["x"]}
