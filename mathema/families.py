# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The claim-family registry: a claim is adjudicated by whichever
registered family recognizes it first, on whichever route that family
offers for it. A family answers three questions, can I handle this
one (by the function's shape, the claim's own name, or both), which
routes do I offer for it (`"derive"`, `"probe:algorithmic"`, ...), and
what actually gets called for each; it never touches how a claim was
written (that's grammar.py's job, upstream of this).

Built-in families register themselves at import time via `register()`.
A third-party package (installed separately, e.g. one adding a new
proof strategy for a shape mathema's own families don't recognize, or a
new probe-side technique for a named property) registers by declaring
an `importlib.metadata` entry point under the group named by
`FAMILY_GROUP` below; `families()` merges both sets, external entries
never overriding a built-in name outright (a same-name external entry
is dropped with a warning, not silently preferred); a plugin adds new
claim families, it doesn't get to silently replace mathema's own.
"""
from __future__ import annotations

import functools
import re
import warnings
from importlib.metadata import entry_points
from typing import Callable, Protocol, runtime_checkable

FAMILY_GROUP = "mathema.claim_families"


@runtime_checkable
class ClaimFamily(Protocol):
    """One claim-adjudication strategy. `fn`/`facts` are the same
    function-under-test and its `analysis.Facts` every lift/prove entry
    point already takes; a route function's own `lhs_src`/`rhs_src`/
    `relation`/`domain`/`tolerance` are the same primitive pieces
    `try_prove()` itself receives (a claim is unpacked into these
    before it reaches this layer; there is no `Conjecture` object
    down here), extended with whatever a probe-tier route additionally
    needs (a seeded RNG, a trial budget) to actually sample `fn`."""

    def can_handle(self, fn, facts, claim_name: str) -> bool:
        """Whether this family recognizes `fn`'s body shape, the
        claim's own name, or both, a shape-based family (`DotFamily`)
        checks `fn`/`facts` and ignores `claim_name`; a name-based
        family checks `claim_name` and ignores `fn`/`facts`. Nothing
        stops a family checking both for a narrower match."""
        ...

    def routes(self) -> dict[str, Callable]:
        """Which adjudication routes this family offers, and the
        function implementing each, e.g. `{"derive": try_prove_dot}`
        or `{"probe:algorithmic": pairwise_monotone_probe}`. A family
        can offer more than one route for what it recognizes. Each
        function returns `None` to decline this specific claim even
        though `can_handle` matched, leaving the caller to fall back
        further, the same way `try_adjudicate` used to."""
        ...


_REGISTRY: dict[str, ClaimFamily] = {}


def call_route(route: Callable, /, *args, **kwargs):
    """Call a family's route function, dropping any keyword argument its
    signature does not accept.

    Intent:
        `routes()` is a published extension seam, so a third-party
        family registered through the `mathema.claim_families` entry
        point was written against whatever the route signature was on
        the day it shipped. mathema passes newer optional keywords
        (`assumption=`, the claim's premises) through here so a family
        that predates one keeps working, receiving the arguments it
        does declare and nothing more.

    Notes:
        A route declaring `**kwargs` is handed everything. Positional
        arguments are never filtered: they are the part of the
        signature the protocol documents as fixed.
    """
    import inspect
    try:
        sig = inspect.signature(route)
    except (TypeError, ValueError):
        return route(*args, **kwargs)
    params = sig.parameters.values()
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params):
        return route(*args, **kwargs)
    accepted = {p.name for p in params
                if p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD,
                              inspect.Parameter.KEYWORD_ONLY)}
    return route(*args, **{k: v for k, v in kwargs.items() if k in accepted})


def register(name: str, family: ClaimFamily) -> None:
    """Register a built-in family under `name`, internal to mathema
    itself. Re-registering the same name replaces the previous entry
    (used by tests to substitute a family for the duration of a test)."""
    _REGISTRY[name] = family


@functools.lru_cache(maxsize=1)
def _discovered_external() -> dict[str, ClaimFamily]:
    discovered: dict[str, ClaimFamily] = {}
    for ep in entry_points(group=FAMILY_GROUP):
        try:
            discovered[ep.name] = ep.load()
        except Exception as e:
            warnings.warn(f"mathema: claim family {ep.value!r} registered "
                          f"under {ep.name!r} failed to load ({e!r}), "
                          "skipping it", stacklevel=2)
    return discovered


def families() -> dict[str, ClaimFamily]:
    """Every available family: mathema's own built-ins, plus any
    externally-registered ones under names the built-ins don't already
    use. Built-in names always win; an external package can add new
    families, not override mathema's own under their own name."""
    merged = dict(_discovered_external())
    for name in _REGISTRY:
        if name in merged and merged[name] is not _REGISTRY[name]:
            warnings.warn(f"mathema: external claim family {name!r} ignored "
                          "-- a built-in family already uses that name",
                          stacklevel=2)
    merged.update(_REGISTRY)
    return merged


# --- claim keyword groups: the battery vocabulary --------------------
#
# A user opts into hazard claims by keyword instead of naming every
# member: check(fn, claims=["defined", "excluding", ...]). Each
# keyword names a group of registered family names; expansion applies
# the members' own structural gates, so a group asks for every
# RELEVANT claim, never an irrelevant one. This dict is the one
# statement of the vocabulary; suggest/check/cli all read it here.
GROUPS: dict[str, tuple[str, ...]] = {
    # all applicable hazard checks, enforced, inside the domain
    "defined_within_domain": ("is_missing_safe", "is_pole_safe",
                              "is_builtin_safe", "is_extremity_safe",
                              "is_representation_safe", "is_empty_safe",
                              "is_defined"),
    # any point outside the declared domain causes a raise
    "excluded_outside_domain": ("excluded_outside_domain",),
    # numerical stability across the declared domain
    "stable": ("is_numerically_stable",),
    # the execution-purity cluster: no external state written, read,
    # or varied on (is_deterministic is one member inside it)
    "stateless": ("is_state_safe", "is_deterministic",
                  "is_reproducible"),
}

# terse spellings (and the spaced forms a claim-text reader would
# naturally type) for the group names above
KEYWORD_ALIASES: dict[str, str] = {
    "defined": "defined_within_domain",
    "defined within domain": "defined_within_domain",
    "excluding": "excluded_outside_domain",
    "excluded outside domain": "excluded_outside_domain",
    "numerically stable": "stable",
}

# one-line meanings, rendered whole in the did-you-mean error so a
# near-miss teaches the entire vocabulary
KEYWORD_MEANINGS: dict[str, str] = {
    "defined": "all in-domain hazard checks (missing/pole/builtin/"
               "extremity/representation/empty + the definedness "
               "region), each gated on structural relevance",
    "excluding": "out-of-domain inputs must raise (the declared "
                 "exclusion, enforced)",
    "stable": "numerical stability across the declared domain",
    "stateless": "no external state written, read, or varied on "
                 "(state safety, determinism, seeded reproducibility)",
}


# the shape a family name must have to contribute a safety predicate;
# anything else registered is an ordinary (shape- or name-based) family
_PREDICATE_SHAPE = re.compile(r"is_[a-z0-9][a-z0-9_]*_safe")


def registered_predicates() -> frozenset:
    """Safety-predicate names contributed by registered claim families:
    every family name shaped like `is_<slug>_safe`. The registered NAME
    is the predicate it owns (the same name-is-the-contract rule target
    resolvers use), so a family owning several predicates registers
    once per predicate. `routes` unions this with its static tables;
    with nothing registered beyond mathema's own members, the union
    adds nothing."""
    return frozenset(name for name in families()
                     if _PREDICATE_SHAPE.fullmatch(name))


def expand_keyword(word: str) -> tuple[str, ...] | None:
    """The registered family names a battery keyword expands to, or
    None when `word` is no keyword at all (the caller then reads it
    as a claim law)."""
    canonical = KEYWORD_ALIASES.get(word.strip(), word.strip())
    return GROUPS.get(canonical)


def keyword_help() -> str:
    """The whole keyword vocabulary with one-line meanings, the
    did-you-mean error body."""
    return "; ".join(f"{k} ({v})" for k, v in KEYWORD_MEANINGS.items())


def close_keyword(word: str) -> str | None:
    """A keyword or alias `word` is plausibly a misspelling of, or
    None; the did-you-mean trigger for a string that parses as
    neither a keyword nor a law."""
    import difflib
    vocabulary = list(GROUPS) + list(KEYWORD_ALIASES)
    matches = difflib.get_close_matches(word.strip(), vocabulary, n=1,
                                        cutoff=0.75)
    return matches[0] if matches else None


# families where at most ONE member states the intended policy;
# adopting a second is a contradiction, not a refinement. The other
# half of the group vocabulary: GROUPS above bundles claims a user
# opts into together, EXCLUSIVE_GROUPS names sets they must pick
# exactly one from.
# empty today: no registered claim family has a second member that
# answers the same question a contradictory way. A group needs two or
# more registered names to mean anything, since a one-member group can
# only ever clash with itself, which is already the "already declared"
# case.
EXCLUSIVE_GROUPS: dict[str, tuple[str, ...]] = {}

# claims that answer the SAME question about one target, so stating any
# member of the set addresses the question and the claim floor asks for
# one rather than all. Distinct from EXCLUSIVE_GROUPS: these are not
# contradictory (affine implies both convex and concave), they are
# alternative answers; "which way does this bend in x" is one
# question whether the answer is convex, concave, or affine. A claim
# absent from this table is its own aspect.
CLAIM_ASPECTS: dict[str, tuple[str, ...]] = {
    "monotonicity": ("monotonic_increasing", "monotonic_decreasing"),
    "shape": ("affine", "convex", "concave"),
    "symmetry": ("even", "odd"),
}

_ASPECT_OF: dict[str, str] = {member: aspect
                              for aspect, members in CLAIM_ASPECTS.items()
                              for member in members}


def claim_aspect(claim_name: str) -> tuple[str, str]:
    """Intent:
        The `(aspect, target)` a claim name occupies: the question it
        answers and what it answers it about. `convex[x]` and
        `concave[x]` share an aspect, `is_representation_safe[a]` and
        `is_representation_safe[b]` share an aspect but not a target.
        A name this table does not group is its own aspect.
    """
    base, _, target = claim_name.partition("[")
    return _ASPECT_OF.get(base, base), target.rstrip("]")


def aspect_label(claim_name: str) -> str:
    """Intent:
        The `aspect[target]` label a suggestion shares with its
        alternatives, or `""` when it answers a question no other
        suggestion competes on. Only the multi-member aspects
        (monotonicity, shape, symmetry) group: `convex[x]`,
        `concave[x]` and `affine[x]` all read `shape[x]`, so a caller
        sees one bending question with three candidate answers rather
        than three independent claims. A same-aspect name over a
        DIFFERENT target (`convex[x]` vs `convex[y]`) gets a distinct
        label, since bending in x is a separate question from bending
        in y. A name that is its own aspect returns `""`.
    Notes:
        This is the redundancy signal, weaker than EXCLUSIVE_GROUPS:
        aspect members are alternative answers (affine implies convex
        and concave), not contradictions, so a label here never blocks
        adoption, it only tells a reader the suggestions overlap.
    """
    base, _, rest = claim_name.partition("[")
    if base not in _ASPECT_OF:
        return ""
    target = rest.rstrip("]")
    aspect = _ASPECT_OF[base]
    return f"{aspect}[{target}]" if target else aspect
