# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Strictness at the boundary: a strict relation is never satisfied by
measured equality (no tolerance credit), an attained zero of the
difference disproves < and > with the root as witness, an open
endpoint is never sampled as a counterexample, a reversed range is an
empty domain and refuses adjudication, and exclusions render on
bare-type domains."""
import math

from mathema.claims import check_conjectures, claim
from mathema.domain import Domain, render_domain_bound


def _v(fn, law, route="derive"):
    return check_conjectures(fn, [claim(law, route=route)])[0]


def para(x):
    return x * x


def zero_fn(x):
    return 0.0


def rootx(x):
    return math.sqrt(x)


def test_probe_strict_gets_no_tolerance_credit():
    # f(x) = 0 claimed > 0: false at EVERY point; the default 1e-9
    # slack once let 0 > 0 pass as holds
    p = _v(zero_fn, "for x in [0, 1], f(x) > 0", route="probe")
    assert p.verdict == "falsified"


def test_attained_zero_disproves_a_strict_ordering():
    # x^2 >= 0 everywhere but == 0 at x=0, so > 0 is false there
    p = _v(para, "for x in [-2, 2], f(x) > 0")
    assert p.verdict == "falsified"
    assert p.counterexample and "0" in p.counterexample
    assert "attains zero" in p.sketch


def test_strict_ordering_away_from_the_zero_still_proves():
    assert _v(para, "for x in [1, 2], f(x) > 0").verdict == "proven"


def test_attained_zero_at_a_closed_endpoint_falsifies():
    # sqrt(x) > x is false at the included x=0 (equality)
    p = _v(rootx, "for x in [0, 0.25], f(x) > x")
    assert p.verdict == "falsified"


def test_open_endpoint_is_not_a_counterexample():
    # the same claim over (0, 0.25] is TRUE: 0 is excluded, and the
    # boundary sampler must not draw the exact excluded endpoint
    p = _v(rootx, "for x in (0, 0.25], f(x) > x")
    assert p.verdict != "falsified", p.counterexample


def test_reversed_range_is_refused_not_adjudicated():
    p = _v(para, "for x in [2, 1], f(x) >= 0")
    assert p.verdict == "skipped:misspecified"
    assert "empty" in p.note
    q = _v(para, "for x in [2, 1], f(x) <= -5")
    assert q.verdict == "skipped:misspecified"


def test_bare_type_domain_renders_its_exclusions():
    d = Domain(base_type="N", pieces=(), excluded=frozenset({3.0}),
               explicit_type=True)
    assert "3" in render_domain_bound(d)
