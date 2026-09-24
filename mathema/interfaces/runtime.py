# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The runtime contract: what executing a claim's function requires.

Adjudication builds every evaluation primitive core-side from the
declared domain and the compiled law; the function under test only ever
appears as a callable being invoked. That is why a C++ function behind
a ctypes shim already passes through the whole probe and corroboration
machinery with no special integration: any callable satisfying the
conventions below is a runtime, whatever produced its values.

This module states those conventions in two layers. The ADAPTOR
contract is the entire obligation of a foreign runner (a process
serving another language's functions): two operations, `describe` and
`call`. The `PointRuntime` protocol is what core builds ON TOP of any
conforming callable (`gates._point_evaluator` returns exactly this
shape), stated here so the seam is testable from outside core.

The adaptor contract, as data rather than code this campaign:

- `describe(target)` returns the facts a frontend can honestly state:
  the signature, parameter kinds in `analysis.Facts.param_kinds`'s
  vocabulary, purity where establishable, and a NAMESPACED form hash
  (`"ts:<sha>"`, `"cpp:<sha>"`; the `"doc:<sha>"` fallback in
  `mathema.analyze` is the shipping precedent). No syntax tree
  crosses the wire; `Facts.tree` is frontend-private.
- `call(target, points)` evaluates a batch of concrete argument
  points and returns, per point, one of: a value; a failure tagged
  with a neutral kind (`raise`, `panic`, `trap`, `abort`) and the
  runtime's own type name; or a non-finite marker (`nan`, `inf`).
  Batched because process round trips and VM startup dominate
  per-point costs, and crash-resilient because some runtimes die with
  the failing call (a stack overflow aborts a native process): the
  runner is relaunched and the fatal point recorded as an `abort`.
  A wrapped integer result is not a failure at this boundary at all;
  it is a value, distinguishable from the true result only against
  exact arithmetic, which is core's job, not the runner's.

What a Python-side proxy for such a runner must do to satisfy the
existing machinery: raise a real exception for the `raise` kinds (the
corroboration gate's `_tag` wrapper attributes it to the function),
return the non-finite float for non-finite markers (`probe_finite`
reads it), and return plain values otherwise.
"""
from __future__ import annotations

from typing import Any, Callable, Protocol, runtime_checkable

#: What a runtime provider can contribute, the vocabulary
#: `verdict_ceiling` in `mathema.routes` prices verdicts against.
#: `runtime` is the ability to call the function at concrete points
#: (the adaptor contract above); `frontend` is source-level analysis
#: (a Facts with body structure, enabling the lifting derive routes);
#: `globals` is visibility of the implementation's ambient state
#: (module globals, argument mutation), which the examine route's
#: empirical half reads and which never crosses a process boundary.
RUNTIME_CAPABILITIES = frozenset({"runtime", "frontend", "globals"})


@runtime_checkable
class PointRuntime(Protocol):
    """The evaluation kit `gates._point_evaluator` builds around a
    callable, one claim at a time. Everything here is derived
    core-side; a runtime provider supplies only the callable.

    `evaluate(point)` decides the claim's relation at a concrete
    point: `True` (holds there), `False` (a genuine counterexample),
    `None` (inconclusive: the law's own plumbing failed, an infinity
    only the law's own arithmetic produced, a NaN propagated from a
    missing input). An inf the callable itself returned is an executed
    value like any other, so a relation that fails on it is a
    counterexample; a NaN computed from non-missing inputs is a value
    the relation is decided against: no ordering holds for it, and it
    equals no number. `probe_finite(point)` reports an
    implementation-failure detail string (a raise, a NaN, an inf or a
    deviation past a magnitude-scaled tolerance where the relation
    fails) or `None`.
    `admits(point)` is domain-and-assumption membership.
    `sample(name, rng)` draws a value respecting the parameter's
    declared bound. `corners` are the domain endpoint combinations,
    and `names` the free variables, in evaluation order."""

    def evaluate(self, point: dict) -> bool | None: ...

    def probe_finite(self, point: dict) -> str | None: ...

    def admits(self, point: dict) -> bool: ...

    def sample(self, name: str, rng: Any) -> Any: ...

    corners: list
    names: list


#: The members a point-runtime kit must carry, with the argument each
#: callable takes. Plain data, mirroring
#: `extension.CAPABILITY_PROTOCOLS`, so a provider's own tests can
#: check conformance without importing mathema's tests.
POINT_RUNTIME_PROTOCOL: dict[str, tuple[str, ...]] = {
    "evaluate": ("point",),
    "probe_finite": ("point",),
    "admits": ("point",),
    "sample": ("name", "rng"),
    "corners": (),
    "names": (),
}


def runtime_problems(kit) -> list[str]:
    """Intent:
        Every way `kit` fails the point-runtime contract, as
        human-readable strings; empty means it conforms. Accepts the
        dict `gates._point_evaluator` returns or any object with the
        same members.

    Notes:
        Callables are checked for presence and callability only, not
        signature: the kit's members are closures built per claim, and
        a closure's parameter names are its own business. `corners`
        and `names` must exist and be lists.
    """
    problems: list[str] = []

    def member(name: str):
        if isinstance(kit, dict):
            return kit.get(name)
        return getattr(kit, name, None)

    for name, _args in POINT_RUNTIME_PROTOCOL.items():
        target = member(name)
        if target is None:
            problems.append(f"point-runtime: missing {name!r}")
            continue
        if name in ("corners", "names"):
            if not isinstance(target, list):
                problems.append(f"point-runtime: {name!r} is not a list")
        elif not isinstance(target, Callable):
            problems.append(f"point-runtime: {name!r} is not callable")
    return problems


__all__ = [
    "POINT_RUNTIME_PROTOCOL",
    "PointRuntime",
    "RUNTIME_CAPABILITIES",
    "runtime_problems",
]
