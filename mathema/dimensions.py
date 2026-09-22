# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Dimensional structure of a function's parameters, in one place.

A parameter has axes: a scalar has none, a 1-D sequence has one, a
matrix marked `Shape("m", "n")` has two. Three questions are asked of
that structure, by three different callers, and each used to answer it
its own way:

- how to SYNTHESISE a value of the right shape (the probe sampler),
- how to MEASURE a value's dimensions at runtime (`dim(x, k)`, the
  `@enforce_dimensions` guard),
- how to NAME dimensions so a premise or law can refer to them
  (`dim(x, 0)`, or a shared marker dim `n`).

`DimResolver` answers all three from one model, so the sampler, the
evaluator and the guard never drift. It is built from a function's
`Facts` and its `Shape` markers and injected where each caller needs
it, rather than each re-deriving parameter structure from `param_kinds`
strings.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field


class DimensionConflict(ValueError):
    """A claim's own space form contradicts the signature's `Shape`
    marker for the same parameter, a different rank or a different
    dimension name at the same axis. The signature is authoritative,
    so the claim is misspecified, and saying so beats silently
    adjudicating one of two disagreeing shapes."""


@dataclass(frozen=True)
class ParamShape:
    """One parameter's dimensional structure. `axes` names each axis:
    a marker dim name (`"n"`), or `None` for an anonymous axis (a plain
    sequence's own length). `()` is a scalar."""

    axes: tuple = ()

    @property
    def ndim(self) -> int:
        return len(self.axes)


@dataclass
class DimResolver:
    """The dimensional model of a whole signature: each parameter's
    `ParamShape`, and the canonical dimension key every axis maps to.

    A canonical key unifies axes that must share a size: two parameters
    carrying the same marker dim name (`Shape("m", "n")` and
    `Shape("n", "p")` both naming `n`) resolve to one key, so one draw
    sizes both. An anonymous axis is keyed by its own `(param, axis)`
    position, shared with nothing unless a premise says so.
    """

    shapes: dict = field(default_factory=dict)     # param -> ParamShape
    # a claim-introduced dimension name aliased to the signature's own
    # name for the same axis: `Shape("n")` with a claim `R^k` reads as
    # "k is n", so both resolve to one dimension rather than clashing.
    aliases: dict = field(default_factory=dict)    # claim name -> canonical

    def canonical(self, name):
        """A dimension name resolved through the alias map to the
        signature's own name, so a claim's alias and the marker name
        are one dimension everywhere."""
        seen = set()
        while name in self.aliases and name not in seen:
            seen.add(name)
            name = self.aliases[name]
        return name

    def key(self, param: str, axis: int):
        """The canonical dimension key for one axis of one parameter: a
        marker name when the axis carries one, else the positional
        `(param, axis)` coordinate."""
        shape = self.shapes.get(param)
        if shape is None or axis >= shape.ndim:
            return None
        name = shape.axes[axis]
        if name is None:
            return (param, axis)
        return self.canonical(name)

    def marker_names(self) -> set:
        """Every dimension name usable as a symbol in a premise or law:
        the signature's own names and every claim alias of them."""
        names = {a for shape in self.shapes.values()
                 for a in shape.axes if isinstance(a, str)}
        return names | set(self.aliases)

    def anchor(self, name: str):
        """A `(param, axis)` position a marker dim name measures at, so
        `n` can be read off a real argument's shape. Any occurrence
        will do, since a shared name means every occurrence agrees."""
        for param, shape in self.shapes.items():
            for axis, a in enumerate(shape.axes):
                if a == name:
                    return (param, axis)
        return None

    def measure(self, value, axis: int) -> int:
        """The size of `value`'s `axis`-th dimension, descending first
        elements. Raises `IndexError`/`TypeError` past the value's real
        depth, the honest failure an over-indexed axis deserves."""
        v = value
        for _ in range(axis):
            v = v[0]
        return len(v)

    def bind_env(self, env: dict, args: dict) -> None:
        """Inject dimension values into a claim's evaluation env: every
        marker dim name bound to the size read off its anchoring
        argument, so `assuming n >= 2` and a law mentioning `n`
        evaluate against the trial's real shapes. Unbound on any
        argument the anchor is missing from, rather than guessed."""
        for name in self.marker_names():
            anchor = self.anchor(self.canonical(name))
            if anchor is None:
                continue
            param, axis = anchor
            if param in args:
                try:
                    env[name] = self.measure(args[param], axis)
                except (IndexError, TypeError):
                    continue

    def distinct_keys(self) -> set:
        """Every canonical dimension key in the signature, one per
        dimension that must be sized. Shared marker names collapse to
        one; an anonymous axis is its own `(param, axis)` key."""
        return {self.key(p, a)
                for p, shape in self.shapes.items()
                for a in range(shape.ndim)}

    def draw_sizes(self, rng: random.Random,
                   lo: "dict | None" = None,
                   hi: "dict | None" = None) -> dict:
        """One size per distinct dimension key for a trial. Shared keys
        get one draw, so two arguments naming the same dimension agree
        by construction; a key with a premise bound draws inside it.
        The default range keeps sequences small and cheap."""
        lo, hi = lo or {}, hi or {}
        out: dict = {}
        for k in self.distinct_keys():
            if isinstance(k, str) and k.isdigit():
                # a fixed numeric dimension (`R^2`) is exactly that size
                out[k] = int(k)
                continue
            # the default range matches the free sequence draw (2..8);
            # a premise bound narrows or lowers it (a `>= 1` floor lets
            # a length-1 vector through, the default never does)
            k_lo = lo.get(k, 2)
            k_hi = hi.get(k, 8)
            out[k] = rng.randint(max(1, k_lo), max(k_lo, k_hi))
        return out

    def synth(self, param: str, sizes: dict, element_synth, rng: random.Random):
        """Build a value for `param` with the per-key sizes in `sizes`
        (a canonical key -> concrete int for this trial). A scalar
        defers to `element_synth`; a shaped parameter nests lists to
        its axes, drawing a fresh element at every leaf. A size the
        plan did not fix falls back to a small random dimension, so an
        unconstrained axis still varies."""
        shape = self.shapes.get(param, ParamShape())
        if shape.ndim == 0:
            return element_synth()

        def build(axis: int):
            if axis == shape.ndim:
                return element_synth()
            n = sizes.get(self.key(param, axis))
            if n is None:
                n = rng.randint(2, 6)
            return [build(axis + 1) for _ in range(n)]

        return build(0)


