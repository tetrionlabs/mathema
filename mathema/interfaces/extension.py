# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The surface a package registering through `mathema.capabilities`,
`mathema.claim_families`, or `mathema.mcp_tools` may import.

This is a different contract from the public API in `docs/api.md`. The
public API is what someone writing claims uses, and it moves with the
package's own version. The names here are the internals a registered
provider needs to do its work: source-text handling, loop-structure
classification, claim-text splitting, domain shapes, tier rendering,
and the conditioned lift. They are stated as a contract so that core
can refactor freely behind them and a provider finds out from a test
rather than from a traceback.

`SURFACE` names everything a provider may import, grouped by seam.
`CAPABILITY_PROTOCOLS` names what core calls back on a registered
provider, which is the same contract read in the opposite direction.
Both are plain data so that a provider's own test suite can check
itself against them without importing anything from mathema's tests.

`EXTENSION_API_VERSION` moves independently of the package version.
An added name or seam leaves it alone; a removal, rename, or changed
signature raises it. `docs/extending.md` states the policy in full.
"""
from __future__ import annotations

import inspect

from ..analysis import Facts as Facts
from ..analysis import LoopFact as LoopFact
from ..analysis import SourceUnavailable as SourceUnavailable
from ..analysis import analyze_source as analyze_source
from ..domain import bound_to_sympy_set as bound_to_sympy_set
from ..domain import domain_bound_from_json as domain_bound_from_json
from ..grammar import normalize as normalize
from ..grammar import parse_raises as parse_raises
from ..grammar import split_quantifier as split_quantifier
from ..grammar import split_relation as split_relation
from ..identity import local_names as local_names
from ..symbolic import ConditionedLift as ConditionedLift
from ..symbolic import lift_conditioned as lift_conditioned
from ..symbolic import bare_seq_name as bare_seq_name
from ..symbolic import classify_loop_header as classify_loop_header
from ..symbolic import diagnose_fold as diagnose_fold
from ..symbolic import seq_one_colon as seq_one_colon
from ..symbolic import strip_docstring as strip_docstring
from ..tiers import LOOP_KIND_LABEL as LOOP_KIND_LABEL
from ..tiers import Rendered as Rendered
from ..tiers import render_condition as render_condition
from ..tiers import render_loop_header as render_loop_header
from ..routes import verdict_ceiling as verdict_ceiling
from ..audit import build_index as build_index
from ..conjecture import evidence_rank as evidence_rank
from ..records import SUPPORTED_VERDICTS as SUPPORTED_VERDICTS
from ..inventory import function_dependencies as function_dependencies
from ..spec import load_declared as load_declared
from ..spec import load_verified as load_verified
from ..spec import save_verified_entry as save_verified_entry
from ..targets import Target as Target
from ..targets import TargetError as TargetError
from ..tiers import unparse_normalized as unparse_normalized
from .runtime import POINT_RUNTIME_PROTOCOL as POINT_RUNTIME_PROTOCOL
from .runtime import PointRuntime as PointRuntime
from .runtime import RUNTIME_CAPABILITIES as RUNTIME_CAPABILITIES
from .runtime import runtime_problems as runtime_problems

EXTENSION_API_VERSION = 1

SURFACE: dict[str, tuple[str, ...]] = {
    # reading a function's own source and the names bound inside it
    "source_text": ("analyze_source", "SourceUnavailable",
                    "strip_docstring", "local_names"),
    # what a `for` loop's target and iterable actually look like
    "loop_structure": ("classify_loop_header", "bare_seq_name",
                       "seq_one_colon", "diagnose_fold"),
    # splitting claim text into its quantifier, relation, and sides
    "claim_text": ("normalize", "split_quantifier", "split_relation",
                   "parse_raises"),
    # domain bounds as JSON and as sympy sets
    "domain_shape": ("bound_to_sympy_set", "domain_bound_from_json"),
    # per-node text for the tier ladder, and the pair it returns
    "rendering": ("render_loop_header", "render_condition", "Rendered",
                  "unparse_normalized", "LOOP_KIND_LABEL"),
    # the lift with its raise guards and branch structure kept
    "lift_structure": ("ConditionedLift", "lift_conditioned"),
    # the runtime contract: what a target provider owes and what a
    # verdict can reach given its capabilities (interfaces.runtime)
    "runtime": ("PointRuntime", "POINT_RUNTIME_PROTOCOL",
                "RUNTIME_CAPABILITIES", "runtime_problems",
                "verdict_ceiling"),
    # the neutral facts record a frontend constructs (tree is
    # frontend-private and optional; see the Facts docstring)
    "facts_ir": ("Facts", "LoopFact"),
    # what a target resolver builds and raises
    "targets": ("Target", "TargetError"),
    # what a record-consuming product reads: one-deep callee edges,
    # the two claim stores, and project membership (the export@1
    # charter's inputs, stated here so the freeze covers them)
    "inventory": ("function_dependencies",),
    "store": ("load_declared", "load_verified", "save_verified_entry"),
    "index": ("build_index",),
    # how strongly a positive verdict was reached, for capping derived
    # evidence at the strength it rides on
    "evidence": ("evidence_rank", "SUPPORTED_VERDICTS"),
}

# What core calls on a registered capability provider: the attribute it
# must expose, mapped to the keyword-only parameters core passes. A
# provider missing a member, or refusing one of these keywords, breaks
# the call site that looks it up through `mathema._providers`.
#: Empty since the describe_diagram hook was retired: core renders the
#: tier ladder itself and calls no provider for it.
#:
#: Diagramming from outside is still fully supported, and does not need
#: an entry here. A third party draws whatever it likes from the
#: `rendering`, `loop_structure` and `source_text` seams above, node
#: labels, loop shapes and the alpha-renamed tree. What is gone is only
#: the ability to *replace* core's own output, which made what
#: `describe` printed depend on which packages happened to be installed.
#:
#: `symbology` remains a registered capability core calls into, and its
#: protocol has never been declared here, the obvious next entry.
CAPABILITY_PROTOCOLS: dict[str, dict[str, tuple[str, ...]]] = {}


def capability_problems(provider, capability: str) -> list[str]:
    """Intent:
        Every way `provider` fails to satisfy `capability`'s protocol,
        as human-readable strings. An empty list means it conforms.
        A provider is normally a module, but anything with the right
        attributes passes.

    Raises:
        KeyError: `capability` is not in `CAPABILITY_PROTOCOLS`.
    """
    protocol = CAPABILITY_PROTOCOLS[capability]
    problems: list[str] = []
    for member, keywords in protocol.items():
        target = getattr(provider, member, None)
        if target is None:
            problems.append(f"{capability}: missing {member!r}")
            continue
        if not callable(target):
            problems.append(f"{capability}: {member!r} is not callable")
            continue
        if not keywords:
            continue
        try:
            params = inspect.signature(target).parameters
        except (TypeError, ValueError):
            continue
        if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
            continue
        for keyword in keywords:
            if keyword not in params:
                problems.append(
                    f"{capability}: {member!r} does not accept {keyword!r}")
    return problems


__all__ = [
    "EXTENSION_API_VERSION", "SURFACE", "CAPABILITY_PROTOCOLS",
    "capability_problems",
    *(name for names in SURFACE.values() for name in names),
]
