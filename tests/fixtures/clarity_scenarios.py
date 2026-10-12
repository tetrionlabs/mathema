# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Clarity scenarios: realistic functions, each with the verified claim
rows a developer would have after checking it, grouped in families
whose order a developer would expect.

Each scenario is `(id, function name, rows, callee rows)`. The rows are
the records `mathema verify` writes (name, statement, verdict, route),
written out by hand so a score is computed from fixed evidence and
never depends on how fast a proof runs. The callee rows are the
records the scenario's callees hold, by function name.

`FAMILIES` names the scenarios of each family in the order a developer
expects their clarity to rise. Ids joined in a tuple are expected to
score about the same (within `SAME_MARGIN` points).
"""
from typing import Literal, Optional

from mathema import enforce_domain

# --- (i) a string function at increasing levels of stated knowledge -------

_SPELLINGS = '{"BUY", "Buy", " buy "}'


def side_bare(side: str) -> str:
    """The order side as a lower-case word."""
    return side.strip().lower()


def side_guarded(side: str) -> str:
    """The order side as a lower-case word."""
    if side not in {"BUY", "Buy", " buy "}:
        raise ValueError(side)
    return side.strip().lower()


@enforce_domain({"side": {"BUY", "Buy", " buy "}})
def side_enforced(side: str) -> str:
    """The order side as a lower-case word."""
    return side.strip().lower()


def side_literal(side: Literal["BUY", "Buy", " buy "]) -> str:
    """The order side as a lower-case word."""
    return side.strip().lower()


# --- (ii, iii) a numeric function and the reach of its claims -------------

def fahrenheit(c: float) -> float:
    """A Celsius temperature in Fahrenheit."""
    return c * 9.0 / 5.0 + 32.0


# --- (iv) a pure total helper -----------------------------------------------

def lerp(a: float, b: float, t: float) -> float:
    """The point a fraction t of the way from a to b."""
    return a + (b - a) * t


# --- (v) a branchy impure function -----------------------------------------

_FEES_CHARGED = 0


def fee(amount: float, tier: str) -> float:
    """The fee on an amount at a customer tier, counted."""
    global _FEES_CHARGED
    if tier == "gold":
        rate = 0.01
    elif tier == "silver":
        rate = 0.02
    else:
        rate = 0.03
    if amount > 10000:
        rate = rate / 2
    _FEES_CHARGED += 1
    return amount * rate


# --- (vi) a caller and its callee ------------------------------------------

def half(x: float) -> float:
    """Half of x."""
    return x / 2.0


def quarter(x: float) -> float:
    """A quarter of x, by halving twice."""
    return half(half(x))


# --- (vii) Optional parameters ---------------------------------------------

def greeting(name: Optional[str]) -> str:
    """A greeting, by name when there is one."""
    if name is None:
        return "Hello"
    return "Hello, " + name


# --- (viii) enforce_domain against the equivalent guard --------------------

def term_months(term: str) -> int:
    """The number of months in a deposit term."""
    return int(term[:-1])


@enforce_domain({"term": {"1m", "3m", "6m", "12m"}})
def term_months_enforced(term: str) -> int:
    """The number of months in a deposit term."""
    return int(term[:-1])


def term_months_guarded(term: str) -> int:
    """The number of months in a deposit term."""
    if term not in {"1m", "3m", "6m", "12m"}:
        raise ValueError(term)
    return int(term[:-1])


# --- the rows ---------------------------------------------------------------

def _row(name, statement, verdict="proven", route="derive", **meta):
    row = {"name": name, "statement": statement, "verdict": verdict,
           "route": route}
    if meta:
        row["meta"] = meta
    return row


_SIDE_PROOF = _row("buy_key", 'f(side) == "buy"', route="derive:brute_force")
_SIDE_POINTS = _row("buy_key", f'for side in {_SPELLINGS}, f(side) == "buy"',
                    route="derive:brute_force")

_F_LAW = "f(c) == 1.8*c + 32"
_F_POINTS = _row("conversion", f"for c in {{-40.0, 0.0, 100.0}}, {_F_LAW}",
                 route="derive:brute_force")
_F_RANGE = _row("conversion", f"for c in [0, 100], {_F_LAW}")
_F_WHOLE = _row("conversion", _F_LAW)
_F_BOUND = _row("above_absolute_zero",
                "for c in [-273.15, inf), f(c) >= -459.67")
_F_SHAPE = _row("increasing[c]", "d(f(c), c) > 0")


def _safe(*families, verdict="proven", route="examine"):
    return [_row(family, f"{family}(f)", verdict=verdict, route=route)
            for family in families]


_PURE_SAFE = _safe("is_state_safe", "is_deterministic")
_NUMERIC_SAFE = (_safe("is_numerically_stable", "is_representation_safe",
                       verdict="holds", route="probe:algorithmic"))

_LERP_FULL = [_row("interpolates", "f(a, b, t) == a + t*(b - a)"),
              *_PURE_SAFE, *_NUMERIC_SAFE]

_QUARTER_FULL = [_row("quarters", "f(x) == x/4"), *_PURE_SAFE]

_ABSENT = {"kind": "absent", "parameter": "name"}

_TERM_PROOF = _row("months", "f(term) >= 1", route="derive:brute_force")

SCENARIOS = [
    # (i) strings
    ("S1 bare str", "side_bare", [], {}),
    ("S1e enforce_domain, no claims", "side_enforced", [], {}),
    ("S2 bare str, claim at 3 names", "side_bare", [_SIDE_POINTS], {}),
    ("S3 guard to the set, proof", "side_guarded", [_SIDE_PROOF], {}),
    ("S4 enforce_domain, proof", "side_enforced", [_SIDE_PROOF], {}),
    ("S5 Literal, proof", "side_literal", [_SIDE_PROOF], {}),
    # (ii) numeric verdicts
    ("N1 no claims", "fahrenheit", [], {}),
    ("N2 holds, random probe", "fahrenheit",
     [dict(_F_WHOLE, verdict="holds", route="probe")], {}),
    ("N3 holds, semi-analytical", "fahrenheit",
     [dict(_F_WHOLE, verdict="holds", route="probe:semi_analytical")], {}),
    ("N4 proven", "fahrenheit", [_F_WHOLE], {}),
    ("N5 proven + bound + shape", "fahrenheit",
     [_F_WHOLE, _F_BOUND, _F_SHAPE], {}),
    ("N6 random holds + bound + shape", "fahrenheit",
     [dict(_F_WHOLE, verdict="holds", route="probe"), _F_BOUND, _F_SHAPE],
     {}),
    # (iii) reach
    ("C1 proven at 3 points", "fahrenheit", [_F_POINTS], {}),
    ("C2 proven over [0, 100]", "fahrenheit", [_F_RANGE], {}),
    ("C3 proven everywhere", "fahrenheit", [_F_WHOLE], {}),
    # (iv) a pure total helper
    ("H1 lerp, no claims", "lerp", [], {}),
    ("H2 lerp, fully claimed", "lerp", _LERP_FULL, {}),
    # (v) branchy and impure
    ("B1 fee, no claims", "fee", [], {}),
    ("B2 fee, bound holds, impurity found", "fee",
     [_row("non_negative", "for amount in [0, inf), f(amount, tier) >= 0",
           verdict="holds", route="probe"),
      _row("is_state_safe", "is_state_safe(f)", verdict="falsified",
           route="probe")], {}),
    # (vi) callees
    ("V1 callee unverified", "quarter", _QUARTER_FULL, {}),
    ("V2 callee defined, proven", "quarter", _QUARTER_FULL,
     {"half": [_row("is_defined", "is_defined(f)")]}),
    ("V3 callee identity, proven", "quarter", _QUARTER_FULL,
     {"half": [_row("halves", "f(x) == x/2")]}),
    # (vii) Optional
    ("O1 Optional, no claims", "greeting", [], {}),
    ("O2 Optional, absent row holds", "greeting",
     [_row("absent[name]", "absent(f, name) == 'Hello'", verdict="holds",
           route="probe:counterfactual", **{"mathema.policy": _ABSENT})], {}),
    ("O3 Optional, absent row proven", "greeting",
     [_row("absent[name]", "absent(f, name) == 'Hello'",
           **{"mathema.policy": _ABSENT})], {}),
    # (viii) the same domain, stated two ways
    ("E0 bare str, no claims", "term_months", [], {}),
    ("E1 enforce_domain, no claims", "term_months_enforced", [], {}),
    ("E2 guard, no claims", "term_months_guarded", [], {}),
    ("E3 enforce_domain, proof", "term_months_enforced", [_TERM_PROOF], {}),
    ("E4 guard, proof", "term_months_guarded", [_TERM_PROOF], {}),
]

# each family's scenarios in the order a developer expects clarity to
# rise, "<" a clear rise and "<=" no fall; a tuple is a group expected to
# score about the same. Three points of an infinite type are a vanishing
# share of it, so a claim at three names may add little.
FAMILIES = {
    "strings": ["S1 bare str", "<=", "S2 bare str, claim at 3 names", "<",
                ("S3 guard to the set, proof", "S4 enforce_domain, proof",
                 "S5 Literal, proof")],
    "verdicts": ["N1 no claims", "<", "N2 holds, random probe", "<",
                 "N3 holds, semi-analytical", "<", "N4 proven"],
    "entailed": [("N4 proven", "N5 proven + bound + shape")],
    "claims added": ["N2 holds, random probe", "<",
                     "N6 random holds + bound + shape"],
    "reach": ["C1 proven at 3 points", "<", "C2 proven over [0, 100]", "<",
              "C3 proven everywhere"],
    "helper": ["H1 lerp, no claims", "<", "H2 lerp, fully claimed"],
    "floors": ["B1 fee, no claims", "<", "H1 lerp, no claims"],
    "impure": ["B1 fee, no claims", "<", "B2 fee, bound holds, impurity found"],
    "callees": ["V1 callee unverified", "<",
                ("V2 callee defined, proven", "V3 callee identity, proven")],
    "optional": ["O1 Optional, no claims", "<", "O2 Optional, absent row holds",
                 "<", "O3 Optional, absent row proven"],
    "stated two ways, unclaimed": [("E1 enforce_domain, no claims",
                                    "E2 guard, no claims")],
    "stated two ways, proven": [("E3 enforce_domain, proof",
                                 "E4 guard, proof")],
}

SAME_MARGIN = 5

# the same function and rows, without and then with its domain stated on
# the function itself
STATED_PAIRS = [("S1 bare str", "S1e enforce_domain, no claims"),
                ("E0 bare str, no claims", "E1 enforce_domain, no claims"),
                ("S2 bare str, claim at 3 names", "S4 enforce_domain, proof")]


def clarity_of(scenario_id: str) -> int:
    """The clarity score of one scenario, from its rows alone: the
    callees' records come from the scenario, and no library claims file
    or verified store on disk is read."""
    import sys

    from mathema.badges import clarity_score
    _id, fn_name, rows, callee_rows = next(
        s for s in SCENARIOS if s[0] == scenario_id)
    module = sys.modules[__name__]
    fn = getattr(module, fn_name)
    store = {f"{module.__name__}.{callee}": {"entry": {"claims": claims}}
             for callee, claims in callee_rows.items()}
    return clarity_score(fn, verified_claims=rows, store=store,
                         library_keys=frozenset())


def order_holds(family: list, scores: dict) -> bool:
    """Whether `scores` (by scenario id) follow one family's expected
    order: each group within `SAME_MARGIN` points, each `<` a rise of at
    least one point from every member of the group before it to every
    member of the group after, each `<=` no fall."""
    groups = [g if isinstance(g, tuple) else (g,) for g in family
              if g not in ("<", "<=")]
    relations = [g for g in family if g in ("<", "<=")]
    for group in groups:
        values = [scores[i] for i in group]
        if max(values) - min(values) > SAME_MARGIN:
            return False
    for relation, low, high in zip(relations, groups, groups[1:]):
        top = max(scores[i] for i in low)
        bottom = min(scores[i] for i in high)
        if (relation == "<" and bottom <= top) or bottom < top:
            return False
    return True