def _reconcile_dims(param: str, marker_dims: tuple, claim_dims: tuple) -> dict:
    """Reconcile a claim's space form with the signature's `Shape`
    marker for `param`. A RANK mismatch is a real conflict (a 2-D
    matrix cannot also be a 1-D vector) and raises. A NAME mismatch at
    the same axis is not a conflict: the claim introduces its own name
    for a dimension the signature already named, so the two are the
    SAME dimension, returned as an alias (`claim name -> marker name`).
    A fixed numeric claim size names no dimension and is left alone;
    a bound the code must actually satisfy is the sampler's concern,
    not an aliasing one."""
    if len(marker_dims) != len(claim_dims):
        raise DimensionConflict(
            f"{param}: the claim gives it {len(claim_dims)} dimension"
            f"{'s' if len(claim_dims) != 1 else ''} "
            f"(^{'*'.join(map(str, claim_dims))}) but its Shape marker "
            f"declares {len(marker_dims)} "
            f"({', '.join(map(str, marker_dims))}); the signature is "
            f"authoritative on how many axes a parameter has")
    aliases: dict = {}
    for md, cd in zip(marker_dims, claim_dims):
        if not isinstance(cd, str) or cd.isdigit():
            continue
        if isinstance(md, str) and md != cd:
            aliases[cd] = md      # the claim's cd is the marker's md
    return aliases


def resolve(facts, shapes: "dict | None" = None,
            claim_domain: "dict | None" = None) -> DimResolver:
    """Build the resolver for a function from its `Facts` and its
    `Shape` markers. A parameter carrying a marker takes that marker's
    axes; a sequence parameter with no marker is one anonymous axis; a
    2-D-or-deeper marker is honoured only where the caller opts into
    nested synthesis (the resolver models it regardless, so `dim(A, 1)`
    measures correctly even before the sampler synthesises it)."""
    out: dict = {}
    aliases: dict = {}
    shapes = shapes or {}
    claim_domain = claim_domain or {}
    for p in getattr(facts, "params", ()):
        marker = shapes.get(p)
        declared = getattr(claim_domain.get(p), "dims", ())
        marker_dims = getattr(marker, "dims", ()) if marker is not None else ()
        if marker_dims and declared:
            aliases.update(_reconcile_dims(p, marker_dims, declared))
        if marker_dims:
            out[p] = ParamShape(axes=tuple(
                d if isinstance(d, str) else None for d in marker_dims))
        elif declared:
            # a claim-declared space (`for xs in R^n`): its dims name
            # the axes even with no type marker on the parameter
            out[p] = ParamShape(axes=tuple(
                d if isinstance(d, str) else None for d in declared))
        elif facts.param_kinds.get(p) == "sequence":
            out[p] = ParamShape(axes=(None,))
        else:
            out[p] = ParamShape(axes=())
    return DimResolver(shapes=out, aliases=aliases)
