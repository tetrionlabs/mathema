# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The runtime seam, pinned from outside core.

Adjudication needs exactly one thing from a target's provider to
execute claims: a callable. Everything else (evaluating the law,
domain membership, sampling, corner enumeration) is built core-side by
`gates._point_evaluator`, and the dict it returns is the contract a
future foreign adaptor's proxy must slot into. These tests hold that
seam still: the real kit satisfies the published protocol, and the
verdict-ceiling table states what each route can reach when a
capability is missing, which is the engine's existing discipline
(an unreproducible disproof stays unknown) as data.
"""
import random

from mathema.analysis import analyze_source
from mathema.conjecture import claim
from mathema.gates import _point_evaluator
from mathema.interfaces.runtime import (POINT_RUNTIME_PROTOCOL, PointRuntime,
                                        runtime_problems)
from mathema.routes import CAPABILITIES, verdict_ceiling


def _kit():
    def double(x: float) -> float:
        """Twice x."""
        return 2 * x

    cj = claim("for x in [0, 10], f(x) >= 0")
    facts = analyze_source(double)
    return _point_evaluator(cj, double, facts, cj.domain, {})


def test_the_real_point_evaluator_satisfies_the_published_contract():
    kit = _kit()
    assert kit is not None
    assert runtime_problems(kit) == []
    assert set(POINT_RUNTIME_PROTOCOL) == set(kit)


def test_the_kit_behaves_as_the_protocol_documents():
    kit = _kit()
    rng = random.Random(7)
    point = {"x": kit["sample"]("x", rng)}
    assert kit["admits"](point) is True
    assert kit["evaluate"](point) is True
    assert kit["probe_finite"](point) is None
    assert not kit["admits"]({"x": 11.0})
    assert kit["names"] == ["x"] and len(kit["corners"]) >= 2


def test_runtime_problems_names_each_gap():
    missing = {"evaluate": lambda point: True}
    problems = runtime_problems(missing)
    assert any("probe_finite" in p for p in problems)
    assert any("corners" in p for p in problems)
    broken = {name: "not-callable" for name in POINT_RUNTIME_PROTOCOL}
    assert len(runtime_problems(broken)) == len(POINT_RUNTIME_PROTOCOL)


class _KitObject:
    """An object-shaped kit conforms too; PointRuntime is the typed
    reading of the same members."""

    def evaluate(self, point):
        return True

    def probe_finite(self, point):
        return None

    def admits(self, point):
        return True

    def sample(self, name, rng):
        return 0.0

    corners: list = []
    names: list = []


def test_an_object_kit_conforms_and_typechecks():
    kit = _KitObject()
    assert runtime_problems(kit) == []
    assert isinstance(kit, PointRuntime)


def test_verdict_ceilings_state_the_existing_discipline():
    full = CAPABILITIES
    no_runtime = frozenset({"frontend", "globals"})
    no_frontend = frozenset({"runtime", "globals"})
    # a symbolic disproof with no executed reproduction stays unknown:
    # the corroboration rule, generalised to "no runtime at all"
    assert verdict_ceiling(full, "derive", "refute") == "falsified"
    assert verdict_ceiling(no_runtime, "derive", "refute") == "unknown"
    # claim-only symbolic proofs need no runtime
    assert verdict_ceiling(no_runtime, "derive", "support") == "proven"
    # probe cannot run without calls
    assert verdict_ceiling(no_runtime, "probe", "support") is None
    assert verdict_ceiling(no_runtime, "probe", "refute") is None
    # no frontend loses body lifting, not evidence strength
    assert verdict_ceiling(no_frontend, "derive", "support") == "proven"
    assert verdict_ceiling(no_frontend, "probe", "support") == "holds"
    # the examine families read ambient implementation state
    assert verdict_ceiling(frozenset({"runtime", "frontend"}),
                           "examine", "support") is None
    assert verdict_ceiling(full, "examine", "refute") == "falsified"
