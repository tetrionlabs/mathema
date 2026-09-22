# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""What each adjudication route can decide.

The routes (`derive`, `probe`) are two mechanisms over one claim space,
not two claim spaces. This module is the single source of truth for
their capabilities, which claim FORMS each can adjudicate, and the
forms one has that the other lacks, so those asymmetries are data in
one table rather than scattered conditionals. The forward direction is
route equivalence (every claim decidable by either route, differing
only in evidence strength); this table is the shrinking ledger of what
still isn't equivalent.

A "form" is a feature of a claim that a route may or may not be able to
evaluate: a symbolic-calculus call (`d`/`lim`/`integrate`/`Sum`/`Prod`/
`cauchy_pv`), a domain-safety predicate, or `raises`. An ordinary value
relation (`==`/`<=`/...) is no form at all, both routes handle it, so
it is never listed.
"""
import ast

# Symbolic-calculus call forms the PROBE route cannot evaluate: there is
# no way to sample a symbolic derivative, limit, integral, or indexed
# sum/product of a black-box Python function. Distinct from sin/cos/abs
# (in conjecture._SAFE_FUNCS), which probe computes numerically.
DERIVE_ONLY_FORMS = frozenset({"d", "lim", "integrate", "Sum", "Prod",
                               "cauchy_pv"})

# Domain-safety predicates: every one is on both routes, a
# structural/symbolic derive half AND a targeted empirical half
# (is_pole_safe trials the admitted pole locations, is_builtin_safe
# the restricted builtins' domain edges, is_missing_safe a literal
# NaN). raises likewise: "every call in the domain raises" is a
# universal fact however it was reached. This set is the ONE
# statement of which relations are safety predicates, grammar,
# records, spec, acceptance, and the adjudication loop all read it
# from here.
SAFETY_PREDICATES = frozenset({"is_pole_safe", "is_builtin_safe",
                               "is_missing_safe", "is_extremity_safe",
                               "is_representation_safe", "is_empty_safe",
                               "is_arbitrary_input_safe",
                               "is_compendium_safe",
                               "excluded_outside_domain",
                               # function-wide implementation checks.
                               # They were registered claim families and
                               # adjudicated through the `stateless`
                               # keyword, but could not be WRITTEN as a
                               # claim law at all, `is_state_safe(f)`
                               # raised NoRelation, while its siblings
                               # parsed. A predicate asserts itself;
                               # there is no relation to spell.
                               "is_state_safe", "is_deterministic",
                               "is_reproducible", "is_defined"})

# Matrix STRUCTURE predicates: facts about a matrix VALUE (a parameter
# or an f(...) output), examined the same way safety predicates are but
# a distinct vocabulary, they examine data, not the function's code.
# Sourced from the property registry so the two never drift.
def _matrix_predicates() -> frozenset:
    from .matrices import PROPERTIES
    return frozenset(PROPERTIES)


MATRIX_PREDICATES = _matrix_predicates()

# Output-contract predicates: facts about a function's OUTPUT value
# (`is_sorted_output(f(xs))`, `output_never_none(f(x))`), the property-
# based-testing invariants that have no relation spelling. Like matrix
# predicates they examine a value and accept an `f(...)` output argument,
# unlike safety predicates which are bare-parameter only.
OUTPUT_PREDICATES = frozenset({"is_sorted_output", "output_never_none"})

# every predicate the examine route owns and the grammar recognizes:
# safety (about the code), matrix structure and output contract (about a
# value)
EXAMINE_PREDICATES = SAFETY_PREDICATES | MATRIX_PREDICATES | OUTPUT_PREDICATES
_ALL_FORMS = DERIVE_ONLY_FORMS | EXAMINE_PREDICATES | {"raises"}

def registered_predicates() -> frozenset:
    """Safety predicates contributed by registered claim families (the
    family's registered name is the predicate it owns). Empty with no
    registrations, so the static tables stand alone; every membership
    check that must see the LIVE vocabulary goes through the functions
    below rather than the tables."""
    from . import families
    return families.registered_predicates()


def safety_predicates() -> frozenset:
    """The live safety vocabulary: `SAFETY_PREDICATES` plus registered
    ones."""
    return SAFETY_PREDICATES | registered_predicates()


def examine_predicates() -> frozenset:
    """The live examine vocabulary: `EXAMINE_PREDICATES` plus
    registered ones."""
    return EXAMINE_PREDICATES | registered_predicates()


ROUTE_CAPABILITIES: dict[str, frozenset] = {
    # derive can attempt every form
    "derive": _ALL_FORMS,
    # probe cannot evaluate the symbolic-calculus forms; every safety
    # predicate and raises has a real sampling half
    "probe": _ALL_FORMS - DERIVE_ONLY_FORMS,
    # examine is the implementation-check route: safety predicates
    # are facts about the code itself, examined through whichever
    # mechanism (structural or trial) can establish them, akin to
    # tests in traditional testing. It owns exactly the safety
    # predicates; an ordinary relation has nothing to examine.
    "examine": EXAMINE_PREDICATES,
}


def route_capabilities(route: str) -> frozenset:
    """The live form vocabulary for `route`: the static table plus
    registered predicates (a family may offer any route for a
    predicate it owns)."""
    return ROUTE_CAPABILITIES[route] | registered_predicates()


# What a runtime provider can contribute; the vocabulary is defined
# beside the adaptor contract in `interfaces.runtime`. `runtime` is
# calling the function at concrete points, `frontend` is source-level
# analysis (a Facts with body structure), `globals` is visibility of
# ambient implementation state (module globals, argument mutation).
CAPABILITIES = frozenset({"runtime", "frontend", "globals"})

# the strongest verdict each route can reach per outcome direction,
# given which capabilities the target's provider supplies. This is the
# existing engine discipline stated as data rather than a new policy:
# a symbolic disproof with no executed reproduction already stays
# unknown (the corroboration gate), a probe cannot run without calls,
# and the safety families are facts about one implementation's own
# state. "support" is the ceiling for proven/holds, "refute" for
# falsified; None means the route contributes nothing at all there.
_CEILINGS: dict[tuple[str, str], dict[str, str | None]] = {
    # derive with a frontend lifts the body; without one it still
    # decides claim-only forms (a matrix identity over declared
    # shapes) at full proof strength. Its refutations need an executed
    # witness either way, so no runtime caps them at unknown.
    ("derive", "support"): {"full": "proven", "no-frontend": "proven",
                            "no-runtime": "proven"},
    ("derive", "refute"): {"full": "falsified", "no-frontend": "falsified",
                           "no-runtime": "unknown"},
    ("probe", "support"): {"full": "holds", "no-frontend": "holds",
                           "no-runtime": None},
    ("probe", "refute"): {"full": "falsified", "no-frontend": "falsified",
                          "no-runtime": None},
    # the examine families are per-implementation facts; the empirical
    # half reads ambient state, so both runtime and globals are needed
    ("examine", "support"): {"full": "holds", "no-frontend": "holds",
                             "no-runtime": None},
    ("examine", "refute"): {"full": "falsified", "no-frontend": "falsified",
                            "no-runtime": None},
}


def verdict_ceiling(capabilities: frozenset, route: str,
                    outcome: str) -> str | None:
    """Intent:
        The strongest verdict `route` can reach in the `outcome`
        direction ("support" or "refute") for a target whose provider
        supplies `capabilities` (a subset of `CAPABILITIES`), or None
        when the route cannot contribute there at all.

    Raises:
        KeyError: an unknown route or outcome.

    Notes:
        The examine route additionally requires `globals`: without it
        the empirical half cannot read the ambient state the safety
        families are about, so examine contributes nothing however
        callable the target is. Brute-force proofs ride the derive
        rows but are execution: with no runtime the finite-domain
        sweep is unavailable, which the derive support ceiling does
        not show because claim-only symbolic proofs remain reachable.
    """
    key = ("no-runtime" if "runtime" not in capabilities else
           "no-frontend" if "frontend" not in capabilities else "full")
    ceiling = _CEILINGS[(route, outcome)][key]
    if route == "examine" and "globals" not in capabilities:
        return None
    return ceiling


def required_forms(cj) -> set[str]:
    """Intent:
        The set of forms a claim actually uses, the symbolic-calculus
        call names appearing in call position in its law, plus a
        predicate/`raises` relation. An ordinary value relation
        contributes nothing (both routes handle it).

    Notes:
        A pure ast scan, tolerant of an unparseable side (contributes
        no call forms from it). Mirrors `_validate`'s call-func-id
        pattern so the two never disagree about what is a call.
    """
    forms: set[str] = set()
    if cj.relation in EXAMINE_PREDICATES or cj.relation == "raises":
        forms.add(cj.relation)
    for src in (cj.lhs, cj.rhs):
        if not src:
            continue
        try:
            tree = ast.parse(str(src), mode="eval")
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and node.func.id in DERIVE_ONLY_FORMS:
                forms.add(node.func.id)
    return forms


def unsupported_forms(route: str, cj) -> list[str]:
    """Intent:
        The forms a concrete route cannot adjudicate for this claim;
        empty when the route can attempt it. `best`/`auto` are not
        concrete routes (they cascade), so they never report anything
        here.

    Notes:
        A route not in `ROUTE_CAPABILITIES` (an unknown route) reports
        every required form as unsupported, so the caller refuses it
        loudly rather than dispatching into nothing.
    """
    if route == "best":
        return []
    capable = ROUTE_CAPABILITIES.get(route, frozenset())
    return sorted(required_forms(cj) - capable)
